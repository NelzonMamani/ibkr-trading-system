"""Offline source timing and owned-worker cleanup for standalone research."""
from concurrent.futures import Future
import json
import socket
import threading
import time
from types import SimpleNamespace

import pytest
import requests

from src.news import batch_rss_adapter, news_fetcher
from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.rss_lifecycle import RssFetchLifecycle


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("W03 lifecycle tests cannot access the network")
    monkeypatch.setattr(socket, "create_connection", refused)
    monkeypatch.setattr(socket.socket, "connect", refused)


class InlineExecutor:
    def __init__(self, **kwargs):
        self._threads = set()
    def submit(self, function, *args):
        future = Future()
        future.set_result(function(*args))
        return future
    def shutdown(self, **kwargs):
        pass


def feed(title="W03X and W03Y company update"):
    return SimpleNamespace(feed={"title": "Controlled publisher"}, entries=[SimpleNamespace(
        title=title, link="https://news.example/article", published_parsed=time.gmtime(time.time() - 60),
    )])


@pytest.mark.parametrize("outcome", ["success", "http_error", "read_timeout", "parse_error", "close_error"])
def test_real_fetch_seam_measures_phases_and_response_cleanup(monkeypatch, outcome):
    clock = [100.0]
    closed = []
    monkeypatch.setattr(news_fetcher.time, "monotonic", lambda: clock[0])
    class Response:
        status_code = 401 if outcome == "http_error" else 200
        text = "offline RSS fixture"
        def raise_for_status(self):
            if self.status_code == 401:
                response = requests.Response()
                response.status_code = 401
                response.url = "https://news.example/rss"
                response.raise_for_status()
        def close(self):
            closed.append(True)
            clock[0] += 0.4  # Cleanup is outside the fetch/parse completion instant.
            if outcome == "close_error":
                raise OSError("controlled close failure")
    def get(url, timeout):
        clock[0] += 0.2
        if outcome == "read_timeout":
            raise requests.exceptions.ReadTimeout("controlled timeout")
        return Response()
    def parse(text):
        assert text == "offline RSS fixture"
        clock[0] += 0.3
        if outcome == "parse_error":
            raise ValueError("controlled parse failure")
        return feed()
    monkeypatch.setattr(news_fetcher, "requests", SimpleNamespace(get=get))
    monkeypatch.setattr(news_fetcher, "feedparser", SimpleNamespace(parse=parse))
    lifecycle = RssFetchLifecycle()
    rows, summary = news_fetcher.fetch_headlines_for_symbols(
        ["W03X"], ["https://news.example/rss"], total_news_budget_seconds=0.6,
        lifecycle=lifecycle,
    )
    source = summary.source_diagnostics[0]
    parsed = outcome in {"success", "parse_error", "close_error"}
    assert source["request_elapsed_seconds"] == pytest.approx(0.2)
    assert source["parse_elapsed_seconds"] == (pytest.approx(0.3) if parsed else None)
    assert source["http_status"] == (None if outcome == "read_timeout" else Response.status_code)
    # Retrieval may be reported before the response-close callback completes.
    assert source["response_closed"] in {None, outcome != "close_error"}
    assert source["feed_item_count"] == (1 if outcome in {"success", "close_error"} else None)
    assert source["elapsed_seconds"] == pytest.approx(0.5 if parsed else 0.2)
    assert source["elapsed_kind"] == "worker_fetch_parse"
    assert source["worker_completed"] is True
    assert source["timed_out"] is (outcome == "read_timeout")
    assert source["budget_exhausted"] is False
    assert summary.news_budget_exhausted is False
    assert len(rows["W03X"]) == int(outcome in {"success", "close_error"})
    snapshot = lifecycle.wait_for_cleanup(1)
    assert closed == ([] if outcome == "read_timeout" else [True])
    assert snapshot["completed_count"] == 1
    assert snapshot["cleanup_complete"] is (outcome != "close_error")
    assert snapshot["response_cleanup_failures_count"] == int(outcome == "close_error")
    observed = snapshot["sources"][0]
    assert observed["source_id"] == "https://news.example/rss"
    assert observed["completed_at_s"] == pytest.approx(100.5 if parsed else 100.2)
    assert observed["worker_completed_at_s"] == pytest.approx(100.5 if parsed else 100.2)
    assert observed["cleanup_completed_at_s"] == pytest.approx(clock[0])
    assert observed["response_closed"] is (None if outcome == "read_timeout" else outcome != "close_error")
    assert observed["failure_reason"] == {
        "success": None, "close_error": None, "http_error": "HTTP_401",
        "read_timeout": "READTIMEOUT", "parse_error": "VALUEERROR",
    }[outcome]
    assert observed["cleanup_error"] == ("OSError" if outcome == "close_error" else None)
    json.dumps(snapshot)


def test_zero_worker_elapsed_and_unknown_injected_phase_times_are_preserved(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(news_fetcher.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(news_fetcher, "_fetch_feed", lambda url, timeout: feed())
    class DelayedCoordinator(InlineExecutor):
        def submit(self, function, *args):
            result = super().submit(function, *args)
            clock[0] += 0.5
            return result
    monkeypatch.setattr(news_fetcher, "ThreadPoolExecutor", DelayedCoordinator)
    lifecycle = RssFetchLifecycle()
    _, summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["W03X"], ["rss://controlled"], total_news_budget_seconds=1, lifecycle=lifecycle,
    )
    source = summary.source_diagnostics[0]
    assert source["elapsed_seconds"] == 0.0
    assert summary.news_elapsed_seconds == 0.5
    assert source["request_elapsed_seconds"] is None
    assert source["parse_elapsed_seconds"] is None
    assert source["http_status"] is None
    assert source["response_closed"] is None
    assert lifecycle.snapshot()["sources"][0]["elapsed_seconds"] == 0.0


def test_bounded_cleanup_reports_running_worker_and_never_promotes_late_evidence(monkeypatch, tmp_path):
    released = threading.Event()
    started = threading.Event()
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(batch_rss_adapter, "get_source_group_urls", lambda group: ("rss://slow", "rss://fast"))
    def fetch(url, timeout):
        if url == "rss://slow":
            started.set()
            assert released.wait(3), "test must release its owned worker"
            return feed("W03X and W03Y late update")
        assert started.wait(1)
        return feed()
    monkeypatch.setattr(news_fetcher, "_fetch_feed", fetch)
    lifecycle = RssFetchLifecycle()
    provider = BatchRssNewsIntelligenceProvider(lifecycle=lifecycle)
    service = CanonicalNewsIntelligenceService(
        evidence_store=CanonicalNewsEvidenceStore(tmp_path / "cache.json", prep_artifact_loader=lambda: {}),
        retrieval_provider=provider,
    )
    try:
        result = service.get_news([NewsCandidate("W03X"), NewsCandidate("W03Y")],
            NewsRequest(freshness_seconds=3600), RetrievalPolicy(
                source_groups=("FAST_TRADING",), total_budget_seconds=0.2, fallback_mode="none",
            ))
        source = next(item for item in result.diagnostics.source_diagnostics if item.source_id == "rss://slow")
        assert source.budget_exhausted is True
        assert source.timed_out is False
        assert source.worker_completed is False
        assert source.elapsed_kind == "since_submission"
        before = lifecycle.wait_for_cleanup(0.01)
        assert before["submitted_count"] == 2
        assert before["completed_count"] == 1
        assert before["unfinished_count"] == 1
        assert before["cleanup_complete"] is False
        assert before["alive_worker_count"] >= 1
        assert before["cancellation_requested_count"] == 1
        assert before["cancellation_succeeded_count"] == 0
        assert before["cleanup_elapsed_seconds"] < 0.5
        assert [item.headline for item in result.evidence_for_symbol("W03X")] == ["W03X and W03Y company update"]
    finally:
        released.set()
        cleaned = lifecycle.wait_for_cleanup(1)
    assert cleaned["cleanup_complete"] is True
    assert cleaned["completed_count"] == 2
    assert cleaned["unfinished_count"] == 0
    assert cleaned["alive_worker_count"] == 0
    assert all(row["state"] == "completed" for row in cleaned["sources"])
    assert result.diagnostics.budget_exhausted is True
    assert [item.headline for item in result.evidence_for_symbol("W03X")] == ["W03X and W03Y company update"]
    json.dumps(cleaned)


def test_lifecycle_tracks_shared_sources_across_both_tiers_once(monkeypatch):
    calls = []
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(batch_rss_adapter, "get_source_group_urls", lambda group: (
        ("rss://shared",) if group == "FAST_TRADING" else ("rss://shared", "rss://extended")
    ))
    def fetch(url, timeout):
        calls.append(url)
        return SimpleNamespace(feed={}, entries=[]) if url == "rss://shared" else feed()
    monkeypatch.setattr(news_fetcher, "_fetch_feed", fetch)
    lifecycle = RssFetchLifecycle()
    result = BatchRssNewsIntelligenceProvider(lifecycle=lifecycle).get_news(
        [NewsCandidate("W03X"), NewsCandidate("W03Y")], NewsRequest(), RetrievalPolicy(
            source_groups=("FAST_TRADING", "PREP_EXTENDED"), total_budget_seconds=2,
            metadata={"unresolved_symbols": ["W03X", "W03Y"]},
        ))
    cleaned = lifecycle.wait_for_cleanup(1)
    assert calls == ["rss://shared", "rss://extended"]
    assert cleaned["submitted_count"] == cleaned["completed_count"] == 2
    assert cleaned["cleanup_complete"] is True
    assert {item["source_tier"] for item in cleaned["sources"]} == {"fast", "extended"}
    assert len(result.evidence_for_symbol("W03X")) == len(result.evidence_for_symbol("W03Y")) == 1
    assert result.diagnostics.diagnostics["duplicate_source_fetches_avoided_count"] == 1
    assert all(item.request_elapsed_seconds is None for item in result.diagnostics.source_diagnostics)


def test_cancelled_work_and_unobservable_threads_are_reported_honestly():
    lifecycle = RssFetchLifecycle()
    lifecycle.register_executor(SimpleNamespace(_threads=set()))
    index = lifecycle.source_submitted("rss://queued", "fast", time.monotonic())
    future = Future()
    lifecycle.register_future(index, future)
    lifecycle.cancellation_requested(index, future.cancel())
    result = lifecycle.wait_for_cleanup(0)
    assert result["cancelled_count"] == 1
    assert result["completed_count"] == result["unfinished_count"] == 0
    assert result["cancellation_succeeded_count"] == 1
    assert result["cleanup_complete"] is True
    unknown = RssFetchLifecycle()
    unknown.register_executor(object())
    assert unknown.snapshot()["cleanup_complete"] is None
    assert unknown.snapshot()["worker_count"] is None


def test_opt_in_result_limit_reports_never_submitted_sources_without_budget_failure(monkeypatch):
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(news_fetcher, "ThreadPoolExecutor", InlineExecutor)
    monkeypatch.setattr(news_fetcher, "DEFAULT_RSS_FETCH_WORKERS", 1)
    monkeypatch.setattr(news_fetcher, "_fetch_feed", lambda url, timeout: feed())
    lifecycle = RssFetchLifecycle()
    rows, summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["W03X"], ["rss://first", "rss://unused"], total_news_budget_seconds=1,
        max_entries_per_symbol=1, lifecycle=lifecycle,
    )
    assert len(rows["W03X"]) == 1
    by_source = {item["source_id"]: item for item in summary.source_diagnostics}
    assert by_source["rss://unused"]["retrieval_status"] == "not_requested"
    assert by_source["rss://unused"]["failure_reason"] == "result_limit_reached"
    assert by_source["rss://unused"]["attempted"] is False
    assert by_source["rss://unused"]["budget_exhausted"] is False
    assert summary.total_sources == 2
    assert summary.sources_attempted_count == 1
    assert summary.sources_skipped_due_to_budget_count == 0
    assert summary.news_budget_exhausted is False
    assert lifecycle.snapshot()["submitted_count"] == 1


def test_in_time_parsed_feed_is_returned_while_owned_response_close_is_pending(monkeypatch):
    closing = threading.Event()
    release_close = threading.Event()
    class Response:
        status_code = 200
        text = "offline parsed feed"
        def raise_for_status(self): pass
        def close(self):
            closing.set()
            assert release_close.wait(3), "test must release owned response close"
    monkeypatch.setattr(news_fetcher, "requests", SimpleNamespace(get=lambda *args, **kwargs: Response()))
    monkeypatch.setattr(news_fetcher, "feedparser", SimpleNamespace(parse=lambda text: feed()))
    lifecycle = RssFetchLifecycle()
    try:
        rows, summary = news_fetcher.fetch_fast_headlines_for_symbols(
            ["W03X"], ["https://news.example/rss"], total_news_budget_seconds=0.2,
            lifecycle=lifecycle,
        )
        assert closing.wait(1)
        assert [item.title for item in rows["W03X"]] == ["W03X and W03Y company update"]
        assert summary.news_budget_exhausted is False
        snapshot = lifecycle.wait_for_cleanup(0.01)
        assert snapshot["completed_count"] == 1
        assert snapshot["unfinished_count"] == 0
        assert snapshot["alive_worker_count"] == 1
        assert snapshot["cleanup_complete"] is False
        assert snapshot["sources"][0]["response_closed"] is None
    finally:
        release_close.set()
        cleaned = lifecycle.wait_for_cleanup(1)
    assert cleaned["cleanup_complete"] is True
    assert cleaned["sources"][0]["response_closed"] is True
    assert cleaned["alive_worker_count"] == 0
