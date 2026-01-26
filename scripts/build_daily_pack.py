import json
import sys
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import time

# ---------------------------------------------------------
# GOAL
# ---------------------------------------------------------
# Create a daily.json for ALL countries:
#   public/<cc>/daily.json
#
# Local & National News is LOCALIZED per country using Google News "NATION".
# Other topics (World/Business/Sport/Tech) are pulled ONCE (global) and reused.
#
# This keeps requests manageable while still giving true local news by user country.
# ---------------------------------------------------------

ITEMS_PER_TOPIC = 5

TOPICS = [
    {"id": "local_national", "label": "Local & National News", "google_topic": "NATION"},
    {"id": "world",         "label": "World News",            "google_topic": "WORLD"},
    {"id": "business",      "label": "Business & Economy",    "google_topic": "BUSINESS"},
    {"id": "sport",         "label": "Sport",                 "google_topic": "SPORTS"},
    {"id": "science_tech",  "label": "Science & Technology",  "google_topic": "TECHNOLOGY"},
]

# Optional: exclude paywalled domains
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

# ISO 3166-1 alpha-2 country codes (common set; includes most globally used codes)
# You can add/remove as needed, but this already covers "global".
COUNTRY_CODES = [
    "ad","ae","af","ag","ai","al","am","ao","ar","as","at","au","aw","ax","az",
    "ba","bb","bd","be","bf","bg","bh","bi","bj","bl","bm","bn","bo","bq","br",
    "bs","bt","bv","bw","by","bz","ca","cc","cd","cf","cg","ch","ci","ck","cl",
    "cm","cn","co","cr","cu","cv","cw","cx","cy","cz","de","dj","dk","dm","do",
    "dz","ec","ee","eg","eh","er","es","et","fi","fj","fk","fm","fo","fr","ga",
    "gb","gd","ge","gf","gg","gh","gi","gl","gm","gn","gp","gq","gr","gs","gt",
    "gu","gw","gy","hk","hm","hn","hr","ht","hu","id","ie","il","im","in","io",
    "iq","ir","is","it","je","jm","jo","jp","ke","kg","kh","ki","km","kn","kp",
    "kr","kw","ky","kz","la","lb","lc","li","lk","lr","ls","lt","lu","lv","ly",
    "ma","mc","md","me","mf","mg","mh","mk","ml","mm","mn","mo","mp","mq","mr",
    "ms","mt","mu","mv","mw","mx","my","mz","na","nc","ne","nf","ng","ni","nl",
    "no","np","nr","nu","nz","om","pa","pe","pf","pg","ph","pk","pl","pm","pn",
    "pr","ps","pt","pw","py","qa","re","ro","rs","ru","rw","sa","sb","sc","sd",
    "se","sg","sh","si","sj","sk","sl","sm","sn","so","sr","ss","st","sv","sx",
    "sy","sz","tc","td","tf","tg","th","tj","tk","tl","tm","tn","to","tr","tt",
    "tv","tw","tz","ua","ug","um","us","uy","uz","va","vc","ve","vg","vi","vn",
    "vu","wf","ws","ye","yt","za","zm","zw"
]

def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (EirDailyPackBot)"})
    with urlopen(req, timeout=25) as resp:
        return resp.read()

def host_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def parse_rss(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        return []

    items = []
    for it in channel.findall("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub  = (it.findtext("pubDate") or "").strip()
        source_el = it.find("source")
        publisher = ((source_el.text if source_el is not None else "") or "").strip()

        if not link.startswith("http"):
            continue

        h = host_from_url(link)
        if h in PAYWALL_BLOCKLIST:
            continue

        items.append({
            "title": title,
            "publisher": publisher or h or "Unknown",
            "url": link,
            "published": pub,
        })
    return items

def dedupe(items):
    seen = set()
    out = []
    for it in items:
        key = (it.get("title","").lower().strip(), it.get("url","").lower().strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def google_topic_rss(hl: str, gl: str, ceid: str, google_topic: str) -> str:
    return f"https://news.google.com/rss/headlines/section/topic/{google_topic}?hl={hl}&gl={gl}&ceid={ceid}"

def build_topic_items(hl: str, gl: str, ceid: str, google_topic: str):
    url = google_topic_rss(hl, gl, ceid, google_topic)
    xml_bytes = fetch_bytes(url)
    items = dedupe(parse_rss(xml_bytes))
    return items[:ITEMS_PER_TOPIC]

def main():
    now = datetime.now(timezone.utc)
    generated_at = now.isoformat().replace("+00:00", "Z")
    valid_for_date = now.date().isoformat()

    # 1) Build GLOBAL topics once (reused for every country)
    # Use US English as the global baseline (stable, high volume).
    global_hl = "en-US"
    global_gl = "US"
    global_ceid = "US:en"

    global_topics_cache = {}
    for t in TOPICS:
        if t["id"] == "local_national":
            continue
        # small pause to reduce risk of rate limiting
        time.sleep(0.2)
        global_topics_cache[t["id"]] = build_topic_items(
            global_hl, global_gl, global_ceid, t["google_topic"]
        )

    # 2) For EVERY country, build a local NATION feed and combine with global topics
    built = 0
    for cc in COUNTRY_CODES:
        gl = cc.upper()

        # Use English interface wherever possible. This is intentional so your app UI stays consistent.
        # If a country doesn't have strong English coverage, NATION may return fewer items (still acceptable).
        hl = "en-" + gl if len(gl) == 2 else "en"
        ceid = f"{gl}:en"

        try:
            time.sleep(0.15)
            local_items = build_topic_items(hl, gl, ceid, "NATION")
        except Exception:
            # If a country feed fails, fall back to global NATION
            local_items = build_topic_items(global_hl, global_gl, global_ceid, "NATION")

        out = {
            "market": gl,
            "edition": hl,
            "generatedAt": generated_at,
            "validForDate": valid_for_date,
            "source": f"Google News RSS ({gl})",
            "topics": [],
        }

        for t in TOPICS:
            if t["id"] == "local_national":
                items = local_items
            else:
                items = global_topics_cache.get(t["id"], [])

            out["topics"].append({
                "id": t["id"],
                "label": t["label"],
                "items": items,
            })

        out_path = f"public/{cc}/daily.json"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        built += 1

    print(f"Done. Wrote {built} country packs to public/<cc>/daily.json")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
