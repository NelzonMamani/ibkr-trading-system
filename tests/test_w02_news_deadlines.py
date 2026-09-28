from __future__ import annotations

from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from src.news import batch_rss_adapter, news_fetcher
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy


class _Clock:
    now = 100.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _InlineExecutor:
    """Complete fake fetches deterministically without threads or network."""

    def __init__(self, **kwargs):
        pass

    def submit(self, fn, *args):
        future = Future()
        future.set_result(fn(*args))
        return future

    def shutdown(self, **kwargs):
        pass


@pytest.mark.parametrize(
    ("extended_budget", "expected_attempts"),
    [(2.0, 2), (0.0, 0), (10.0, 7), (None, 7)],
    ids=["smaller-tier-cap", "zero-tier-cap", "global-cap", "remaining-global-default"],
)
def test_extended_tier_deadline_bounds_actual_source_attempts(
    monkeypatch: pytest.MonkeyPatch,
    extended_budget: float | None,
    expected_attempts: int,
) -> None:
    clock = _Clock()
    extended_sources = tuple(f"rss://extended-{index}" for index in range(10))
    calls: list[str] = []
    monkeypatch.setattr(batch_rss_adapter.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(batch_rss_adapter, "get_source_group_urls", lambda group: (
        ("rss://fast",) if group == "FAST_TRADING" else extended_sources
    ))
    monkeypatch.setattr(news_fetcher, "ThreadPoolExecutor", _InlineExecutor)
    monkeypatch.setattr(news_fetcher, "DEFAULT_RSS_FETCH_WORKERS", 1)
    monkeypatch.setattr(news_fetcher, "feedparser", object())

    def fake_fast(symbols, sources, **kwargs):
        assert list(sources) == ["rss://fast"]
        clock.advance(1.0)
        return {symbol: [] for symbol in symbols}, news_fetcher.RssFailureSummary(
            total_sources=1, failure_count=0, failures_by_domain={}, reason=None,
        )

    def fake_feed(url: str, timeout_s: float):
        calls.append(url)
        clock.advance(1.0)
        return SimpleNamespace(feed={"title": "Controlled feed"}, entries=[])

    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_feed)
    tier_budgets = {"fast": 5.2}
    if extended_budget is not None:
        tier_budgets["extended"] = extended_budget
    policy = RetrievalPolicy(
        source_groups=("FAST_TRADING", "PREP_EXTENDED"),
        total_budget_seconds=8.0,
        tier_budgets=tier_budgets,
        extended_reserve_fraction=0.35,
        request_timeout_seconds=5.0,
        metadata={"unresolved_symbols": ("W02X",)},
    )

    result = batch_rss_adapter.BatchRssNewsIntelligenceProvider(
        fast_fetcher=fake_fast,
    ).get_news(
        [NewsCandidate("W02X")],
        NewsRequest(lookback_seconds=86400.0, max_evidence_per_symbol=5),
        policy,
    )

    assert calls == list(extended_sources[:expected_attempts])
    diagnostics = result.diagnostics.diagnostics
    assert diagnostics["extended_sources_attempted_count"] == expected_attempts
    assert diagnostics["sources_skipped_due_to_budget_count"] == 10 - expected_attempts
    assert diagnostics["extended_budget_exhausted"] is True
    assert result.diagnostics.elapsed_seconds == pytest.approx(1.0 + expected_attempts)
    assert result.diagnostics.total_budget_seconds == 8.0
    assert result.retrieval_policy is policy
    assert diagnostics["extended_budget_seconds"] == pytest.approx(
        7.0 if extended_budget is None else min(7.0, extended_budget)
    )


def test_extended_tier_exhaustion_marks_only_requested_unresolved_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    monkeypatch.setattr(batch_rss_adapter.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(batch_rss_adapter, "get_source_group_urls", lambda group: (
        ("rss://fast",) if group == "FAST_TRADING" else ("rss://extended",)
    ))

    def fake_fast(symbols, sources, **kwargs):
        clock.advance(1.0)
        headline = news_fetcher.Headline(
            title="W02Y issuer announcement", source="Controlled feed",
            published_ts=batch_rss_adapter.time.time() - 60.0,
            url="https://news.example/w02y",
        )
        return {"W02X": [], "W02Y": [headline]}, news_fetcher.RssFailureSummary(
            total_sources=1, failure_count=0, failures_by_domain={}, reason=None,
        )

    def fake_extended(symbols, sources, **kwargs):
        assert list(symbols) == ["W02X"]
        clock.advance(2.0)
        return {"W02X": []}, news_fetcher.RssFailureSummary(
            total_sources=1, failure_count=0, failures_by_domain={}, reason=None,
            total_news_budget_seconds=8.0, news_elapsed_seconds=3.0,
            news_budget_exhausted=False, tier_budget_exhausted=True,
            tier_budget_seconds_by_tier={"extended": 2.0},
            tier_elapsed_seconds_by_tier={"extended": 2.0},
            tier_budget_exhausted_by_tier={"extended": True},
        )

    result = batch_rss_adapter.BatchRssNewsIntelligenceProvider(
        fast_fetcher=fake_fast, extended_fetcher=fake_extended,
    ).get_news(
        [NewsCandidate("W02X"), NewsCandidate("W02Y")],
        NewsRequest(lookback_seconds=86400.0, max_evidence_per_symbol=5),
        RetrievalPolicy(
            source_groups=("FAST_TRADING", "PREP_EXTENDED"),
            total_budget_seconds=8.0,
            tier_budgets={"fast": 5.2, "extended": 2.0},
            extended_reserve_fraction=0.35, request_timeout_seconds=5.0,
            metadata={"unresolved_symbols": ("W02X",)},
        ),
    )

    assert result.diagnostics.budget_exhausted is True
    assert result.diagnostics.unresolved_symbols == ("W02X",)
    assert result.diagnostics.elapsed_seconds == 3.0
    assert result.diagnostics.total_budget_seconds == 8.0
    assert result.diagnostics.diagnostics["extended_budget_exhausted"] is True
    assert result.diagnostics.diagnostics["total_budget_exhausted"] is False
    assert result.summary_for_symbol("W02X").retrieval_status == "budget_exhausted"
    assert result.summary_for_symbol("W02X").budget_exhausted is True
    assert result.summary_for_symbol("W02Y").retrieval_status == "available"
    assert result.summary_for_symbol("W02Y").budget_exhausted is False
    assert result.evidence_for_symbol("W02Y")[0].retrieval_status == "available"
    assert result.evidence_for_symbol("W02Y")[0].budget_exhausted is False
