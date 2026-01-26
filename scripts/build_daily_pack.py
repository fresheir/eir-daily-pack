import json
import re
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

GOOGLE_NEWS_AU_RSS = "https://news.google.com/rss?hl=en-AU&gl=AU&ceid=AU:en"

# How many items to try to show per topic
TARGET_PER_TOPIC = 5

# Require at least this score to "confidently" assign an item to a topic
# (prevents generic AU headlines being dumped into World/Business)
MIN_ASSIGN_SCORE = 2

TOPICS = [
    {
        "id": "local_national",
        "label": "Local & National News",
        "keywords": [
            # AU/States/Institutions
            "australia", "australian", "nsw", "new south wales", "victoria", "vic",
            "queensland", "qld", "tasmania", "tas", "south australia", "sa",
            "western australia", "wa", "canberra", "act", "parliament",
            "federal", "government", "sydney", "melbourne", "brisbane", "perth", "adelaide",
        ],
    },
    {
        "id": "world",
        "label": "World News",
        "keywords": [
            # Countries/regions + common world terms
            "ukraine", "russia", "israel", "gaza", "palestine", "china", "beijing",
            "taiwan", "japan", "north korea", "south korea", "iran",
            "united states", "u.s.", "us ", "usa", "washington", "white house",
            "europe", "eu ", "united nations", "nato", "global", "international",
            "world", "overseas",
        ],
    },
    {
        "id": "business",
        "label": "Business & Economy",
        "keywords": [
            "asx", "stocks", "shares", "market", "economy", "inflation", "rates",
            "rba", "reserve bank", "jobs", "unemployment", "gdp", "trade",
            "business", "earnings", "profit", "revenue", "merger", "acquisition",
            "bank", "housing", "property", "mortgage", "rent", "construction",
            "oil", "gold", "iron ore", "gas", "commodities", "currency", "aud",
        ],
    },
    {
        "id": "sport",
        "label": "Sport",
        "keywords": [
            "afl", "nrl", "cricket", "tennis", "soccer", "football",
            "a-league", "epl", "premier league", "champions league",
            "nba", "nfl", "mlb", "nhl", "ufc", "formula 1", "f1",
            "grand slam", "olympics", "sport",
        ],
    },
    {
        "id": "science_tech",
        "label": "Science & Technology",
        "keywords": [
            "technology", "tech", "ai", "artificial intelligence", "cyber", "security",
            "hack", "breach", "data", "privacy", "space", "nasa", "science",
            "research", "innovation", "startup", "chip", "semiconductor",
            "quantum", "robot", "biotech",
        ],
    },
]

# Optional: reduce paywall frustration — block by PUBLISHER NAME (not host)
PAYWALL_PUBLISHER_BLOCKLIST = {
    "australian financial review",
    "the australian",
    "financial times",
    "the wall street journal",
    "the economist",
    "bloomberg",
    "the new york times",
    "the times",
    "the telegraph",
}

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def fetch_rss(url: str) -> bytes:
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
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        source_el = it.find("source")
        publisher = ((source_el.text if source_el is not None else "") or "").strip()

        if not title or not link.startswith("http"):
            continue

        # Paywall block by publisher name (more reliable for Google News RSS)
        pub_norm = norm(publisher)
        if pub_norm in PAYWALL_PUBLISHER_BLOCKLIST:
            continue

        items.append({
            "title": title,
            "publisher": publisher or "Unknown",
            "url": link,
            "published": pub,
        })
    return items

def score_item_to_topic(title: str, topic_keywords):
    t = norm(title)

    score = 0
    for kw in topic_keywords:
        kw_n = norm(kw)
        if kw_n and kw_n in t:
            score += 1

    # Small boost rules to reduce obvious mis-bucketing
    # e.g. if it explicitly says "Australia Day", it's not World.
    if "australia" in t or "australian" in t:
        # local/national should dominate AU mentions
        score += 1

    return score

def allocate(items):
    # De-dupe early by URL (Google News sometimes repeats)
    seen_urls = set()
    unique = []
    for it in items:
        if it["url"] in seen_urls:
            continue
        seen_urls.add(it["url"])
        unique.append(it)

    buckets = {t["id"]: [] for t in TOPICS}
    unassigned = []

    # First pass: only assign if confidence is good (>= MIN_ASSIGN_SCORE)
    for item in unique:
        best_id = None
        best_score = 0

        for t in TOPICS:
            s = score_item_to_topic(item["title"], t["keywords"])
            if s > best_score:
                best_score = s
                best_id = t["id"]

        if best_id and best_score >= MIN_ASSIGN_SCORE:
            buckets[best_id].append((best_score, item))
        else:
            unassigned.append(item)

    # Sort each bucket by score desc, keep only items
    for tid in buckets:
        buckets[tid].sort(key=lambda x: x[0], reverse=True)
        buckets[tid] = [it for _, it in buckets[tid]]

    # Second pass: top-up each topic ONLY with items that match that topic at least 1 keyword,
    # and never steal from other topics. Still no "random leftovers".
    used_urls = set()
    for t in TOPICS:
        tid = t["id"]
        for it in buckets[tid]:
            used_urls.add(it["url"])

    def best_unassigned_for_topic(topic):
        candidates = []
        for it in unassigned:
            if it["url"] in used_urls:
                continue
            s = score_item_to_topic(it["title"], topic["keywords"])
            if s >= 1:  # weak match acceptable ONLY for top-up
                candidates.append((s, it))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in candidates]

    for t in TOPICS:
        tid = t["id"]
        if len(buckets[tid]) >= TARGET_PER_TOPIC:
            buckets[tid] = buckets[tid][:TARGET_PER_TOPIC]
            continue

        need = TARGET_PER_TOPIC - len(buckets[tid])
        topups = best_unassigned_for_topic(t)[:need]
        for it in topups:
            buckets[tid].append(it)
            used_urls.add(it["url"])

    # Final truncate
    for t in TOPICS:
        tid = t["id"]
        buckets[tid] = buckets[tid][:TARGET_PER_TOPIC]

    return buckets

def main():
    now = datetime.now(timezone.utc)

    xml_bytes = fetch_rss(GOOGLE_NEWS_AU_RSS)
    items = parse_rss(xml_bytes)
    buckets = allocate(items)

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
