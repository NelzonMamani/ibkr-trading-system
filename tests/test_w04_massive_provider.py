"""Synthetic public fixtures only; these tests never call Massive or any network."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest
import requests

from src.news import massive_news_adapter as adapter
from src.news.massive_news_adapter import ENDPOINT, MassiveNewsIntelligenceProvider, trusted_page_url
from src.news.massive_rate_limit import MassiveRateLimiter
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.rss_lifecycle import RssFetchLifecycle


NOW = datetime(2026, 9, 28, 22, tzinfo=timezone.utc)
SECRET = "offline-private-test-credential"
CANDIDATE = NewsCandidate("IRON", company_name="Disc Medicine", aliases=("Disc Medicine Inc",))
REQUEST = NewsRequest(lookback_seconds=86400, freshness_seconds=86400, max_evidence_per_symbol=20,
                      query_start_utc=NOW-timedelta(days=1), query_end_utc=NOW)
POLICY = RetrievalPolicy(total_budget_seconds=2, request_timeout_seconds=1)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("W04 provider fixtures cannot access the network")
    monkeypatch.setattr(socket, "create_connection", refused)
    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setenv("MASSIVE_API_KEY", SECRET)
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)


class NoLimit:
    def __init__(self):
        self.starts = 0
        self.cooldowns = []
    def acquire(self, deadline):
        self.starts += 1
        return None
    def cooldown(self, seconds):
        self.cooldowns.append(seconds)
        return True


class Response:
    def __init__(self, payload=None, status=200, *, headers=None, closing=None):
        self.payload = payload if payload is not None else {"status": "OK", "results": []}
        self.status_code = status
        self.headers = headers or {}
        self.closed = False
        self.closing = closing
    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload
    def close(self):
        if self.closing:
            self.closing()
        self.closed = True


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def article(identifier="a", *, title="Disc Medicine announces company update", published=None, **changes):
    return {"id": identifier, "title": title, "description": "Research fixture only",
            "published_utc": (published or NOW-timedelta(hours=18)).isoformat(),
            "article_url": "https://publisher.example/articles/"+identifier,
            "publisher": {"name": "Synthetic Publisher"}, "tickers": ["IRON"], **changes}


def page(*articles, next_url=None):
    result = {"status": "OK", "count": len(articles), "results": list(articles)}
    if next_url is not None:
        result["next_url"] = next_url
    return Response(result)


def invoke(transport, candidates=(CANDIDATE,), request=REQUEST, policy=POLICY, limiter=None):
    tracker = RssFetchLifecycle()
    provider = MassiveNewsIntelligenceProvider(lifecycle=tracker, transport=transport, limiter=limiter or NoLimit())
    result = provider.get_news(candidates, request, policy)
    cleanup = tracker.wait_for_cleanup(2)
    assert cleanup["cleanup_complete"] is True
    return result, cleanup


def test_identity_single_batch_duplicates_and_round_robin_pages():
    first = replace(CANDIDATE, metadata={"identity_source": "synthetic"})
    other = NewsCandidate("MSFT", company_name="Microsoft Corporation")
    transport = Transport(page(article(), next_url=ENDPOINT+"?cursor=iron2"),
                          page(article("m", title="Microsoft Corporation update", tickers=["MSFT"])),
                          page(article(), article("b")))
    result, cleanup = invoke(transport, [first, other, replace(first, company_name="Wrong duplicate")])
    assert result.candidates == (first, other)
    assert [call[1]["params"]["ticker"] if call[1]["params"] else "page2" for call in transport.calls] == ["IRON", "MSFT", "page2"]
    assert [item.reference_id for item in result.evidence_for_symbol("IRON")] == ["a", "b"]
    item = result.evidence_for_symbol("IRON")[0]
    assert item.original_source == "Synthetic Publisher"
    assert item.raw["provider_article_id"] == "a" and item.raw["provider_tickers"] == ("IRON",)
    assert item.published_at == NOW-timedelta(hours=18)
    assert item.fetched_at != item.published_at
    assert item.company_name == first.company_name and item.aliases == first.aliases
    assert item.is_qualifying_event_class is False
    assert result.summary_for_symbol("IRON").diagnostics["duplicate_article_count"] == 1
    assert cleanup["submitted_count"] == cleanup["completed_count"] == 3
    for url, kwargs in transport.calls:
        assert SECRET not in url and kwargs["headers"] == {"Authorization": "Bearer " + SECRET}
        assert kwargs["allow_redirects"] is False
    assert result.diagnostics.source_diagnostics[0].matched_count == 1
    assert result.diagnostics.source_diagnostics[0].feed_item_count == 1


@pytest.mark.parametrize("metadata", [{"company_name": "Disc Medicine"}, {"aliases": ["Disc Medicine"]}])
def test_metadata_only_issuer_identity_remains_available(metadata):
    result, _ = invoke(Transport(page(article())), [NewsCandidate("IRON", metadata=metadata)])
    assert len(result.evidence_for_symbol("IRON")) == 1


def test_exact_utc_window_and_tag_is_not_relevance_proof():
    rows = [article("lower", published=REQUEST.query_start_utc), article("upper", published=NOW),
            article("before", published=REQUEST.query_start_utc-timedelta(microseconds=1)),
            article("after", published=NOW+timedelta(microseconds=1)),
            article("future", published=datetime.now(timezone.utc)+timedelta(days=1)),
            article("missing", published_utc=None), article("naive", published_utc="2026-09-28T12:00:00"),
            article("unrelated", title="Iron ore prices rise on industrial demand", tickers=["IRON"])]
    transport = Transport(page(*rows))
    result, _ = invoke(transport)
    assert [item.reference_id for item in result.evidence_for_symbol("IRON")] == ["upper", "lower"]
    details = result.summary_for_symbol("IRON").diagnostics
    assert details["rejected_article_counts"] == {"outside_query_window": 2, "future_publication_time": 1,
                                                  "invalid_publication_time": 2, "issuer_relevance_rejected": 1}
    params = transport.calls[0][1]["params"]
    assert params["ticker"] == "IRON" and params["published_utc.gte"] == REQUEST.query_start_utc.isoformat()
    assert params["published_utc.lte"] == NOW.isoformat()


def test_rolling_window_frozen_across_symbols_and_cursor_pages():
    transport = Transport(page(next_url=ENDPOINT+"?cursor=next"), page(), page())
    result, _ = invoke(transport, [CANDIDATE, NewsCandidate("MSFT")], replace(REQUEST, query_start_utc=None, query_end_utc=None))
    first, second, third = [kwargs["params"] for _, kwargs in transport.calls]
    assert first["published_utc.gte"] == second["published_utc.gte"]
    assert first["published_utc.lte"] == second["published_utc.lte"]
    assert third is None
    assert result.diagnostics.diagnostics["query_end_utc"] == first["published_utc.lte"]


@pytest.mark.parametrize("url", ["http://api.massive.com/v2/reference/news?cursor=x", "https://evil.example/v2/reference/news?cursor=x",
    "https://api.massive.com.evil.example/v2/reference/news?cursor=x", "https://api.massive.com:444/v2/reference/news?cursor=x",
    "https://x@api.massive.com/v2/reference/news?cursor=x", "https://api.massive.com/other?cursor=x",
    ENDPOINT, ENDPOINT+"?ticker=MSFT", ENDPOINT+"?cursor=", ENDPOINT+"?cursor=x&cursor=y",
    ENDPOINT+"?cursor=x&apiKey="+SECRET, ENDPOINT+"?cursor=x#fragment", "//api.massive.com/v2/reference/news?cursor=x"])
def test_unsafe_pagination_never_receives_credentials(url):
    transport = Transport(page(next_url=url))
    result, _ = invoke(transport)
    assert len(transport.calls) == 1
    assert result.summary_for_symbol("IRON").retrieval_status == "partial"
    assert result.summary_for_symbol("IRON").diagnostics["failure_reason"] == "untrusted_pagination_url"
    assert SECRET not in json.dumps(asdict(result), default=str)


def test_explicit443_cursor_and_caps_are_partial_even_without_matches():
    assert trusted_page_url("https://api.massive.com:443/v2/reference/news?cursor=opaque%2Bvalue")
    transport = Transport(page(next_url=ENDPOINT+"?cursor=2"))
    result, _ = invoke(transport, policy=replace(POLICY, metadata={"massive_max_pages_per_symbol": 1}))
    assert result.summary_for_symbol("IRON").retrieval_status == "partial"
    assert result.summary_for_symbol("IRON").diagnostics["failure_reason"] == "page_limit_reached"
    transport = Transport(page())
    result, _ = invoke(transport, [CANDIDATE, NewsCandidate("MSFT")], policy=replace(POLICY, metadata={"massive_max_requests": 1}))
    assert result.summary_for_symbol("IRON").retrieval_status == "available"
    assert result.summary_for_symbol("MSFT").diagnostics["failure_reason"] == "request_limit_reached"
    assert result.diagnostics.source_diagnostics[-1].attempted is False


def test_item_cap_reports_accepted_before_cap_and_full_last_page_can_be_complete():
    result, _ = invoke(Transport(page(article("a"), article("b"))), request=replace(REQUEST, max_evidence_per_symbol=1))
    details = result.summary_for_symbol("IRON").diagnostics
    assert details["accepted_before_cap_count"] == 2 and details["retained_article_count"] == 1
    assert details["result_truncated"] is True and result.summary_for_symbol("IRON").retrieval_status == "partial"
    result, _ = invoke(Transport(page(article())), policy=replace(POLICY, metadata={"massive_page_size": 1}))
    assert result.summary_for_symbol("IRON").retrieval_status == "available"
    result, _ = invoke(Transport(page(article("a"), article("b"))), policy=replace(POLICY, metadata={"massive_page_size": 1}))
    assert result.summary_for_symbol("IRON").diagnostics["failure_reason"] == "response_limit_reached"
    assert len(result.evidence_for_symbol("IRON")) == 1


@pytest.mark.parametrize("payload", [{"status": "ERROR", "results": []}, {"results": None},
    {"status": "OK", "count": 3, "results": []}, ValueError("server echoed " + SECRET)])
def test_invalid_success_payload_is_not_completed_empty(payload):
    result, _ = invoke(Transport(Response(payload)))
    assert result.summary_for_symbol("IRON").retrieval_status == "unavailable"
    assert result.diagnostics.source_diagnostics[0].retrieval_status == "provider_error"
    assert SECRET not in json.dumps(asdict(result), default=str)


@pytest.mark.parametrize("status", [401, 403, 429, 302])
def test_auth_throttle_and_redirect_errors_are_safe(status):
    limiter = NoLimit()
    transport = Transport(Response({"error": SECRET}, status, headers={"Retry-After": "90", "Location": "https://evil.example/?apiKey="+SECRET}))
    result, cleanup = invoke(transport, [CANDIDATE], limiter=limiter)
    assert len(transport.calls) == 1 and result.summary_for_symbol("IRON").retrieval_status == "unavailable"
    assert SECRET not in json.dumps(asdict(result), default=str) + json.dumps(cleanup)
    if status == 429:
        assert limiter.cooldowns == [90] and result.summary_for_symbol("IRON").diagnostics["cooldown_persisted"] is True


def test_auth_failure_stops_remaining_symbols_but_server_failure_is_isolated():
    transport = Transport(Response(status=401))
    result, _ = invoke(transport, [CANDIDATE, NewsCandidate("MSFT")])
    assert len(transport.calls) == 1 and result.diagnostics.source_diagnostics[-1].attempted is False
    transport = Transport(Response(status=500), page())
    result, _ = invoke(transport, [CANDIDATE, NewsCandidate("MSFT")])
    assert result.summary_for_symbol("IRON").retrieval_status == "unavailable"
    assert result.summary_for_symbol("MSFT").retrieval_status == "available"


def test_missing_key_no_transport_threads_or_ledger_and_legacy_key_fallback(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY")
    def forbidden(*args, **kwargs):
        pytest.fail("missing credentials must stop before infrastructure")
    monkeypatch.setattr(adapter, "MassiveRateLimiter", forbidden)
    result, cleanup = invoke(forbidden)
    assert result.summary_for_symbol("IRON").provider_status == "missing_credential"
    assert cleanup["submitted_count"] == cleanup["worker_count"] == 0
    monkeypatch.setenv("POLYGON_API_KEY", SECRET)
    result, _ = invoke(Transport(page()))
    assert result.summary_for_symbol("IRON").retrieval_status == "available"


def test_secret_echo_fields_are_redacted_or_rejected():
    transport = Transport(page(article(SECRET, title="Disc Medicine " + SECRET, article_url="https://publisher.example/safe"),
                               article("url", article_url="https://publisher.example/"+SECRET),
                               article("query", article_url="https://publisher.example/a?apiKey=x")))
    result, _ = invoke(transport)
    serialized = json.dumps(asdict(result), default=str)
    assert SECRET not in serialized and "apiKey=" not in serialized
    assert result.evidence_for_symbol("IRON")[0].reference_id == "[REDACTED]"
    assert result.summary_for_symbol("IRON").diagnostics["rejected_article_counts"] == {"invalid_article_identity_or_url": 2}


def test_shared_ledger_restart_cooldown_and_failure_closed(tmp_path):
    clock = [1000.0]
    mono = [0.0]
    def sleep(seconds):
        clock[0] += seconds
        mono[0] += seconds
    def limiter():
        return MassiveRateLimiter(tmp_path/"quota.sqlite3", clock=lambda:clock[0], monotonic=lambda:mono[0], sleep=sleep)
    assert [limiter().acquire(1) for _ in range(5)] == [None]*5
    assert limiter().acquire(1) == "rate_limit_deadline"
    clock[0] += 60.002
    assert limiter().acquire(1) is None
    assert limiter().cooldown(90) is True
    assert limiter().acquire(1) == "rate_limit_deadline"
    assert SECRET not in (tmp_path/"quota.sqlite3").read_bytes().decode("latin1")
    bad = tmp_path/"bad.sqlite3"
    bad.write_text("not sqlite")
    assert MassiveRateLimiter(bad).acquire(time.monotonic()+1) == "rate_limiter_unavailable"


def test_shared_ledger_limits_two_independent_processes(tmp_path):
    code = "from src.news.massive_rate_limit import MassiveRateLimiter; import sys,time,json; r=MassiveRateLimiter(__import__('pathlib').Path(sys.argv[1])); print(json.dumps([r.acquire(time.monotonic()+0.5) for _ in range(3)]))"
    processes = [subprocess.Popen([sys.executable, "-c", code, str(tmp_path/"shared.sqlite3")], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = []
    try:
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == 0, stderr
            results += json.loads(stdout)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=3)
    assert results.count(None) == 5 and results.count("rate_limit_deadline") == 1


def test_late_http_completion_discarded_and_owned_cleanup_reported():
    released, begun = threading.Event(), threading.Event()
    response = page(article())
    def transport(*args, **kwargs):
        begun.set()
        assert released.wait(3)
        return response
    tracker = RssFetchLifecycle()
    provider = MassiveNewsIntelligenceProvider(lifecycle=tracker, transport=transport, limiter=NoLimit())
    try:
        result = provider.get_news([CANDIDATE], REQUEST, replace(POLICY, total_budget_seconds=0.08))
        assert begun.is_set() and result.diagnostics.budget_exhausted is True
        assert result.evidence_for_symbol("IRON") == ()
        assert tracker.wait_for_cleanup(0)["cleanup_complete"] is False
    finally:
        released.set()
    assert tracker.wait_for_cleanup(2)["cleanup_complete"] is True
    assert response.closed and result.evidence_for_symbol("IRON") == ()


def test_slow_response_close_preserves_in_time_evidence():
    released, closing = threading.Event(), threading.Event()
    def close():
        closing.set()
        assert released.wait(3)
    tracker = RssFetchLifecycle()
    provider = MassiveNewsIntelligenceProvider(lifecycle=tracker, transport=Transport(Response(page(article()).payload, closing=close)), limiter=NoLimit())
    try:
        result = provider.get_news([CANDIDATE], REQUEST, replace(POLICY, total_budget_seconds=0.3))
        assert closing.wait(1) and len(result.evidence_for_symbol("IRON")) == 1
        assert result.diagnostics.budget_exhausted is False
        assert tracker.snapshot()["cleanup_complete"] is False
    finally:
        released.set()
    assert tracker.wait_for_cleanup(2)["cleanup_complete"] is True


def test_slow_relevance_normalization_cannot_promote_late_evidence(monkeypatch):
    original = adapter.symbol_relevance_match
    def slow(*args, **kwargs):
        time.sleep(0.1)
        return original(*args, **kwargs)
    monkeypatch.setattr(adapter, "symbol_relevance_match", slow)
    result, _ = invoke(Transport(page(article())), policy=replace(POLICY, total_budget_seconds=0.05))
    assert result.diagnostics.budget_exhausted is True and result.evidence_for_symbol("IRON") == ()


def test_observed_timeout_and_close_failure_are_truthful():
    result, cleanup = invoke(Transport(requests.exceptions.ReadTimeout(SECRET)))
    assert result.diagnostics.timeout_count == 1
    assert result.diagnostics.source_diagnostics[0].failure_reason == "request_timeout"
    assert SECRET not in json.dumps(asdict(result), default=str)
    def failed_close():
        raise OSError(SECRET)
    tracker = RssFetchLifecycle()
    provider = MassiveNewsIntelligenceProvider(lifecycle=tracker, transport=Transport(Response(closing=failed_close)), limiter=NoLimit())
    result = provider.get_news([CANDIDATE], REQUEST, POLICY)
    cleanup = tracker.wait_for_cleanup(2)
    assert cleanup["cleanup_complete"] is False and cleanup["response_cleanup_failures_count"] == 1
    assert SECRET not in json.dumps(cleanup)


@pytest.mark.parametrize("failure", ["HTTP_401", "request_timeout"])
@pytest.mark.parametrize("completion", [1.0, 1.1])
def test_at_or_after_deadline_retains_observed_failure_and_timeout(monkeypatch, failure, completion):
    clock = [0.0]
    monkeypatch.setattr(adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    original_wait = adapter.wait
    # Model a coordinator observing an already completed failure, not a worker
    # still waiting for the callback-registration barrier at the fake deadline.
    monkeypatch.setattr(adapter, "wait", lambda futures, timeout: original_wait(futures, timeout=1))
    def transport(*args, **kwargs):
        clock[0] = completion
        if failure == "request_timeout":
            raise requests.exceptions.ReadTimeout(SECRET)
        return Response(status=401)
    result, _ = invoke(transport, policy=replace(POLICY, total_budget_seconds=1))
    row = result.diagnostics.source_diagnostics[0]
    assert row.budget_exhausted and row.worker_completed and row.failure_reason == failure
    assert result.diagnostics.timeout_count == int(failure == "request_timeout")
    assert result.diagnostics.budget_exhausted and result.evidence_for_symbol("IRON") == ()


def test_in_time_completion_late_coordinator_is_not_exhaustion(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    original = adapter.wait
    def late_wait(futures, timeout):
        result = original(futures, timeout=timeout)
        clock[0] = 2.0
        return result
    monkeypatch.setattr(adapter, "wait", late_wait)
    result, _ = invoke(Transport(page(article())), policy=replace(POLICY, total_budget_seconds=1))
    assert len(result.evidence_for_symbol("IRON")) == 1
    assert result.diagnostics.budget_exhausted is False
    assert result.summary_for_symbol("IRON").retrieval_status == "available"


def test_rate_deadline_never_calls_http():
    class Blocked(NoLimit):
        def acquire(self, deadline):
            return "rate_limit_deadline"
    transport = Transport()
    result, _ = invoke(transport, limiter=Blocked())
    assert not transport.calls and result.diagnostics.sources_attempted_count == 0
    assert result.diagnostics.budget_exhausted


def test_explicit_bearer_cannot_be_replaced_by_netrc(monkeypatch):
    monkeypatch.setattr(requests.sessions, "get_netrc_auth", lambda url: ("other-user", "other-secret"))
    transport = Transport(page())
    invoke(transport)
    url, kwargs = transport.calls[0]
    prepared = requests.Session().prepare_request(requests.Request("GET", url, headers=kwargs["headers"], auth=kwargs["auth"]))
    assert prepared.headers["Authorization"] == "Bearer " + SECRET


def test_future_query_window_rejected_before_transport():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    transport = Transport()
    provider = MassiveNewsIntelligenceProvider(transport=transport, limiter=NoLimit())
    with pytest.raises(ValueError, match="future"):
        provider.get_news([CANDIDATE], replace(REQUEST, query_start_utc=future-timedelta(hours=1), query_end_utc=future), POLICY)
    assert transport.calls == []


def test_candidate_aliases_only_and_metadata_aliases_are_both_retained():
    candidate = NewsCandidate("IRON", aliases=("Disc Medicine",), metadata={"aliases": ["Legacy Medicine"]})
    result, _ = invoke(Transport(page(article(), article("legacy", title="Legacy Medicine news"))), [candidate])
    assert {item.reference_id for item in result.evidence_for_symbol("IRON")} == {"a", "legacy"}


class OrderedCorpusTransport:
    """A cursor carries the initial sort; pages reflect the requested order."""
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __call__(self, url, **kwargs):
        from urllib.parse import parse_qs, urlsplit
        self.calls.append((url, kwargs))
        params = kwargs["params"]
        if params is not None:
            assert params["sort"] == "published_utc"
            order, offset, size = params["order"], 0, params["limit"]
        else:
            order, offset, size = parse_qs(urlsplit(url).query)["cursor"][0].split("_")
            offset, size = int(offset), int(size)
        rows = sorted(self.rows, key=lambda row: row["published_utc"], reverse=order == "desc")
        end = offset + size
        return page(*rows[offset:end], next_url=(ENDPOINT + f"?cursor={order}_{end}_{size}" if end < len(rows) else None))


def test_ordered_corpus_retains_newest_unique_articles_before_page_cap():
    rows = [article(str(n), published=NOW-timedelta(minutes=n)) for n in range(1, 8)]
    transport = OrderedCorpusTransport(rows)
    result, _ = invoke(transport, request=replace(REQUEST, max_evidence_per_symbol=2),
                       policy=replace(POLICY, metadata={"massive_page_size": 3}))
    assert [item.reference_id for item in result.evidence_for_symbol("IRON")] == ["1", "2"]
    assert len(transport.calls) == 1
    details = result.summary_for_symbol("IRON").diagnostics
    assert details["result_truncated"] is True
    assert details["failure_reason"] == "result_limit_reached"


@pytest.mark.parametrize("further_page", [False, True])
def test_ordered_corpus_duplicate_and_rejection_leave_room_and_exact_cap(further_page):
    newest = article("newest", published=NOW-timedelta(minutes=1))
    rows = [newest, dict(newest),
            article("rejected", title="Iron ore prices rise", published=NOW-timedelta(minutes=2)),
            article("second", published=NOW-timedelta(minutes=3))]
    if further_page:
        rows.append(article("older", published=NOW-timedelta(minutes=4)))
    transport = OrderedCorpusTransport(rows)
    result, _ = invoke(transport, request=replace(REQUEST, max_evidence_per_symbol=2),
                       policy=replace(POLICY, metadata={"massive_page_size": 2}))
    assert [item.reference_id for item in result.evidence_for_symbol("IRON")] == ["newest", "second"]
    assert len(transport.calls) == 2
    details = result.summary_for_symbol("IRON").diagnostics
    assert details["returned_article_count"] == 4
    assert details["accepted_article_count"] == 3
    assert details["duplicate_article_count"] == 1
    assert details["rejected_article_counts"] == {"issuer_relevance_rejected": 1}
    assert details["result_truncated"] is further_page
    assert details["complete"] is not further_page
    assert result.summary_for_symbol("IRON").retrieval_status == ("partial" if further_page else "available")
