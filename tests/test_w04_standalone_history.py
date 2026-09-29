"""Offline standalone historical integration; fixtures are not provider discoveries."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import socket

import pytest

from scripts import verify_news_discovery as command
from src.config.config_resolver import set_config_overrides
from src.news import evidence_store, news_intelligence_service, standalone_lookup
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import (
    NewsBatchResult, NewsCandidate, NewsEvidence, NewsEvidenceSummary,
    RetrievalDiagnostics, SourceDiagnostic,
)
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.standalone_lookup import LookupSettings, human_report, jsonable, lookup_news, research_contracts

NOW = datetime(2026, 9, 29, 20, tzinfo=timezone.utc)
START = NOW - timedelta(days=3)
END = NOW - timedelta(days=2)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("W04 standalone tests must remain offline")

    class Clock(datetime):
        current = NOW

        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(cls.current.timestamp(), tz=tz)

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    for module in (evidence_store, news_intelligence_service, standalone_lookup):
        monkeypatch.setattr(module, "datetime", Clock)
    set_config_overrides({"NEWS_ENABLED": True})
    yield Clock
    set_config_overrides({})


def settings(tmp_path, **changes):
    return replace(LookupSettings(provider="massive", cache_file=tmp_path / "history.json",
                                  published_after=START.isoformat(), published_before=END.isoformat()), **changes)


def test_research_selection_keeps_rss_default_and_uses_fixed_massive_contract(tmp_path):
    rss_request, rss_policy = research_contracts(LookupSettings())
    assert rss_request.query_start_utc is rss_request.query_end_utc is None
    assert rss_policy.source_groups == ("FAST_TRADING", "PREP_EXTENDED")
    assert rss_policy.provider_groups == ("rss_batch",)
    assert rss_policy.fallback_mode == "unresolved_only"
    selected = settings(tmp_path, published_after="2026-09-26T22:00:00+02:00",
                        published_before="2026-09-27T22:00:00+02:00")
    request, policy = research_contracts(selected)
    assert request.query_start_utc == START and request.query_end_utc == END
    assert request.query_start_utc.tzinfo is timezone.utc
    assert policy.source_groups == ("MASSIVE_TICKER_NEWS",)
    assert policy.provider_groups == ("massive_ticker_news",)
    assert policy.fallback_mode == "none"
    assert {key: value for key, value in policy.metadata.items() if key.startswith("massive_")} == {
        "massive_page_size": 100, "massive_max_pages_per_symbol": 2,
        "massive_max_requests": 5, "massive_requests_per_minute": 5,
    }
    rolling, _ = research_contracts(settings(tmp_path, published_after=None, published_before=None))
    assert rolling.query_start_utc is rolling.query_end_utc is None
    assert not any("key" in key.lower() for key in jsonable(selected))


@pytest.mark.parametrize("changes,reason", [
    ({"published_after": None}, "supplied together"),
    ({"published_before": None}, "supplied together"),
    ({"published_after": "2026-09-26T20:00:00"}, "explicit timezone"),
    ({"published_after": "invalid"}, "ISO 8601"),
    ({"published_after": END.isoformat()}, "earlier than"),
    ({"published_before": (NOW + timedelta(seconds=1)).isoformat()}, "must not be in the future"),
    ({"published_after": (END - timedelta(days=31)).isoformat()}, "at most 720 hours"),
    ({"provider": "rss"}, "require --provider massive"),
    ({"source_groups": ("FAST_TRADING",)}, "only MASSIVE_TICKER_NEWS"),
    ({"massive_page_size": 1001}, "massive_page_size"),
    ({"massive_max_pages_per_symbol": 11}, "massive_max_pages_per_symbol"),
    ({"massive_max_requests": 51}, "massive_max_requests"),
])
def test_invalid_history_fails_before_canonical_call(tmp_path, changes, reason):
    class NoService:
        def get_news(self, *args):
            pytest.fail("Invalid historical settings reached canonical service")

    with pytest.raises(ValueError, match=reason):
        lookup_news(["ACME"], settings(tmp_path, **changes), service=NoService())
    assert not (tmp_path / "history.json").exists()


class HistoricalProvider:
    provider_id = "massive_ticker_news"

    def __init__(self):
        self.calls = []

    def get_news(self, candidates, request, policy):
        self.calls.append((tuple(candidates), request, policy))
        evidence, summaries, all_rows = {}, {}, []
        for candidate in candidates:
            symbol = candidate.normalized_symbol
            rows = tuple(SourceDiagnostic(source_id=f"massive:{symbol}:page:{page}",
                provider=self.provider_id, source_group="MASSIVE_TICKER_NEWS",
                retrieval_status="available", attempted=True) for page in (1, 2))
            all_rows.extend(rows)
            details = {"source_diagnostics": [asdict(row) for row in rows], "returned_article_count": 2,
                       "accepted_article_count": 2, "rejected_article_count": 0, "rejection_reasons": {},
                       "query_start_utc": request.query_start_utc.isoformat(),
                       "query_end_utc": request.query_end_utc.isoformat()}
            evidence[symbol] = tuple(NewsEvidence(symbol=symbol, evidence_id=f"fixture:{symbol}:{name}",
                headline=f"{candidate.company_name} reports {name} product update",
                summary=f"{candidate.company_name} statement", company_name=candidate.company_name,
                match_type="company_name", matched_field="headline", provider=self.provider_id,
                published_at=standalone_lookup.datetime.fromtimestamp(boundary.timestamp(), tz=timezone.utc),
                fetched_at=standalone_lookup.datetime.now(timezone.utc), original_source="Synthetic publisher",
                url=f"https://example.test/{symbol}/{name}", raw={"provider_article_id": f"{symbol}:{name}",
                "provider_tickers": [symbol]}) for name, boundary in (("start", START), ("end", END)))
            summaries[symbol] = NewsEvidenceSummary(symbol=symbol, retrieval_status="available",
                provider_status="ok", provider_available=True, diagnostics=details)
        return NewsBatchResult(candidates=tuple(candidates), evidence_by_symbol=evidence,
            summaries_by_symbol=summaries, request=request, retrieval_policy=policy,
            diagnostics=RetrievalDiagnostics(retrieval_status="available", provider_status="ok",
                provider_available=True, source_groups_queried=("MASSIVE_TICKER_NEWS",),
                provider_groups_queried=(self.provider_id,), source_diagnostics=tuple(all_rows),
                sources_attempted_count=len(all_rows)), completed_at=standalone_lookup.datetime.now(timezone.utc))


def test_public_batch_history_preserves_real_age_page_coverage_and_cached_provenance(tmp_path, offline):
    provider = HistoricalProvider()
    selected = settings(tmp_path)
    candidates = (NewsCandidate("ACME", company_name="Acme Industries", aliases=("Acme Holdings",),
                                metadata={"identity_source": "synthetic"}),
                  NewsCandidate("BETA", company_name="Beta Systems"))

    def service():
        return CanonicalNewsIntelligenceService(
            evidence_store=CanonicalNewsEvidenceStore(selected.cache_file, prep_artifact_loader=lambda: {}),
            retrieval_provider=provider)

    cold = lookup_news(candidates, selected, service=service())
    assert provider.calls[0][0] == candidates
    assert len(provider.calls) == 1
    assert cold["provider"] == "massive"
    assert cold["research_results_are_trading_catalysts"] is False
    assert cold["request"]["query_start_utc"] == START.isoformat()
    for symbol in ("ACME", "BETA"):
        result = cold["symbols"][symbol]
        assert result["coverage_status"] == "complete"
        assert result["outcome"] == "matched"
        assert result["current_retrieval_article_count"] == 2
        assert [row["source_id"] for row in result["sources"]] == [f"massive:{symbol}:page:1", f"massive:{symbol}:page:2"]
        assert result["provider_details"]["returned_article_count"] == 2
        assert {item["published_at"] for item in result["articles"]} == {START.isoformat(), END.isoformat()}
        assert all(item["age_seconds"] >= 48 * 3600 for item in result["articles"])
        assert all(item["provider"] == "massive_ticker_news" for item in result["articles"])
    offline.current += timedelta(seconds=60)
    warm = lookup_news(candidates, selected, service=service())
    assert len(provider.calls) == 1
    for symbol in ("ACME", "BETA"):
        result = warm["symbols"][symbol]
        assert result["coverage_status"] == "complete"
        assert result["provenance"] == "cached_acquisition"
        assert result["current_retrieval_article_count"] == 0
        assert result["reused_article_count"] == 2
        assert result["provider_details"] == cold["symbols"][symbol]["provider_details"]
        assert all(row["origin"] == "cached_acquisition" for row in result["sources"])
        for previous, cached in zip(cold["symbols"][symbol]["articles"], result["articles"]):
            assert cached["evidence_id"] == previous["evidence_id"]
            assert cached["published_at"] == previous["published_at"]
            assert cached["age_seconds"] == previous["age_seconds"] + 60
            assert cached["acquisition_origin"] == "cache_or_prep"
    report = human_report(warm)
    assert "provider=massive" in report and "Publication window (inclusive UTC)" in report
    assert "Research evidence only" in report and "returned_article_count" in report


def test_cli_batch_history_retains_candidate_identity_and_utc_window(monkeypatch, tmp_path, capsys):
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps([{"symbol": "acme", "company_name": "Acme Industries", "aliases": ["Acme Holdings"],
                               "metadata": {"issuer_id": "offline"}}, {"symbol": "beta"}]), encoding="utf-8")
    calls = []

    def capture(candidates, selected):
        calls.append((candidates, selected))
        return {"ok": True, "settings": jsonable(selected)}, 0

    monkeypatch.setattr(command, "run_supervised", capture)
    assert command.main(["--provider", "massive", "--candidates-file", str(path),
        "--published-after", START.isoformat(), "--published-before", END.isoformat(),
        "--massive-page-size", "25", "--massive-max-pages-per-symbol", "3", "--massive-max-requests", "4",
        "--cache-file", str(tmp_path / "cache.json"), "--format", "json"]) == 0
    candidates, selected = calls[0]
    assert candidates[0].symbol == "ACME" and candidates[0].aliases == ("Acme Holdings",)
    assert candidates[0].metadata == {"issuer_id": "offline"}
    assert candidates[1].symbol == "BETA"
    assert selected.published_after == START and selected.published_before == END
    assert (selected.massive_page_size, selected.massive_max_pages_per_symbol, selected.massive_max_requests) == (25, 3, 4)
    assert json.loads(capsys.readouterr().out)["settings"]["source_groups"] == ["MASSIVE_TICKER_NEWS"]


@pytest.mark.parametrize("arguments", [
    ["--published-after", START.isoformat()],
    ["--source-groups", "FAST_TRADING"],
    ["--published-after", START.isoformat(), "--published-before", (NOW + timedelta(hours=1)).isoformat()],
])
def test_cli_rejects_invalid_history_before_worker(monkeypatch, arguments, capsys):
    monkeypatch.setattr(command, "run_supervised", lambda *args: pytest.fail("Invalid history reached worker"))
    with pytest.raises(SystemExit) as raised:
        command.main(["ACME", "--provider", "massive", *arguments])
    assert raised.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_massive_worker_exception_does_not_publish_request_credentials(monkeypatch, tmp_path, capsys):
    synthetic_secret = "fixture-private-header-do-not-publish"
    config_path, output_path = tmp_path / "request.json", tmp_path / "result.json"
    config_path.write_text(json.dumps({"candidates": [{"symbol": "ACME"}],
        "settings": jsonable(settings(tmp_path)), "result_file": str(output_path)}), encoding="utf-8")
    monkeypatch.setattr(command, "_source_identity", lambda: {"source_hashes": {}})

    def fail(*args, **kwargs):
        raise RuntimeError("Bearer " + synthetic_secret)

    monkeypatch.setattr(command, "lookup_news", fail)
    assert command._worker(config_path) == 1
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["ok"] is False
    assert result["error"] == "RuntimeError: historical news lookup failed"
    captured = capsys.readouterr()
    assert synthetic_secret not in output_path.read_text(encoding="utf-8") + captured.out + captured.err


@pytest.mark.parametrize("candidates", [["ACME"], [NewsCandidate("ACME", company_name="Acme Industries"), "BETA"]])
def test_public_massive_selection_without_key_is_unavailable_without_http_or_quota_state(monkeypatch, tmp_path, candidates):
    from src.news import massive_news_adapter

    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("Missing credential must not create quota state or attempt HTTP")

    monkeypatch.setattr(massive_news_adapter, "MassiveRateLimiter", forbidden)
    monkeypatch.setattr(massive_news_adapter.requests, "get", forbidden)
    result = lookup_news(candidates, settings(tmp_path, cache_mode="off"))
    assert result["ok"] is True
    assert result["provider"] == "massive"
    assert result["diagnostics"]["sources_attempted_count"] == 0
    assert result["queried_source_groups"] == []
    assert result["cleanup"]["cleanup_complete"] is True
    assert result["cleanup"]["unfinished_count"] == result["cleanup"]["alive_worker_count"] == 0
    assert not (tmp_path / "history.json").exists()
    for symbol, item in result["symbols"].items():
        assert item["articles"] == []
        assert item["outcome"] == "retrieval_unavailable"
        assert item["coverage_status"] == "unavailable"
        assert item["provider_status"] == "missing_credential"
        assert item["provider_details"]["failure_reason"] == "missing_credential"
        assert item["provider_details"]["pages_attempted"] == 0
        source, = item["sources"]
        assert source["source_id"] == f"massive:{symbol}:page:1"
        assert source["attempted"] is False and source["failure_reason"] == "missing_credential"
