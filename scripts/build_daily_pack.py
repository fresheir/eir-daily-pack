import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Optional, Set

# -----------------------------
# PAYWALL / SUBSCRIPTION DOMAINS
# -----------------------------
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

# -----------------------------
# COUNTRY SUPPORT
# You can expand later. Keep to the list you generate in the workflow.
# Format: cc -> (hl, gl, ceid)
# hl = language-locale, gl = country, ceid = edition:lang
# -----------------------------
COUNTRY_EDITIONS: Dict[str, Tuple[str, str, str]] = {
    "au": ("en-AU", "AU", "AU:en"),
    "us": ("en-US", "US", "US:en"),
    "gb": ("en-GB", "GB", "GB:en"),
    "ca": ("en-CA", "CA", "CA:en"),
    "nz": ("en-NZ", "NZ", "NZ:en"),
    "ie": ("en-IE", "IE", "IE:en"),
    "sg": ("en-SG", "SG", "SG:en"),
    "jp": ("en-JP", "JP", "JP:en"),
    "br": ("pt-BR", "BR", "BR:pt-419"),
    "ar": ("es-AR", "AR", "AR:es-419"),
}

# If a cc isn't in the map, fallback to US edition.
DEFAULT_CC = "us"

# -----------------------------
# TOPICS (stable set)
# For local topics: fetch with the user's country edition.
# For global topics: fetch with a fixed edition so it’s consistent everywhere.
# -----------------------------
TOPICS = [
    {"id": "local_national", "label": "Local & National News", "kind": "topic", "topic_code": "NATION", "scope": "local"},
    {"id": "world",          "label": "World News",            "kind": "topic", "topic_code": "WORLD",  "scope": "local"},
    {"id": "business",       "label": "Business & Economy",    "kind": "topic", "topic_code": "BUSINESS","scope": "local"},
    {"id": "sport",          "label": "Sport",                 "kind": "topic", "topic_code": "SPORTS", "scope": "local"},
    {"id": "science_tech",   "label": "Science & Technology",  "kind": "topic", "topic_code": "TECHNOLOGY", "scope": "local"},

    # Global topics:
    {"id": "football",       "label": "Football (Global)",     "kind": "search", "query": None, "scope": "global"},
    {"id": "entertainment",  "label": "Entertainment (Global)","kind": "topic", "topic_code": "ENTERTAINMENT", "scope": "global"},
]

# Football query: broad soccer focus + major comps.
FOOTBALL_QUERY = (
    '("football" OR "soccer") '
    '("UEFA" OR "Champions League" OR "Europa League" OR "Conference League" OR '
    '"World Cup" OR "FIFA" OR "Copa America" OR "AFCON" OR "AFC Asian Cup" OR '
    '"Premier League" OR "EPL" OR "La Liga" OR "Serie A" OR "Bundesliga" OR "Ligue 1" OR '
    '"UCL" OR "UEL") '
    '-("NFL" OR "AFL" OR "NRL")'
)

# Choose a single global edition to keep global topics consistent.
GLOBAL_EDITION = ("en-US", "US", "US:en")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def host_from_url(url: str) -> str:
    m = re.match(r"^https?://([^/]+)/", url or "")
    return m.group(1).lower() if m else ""


def is_blocklisted(url: str) -> bool:
    h = host_from_url(url)
    return any(h == d or h.endswith("." + d) for d in PAYWALL_BLOCKLIST)


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (EirDailyPackBot)"})
    with urlopen(req, timeout=25) as resp:
        return resp.read()


def parse_rss(xml_bytes: bytes) -> List[dict]:
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
        publisher = (source_el.text if source_el is not None else "") or ""

        if not link.startswith("http"):
            continue
        if is_blocklisted(link):
            continue

        items.append({
            "title": title,
            "publisher": publisher.strip() or host_from_url(link),
            "url": link,
            "published": pub,
        })

    return items


def dedupe_keep_order(items: List[dict], seen_urls: Set[str]) -> List[dict]:
    out = []
    for it in items:
        u = it.get("url", "")
        if not u or u in seen_urls:
            continue
        seen_urls.add(u)
        out.append(it)
    return out


def build_topic_rss_url(topic_code: str, hl: str, gl: str, ceid: str) -> str:
    # Example:
    # https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-AU&gl=AU&ceid=AU:en
    return f"https://news.google.com/rss/headlines/section/topic/{topic_code}?hl={hl}&gl={gl}&ceid={ceid}"


def build_search_rss_url(query: str, hl: str, gl: str, ceid: str) -> str:
    q = quote_plus(query)
    # Example:
    # https://news.google.com/rss/search?q=...&hl=en-US&gl=US&ceid=US:en
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def fetch_topic_items(topic: dict, local_edition: Tuple[str, str, str], limit: int, seen_urls: Set[str]) -> List[dict]:
    if topic.get("scope") == "global":
        hl, gl, ceid = GLOBAL_EDITION
    else:
        hl, gl, ceid = local_edition

    if topic["kind"] == "topic":
        url = build_topic_rss_url(topic["topic_code"], hl, gl, ceid)
    elif topic["kind"] == "search":
        query = FOOTBALL_QUERY if topic["id"] == "football" else (topic.get("query") or "")
        url = build_search_rss_url(query, hl, gl, ceid)
    else:
        return []

    xml_bytes = fetch_bytes(url)
    items = parse_rss(xml_bytes)

    # Dedupe across ALL topics
    items = dedupe_keep_order(items, seen_urls)

    # Return up to limit
    return items[:limit]


def resolve_country_edition(cc: str) -> Tuple[str, str, str]:
    cc = (cc or "").strip().lower()
    if cc in COUNTRY_EDITIONS:
        return COUNTRY_EDITIONS[cc]
    return COUNTRY_EDITIONS[DEFAULT_CC]


def main():
    # Country code argument (lowercase ISO-2), default to US if missing
    cc = sys.argv[1].strip().lower() if len(sys.argv) > 1 else DEFAULT_CC

    local_edition = resolve_country_edition(cc)
    now = datetime.now(timezone.utc)

    # Build output object
    valid_for_date = now.date().isoformat()
    out = {
        "market": cc.upper(),
        "edition": local_edition[0],
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "validForDate": valid_for_date,
        "source": "Google News RSS",
        "topics": []
    }

    seen_urls: Set[str] = set()

    # Fetch 5 items per topic
    for t in TOPICS:
        try:
            items = fetch_topic_items(t, local_edition, limit=5, seen_urls=seen_urls)
        except Exception as e:
            # If a specific topic feed fails, return empty list for that topic,
            # but keep building the pack.
            items = []
            print(f"[WARN] Topic {t['id']} failed for {cc}: {e}", file=sys.stderr)

        out["topics"].append({
            "id": t["id"],
            "label": t["label"],
            "items": items
        })

    # Write output
    out_path = f"public/{cc}/daily.json"
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
