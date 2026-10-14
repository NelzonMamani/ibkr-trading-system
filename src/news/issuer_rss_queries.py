"""Explicit research URL contracts; no transport, cache or trading authority.

Yahoo's ticker endpoint is recovered from the archived stock-selection scripts.
Google's RSS search endpoint/locale parameters already occur in verified_rss.txt.
These contracts do not establish present-day access or complete search coverage.
"""
from __future__ import annotations

import re
from typing import Any, Sequence
from urllib.parse import urlencode

from src.news.news_intelligence_contract import NewsCandidate
from src.news.source_groups import get_source_group_urls

OPERATIONAL_GROUP = "ROSS_ISSUER_QUERY"
OPERATIONAL_GROUPS = ("FAST_TRADING", "PREP_EXTENDED", OPERATIONAL_GROUP)

QUERY_PROFILE = "issuer_query_rss_research_v1"
QUERY_GROUP = "ISSUER_QUERY_RSS"
QUERY_GROUPS = ("FAST_TRADING", "PREP_EXTENDED", QUERY_GROUP)


def query_sources(candidates: Sequence[NewsCandidate]) -> list[dict[str, Any]]:
    """At most two URLs per issuer; identical URLs share one acquisition."""
    rows = {}
    if len(candidates) > 50:
        raise ValueError("Issuer-query RSS accepts at most 50 issuers")
    for candidate in candidates:
        symbol = candidate.normalized_symbol
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\^-]{0,29}", symbol):
            raise ValueError("Issuer-query RSS requires a plain US ticker")
        names = list(dict.fromkeys(" ".join(str(name).split()) for name in
                                  (candidate.company_name, *candidate.aliases) if name))
        if not candidate.company_name or not str(candidate.company_name).strip():
            raise ValueError("Issuer-query RSS requires company_name for every issuer")
        if len(names) > 9 or any(not name or len(name) > 160 or '"' in name or '\\' in name for name in names):
            raise ValueError("Issuer-query RSS accepts at most 9 literal names of 160 characters without quotes/backslashes")
        exchange = str(candidate.exchange or "").upper()
        terms = [f'"{name}"' for name in sorted(names, key=str.casefold)]
        terms.append(f'"${symbol}"')
        if exchange in {"NASDAQ", "NYSE", "AMEX"}:
            terms.append(f'"{exchange}:{symbol}"')
        google = "https://news.google.com/rss/search?" + urlencode({
            "q": "(" + " OR ".join(terms) + ")", "hl": "en-US", "gl": "US", "ceid": "US:en"})
        yahoo = "https://feeds.finance.yahoo.com/rss/2.0/headline?" + urlencode({
            "s": symbol, "region": "US", "lang": "en-US"})
        for provider, url in (("google_news_search", google), ("yahoo_ticker_rss", yahoo)):
            row = rows.setdefault(url, {"source_id": url, "source_group": QUERY_GROUP,
                                        "query_provider": provider, "query_issuers": []})
            if symbol not in row["query_issuers"]:
                row["query_issuers"].append(symbol)
    return list(rows.values())


def query_plan(candidates):
    # Research discovery precedes fixed feeds; operational ordering is untouched.
    rows = {row["source_id"]: row for row in query_sources(candidates)}
    for group in QUERY_GROUPS[:-1]:
        for url in get_source_group_urls(group):
            rows.setdefault(url, {"source_id": url, "source_group": group})
    return list(rows.values())


def operational_queries(candidates):
    # Yahoo's observed 429 remains research evidence; no operational retry loop.
    rows = {}
    for candidate in sorted(candidates, key=lambda c: (c.priority_rank is None, c.priority_rank or 0, c.normalized_symbol)):
        try:
            queries = query_sources((candidate,))
        except ValueError:
            # Invalid identities have explicit per-issuer coverage; no invented URL.
            continue
        for row in queries:
            if row["query_provider"] != "google_news_search":
                continue
            shared = rows.setdefault(row["source_id"], {**row, "source_group": OPERATIONAL_GROUP, "query_issuers": []})
            shared["query_issuers"].extend(s for s in row["query_issuers"] if s not in shared["query_issuers"])
    return list(rows.values())
