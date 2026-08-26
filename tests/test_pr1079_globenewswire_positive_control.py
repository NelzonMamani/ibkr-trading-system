from __future__ import annotations

import time
from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.news import news_fetcher
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.source_groups import get_source_group_urls
from src.scanner import scanner_runner
from src.strategies.ross_momentum.policy.catalyst_policy import assess_catalyst


GLOBENEWSWIRE_FINANCE_RSS = "https://www.globenewswire.com/RssFeed?Category=Finance"
GLOBENEWSWIRE_TECHNOLOGY_RSS = (
    "https://www.globenewswire.com/RssFeed/industry/9000-Technology/feedTitle/"
    "GlobeNewswire%20-%20Industry%20News%20on%20Technology"
)
IPDN_TITLE = (
    "Professional Diversity Network Launches PDN Intelligence to Advance GPU-Powered "
    "AI Infrastructure"
)
IPDN_URL = (
    "https://www.globenewswire.com/news-release/2026/08/21/3349010/25762/en/"
    "professional-diversity-network-launches-pdn-intelligence-to-advance-gpu-powered-ai-infrastructure.html"
)
IPDN_SUMMARY = (
    "CHICAGO, Aug. 21, 2026 (GLOBE NEWSWIRE) -- Professional Diversity Network, Inc. "
    "(Nasdaq: IPDN) announced the formation of PDN Intelligence, Inc., a wholly owned "
    "subsidiary established to lead expansion into artificial intelligence infrastructure "
    "and GPU-powered computing."
)


def _entry(title: str, *, summary: str = "", link: str = IPDN_URL, age_seconds: int = 300):
    return SimpleNamespace(
        title=title,
        summary=summary,
        link=link,
        published_parsed=time.gmtime(time.time() - age_seconds),
    )


def _feed(title: str, entries: list[object]):
    return SimpleNamespace(feed={"title": title}, entries=entries)


def test_pr1079_ipdn_miss_is_globenewswire_source_coverage_not_matching(monkeypatch):
    monkeypatch.setattr(news_fetcher, "feedparser", object())

    def fake_fetch_feed(url: str, timeout_s: float):
        if url == GLOBENEWSWIRE_FINANCE_RSS:
            return _feed("GlobeNewswire RSS Feed", [])
        if url == GLOBENEWSWIRE_TECHNOLOGY_RSS:
            return _feed(
                "GlobeNewswire - Industry News on Technology",
                [_entry(IPDN_TITLE, summary=IPDN_SUMMARY)],
            )
        return _feed(url, [])

    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_fetch_feed)
    metadata = {"IPDN": {"company_name": "Professional Diversity Network, Inc.", "aliases": ("PDN",)}}

    finance_only, finance_summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["IPDN"],
        [GLOBENEWSWIRE_FINANCE_RSS],
        lookback_hours=6.0,
        request_timeout_s=5.0,
        symbol_metadata=metadata,
        max_entries_per_symbol=5,
        total_news_budget_seconds=8.0,
    )
    assert finance_only["IPDN"] == []
    assert finance_summary.tier_match_counts == {"fast": 0}

    technology, technology_summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["IPDN"],
        [GLOBENEWSWIRE_TECHNOLOGY_RSS],
        lookback_hours=6.0,
        request_timeout_s=5.0,
        symbol_metadata=metadata,
        max_entries_per_symbol=5,
        total_news_budget_seconds=8.0,
    )
    assert [item.title for item in technology["IPDN"]] == [IPDN_TITLE]
    assert technology["IPDN"][0].match_type == "ticker_token"
    assert technology["IPDN"][0].matched_field == "summary"
    assert technology_summary.ticker_token_match_count == 1
    assert technology_summary.description_summary_match_count == 1


def test_pr1079_canonical_fast_trading_retrieves_ipdn_and_ross_confirms(monkeypatch, tmp_path):
    set_config_overrides(
        {
            "NEWS_CACHE_FILE": str(tmp_path / "news_cache.json"),
            "NEWS_MAX_ENTRIES_PER_SYMBOL": 5,
            "NEWS_LOOKBACK_HOURS": 6.0,
            "NEWS_TOTAL_BUDGET_S": 8.0,
            "NEWS_EXTENDED_TIER_RESERVE_FRACTION": 0.35,
            "NEWS_REQUEST_TIMEOUT_S": 5,
        }
    )
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._NEWS_CACHE = {}
    monkeypatch.setattr(news_fetcher, "feedparser", object())

    def fake_fetch_feed(url: str, timeout_s: float):
        if url == GLOBENEWSWIRE_TECHNOLOGY_RSS:
            return _feed(
                "GlobeNewswire - Industry News on Technology",
                [_entry(IPDN_TITLE, summary=IPDN_SUMMARY)],
            )
        return _feed(url, [])

    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_fetch_feed)

    fast_sources = get_source_group_urls("FAST_TRADING")
    assert GLOBENEWSWIRE_FINANCE_RSS in fast_sources
    assert GLOBENEWSWIRE_TECHNOLOGY_RSS in fast_sources

    result = CanonicalNewsIntelligenceService().get_news(
        [
            NewsCandidate(
                "IPDN",
                company_name="Professional Diversity Network, Inc.",
                aliases=("PDN",),
                exchange="NASDAQ",
            )
        ],
        NewsRequest(
            strategy_id="ross_momentum",
            lookback_seconds=6 * 3600,
            freshness_seconds=6 * 3600,
            include_generic_news=True,
            need_heat=True,
            need_velocity=True,
            need_reliability=True,
            max_evidence_per_symbol=5,
            session_phase="RTH",
            audit_reason="issue_1079_ipdn_positive_control",
        ),
        RetrievalPolicy(
            source_groups=("FAST_TRADING",),
            provider_groups=("rss_batch",),
            allow_cache_read=False,
            allow_cache_write=False,
            refresh_mode="bounded_refresh",
            network_allowed=True,
            total_budget_seconds=8.0,
            extended_reserve_fraction=0.35,
            request_timeout_seconds=5.0,
            fallback_mode="unresolved_only",
            metadata={"refresh_symbols": ("IPDN",), "unresolved_symbols": ("IPDN",)},
        ),
    )

    evidence = result.evidence_for_symbol("IPDN")
    assert len(evidence) == 1
    assert evidence[0].headline == IPDN_TITLE
    assert evidence[0].url == IPDN_URL
    assert evidence[0].source_group == "FAST_TRADING"
    assert evidence[0].source_tier == "fast"
    assert evidence[0].match_type == "ticker_token"
    assert evidence[0].stale is False
    assert result.diagnostics.diagnostics["source_provenance_by_symbol"]["IPDN"][0]["url"] == IPDN_URL
    source_diags = {item.source_id: item for item in result.diagnostics.source_diagnostics}
    assert source_diags[GLOBENEWSWIRE_FINANCE_RSS].matched_count == 0
    assert source_diags[GLOBENEWSWIRE_TECHNOLOGY_RSS].matched_count == 1

    news_context = scanner_runner._ross_news_contexts_from_news_intelligence_result(result)["IPDN"]
    assert news_context["news_present"] is True
    assert news_context["catalyst_type"] == "TECH_CATALYST"
    assert news_context["ross_catalyst_valid"] is True
    assert news_context["news_diagnostic_status"] == "catalyst_confirmed"

    ross_decision = assess_catalyst(
        mode=RunMode.READ_ONLY,
        news_enabled=True,
        news_available=bool(news_context["news_present"]),
        confirmed=news_context["ross_catalyst_valid"],
    )
    assert ross_decision.status.value == "CONFIRMED"
    assert ross_decision.reason == "confirmed"

    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({})
