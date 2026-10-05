"""Focused offline tests for ordinary RSS diagnostic facts."""
import json
from types import SimpleNamespace

import pytest

from src.news import news_fetcher
from src.news.news_intelligence_contract import NewsBatchResult, NewsCandidate, SourceDiagnostic, RetrievalDiagnostics
from src.news.retrieval_diagnostics import emit_retrieval_diagnostics


@pytest.mark.parametrize("feed,expected_count,status", [
    (SimpleNamespace(feed={}, entries=[]), 0, "available"),
    (SimpleNamespace(feed={}, entries=[{}, {}, {}]), 3, "available"),
    (None, None, "unavailable"),
    (SimpleNamespace(feed={}), None, "available"),
    (RuntimeError("private transport message"), None, "provider_error"),
])
def test_ordinary_completed_source_counts_parsed_not_matched(monkeypatch, feed, expected_count, status):
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    def fetched(*args):
        if isinstance(feed, Exception):
            raise feed
        return feed
    monkeypatch.setattr(news_fetcher, "_fetch_feed", fetched)
    rows, summary = news_fetcher.fetch_fast_headlines_for_symbols(["SYNX"], ["rss://offline"])
    source = summary.source_diagnostics[0]
    assert rows == {"SYNX": []}
    assert source["feed_item_count"] == expected_count
    assert source["matched_count"] == 0
    assert source["worker_completed"] is True
    assert source["retrieval_status"] == status
    assert source["http_status"] is None


def test_empty_result_retains_supplied_and_effective_identity_without_extra_metadata(capsys):
    result = NewsBatchResult(candidates=(NewsCandidate(" synx ", "Supplied Issuer Inc", ("Original Alias",),
        exchange="NASDAQ", metadata={"company_name": "Effective Issuer Limited", "aliases": ["Effective Alias"],
        "con_id": 123, "api_key": "SECRET", "account": "DU1234567"}), NewsCandidate("MISSING")))
    emit_retrieval_diagnostics(result, provider_invoked=True)
    raw = capsys.readouterr().out
    payload = json.loads(raw.split(" ", 1)[1])
    first, missing = payload["candidate_identities"]
    assert first["company_name"] == "Supplied Issuer Inc"
    assert first["aliases"] == ["Original Alias"]
    assert first["issuer_identifiers"] == {"con_id": "123"}
    assert first["effective_rss_matching_identity"] == {"symbol": "SYNX", "company_aliases": ["EFFECTIVE ISSUER", "EFFECTIVE ALIAS"]}
    assert missing["company_name"] is None
    assert missing["aliases"] == []
    assert missing["effective_rss_matching_identity"]["company_aliases"] == []
    assert "SECRET" not in raw and "DU1234567" not in raw


def test_source_measurements_survive_canonical_emission(capsys):
    source = SourceDiagnostic("rss://offline", feed_item_count=7, worker_completed=True,
        matched_count=0, http_status=200, request_elapsed_seconds=.2, parse_elapsed_seconds=.1,
        response_closed=True, elapsed_kind="worker_fetch_parse", budget_exhausted=True)
    emit_retrieval_diagnostics(NewsBatchResult(diagnostics=RetrievalDiagnostics(source_diagnostics=(source,))), provider_invoked=True)
    record = json.loads(capsys.readouterr().out.split(" ", 1)[1])["sources"][0]
    for key in ("feed_item_count", "worker_completed", "matched_count", "http_status", "request_elapsed_seconds", "parse_elapsed_seconds", "response_closed", "elapsed_kind", "budget_exhausted"):
        assert record[key] == getattr(source, key)


def test_capture_working_directory_isolates_all_reached_stores(monkeypatch, tmp_path):
    import sqlite3
    from src.config.config_resolver import set_config_overrides
    from src.market_data import float_discovery_worker as workers
    from src.market_data.float_provider import FloatProvider
    from src.market_data.reference_resolver import PersistentReferenceCache
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.prep.premarket_prep_artifact import write_canonical_premarket_prep_artifact
    from src.scanner import scanner_runner as scanner

    operational = tmp_path / "operational"
    relative_paths = ("data/reference/reference_cache.json", "data/reference/float_cache.json",
                      "data/news/news_cache.json", "data/prep/premarket_prep.json", "data/ibkr_system.db")
    sentinels = {}
    for relative in relative_paths:
        path = operational / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"operational sentinel - preserve exactly")
        sentinels[path] = path.read_bytes()
    capture = tmp_path / "capture"
    capture.mkdir()
    monkeypatch.chdir(capture)
    # Same cwd + absolute paths as the private wrapper, using canonical env resolution.
    for name, filename in (("SCANNER_FLOAT_CACHE_FILE", "float_cache.json"),
                           ("NEWS_CACHE_FILE", "news_cache.json"),
                           ("PERSISTENCE_SQLITE_PATH", "runtime.sqlite3")):
        monkeypatch.setenv(name, str(capture / filename))
    set_config_overrides({"RUN_MODE": "READ_ONLY"})
    monkeypatch.setattr(workers, "_WORKERS", {})
    monkeypatch.setattr(workers.FloatDiscoveryWorker, "ensure_started", lambda self: None)
    monkeypatch.setattr(FloatProvider, "provider_yahoo", lambda self, symbol: (123456, "OK"))
    monkeypatch.setattr(FloatProvider, "provider_finviz", lambda *args: pytest.fail("unexpected fallback"))
    try:
        reference = PersistentReferenceCache()
        reference.put(("SYNX",), {"reference_price": 5})
        assert reference.path.resolve() == capture / relative_paths[0]
        assert scanner._resolve_float_cache_path() == capture / "float_cache.json"
        worker = workers.get_float_discovery_worker(scanner._resolve_float_cache_path())
        worker.discover_now("SYNX")
        assert json.loads((capture / "float_cache.json").read_text())["SYNX"]
        with sqlite3.connect(capture / "runtime.sqlite3") as conn:
            assert conn.execute("select symbol from symbol_fundamentals").fetchall() == [("SYNX",)]
        store = CanonicalNewsEvidenceStore()
        assert store.cache_path == capture / "news_cache.json"
        assert store.write({"SYNX": ()})["cache_write_failed"] is False
        prep = write_canonical_premarket_prep_artifact({"watchlist": []})
        assert prep.resolve() == capture / relative_paths[3]
        for path in (reference.path, store.cache_path, prep, capture / "float_cache.json", capture / "runtime.sqlite3"):
            assert path.is_file()
        for path, before in sentinels.items():
            assert path.read_bytes() == before
    finally:
        set_config_overrides(None)


def test_ordinary_transport_fetches_and_parses_once(monkeypatch):
    calls = []
    class Response:
        text = "offline feed"
        def raise_for_status(self):
            pass
    def get(url, timeout):
        calls.append((url, timeout))
        return Response()
    def parse(text):
        assert text == "offline feed"
        calls.append("parsed")
        return SimpleNamespace(feed={}, entries=[{}, {}])
    monkeypatch.setattr(news_fetcher, "requests", SimpleNamespace(get=get))
    monkeypatch.setattr(news_fetcher, "feedparser", SimpleNamespace(parse=parse))
    _, summary = news_fetcher.fetch_fast_headlines_for_symbols(["SYNX"], ["https://offline.example/rss"])
    assert len(calls) == 2 and calls[1] == "parsed"
    assert summary.source_diagnostics[0]["feed_item_count"] == 2
    assert summary.source_diagnostics[0]["worker_completed"] is True
