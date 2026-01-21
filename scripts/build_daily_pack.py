import json
import re
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

GOOGLE_NEWS_AU_RSS = "https://news.google.com/rss?hl=en-AU&gl=AU&ceid=AU:en"

TOPICS = [
    {
        "id": "local_national",
        "label": "Local & National News",
        "keywords": [
            "australia", "australian", "nsw", "new south wales", "victoria", "vic",
            "queensland", "qld", "tasmania", "tas", "south australia", "sa",
            "western australia", "wa", "canberra", "parliament", "federal", "government"
        ],
    },
    {
        "id": "world",
        "label": "World News",
        "keywords": [
            "ukraine", "russia", "israel", "gaza", "china", "us", "u.s.", "america",
            "europe", "united nations", "iran", "global", "international", "world"
        ],
    },
    {
        "id": "business",
        "label": "Business & Economy",
        "keywords": [
            "asx", "stocks", "shares", "market", "economy", "inflation", "rates",
            "rba", "reserve bank", "jobs", "unemployment", "gdp", "trade", "business",
            "bank", "housing", "property", "mortgage", "oil", "gold"
        ],
    },
    {
        "id": "sport",
        "label": "Sport",
        "keywords": [
            "afl", "nrl", "cricket", "tennis", "soccer", "football", "a-league",
            "nba", "nfl", "formula 1", "f1", "grand slam", "olympics", "sport"
        ],
    },
    {
        "id": "science_tech",
        "label": "Science & Technology",
        "keywords": [
            "technology", "tech", "ai", "artificial intelligence", "cyber", "security",
            "space", "nasa", "science", "research", "innovation", "startup", "chip", "quantum"
        ],
    },
]

# Optional: reduce paywall frustration (domains to exclude from FREE pack)
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

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def host_from_url(url: str) -> str:
    m = re.match(r"^https?://([^/]+)/", url or "")
    return m.group(1).lower() if m else ""

def fetch_rss(url: str) -> bytes:
    # Set a basic UA; some endpoints behave better with it.
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (EirDailyPackBot)"})
    with urlopen(req, timeout=20) as resp:
        return resp.read()

def parse_rss(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        return []

    items = []
    for it in channel.findall("item"):
        title = it.findtext("title") or ""
        link = it.findtext("link") or ""
        pub = it.findtext("pubDate") or ""
        source_el = it.find("source")
        publisher = (source_el.text if source_el is not None else "") or ""

        # Basic validity
        if not link.startswith("http"):
            continue
        h = host_from_url(link)
        if h in PAYWALL_BLOCKLIST:
            continue

        items.append({
            "title": title.strip(),
            "publisher": publisher.strip() or h,
            "url": link.strip(),
            "published": pub.strip(),
        })
    return items

def score_item_to_topic(title: str, topic_keywords):
    t = norm(title)
    score = 0
    for kw in topic_keywords:
        if kw in t:
            score += 1
    return score

def allocate(items):
    # Allocate each item to the best-scoring topic (if any score>0).
    buckets = {t["id"]: [] for t in TOPICS}
    leftovers = []

    for item in items:
        best_id = None
        best_score = 0
        for t in TOPICS:
            s = score_item_to_topic(item["title"], t["keywords"])
            if s > best_score:
                best_score = s
                best_id = t["id"]
        if best_score > 0 and best_id:
            buckets[best_id].append(item)
        else:
            leftovers.append(item)

    # Fill short buckets with leftovers so each topic can reach 5
    for t in TOPICS:
        tid = t["id"]
        if len(buckets[tid]) < 5:
            need = 5 - len(buckets[tid])
            buckets[tid].extend(leftovers[:need])
            leftovers = leftovers[need:]

    # Truncate to 5 each
    for t in TOPICS:
        buckets[t["id"]] = buckets[t["id"]][:5]

    return buckets

def main():
    now = datetime.now(timezone.utc)
    xml_bytes = fetch_rss(GOOGLE_NEWS_AU_RSS)
    items = parse_rss(xml_bytes)
    buckets = allocate(items)

    # Use AU date based on Sydney time (approx by +10/+11 is messy in pure stdlib).
    # We'll store UTC date; app can display local. If you want strict AU date, we can add zoneinfo later.
    valid_for_date = now.date().isoformat()

    out = {
        "market": "AU",
        "edition": "en-AU",
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "validForDate": valid_for_date,
        "source": "Google News RSS (AU)",
        "topics": []
    }

    for t in TOPICS:
        out["topics"].append({
            "id": t["id"],
            "label": t["label"],
            "items": buckets[t["id"]],
        })

    # Write output
    out_path = "public/au/daily.json"
    import os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_path} with {sum(len(t['items']) for t in out['topics'])} items")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
