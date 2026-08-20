from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import batch_rss_adapter, news_fetcher, rss_batch_runtime
from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
from src.news.news_fetcher import Headline, RssFailureSummary
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.source_groups import get_source_group_urls
from src.scanner import scanner_runner


@pytest.fixture(autouse=True)
def _news_config_defaults(tmp_path):
    set_config_overrides(
        {
            "NEWS_MAX_ENTRIES_PER_SYMBOL": 5,
            "NEWS_LOOKBACK_HOURS": 24.0,
            "NEWS_REQUEST_TIMEOUT_S": 5,
            "NEWS_TOTAL_BUDGET_S": 8.0,
            "NEWS_EXTENDED_TIER_RESERVE_FRACTION": 0.35,
            "NEWS_CACHE_FILE": str(tmp_path / "news_cache.json"),
        }
    )
    yield
    set_config_overrides({})


def _headline(
    title: str,
    *,
    age_seconds: float = 300.0,
    source: str = "PR1067 Feed",
    url: str = "https://news.example/pr1067",
    summary: str = "",
    source_tier: str = "fast",
    match_type: str = "ticker_token",
    matched_field: str = "title",
) -> Headline:
    return Headline(
        title=title,
        source=source,
        published_ts=time.time() - age_seconds,
        url=url,
        summary=summary,
        source_tier=source_tier,
        match_type=match_type,
        matched_field=matched_field,
    )


def _summary(
    *,
    total_sources: int,
    tier: str,
    failure_count: int = 0,
    failures_by_domain: dict[str, dict[str, int]] | None = None,
    reason: str | None = None,
    tier_matches: int = 0,
    ticker_matches: int = 0,
    company_matches: int = 0,
    summary_matches: int = 0,
    max_entries: int = 5,
    budget: float = 8.0,
    elapsed: float = 0.02,
    budget_exhausted: bool = False,
    attempted: int | None = None,
    skipped: int = 0,
    tier_budget: float = 5.2,
    tier_elapsed: float = 0.01,
    tier_exhausted: bool = False,
) -> RssFailureSummary:
    attempted_count = total_sources if attempted is None else attempted
    return RssFailureSummary(
        total_sources=total_sources,
        failure_count=failure_count,
        failures_by_domain=failures_by_domain or {},
        reason=reason,
        tier_source_counts={tier: total_sources} if total_sources else {},
        tier_match_counts={tier: tier_matches} if tier_matches else {},
        ticker_token_match_count=ticker_matches,
        company_name_match_count=company_matches,
        description_summary_match_count=summary_matches,
        max_entries_per_symbol=max_entries,
        total_news_budget_seconds=budget,
        news_elapsed_seconds=elapsed,
        news_budget_exhausted=budget_exhausted,
        sources_attempted_count=attempted_count,
        sources_skipped_due_to_budget_count=skipped,
        tier_sources_attempted_counts={tier: attempted_count} if total_sources else {},
        tier_budget_seconds=tier_budget,
        tier_elapsed_seconds=tier_elapsed,
        tier_budget_exhausted=tier_exhausted,
        tier_budget_seconds_by_tier={tier: tier_budget} if total_sources else {},
        tier_elapsed_seconds_by_tier={tier: tier_elapsed} if total_sources else {},
        tier_budget_exhausted_by_tier={tier: tier_exhausted} if total_sources else {},
    )


def test_pr1067_fast_sources_order_and_batch_once_without_catalyst_classification(monkeypatch):
    fast_sources = list(get_source_group_urls("FAST_TRADING"))
    calls: dict[str, object] = {}

    def fake_fast(symbols, sources, **kwargs):
        calls["fast"] = {"symbols": list(symbols), "sources": list(sources), "kwargs": kwargs}
        return (
            {
                "PR67A": [_headline("PR67A reports earnings beat")],
                "PR67B": [_headline("PR67B announces strategic partnership")],
            },
            _summary(
                total_sources=len(sources),
                tier="fast",
                tier_matches=2,
                ticker_matches=2,
                tier_budget=5.2,
            ),
        )

    def fake_extended(*args, **kwargs):
        raise AssertionError("common provider must not infer unresolved Ross catalyst symbols")

    monkeypatch.setattr(batch_rss_adapter, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(batch_rss_adapter, "fetch_headlines_for_symbols", fake_extended)

    result = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("PR67A"), NewsCandidate("PR67B")],
        NewsRequest(),
        RetrievalPolicy(),
    )

    assert calls["fast"]["symbols"] == ["PR67A", "PR67B"]
    assert calls["fast"]["sources"] == fast_sources
    assert calls["fast"]["kwargs"]["request_timeout_s"] == 5.0
    assert calls["fast"]["kwargs"]["total_news_budget_seconds"] == 8.0
    assert calls["fast"]["kwargs"]["tier_budget_seconds"] == pytest.approx(5.2)
    assert result.diagnostics.source_groups_queried == ("FAST_TRADING",)
    evidence = result.evidence_for_symbol("PR67A")[0]
    assert evidence.event_class is None
    assert evidence.catalyst_classification is None
    assert evidence.is_qualifying_event_class is False
    assert result.summaries_by_symbol["PR67A"].qualifying_event_class_count == 0
    assert result.summaries_by_symbol["PR67B"].diagnostics["objective_news_status"] == "news_present_unclassified"
    assert result.diagnostics.diagnostics["classification_authority"] == "strategy_adapter_not_common_provider"


def test_pr1067_unresolved_only_extended_fallback_uses_explicit_strategy_symbols(monkeypatch):
    captured_extended: dict[str, object] = {}

    def fake_fast(symbols, sources, **kwargs):
        return (
            {
                "FASTY": [_headline("FASTY reports earnings beat")],
                "SLOWY": [_headline("SLOWY moves higher in morning trading")],
            },
            _summary(
                total_sources=len(sources),
                tier="fast",
                tier_matches=2,
                ticker_matches=2,
            ),
        )

    def fake_extended(symbols, sources, **kwargs):
        captured_extended["symbols"] = list(symbols)
        captured_extended["sources"] = list(sources)
        captured_extended["kwargs"] = kwargs
        return (
            {"SLOWY": [_headline("SLOWY receives FDA approval", source_tier="extended")]},
            _summary(
                total_sources=len(sources),
                tier="extended",
                tier_matches=1,
                ticker_matches=1,
                tier_budget=2.8,
            ),
        )

    monkeypatch.setattr(batch_rss_adapter, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(batch_rss_adapter, "fetch_headlines_for_symbols", fake_extended)

    result = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("FASTY"), NewsCandidate("SLOWY")],
        NewsRequest(),
        RetrievalPolicy(metadata={"unresolved_symbols": ("SLOWY",)}),
    )

    assert captured_extended["symbols"] == ["SLOWY"]
    assert captured_extended["sources"] == list(get_source_group_urls("PREP_EXTENDED"))
    assert result.diagnostics.diagnostics["extended_fallback_requested"] is True
    assert result.diagnostics.diagnostics["extended_fallback_symbol_count"] == 1
    assert result.diagnostics.source_groups_queried == ("FAST_TRADING", "PREP_EXTENDED")
    assert result.evidence_for_symbol("SLOWY")[1].source_group == "PREP_EXTENDED"
    assert result.evidence_for_symbol("SLOWY")[1].event_class is None


def test_pr1067_no_implicit_extended_fallback_without_strategy_unresolved_symbols(monkeypatch):
    def fake_fast(symbols, sources, **kwargs):
        return (
            {"WAIT": []},
            _summary(total_sources=len(sources), tier="fast"),
        )

    def fake_extended(*args, **kwargs):
        raise AssertionError("extended fallback requires explicit unresolved symbols from strategy policy")

    monkeypatch.setattr(batch_rss_adapter, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(batch_rss_adapter, "fetch_headlines_for_symbols", fake_extended)

    result = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("WAIT")],
        NewsRequest(),
        RetrievalPolicy(),
    )

    assert result.diagnostics.diagnostics["extended_fallback_requested"] is False
    assert result.diagnostics.diagnostics["explicit_unresolved_symbol_count"] == 0
    assert result.summaries_by_symbol["WAIT"].diagnostics["objective_news_status"] == "no_recent_news"


def test_pr1067_company_summary_matching_uses_existing_fetcher(monkeypatch):
    published = time.gmtime(time.time() - 300)

    def fake_fetch_feed(url, timeout_s):
        return SimpleNamespace(
            feed={"title": "PR1067 Feed"},
            entries=[
                SimpleNamespace(
                    title="FDA approval granted for lead therapy",
                    summary="Avidity Biosciences announced the update before the open.",
                    link="https://news.example/avidity",
                    published_parsed=published,
                )
            ],
        )

    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_fetch_feed)

    result = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("RNAZ", company_name="Avidity Biosciences Inc.")],
        NewsRequest(),
        RetrievalPolicy(source_groups=("FAST_TRADING",)),
    )

    evidence = result.evidence_for_symbol("RNAZ")
    assert len(evidence) == 1
    assert evidence[0].match_type == "company_name"
    assert evidence[0].matched_field == "summary"
    assert evidence[0].event_class is None
    assert evidence[0].is_qualifying_event_class is False
    assert result.diagnostics.diagnostics["company_name_match_count"] == 1
    assert result.diagnostics.diagnostics["description_summary_match_count"] == 1


def test_pr1067_budget_exhaustion_maps_unavailable_not_absent_or_confirmed(monkeypatch):
    fast_sources = list(get_source_group_urls("FAST_TRADING"))

    def fake_fast(symbols, sources, **kwargs):
        return (
            {symbol: [] for symbol in symbols},
            _summary(
                total_sources=len(sources),
                tier="fast",
                budget=0.5,
                elapsed=0.5,
                budget_exhausted=True,
                attempted=1,
                skipped=len(fast_sources) - 1,
                tier_budget=0.5,
                tier_elapsed=0.5,
                tier_exhausted=True,
            ),
        )

    def fake_extended(*args, **kwargs):
        raise AssertionError("extended fallback must not start after stage budget exhaustion")

    monkeypatch.setattr(batch_rss_adapter, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(batch_rss_adapter, "fetch_headlines_for_symbols", fake_extended)

    result = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("BUDG")],
        NewsRequest(),
        RetrievalPolicy(total_budget_seconds=0.5),
    )

    summary = result.summaries_by_symbol["BUDG"]
    assert result.diagnostics.retrieval_status == "budget_exhausted"
    assert result.diagnostics.budget_exhausted is True
    assert result.diagnostics.unresolved_symbols == ("BUDG",)
    assert summary.retrieval_status == "budget_exhausted"
    assert summary.retrieval_unavailable is True
    assert summary.qualifying_event_class_count == 0
    assert result.diagnostics.diagnostics["result_status_counts"] == {"budget_exhausted": 1}


def test_pr1067_generic_or_keyword_news_remains_unclassified_and_fail_closed(monkeypatch):
    def fake_fast(symbols, sources, **kwargs):
        return (
            {"GENR": [_headline("GENR announces earnings guidance and partnership")]},
            _summary(total_sources=len(sources), tier="fast", tier_matches=1, ticker_matches=1),
        )

    def fake_extended(*args, **kwargs):
        raise AssertionError("adapter must not infer unresolved status from keyword headlines")

    monkeypatch.setattr(batch_rss_adapter, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(batch_rss_adapter, "fetch_headlines_for_symbols", fake_extended)

    result = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("GENR")],
        NewsRequest(),
        RetrievalPolicy(),
    )

    evidence = result.evidence_for_symbol("GENR")
    assert evidence[0].event_class is None
    assert evidence[0].catalyst_classification is None
    assert evidence[0].is_qualifying_event_class is False
    assert result.summaries_by_symbol["GENR"].qualifying_event_class_count == 0
    assert result.summaries_by_symbol["GENR"].diagnostics["classification_authority"] == "strategy_adapter_not_common_provider"


def test_pr1067_partial_failure_mapping(monkeypatch):
    def fake_fast(symbols, sources, **kwargs):
        return (
            {symbol: [] for symbol in symbols},
            _summary(
                total_sources=len(sources),
                tier="fast",
                failure_count=1,
                failures_by_domain={"timeout.example": {"TIMEOUT": 1}},
            ),
        )

    def fake_extended(*args, **kwargs):
        raise AssertionError("extended fallback requires explicit unresolved symbols")

    monkeypatch.setattr(batch_rss_adapter, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(batch_rss_adapter, "fetch_headlines_for_symbols", fake_extended)

    result = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("PART")],
        NewsRequest(),
        RetrievalPolicy(),
    )

    assert result.diagnostics.retrieval_status == "partial"
    assert result.diagnostics.provider_status == "partial_request_failure"
    assert result.diagnostics.timeout_count == 1
    assert result.diagnostics.source_failures == {"timeout.example": "TIMEOUT:1"}


def test_pr1067_batch_of_one_uses_batch_contract(monkeypatch):
    def fake_fast(symbols, sources, **kwargs):
        assert symbols == ["ONE"]
        return (
            {"ONE": [_headline("ONE announces new contract")]},
            _summary(total_sources=len(sources), tier="fast", tier_matches=1, ticker_matches=1),
        )

    monkeypatch.setattr(batch_rss_adapter, "fetch_fast_headlines_for_symbols", fake_fast)

    result = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("ONE")],
        NewsRequest(),
        RetrievalPolicy(source_groups=("FAST_TRADING",)),
    )

    assert result.symbols == ("ONE",)
    assert result.evidence_for_symbol("ONE")[0].event_class is None


def test_pr1067_adapter_and_neutral_runtime_do_not_own_ross_catalyst_policy():
    adapter_source = Path("src/news/batch_rss_adapter.py").read_text(encoding="utf-8")
    runtime_source = Path("src/news/rss_batch_runtime.py").read_text(encoding="utf-8")
    scanner_source = Path("src/scanner/scanner_runner.py").read_text(encoding="utf-8")

    forbidden = (
        "CATALYST_KEYWORDS",
        "DILUTION_KEYWORDS",
        "_detect_catalyst_type",
        "_headlines_have_confirmed_catalyst",
        "catalyst_confirmed",
    )
    for token in forbidden:
        assert token not in adapter_source
        assert token not in runtime_source
    assert "CATALYST_KEYWORDS" in scanner_source
    assert "DILUTION_KEYWORDS" in scanner_source
    assert "def _detect_catalyst_type" in scanner_source


def test_pr1067_neutral_runtime_helpers_match_scanner_wrappers():
    fast = _summary(total_sources=2, tier="fast", tier_matches=1, ticker_matches=1)
    extended = _summary(
        total_sources=3,
        tier="extended",
        failure_count=1,
        failures_by_domain={"example.com": {"TIMEOUT": 1}},
        tier_budget=2.8,
    )

    assert scanner_runner._news_provider_status(fast) == rss_batch_runtime.news_provider_status(fast)
    assert scanner_runner._news_fast_tier_budget_seconds(8.0, extended_sources_available=True) == pytest.approx(5.2)
    assert scanner_runner._news_fast_tier_budget_seconds(8.0, extended_sources_available=False) == pytest.approx(8.0)

    scanner_merged = scanner_runner._merge_rss_failure_summaries(fast, extended)
    runtime_merged = rss_batch_runtime.merge_rss_failure_summaries(fast, extended)
    assert scanner_merged == runtime_merged

    duplicate = _headline("SAME headline", source="Same Source")
    deduped = scanner_runner._dedupe_bounded_headlines([duplicate, duplicate], 5)
    assert deduped == rss_batch_runtime.dedupe_bounded_headlines([duplicate, duplicate], 5)
    assert len(deduped) == 1
    assert len(rss_batch_runtime.dedupe_bounded_headlines([duplicate], 0)) == 1


def test_pr1067_scanner_runtime_uses_news_intelligence_with_fetcher_compatibility():
    scanner_source = Path("src/scanner/scanner_runner.py").read_text(encoding="utf-8")

    assert "BatchRssNewsIntelligenceProvider" in scanner_source
    assert "CanonicalNewsIntelligenceService" in scanner_source
    assert "src.news.batch_rss_adapter" in scanner_source
    assert "fetch_fast_headlines_for_symbols" in scanner_source
    assert "fetch_headlines_for_symbols" in scanner_source
    assert "RSS_FAST_TRADING" in scanner_source
    assert "RSS_PREP_EXTENDED" in scanner_source
    assert "CATALYST_KEYWORDS" in scanner_source
    assert "def _detect_catalyst_type" in scanner_source