"""Offline W02 source-outcome verification; no HTTP or broker access."""
from concurrent.futures import Future
from types import SimpleNamespace
import time

import pytest
import requests

from src.news import news_fetcher
from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService


def test_local_deadline_is_not_an_observed_http_timeout(monkeypatch, tmp_path):
    clock = [100.0]
    monkeypatch.setattr(news_fetcher.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    class PendingExecutor:
        def __init__(self, **kwargs): pass
        def submit(self, *args):
            future = Future()
            future.set_running_or_notify_cancel()
            return future
        def shutdown(self, **kwargs): pass
    monkeypatch.setattr(news_fetcher, "ThreadPoolExecutor", PendingExecutor)
    def wait_at_deadline(futures, timeout, return_when):
        clock[0] += timeout
        return set(), set(futures)
    monkeypatch.setattr(news_fetcher, "wait", wait_at_deadline)
    def bounded_fetch(symbols, sources, **kwargs):
        return news_fetcher.fetch_fast_headlines_for_symbols(symbols, sources[:1], **kwargs)
    provider = BatchRssNewsIntelligenceProvider(fast_fetcher=bounded_fetch)
    service = CanonicalNewsIntelligenceService(
        evidence_store=CanonicalNewsEvidenceStore(tmp_path / "cache.json", prep_artifact_loader=lambda: {}),
        retrieval_provider=provider)
    result = service.get_news([NewsCandidate("KNRX")], NewsRequest(), RetrievalPolicy(
        source_groups=("FAST_TRADING",), total_budget_seconds=1.0,
        request_timeout_seconds=5, fallback_mode="none", metadata={"refresh_symbols": ["KNRX"]}))
    source = result.diagnostics.source_diagnostics[0]
    assert source.attempted is True
    assert source.budget_exhausted is True
    assert source.failure_reason == "deadline_exhausted"
    assert source.timed_out is False  # No HTTP exception was observed.
    assert result.diagnostics.timeout_count == 0
    assert result.summary_for_symbol("KNRX").retrieval_unavailable is True


def test_observed_http_read_timeout_remains_a_timeout(monkeypatch):
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    def timeout(*args):
        raise requests.exceptions.ReadTimeout("offline controlled exception")
    monkeypatch.setattr(news_fetcher, "_fetch_feed", timeout)
    rows, diagnostics = news_fetcher.fetch_fast_headlines_for_symbols(
        ["KNRX"], ["https://www.benzinga.com/feed"], total_news_budget_seconds=8.0)
    assert rows == {"KNRX": []}
    source = diagnostics.source_diagnostics[0]
    assert source["failure_reason"] == "READTIMEOUT"
    assert source["timed_out"] is True
    assert source["budget_exhausted"] is False


@pytest.mark.parametrize("deadline_kind", ["stage", "tier"])
@pytest.mark.parametrize(
    ("completion_offset", "coordinator_lag"),
    [(-0.001, 0.0), (0.0, 0.0), (0.001, 0.0), (-0.001, 0.002)],
    ids=["before", "at", "after", "before-with-late-coordinator"],
)
def test_completed_future_is_accepted_only_before_applicable_deadline(
    monkeypatch, deadline_kind, completion_offset, coordinator_lag,
):
    clock = [100.0]
    pending_work = {}
    monkeypatch.setattr(news_fetcher.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(news_fetcher, "feedparser", object())

    class DeferredExecutor:
        def __init__(self, **kwargs):
            pass

        def submit(self, function, *args):
            future = Future()
            future.set_running_or_notify_cancel()
            pending_work[future] = (function, args)
            return future

        def shutdown(self, **kwargs):
            pass

    monkeypatch.setattr(news_fetcher, "ThreadPoolExecutor", DeferredExecutor)
    feed = SimpleNamespace(feed={"title": "Controlled source"}, entries=[SimpleNamespace(
        title="W02X wins contract", link="https://news.example/w02x",
        published_parsed=time.gmtime(time.time() - 60),
    )])
    monkeypatch.setattr(news_fetcher, "_fetch_feed", lambda *args: feed)

    def completed_after_wait(futures, timeout, return_when):
        # Model a completion racing the coordinator's bounded wait. No real sleep.
        clock[0] = 101.0 + completion_offset
        for future in futures:
            function, args = pending_work.pop(future)
            future.set_result(function(*args))
        clock[0] += coordinator_lag
        return set(futures), set()

    monkeypatch.setattr(news_fetcher, "wait", completed_after_wait)
    stage_budget = 1.0 if deadline_kind == "stage" else 3.0
    tier_budget = 1.0 if deadline_kind == "tier" else 3.0
    headlines, summary = news_fetcher.fetch_headlines_for_symbols(
        ["W02X"], ["rss://controlled"], source_tier="extended",
        total_news_budget_seconds=stage_budget, stage_started_at_s=100.0,
        stage_deadline_s=100.0 + stage_budget,
        tier_budget_seconds=tier_budget, tier_started_at_s=100.0,
        tier_deadline_s=100.0 + tier_budget,
    )

    source = summary.source_diagnostics[0]
    assert source["attempted"] is True
    assert source["timed_out"] is False
    assert summary.failure_count == 0
    if completion_offset < 0:
        assert [item.title for item in headlines["W02X"]] == ["W02X wins contract"]
        assert source["retrieval_status"] == "available"
        assert source["matched_count"] == 1
        assert source["budget_exhausted"] is False
        if not coordinator_lag:
            assert summary.news_budget_exhausted is False
            assert summary.tier_budget_exhausted is False
    else:
        assert headlines["W02X"] == []
        assert source["retrieval_status"] == "budget_exhausted"
        assert source["failure_reason"] == "deadline_exhausted"
        assert source["matched_count"] == 0
        assert source["budget_exhausted"] is True
        assert summary.news_budget_exhausted is (deadline_kind == "stage")
        assert summary.tier_budget_exhausted is (deadline_kind == "tier")

@pytest.mark.parametrize("deadline_kind", ["stage", "tier"])
@pytest.mark.parametrize("completion_offset", [0.0, 0.001], ids=["at", "after"])
@pytest.mark.parametrize("failure_code", ["HTTP_401", "READTIMEOUT"])
def test_late_observed_transport_failure_retains_error_and_budget_facts(
    monkeypatch, deadline_kind, completion_offset, failure_code,
):
    clock = [100.0]
    pending_work = {}
    monkeypatch.setattr(news_fetcher.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(news_fetcher, "feedparser", object())

    class DeferredExecutor:
        def __init__(self, **kwargs):
            pass

        def submit(self, function, *args):
            future = Future()
            future.set_running_or_notify_cancel()
            pending_work[future] = (function, args)
            return future

        def shutdown(self, **kwargs):
            pass

    monkeypatch.setattr(news_fetcher, "ThreadPoolExecutor", DeferredExecutor)

    def failed_feed(*args):
        if failure_code == "READTIMEOUT":
            raise requests.exceptions.ReadTimeout("offline controlled exception")
        response = requests.Response()
        response.status_code = 401
        response.url = "https://news.example/rss"
        response.raise_for_status()

    def completed_after_wait(futures, timeout, return_when):
        clock[0] = 101.0 + completion_offset
        for future in futures:
            function, args = pending_work.pop(future)
            future.set_result(function(*args))
        return set(futures), set()

    monkeypatch.setattr(news_fetcher, "_fetch_feed", failed_feed)
    monkeypatch.setattr(news_fetcher, "wait", completed_after_wait)
    stage_budget = 1.0 if deadline_kind == "stage" else 3.0
    tier_budget = 1.0 if deadline_kind == "tier" else 3.0
    headlines, summary = news_fetcher.fetch_headlines_for_symbols(
        ["W02X"], ["https://news.example/rss"], source_tier="extended",
        total_news_budget_seconds=stage_budget, stage_started_at_s=100.0,
        stage_deadline_s=100.0 + stage_budget,
        tier_budget_seconds=tier_budget, tier_started_at_s=100.0,
        tier_deadline_s=100.0 + tier_budget,
    )

    source = summary.source_diagnostics[0]
    assert headlines == {"W02X": []}
    assert source["attempted"] is True
    assert source["retrieval_status"] == "budget_exhausted"
    assert source["budget_exhausted"] is True
    assert source["failure_reason"] == failure_code
    assert source["timed_out"] is (failure_code == "READTIMEOUT")
    assert summary.failure_count == 1
    assert summary.failures_by_domain == {"news.example": {failure_code: 1}}
    assert summary.news_budget_exhausted is (deadline_kind == "stage")
    assert summary.tier_budget_exhausted is (deadline_kind == "tier")

    # The public provider must retain the observed error count and unavailability.
    provider = BatchRssNewsIntelligenceProvider(
        extended_fetcher=lambda *args, **kwargs: (headlines, summary),
    )
    result = provider.get_news([NewsCandidate("W02X")], NewsRequest(), RetrievalPolicy(
        source_groups=("PREP_EXTENDED",), total_budget_seconds=8.0,
        metadata={"unresolved_symbols": ["W02X"]},
    ))
    assert result.diagnostics.budget_exhausted is True
    assert result.diagnostics.timeout_count == int(failure_code == "READTIMEOUT")
    assert result.diagnostics.diagnostics["rss_failures"] == 1
    assert result.summary_for_symbol("W02X").retrieval_unavailable is True
