import json
import re
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

# -----------------------------------------------------------------------------
# Ave / EIR Daily Pack
# Goal: HIGH data quality topic categorisation for daily.json
#
# FIXES:
# - Stop using one generic AU RSS feed (mixed content by design)
# - Use per-topic Google News RSS "search" feeds (far more accurate)
# - No "leftovers backfill" (this caused sport/cars inside business etc)
# - Optional per-topic domain + keyword exclusions
#
# Output schema remains unchanged:
# {
#   market, edition, generatedAt, validForDate, source,
#   topics: [{ id, label, items: [{title,publisher,url,published}]}]
# }
# -----------------------------------------------------------------------------

# Google News RSS search endpoint
GOOGLE_NEWS_SEARCH_RSS = "https://news.google.com/rss/search?q={query}&hl=en-AU&gl=AU&ceid=AU:en"

TOPICS = [
    {"id": "local_national", "label": "Local & National News"},
    {"id": "world", "label": "World News"},
    {"id": "business", "label": "Business & Economy"},
    {"id": "sport", "label": "Sport"},
    {"id": "science_tech", "label": "Science & Technology"},
]

# Tight topic queries (tweak these over time if needed)
TOPIC_QUERIES = {
    "local_national": 'Australia OR Australian OR NSW OR "New South Wales" OR Victoria OR Queensland OR Canberra OR Parliament OR "Federal government"',
    "world": 'Ukraine OR Russia OR Gaza OR Israel OR China OR "United Nations" OR Iran OR "international" OR "world"',
    "business": 'ASX OR RBA OR inflation OR rates OR "Reserve Bank" OR GDP OR unemployment OR markets OR economy OR housing OR property OR mortgage',
    "sport": 'AFL OR NRL OR cricket OR tennis OR soccer OR football OR "A-League" OR NBA OR NFL OR F1 OR "Formula 1" OR Olympics',
    "science_tech": 'technology OR tech OR AI OR "artificial intelligence" OR cyber OR security OR NASA OR space OR science OR research OR quantum OR startup',
}

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

# Optional: stop obvious topic pollution (edit as you like)
EXCLUDE_DOMAINS_PER_TOPIC = {
    # Business often gets polluted by car sites
    "business": {"drive.com.au", "streetmachine.com.au"},
    # If you dislike press-release sources, exclude them
    "science_tech": {"miragenews.com"},
}

EXCLUDE_KEYWORDS_PER_TOPIC = {
    "business": [
        "owner review",
        "test drive",
        "torana",
        "porsche",
        "car review",
        "road test",
    ],
}

MAX_ITEMS_PER_TOPIC = 5


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def host_from_url(url: str) -> str:
    m = re.match(r"^https?://([^/]+)/", url or "")
    return m.group(1).lower() if m else ""


def fetch_rss(url: str) -> bytes:
    # Basic UA helps with some endpoints
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (EirDailyPackBot)"})
    with urlopen(req, timeout=25) as resp:
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

        # Basic validity
        if not link.startswith("http"):
            continue

        host = host_from_url(link)
        if host in PAYWALL_BLOCKLIST:
            continue

        items.append(
            {
                "title": title,
                "publisher": publisher or host,
                "url": link,
                "published": pub,
            }
        )

    return items


def item_allowed_for_topic(item: dict, topic_id: str) -> bool:
    url = item.get("url", "")
    title = norm(item.get("title", ""))
    host = host_from_url(url)

    # Domain exclusions
    if topic_id in EXCLUDE_DOMAINS_PER_TOPIC:
        if host in EXCLUDE_DOMAINS_PER_TOPIC[topic_id]:
            return False

    # Keyword exclusions
    for bad in EXCLUDE_KEYWORDS_PER_TOPIC.get(topic_id, []):
        if norm(bad) in title:
            return False

    return True


def build_topics():
    """
    Build each topic using its own Google News RSS search feed.
    - Deduplicate globally by URL
    - Filter per-topic
    - NO leftovers backfill (prevents wrong-topic items)
    """
    built = []
    seen_urls = set()

    for t in TOPICS:
        tid = t["id"]
        label = t["label"]
        query = TOPIC_QUERIES.get(tid, "").strip()

        if not query:
            built.append({"id": tid, "label": label, "items": []})
            continue

        rss_url = GOOGLE_NEWS_SEARCH_RSS.format(query=quote_plus(query))
        xml_bytes = fetch_rss(rss_url)
        items = parse_rss(xml_bytes)

        filtered = []
        for it in items:
            if it["url"] in seen_urls:
                continue
            if not item_allowed_for_topic(it, tid):
                continue

            filtered.append(it)
            seen_urls.add(it["url"])

            if len(filtered) >= MAX_ITEMS_PER_TOPIC:
                break

        built.append({"id": tid, "label": label, "items": filtered})

    return built


def main():
    now = datetime.now(timezone.utc)

    out = {
        "market": "AU",
        "edition": "en-AU",
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "validForDate": now.date().isoformat(),  # app can display local date
        "source": "Google News RSS search (AU) — per-topic feeds",
        "topics": build_topics(),
    }

    out_path = "public/au/daily.json"
    import os

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    total = sum(len(t["items"]) for t in out["topics"])
    print(f"Wrote {out_path} with {total} items")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
