import json
import re
import sys
import os
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import xml.etree.ElementTree as ET

# -----------------------------
# GLOBAL SETTINGS
# -----------------------------

# Best-effort list: ISO 3166-1 alpha-2 (commonly used country codes)
# This is intentionally broad. Some markets won't have Google News RSS editions.
ISO_ALPHA2 = [
    "AD","AE","AF","AG","AI","AL","AM","AO","AR","AS","AT","AU","AW","AX","AZ",
    "BA","BB","BD","BE","BF","BG","BH","BI","BJ","BL","BM","BN","BO","BQ","BR","BS","BT","BV","BW","BY","BZ",
    "CA","CC","CD","CF","CG","CH","CI","CK","CL","CM","CN","CO","CR","CU","CV","CW","CX","CY","CZ",
    "DE","DJ","DK","DM","DO","DZ",
    "EC","EE","EG","EH","ER","ES","ET",
    "FI","FJ","FK","FM","FO","FR",
    "GA","GB","GD","GE","GF","GG","GH","GI","GL","GM","GN","GP","GQ","GR","GS","GT","GU","GW","GY",
    "HK","HM","HN","HR","HT","HU",
    "ID","IE","IL","IM","IN","IO","IQ","IR","IS","IT",
    "JE","JM","JO","JP",
    "KE","KG","KH","KI","KM","KN","KP","KR","KW","KY","KZ",
    "LA","LB","LC","LI","LK","LR","LS","LT","LU","LV","LY",
    "MA","MC","MD","ME","MF","MG","MH","MK","ML","MM","MN","MO","MP","MQ","MR","MS","MT","MU","MV","MW","MX","MY","MZ",
    "NA","NC","NE","NF","NG","NI","NL","NO","NP","NR","NU","NZ",
    "OM",
    "PA","PE","PF","PG","PH","PK","PL","PM","PN","PR","PS","PT","PW","PY",
    "QA",
    "RE","RO","RS","RU","RW",
    "SA","SB","SC","SD","SE","SG","SH","SI","SJ","SK","SL","SM","SN","SO","SR","SS","ST","SV","SX","SY","SZ",
    "TC","TD","TF","TG","TH","TJ","TK","TL","TM","TN","TO","TR","TT","TV","TW","TZ",
    "UA","UG","UM","US","UY","UZ",
    "VA","VC","VE","VG","VI","VN","VU",
    "WF","WS",
    "YE","YT",
    "ZA","ZM","ZW"
]

# Topics (same as you have, but improved allocation behavior below)
TOPICS = [
    {
        "id": "local_national",
        "label": "Local & National News",
        "keywords": [
            "australia","australian","nsw","new south wales","victoria","vic","queensland","qld",
            "tasmania","tas","south australia","sa","western australia","wa","canberra","parliament",
            "federal","government","election","budget","police","court","bushfire","flood"
        ],
    },
    {
        "id": "world",
        "label": "World News",
        "keywords": [
            "ukraine","russia","israel","gaza","china","united states","u.s.","america","europe",
            "united nations","iran","global","international","world","nato","war","sanctions"
        ],
    },
    {
        "id": "business",
        "label": "Business & Economy",
        "keywords": [
            "asx","stocks","shares","market","economy","inflation","rates","rba","reserve bank","jobs",
            "unemployment","gdp","trade","business","bank","housing","property","mortgage","oil","gold",
            "commodities","earnings","profits","revenue","ipo"
        ],
    },
    {
        "id": "sport",
        "label": "Sport",
        "keywords": [
            "afl","nrl","cricket","tennis","soccer","football","a-league","nba","nfl","formula 1","f1",
            "grand slam","olympics","sport","match","final","win","loss","coach"
        ],
    },
    {
        "id": "science_tech",
        "label": "Science & Technology",
        "keywords": [
            "technology","tech","ai","artificial intelligence","cyber","security","space","nasa","science",
            "research","innovation","startup","chip","quantum","robot","software","data","privacy"
        ],
    },
]

# Optional blocklist (only applied if you want it)
PAYWALL_BLOCKLIST = {
    "afr.com",
    "theaustralian.com.au",
    "ft.com",
    "wsj.com",
    "economist.com",
    "bloomberg.com",
    "nytimes.com",
    "thetimes.co.uk",
    "telegraph.co.uk",
}

UA = "Mozilla/5.0 (EirDailyPackBot)"
REQUEST_SLEEP_SECONDS = 0.25
REQUEST_TIMEOUT_SECONDS = 20

# -----------------------------
# HELPERS
# -----------------------------

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def host_from_url(url: str) -> str:
    m = re.match(r"^https?://([^/]+)/", url or "")
    return m.group(1).lower() if m else ""

def google_news_rss(gl_country: str) -> str:
    """
    Best-effort RSS URL.
    Many countries work with ceid=CC:en and hl=en-CC.
    If a market doesn't exist, request may fail and we skip it.
    """
    cc = gl_country.upper()
    return f"https://news.google.com/rss?hl=en-{cc}&gl={cc}&ceid={cc}:en"

def fetch_rss(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return resp.read()

def parse_rss(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        return []

    items = []
    for it in channel.findall("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        source_el = it.find("source")
        publisher = ((source_el.text if source_el is not None else "") or "").strip()

        if not link.startswith("http"):
            continue

        h = host_from_url(link)
        if h in PAYWALL_BLOCKLIST:
            continue

        items.append({
            "title": title,
            "publisher": publisher or h,
            "url": link,
            "published": pub,
            # add convenience fields for better allocation
            "host": h,
        })
    return items

def score_item_to_topic(title: str, topic_keywords):
    t = norm(title)
    score = 0
    for kw in topic_keywords:
        if kw in t:
            score += 1
    return score

def allocate(items, per_topic=5):
    """
    Improved allocation:
    1) assign by keyword score
    2) DO NOT "backfill with random leftovers" across topics (this is why your World gets local)
       Instead: if a bucket is short, leave it short.
    3) provide a confidence label per topic based on average match score.
    """
    buckets = {t["id"]: {"items": [], "scores": []} for t in TOPICS}

    for item in items:
        best_id = None
        best_score = 0
        for t in TOPICS:
            s = score_item_to_topic(item["title"], t["keywords"])
            if s > best_score:
                best_score = s
                best_id = t["id"]

        if best_score > 0 and best_id:
            buckets[best_id]["items"].append(item)
            buckets[best_id]["scores"].append(best_score)

    # Truncate each to per_topic (keeps best-matching first by score)
    out = {}
    confidence = {}

    for t in TOPICS:
        tid = t["id"]
        # sort by score desc, then by recency string (best-effort)
        paired = list(zip(buckets[tid]["scores"], buckets[tid]["items"]))
        paired.sort(key=lambda x: x[0], reverse=True)
        final_items = [it for _, it in paired][:per_topic]

        avg = (sum([s for s, _ in paired[:per_topic]]) / len(paired[:per_topic])) if paired[:per_topic] else 0.0
        if avg >= 2.0:
            conf = "high"
        elif avg >= 1.0:
            conf = "moderate"
        else:
            conf = "low"

        out[tid] = final_items
        confidence[tid] = conf

    return out, confidence

def write_json(path: str, payload: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

# -----------------------------
# MAIN
# -----------------------------

def main():
    now = datetime.now(timezone.utc)
    valid_for_date = now.date().isoformat()

    successes = []
    failures = []

    for cc in ISO_ALPHA2:
        url = google_news_rss(cc)
        try:
            time.sleep(REQUEST_SLEEP_SECONDS)
            xml_bytes = fetch_rss(url)
            items = parse_rss(xml_bytes)

            # If a country returns almost nothing, skip (prevents empty/noise packs)
            if len(items) < 8:
                failures.append({"cc": cc.lower(), "reason": f"too_few_items({len(items)})"})
                continue

            buckets, conf = allocate(items, per_topic=5)

            out = {
                "market": cc.upper(),
                "edition": f"en-{cc.upper()}",
                "generatedAt": now.isoformat().replace("+00:00", "Z"),
                "validForDate": valid_for_date,
                "source": "Google News RSS",
                "rss": url,
                "topics": []
            }

            for t in TOPICS:
                tid = t["id"]
                out["topics"].append({
                    "id": tid,
                    "label": t["label"],
                    "confidence": conf.get(tid, "low"),
                    "items": [
                        {
                            "title": it["title"],
                            "publisher": it["publisher"],
                            "url": it["url"],
                            "published": it["published"]
                        } for it in buckets.get(tid, [])
                    ]
                })

            out_path = f"public/{cc.lower()}/daily.json"
            write_json(out_path, out)

            successes.append(cc.lower())

        except (HTTPError, URLError, TimeoutError, ET.ParseError) as e:
            failures.append({"cc": cc.lower(), "reason": str(e).splitlines()[0][:200]})
            continue
        except Exception as e:
            failures.append({"cc": cc.lower(), "reason": f"unknown:{str(e)[:200]}"})
            continue

    # Manifest used by the app to know which countries exist today
    manifest = {
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "validForDate": valid_for_date,
        "countries": sorted(successes),
        "failuresCount": len(failures),
    }
    write_json("public/manifest.json", manifest)
    write_json("public/failures.json", {"failures": failures})

    print(f"Generated {len(successes)} country packs. Failures: {len(failures)}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
