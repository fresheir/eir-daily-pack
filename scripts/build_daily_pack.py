def build_global_football_feed(existing_urls: set):
    # Global soccer-only feed with expanded competition coverage.
    # Uses GB English edition for broad football coverage.

    hl, gl, ceid = "en-GB", "GB", "GB:en"

    # Core idea:
    # - Positive keywords heavily biased to soccer/football + major competitions.
    # - Strong negative filters to remove American football + other non-soccer sports.
    #
    # NOTE: Google News RSS search supports basic boolean operators, quotes, and minus terms,
    # but not always perfectly. This query is designed to work even with partial support.

    include = (
        "("
        # Generic soccer terms (still required)
        'soccer OR football OR "match report" OR "fixture" OR "kick-off" OR kickoff OR "VAR" OR '
        "goal OR goals OR striker OR midfielder OR defender OR goalkeeper OR gaffer OR "
        '"transfer" OR "transfer window" OR "loan deal" OR "signing" OR "contract extension" OR '
        '"manager sacked" OR "head coach" OR "press conference" OR "injury update" OR '

        # UEFA club competitions
        '"champions league" OR UCL OR "uefa champions league" OR '
        '"europa league" OR UEL OR "uefa europa league" OR '
        '"conference league" OR UECL OR "uefa conference league" OR '
        '"uefa super cup" OR '

        # UEFA national team competitions
        '"uefa nations league" OR "euro qualifiers" OR "european championship" OR euros OR UEFA OR '

        # FIFA competitions
        '"world cup" OR "fifa world cup" OR "world cup qualifiers" OR '
        '"club world cup" OR "fifa club world cup" OR FIFA OR '

        # CONMEBOL
        '"copa libertadores" OR libertadores OR "copa sudamericana" OR sudamericana OR '
        '"copa america" OR "copa américa" OR CONMEBOL OR '

        # CONCACAF
        '"gold cup" OR "concacaf champions cup" OR "champions cup" OR CONCACAF OR '

        # AFC / CAF / OFC
        '"afc champions league" OR AFC OR "asian cup" OR '
        '"caf champions league" OR CAF OR "africa cup of nations" OR AFCON OR '
        "OFC"
        ")"
    )

    exclude = (
        "("
        # American football & common collisions
        "nfl OR nba OR nhl OR mlb OR ncaa OR "
        '"college football" OR "super bowl" OR "quarterback" OR touchdown OR '
        # Australian rules / rugby codes
        "afl OR nrl OR "
        '"rugby league" OR "rugby union" OR rugby OR '
        # Other sports
        "cricket OR tennis OR boxing OR ufc OR golf OR motogp OR "
        '"formula 1" OR f1'
        ")"
    )

    # Combine include/exclude
    query = f"{include} -{exclude}"

    url = google_search_url(query, hl, gl, ceid)
    xml_bytes = fetch_rss(url)
    items = parse_rss(xml_bytes)

    # Extra safeguard: filter obvious non-soccer titles (failsafe if query matching is leaky)
    bad_markers = [
        "nfl", "super bowl", "touchdown", "quarterback", "college football",
        "afl", "nrl", "rugby league", "rugby union", "ufc", "nba", "mlb", "nhl"
    ]
    def is_bad(title: str) -> bool:
        t = (title or "").lower()
        return any(m in t for m in bad_markers)

    items = [it for it in items if it["url"] not in existing_urls and not is_bad(it["title"])]

    return {
        "id": "football_global",
        "label": "Football News",
        "items": take_top(items, 12),  # a little more breadth for comps + transfers
    }
