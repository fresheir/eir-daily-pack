import json
import re
import sys
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

# -----------------------------
# MARKETS (major countries only)
# -----------------------------
MARKETS = {
    # Americas
    "us": {"hl": "en-US", "gl": "US", "ceid": "US:en", "region": "AMER"},
    "ca": {"hl": "en-CA", "gl": "CA", "ceid": "CA:en", "region": "AMER"},
    "mx": {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419", "region": "AMER"},
    "br": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-BR", "region": "AMER"},
    "ar": {"hl": "es-419", "gl": "AR", "ceid": "AR:es-419", "region": "AMER"},
    "cl": {"hl": "es-419", "gl": "CL", "ceid": "CL:es-419", "region": "AMER"},
    "co": {"hl": "es-419", "gl": "CO", "ceid": "CO:es-419", "region": "AMER"},
    "pe": {"hl": "es-419", "gl": "PE", "ceid": "PE:es-419", "region": "AMER"},

    # Europe
    "gb": {"hl": "en-GB", "gl": "GB", "ceid": "GB:en", "region": "EU"},
    "ie": {"hl": "en-IE", "gl": "IE", "ceid": "IE:en", "region": "EU"},
    "fr": {"hl": "fr-FR", "gl": "FR", "ceid": "FR:fr", "region": "EU"},
    "de": {"hl": "de-DE", "gl": "DE", "ceid": "DE:de", "region": "EU"},
    "es": {"hl": "es-ES", "gl": "ES", "ceid": "ES:es", "region": "EU"},
    "pt": {"hl": "pt-PT", "gl": "PT", "ceid": "PT:pt-PT", "region": "EU"},
    "it": {"hl": "it-IT", "gl": "IT", "ceid": "IT:it", "region": "EU"},
    "nl": {"hl": "nl-NL", "gl": "NL", "ceid": "NL:nl", "region": "EU"},
    "be": {"hl": "fr-BE", "gl": "BE", "ceid": "BE:fr", "region": "EU"},
    "ch": {"hl": "de-CH", "gl": "CH", "ceid": "CH:de", "region": "EU"},
    "at": {"hl": "de-AT", "gl": "AT", "ceid": "AT:de", "region": "EU"},
    "dk": {"hl": "da-DK", "gl": "DK", "ceid": "DK:da", "region": "EU"},
    "se": {"hl": "sv-SE", "gl": "SE", "ceid": "SE:sv", "region": "EU"},
    "no": {"hl": "nb-NO", "gl": "NO", "ceid": "NO:nb", "region": "EU"},
    "fi": {"hl": "fi-FI", "gl": "FI", "ceid": "FI:fi", "region": "EU"},
    "pl": {"hl": "pl-PL", "gl": "PL", "ceid": "PL:pl", "region": "EU"},
    "cz": {"hl": "cs-CZ", "gl": "CZ", "ceid": "CZ:cs", "region": "EU"},
    "sk": {"hl": "sk-SK", "gl": "SK", "ceid": "SK:sk", "region": "EU"},
    "hu": {"hl": "hu-HU", "gl": "HU", "ceid": "HU:hu", "region": "EU"},
    "ro": {"hl": "ro-RO", "gl": "RO", "ceid": "RO:ro", "region": "EU"},
    "bg": {"hl": "bg-BG", "gl": "BG", "ceid": "BG:bg", "region": "EU"},
    "gr": {"hl": "el-GR", "gl": "GR", "ceid": "GR:el", "region": "EU"},
    "ua": {"hl": "uk-UA", "gl": "UA", "ceid": "UA:uk", "region": "EU"},
    "tr": {"hl": "tr-TR", "gl": "TR", "ceid": "TR:tr", "region": "EU"},
    "hr": {"hl": "hr-HR", "gl": "HR", "ceid": "HR:hr", "region": "EU"},
    "rs": {"hl": "sr-RS", "gl": "RS", "ceid": "RS:sr", "region": "EU"},
    "si": {"hl": "sl-SI", "gl": "SI", "ceid": "SI:sl", "region": "EU"},
    "ba": {"hl": "bs-BA", "gl": "BA", "ceid": "BA:bs", "region": "EU"},
    "al": {"hl": "sq-AL", "gl": "AL", "ceid": "AL:sq", "region": "EU"},
    "lt": {"hl": "lt-LT", "gl": "LT", "ceid": "LT:lt", "region": "EU"},
    "lv": {"hl": "lv-LV", "gl": "LV", "ceid": "LV:lv", "region": "EU"},
    "ee": {"hl": "et-EE", "gl": "EE", "ceid": "EE:et", "region": "EU"},

    # APAC
    "au": {"hl": "en-AU", "gl": "AU", "ceid": "AU:en", "region": "APAC"},
    "nz": {"hl": "en-NZ", "gl": "NZ", "ceid": "NZ:en", "region": "APAC"},
    "jp": {"hl": "ja-JP", "gl": "JP", "ceid": "JP:ja", "region": "APAC"},
    "cn": {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans", "region": "APAC"},
    "hk": {"hl": "zh-HK", "gl": "HK", "ceid": "HK:zh-Hant", "region": "APAC"},
    "sg": {"hl": "en-SG", "gl": "SG", "ceid": "SG:en", "region": "APAC"},
    "in": {"hl": "en-IN", "gl": "IN", "ceid": "IN:en", "region": "APAC"},
    "kr": {"hl": "ko-KR", "gl": "KR", "ceid": "KR:ko", "region": "APAC"},
    "tw": {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant", "region": "APAC"},
    "id": {"hl": "id-ID", "gl": "ID", "ceid": "ID:id", "region": "APAC"},
    "my": {"hl": "ms-MY", "gl": "MY", "ceid": "MY:ms", "region": "APAC"},
    "th": {"hl": "th-TH", "gl": "TH", "ceid": "TH:th", "region": "APAC"},
    "vn": {"hl": "vi-VN", "gl": "VN", "ceid": "VN:vi", "region": "APAC"},
    "ph": {"hl": "en-PH", "gl": "PH", "ceid": "PH:en", "region": "APAC"},

    # Other majors (optional)
    "za": {"hl": "en-ZA", "gl": "ZA", "ceid": "ZA:en", "region": "OTHER"},
    "ae": {"hl": "en-AE", "gl": "AE", "ceid": "AE:en", "region": "OTHER"},
    "sa": {"hl": "ar-SA", "gl": "SA", "ceid": "SA:ar", "region": "OTHER"},
    "il": {"hl": "he-IL", "gl": "IL", "ceid": "IL:he", "region": "OTHER"},
    "eg": {"hl": "ar-EG", "gl": "EG", "ceid": "EG:ar", "region": "OTHER"},
    "ng": {"hl": "en-NG", "gl": "NG", "ceid": "NG:en", "region": "OTHER"},
}

# -----------------------------
# 5 LOCAL topics (topic RSS)
# -----------------------------
TOPICS = [
    {"id": "local_national", "label": "Local & National News", "gn_topic": "NATION"},
    {"id": "world", "label": "World News", "gn_topic": "WORLD"},
    {"id": "business", "label": "Business & Economy", "gn_topic": "BUSINESS"},
    {"id": "sport", "label": "Sport", "gn_topic": "SPORTS"},
    {"id": "science_tech", "label": "Science & Technology", "gn_topic": "TECHNOLOGY"},
]

# Optional paywall blocklist
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

def host_from_url(url: str) -> str:
    m = re.match(r"^https?://([^/]+)/", url or "")
    return m.group(1).lower() if m else ""

def fetch_rss(url: str) -> bytes:
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
        })
    return items

def google_topic_url(gn_topic: str, hl: str, gl: str, ceid: str) -> str:
    return f"https://news.google.com/rss/headlines/section/topic/{gn_topic}?hl={hl}&gl={gl}&ceid={ceid}"

def google_search_url(query: str, hl: str, gl: str, ceid: str) -> str:
    q = quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"

def dedupe_by_url(items):
    seen = set()
    out = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        out.append(it)
    return out

def take_top(items, n=5):
    return dedupe_by_url(items)[:n]

def build_market_pack(market_key: str, cfg: dict):
    now = datetime.now(timezone.utc)
    valid_for_date = now.date().isoformat()

    out = {
        "market": cfg["gl"],
        "edition": cfg["hl"],
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "validForDate": valid_for_date,
        "source": "Google News RSS",
        "topics": []
    }

    # 5 local topics
    for t in TOPICS:
        url = google_topic_url(t["gn_topic"], cfg["hl"], cfg["gl"], cfg["ceid"])
        xml_bytes = fetch_rss(url)
        items = parse_rss(xml_bytes)
        out["topics"].append({
            "id": t["id"],
            "label": t["label"],
            "items": take_top(items, 5),
        })

    return out

def build_global_football_feed(existing_urls: set):
    # Global soccer-only feed
    hl, gl, ceid = "en-GB", "GB", "GB:en"
    query = (
        '(soccer OR football OR "premier league" OR "champions league" OR "ucl" OR "la liga" '
        'OR "serie a" OR bundesliga OR "ligue 1" OR uefa OR fifa OR "transfer window" OR "transfer" '
        'OR "match report") '
        '-nfl -"super bowl" -"college football" -"afl" -"nrl" -"rugby league" -"rugby union"'
    )
    url = google_search_url(query, hl, gl, ceid)
    xml_bytes = fetch_rss(url)
    items = parse_rss(xml_bytes)
    items = [it for it in items if it["url"] not in existing_urls]
    return {
        "id": "football_global",
        "label": "Football News",
        "items": take_top(items, 10),
    }

def build_global_entertainment_feed(existing_urls: set):
    # Global entertainment feed
    hl, gl, ceid = "en-US", "US", "US:en"
    query = (
        '(entertainment OR celebrity OR "box office" OR "film" OR "movie" OR "tv" OR "streaming" '
        'OR "netflix" OR "disney" OR "hbo" OR "music" OR "album" OR "tour" OR "festival" '
        'OR "hollywood" OR "red carpet") '
        '-sports -nfl -nba -afl -nrl -cricket'
    )
    url = google_search_url(query, hl, gl, ceid)
    xml_bytes = fetch_rss(url)
    items = parse_rss(xml_bytes)
    items = [it for it in items if it["url"] not in existing_urls]
    return {
        "id": "entertainment_global",
        "label": "Entertainment",
        "items": take_top(items, 10),
    }

def main():
    # Optional batching: set REGION=EU / AMER / APAC / OTHER
    region_filter = os.environ.get("REGION", "").strip().upper()

    markets_to_build = []
    for k, cfg in MARKETS.items():
        if region_filter and cfg.get("region", "").upper() != region_filter:
            continue
        markets_to_build.append((k, cfg))

    if not markets_to_build:
        print(f"No markets to build for REGION='{region_filter}'. Exiting cleanly.")
        return

    for market_key, cfg in markets_to_build:
        pack = build_market_pack(market_key, cfg)

        existing_urls = set()
        for topic in pack["topics"]:
            for item in topic["items"]:
                existing_urls.add(item["url"])

        # Append global extras (no overlap)
        pack["topics"].append(build_global_football_feed(existing_urls))
        # refresh existing_urls after adding football
        for item in pack["topics"][-1]["items"]:
            existing_urls.add(item["url"])

        pack["topics"].append(build_global_entertainment_feed(existing_urls))

        out_path = f"public/{market_key}/daily.json"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False, indent=2)

        print(f"Wrote {out_path} ({len(pack['topics'])} topics)")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
