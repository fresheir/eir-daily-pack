import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Set, Optional

# =====================================================
# PAYWALL DOMAINS (excluded from free JSON)
# =====================================================
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

# =====================================================
# GOOGLE NEWS EDITIONS
# (hl, gl, ceid)
# =====================================================
EXPLICIT_EDITIONS: Dict[str, Tuple[str, str, str]] = {
    # English core
    "au": ("en-AU", "AU", "AU:en"),
    "us": ("en-US", "US", "US:en"),
    "gb": ("en-GB", "GB", "GB:en"),
    "ie": ("en-IE", "IE", "IE:en"),
    "ca": ("en-CA", "CA", "CA:en"),
    "nz": ("en-NZ", "NZ", "NZ:en"),

    # Europe
    "fr": ("fr-FR", "FR", "FR:fr"),
    "de": ("de-DE", "DE", "DE:de"),
    "es": ("es-ES", "ES", "ES:es"),
    "pt": ("pt-PT", "PT", "PT:pt-150"),
    "it": ("it-IT", "IT", "IT:it"),
    "nl": ("nl-NL", "NL", "NL:nl"),
    "be": ("nl-BE", "BE", "BE:nl"),
    "ch": ("de-CH", "CH", "CH:de"),
    "at": ("de-AT", "AT", "AT:de"),
    "se": ("sv-SE", "SE", "SE:sv"),
    "no": ("nb-NO", "NO", "NO:no"),
    "dk": ("da-DK", "DK", "DK:da"),
    "fi": ("fi-FI", "FI", "FI:fi"),
    "pl": ("pl-PL", "PL", "PL:pl"),
    "cz": ("cs-CZ", "CZ", "CZ:cs"),
    "sk": ("sk-SK", "SK", "SK:sk"),
    "hu": ("hu-HU", "HU", "HU:hu"),
    "ro": ("ro-RO", "RO", "RO:ro"),
    "bg": ("bg-BG", "BG", "BG:bg"),
    "gr": ("el-GR", "GR", "GR:el"),
    "tr": ("tr-TR", "TR", "TR:tr"),
    "ru": ("ru-RU", "RU", "RU:ru"),
    "ua": ("uk-UA", "UA", "UA:uk"),
    "rs": ("sr-RS", "RS", "RS:sr"),
    "hr": ("hr-HR", "HR", "HR:hr"),
    "si": ("sl-SI", "SI", "SI:sl"),
    "ba": ("bs-BA", "BA", "BA:bs"),
    "me": ("sr-ME", "ME", "ME:sr"),
    "mk": ("mk-MK", "MK", "MK:mk"),
    "al": ("sq-AL", "AL", "AL:sq"),
    "lt": ("lt-LT", "LT", "LT:lt"),
    "lv": ("lv-LV", "LV", "LV:lv"),
    "ee": ("et-EE", "EE", "EE:et"),
    "is": ("is-IS", "IS", "IS:is"),
    "lu": ("fr-LU", "LU", "LU:fr"),
    "mt": ("mt-MT", "MT", "MT:mt"),
    "cy": ("el-CY", "CY", "CY:el"),

    # South America (major)
    "br": ("pt-BR", "BR", "BR:pt-419"),
    "ar": ("es-AR", "AR", "AR:es-419"),

    # Middle East
    "ae": ("ar-AE", "AE", "AE:ar"),
}

GLOBAL_EDITION = ("en-US", "US", "US:en")

# =====================================================
# TOPICS
# =====================================================
TOPICS = [
    {"id": "local_national", "label": "Local & National News", "kind": "topic", "topic_code": "NATION", "scope": "local"},
    {"id": "world",          "label": "World News",            "kind": "topic", "topic_code": "WORLD",  "scope": "local"},
    {"id": "business",       "label": "Business & Economy",    "kind": "topic", "topic_code": "BUSINESS","scope": "local"},
    {"id": "sport",          "label": "Sport",                 "kind": "topic", "topic_code": "SPORTS", "scope": "local"},
    {"id": "science_tech",   "label": "Science & Technology",  "kind": "topic", "topic_code": "TECHNOLOGY", "scope": "local"},

    # Global
    {"id": "football",       "label": "Football (Global)",     "kind": "search", "scope": "global"},
    {"id": "entertainment",  "label": "Entertainment (Global)","kind": "topic",  "topic_code": "ENTERTAINMENT", "scope": "global"},
]

FOOTBALL_QUERY = (
    '("football" OR "soccer") '
    '("UEFA" OR "Champions League" OR "Europa League" OR "Conference League" OR '
    '"World Cup" OR "FIFA" OR "Copa America" OR "AFCON" OR "Asian Cup" OR '
    '"Premier League" OR "EPL" OR "La Liga" OR "Serie A" OR "Bundesliga" OR "Ligue 1") '
    '-("NFL" OR "AFL" OR "NRL")'
)

# =====================================================
# HELPERS
# =====================================================
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

def dedupe(items: List[dict], seen: Set[str]) -> List[dict]:
    out = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        out.append(it)
    return out

def topic_url(code: str, hl: str, gl: str, ceid: str) -> str:
    return f"https://news.google.com/rss/headlines/section/topic/{code}?hl={hl}&gl={gl}&ceid={ceid}"

def search_url(query: str, hl: str, gl: str, ceid: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={ceid}"

def edition_candidates(cc: str):
    if cc in EXPLICIT_EDITIONS:
        yield EXPLICIT_EDITIONS[cc]
    yield (f"en-{cc.upper()}", cc.upper(), f"{cc.upper()}:en")
    yield ("en-GB", cc.upper(), f"{cc.upper()}:en")
    yield GLOBAL_EDITION

def fetch_topic(topic, cc, seen):
    editions = [GLOBAL_EDITION] if topic["scope"] == "global" else edition_candidates(cc)

    for (hl, gl, ceid) in editions:
        try:
            if topic["kind"] == "topic":
                url = topic_url(topic["topic_code"], hl, gl, ceid)
            else:
                url = search_url(FOOTBALL_QUERY, hl, gl, ceid)

            items = parse_rss(fetch_bytes(url))
            return dedupe(items, seen)[:5]
        except Exception:
            continue

    return []

# =====================================================
# MAIN
# =====================================================
def main():
    cc = sys.argv[1].lower() if len(sys.argv) > 1 else "us"
    now = datetime.now(timezone.utc)

    out = {
        "market": cc.upper(),
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "validForDate": now.date().isoformat(),
        "source": "Google News RSS",
        "topics": []
    }

    seen = set()

    for t in TOPICS:
        items = fetch_topic(t, cc, seen)
        out["topics"].append({
            "id": t["id"],
            "label": t["label"],
            "items": items
        })

    path = f"public/{cc}/daily.json"
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {path}")

if __name__ == "__main__":
    main()
