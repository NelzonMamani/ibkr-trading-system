from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib
import json

import pytest

from src.config.config_resolver import set_config_overrides
from src.news.evidence_store import CanonicalNewsEvidenceStore, refresh_evidence_age
from src.news.news_intelligence_contract import NewsBatchResult, NewsCandidate, NewsEvidence, NewsRequest, RetrievalDiagnostics, RetrievalPolicy
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.prep_adapter import NewsProvider


@pytest.fixture(autouse=True)
def config(tmp_path):
    set_config_overrides({"NEWS_CACHE_FILE": str(tmp_path / "news.json"), "NEWS_ENABLED": True,
                          "NEWS_TOTAL_BUDGET_S": 8.0, "NEWS_MAX_AGE_HOURS": 6.0})
    yield
    set_config_overrides({})


def test_prep_uses_one_canonical_batch_and_preserves_missing_publication_time():
    class Service:
        provider_id = "canonical_news_intelligence"
        calls = []
        def get_news(self, candidates, request, policy):
            self.calls.append((candidates, request, policy))
            return NewsBatchResult(evidence_by_symbol={"EGG": (NewsEvidence(
                symbol="EGG", headline="EGG reports earnings", provider="rss_batch",
                fetched_at=datetime.now(timezone.utc), stale=None,
            ),)}, diagnostics=RetrievalDiagnostics(retrieval_status="partial"))
    service = Service()
    result = NewsProvider(service=service).get_news_batch([" egg ", "EGG", "LFCR", ""])
    assert list(result) == ["EGG", "LFCR"]
    assert len(service.calls) == 1
    _, request, policy = service.calls[0]
    assert request.freshness_seconds == 6 * 3600
    assert policy.total_budget_seconds == 8
    assert policy.source_groups == ("FAST_TRADING",)
    row = result["EGG"].news_context[0]
    assert row["published_at"] is None
    assert row["age_hours"] is None
    assert row["freshness"] == "unknown"
    assert row["catalyst_tag"] == "generic"
    assert result["LFCR"].diagnostics["retrieval"]["retrieval_status"] == "partial"


@pytest.mark.parametrize("origin", ["legacy", "prep", "canonical"])
def test_persisted_unrelated_news_cannot_suppress_refresh(tmp_path, origin):
    now = datetime.now(timezone.utc)
    item = {"title": "Malaysia launches AI research", "summary": "Visitors enjoy egg tarts.",
            "published_at": now.isoformat(), "catalyst_tag": "contract_order"}
    path = tmp_path / "cache.json"
    prep = {"symbols": []}
    payload = {}
    if origin == "legacy":
        payload = {"symbols": {"EGG": {"fetched_at": now.isoformat(), "news_context": [item]}}}
    elif origin == "prep":
        prep = {"symbols": [{"symbol": "EGG", "news_asof": now.isoformat(), "news_context": [item]}]}
    else:
        payload = {"news_intelligence": {"symbols": {"EGG": {"evidence": [{
            "symbol": "EGG", "headline": item["title"], "summary": item["summary"],
            "published_at": now.isoformat(), "provider": "rss_batch", "match_type": "ticker_token",
        }]}}}}
    path.write_text(json.dumps(payload))
    store = CanonicalNewsEvidenceStore(path, prep_artifact_loader=lambda: prep)
    class Retrieval:
        calls = []
        def get_news(self, candidates, request, policy):
            self.calls.append([c.symbol for c in candidates])
            return NewsBatchResult(diagnostics=RetrievalDiagnostics(retrieval_status="unavailable", provider_available=False))
    retrieval = Retrieval()
    service = CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=retrieval)
    result = service.get_news([NewsCandidate("EGG")], NewsRequest(), RetrievalPolicy())
    assert retrieval.calls == [["EGG"]]
    assert not result.evidence_by_symbol["EGG"]
    assert result.summary_for_symbol("EGG").fresh_evidence_count == 0


@pytest.mark.parametrize("origin", ["legacy", "prep"])
def test_legacy_relative_age_is_anchored_to_saved_acquisition(tmp_path, origin):
    old = datetime.now(timezone.utc) - timedelta(days=2)
    item = {"title": "EGG reports earnings", "age_hours": 1, "catalyst_tag": "earnings"}
    path = tmp_path / "cache.json"
    prep = {"symbols": []}
    if origin == "legacy":
        path.write_text(json.dumps({"symbols": {"EGG": {"fetched_at": old.isoformat(), "news_context": [item]}}}))
    else:
        prep = {"symbols": [{"symbol": "EGG", "news_asof": old.isoformat(), "news_context": [item]}]}
    store = CanonicalNewsEvidenceStore(path, prep_artifact_loader=lambda: prep)
    result = store.read([NewsCandidate("EGG")])
    evidence = result.evidence_by_symbol["EGG"][0]
    assert evidence.published_at == old - timedelta(hours=1)
    assert evidence.stale is True
    assert not result.diagnostics["cache_hit_symbols"]


def test_receipt_or_saved_age_cannot_substitute_for_publication():
    now = datetime.now(timezone.utc)
    evidence = NewsEvidence(symbol="EGG", fetched_at=now, first_seen_at=now, age_seconds=0, stale=False)
    for item in (evidence, replace(evidence, published_at=now + timedelta(hours=1))):
        refreshed = refresh_evidence_age(item, now=now)
        assert refreshed.age_seconds is None
        assert refreshed.stale is None


@pytest.mark.parametrize(("old", "new", "name"), [
    ("src.core.managers.market_data_snapshot_manager", "src.market_data.market_data_snapshot_manager", "MarketDataSnapshotManager"),
    ("src.scanner.reference_resolver", "src.market_data.reference_resolver", "CanonicalReferenceResolver"),
    ("src.scanner.session_pct_change", "src.market_data.session_pct_change", "compute_phase_aware_rvol"),
    ("src.data.fundamentals.float_provider", "src.market_data.float_provider", "FloatProvider"),
    ("src.data.news.news_provider", "src.news.prep_adapter", "NewsProvider"),
])
def test_compatibility_paths_share_the_same_authority(old, new, name):
    assert getattr(importlib.import_module(old), name) is getattr(importlib.import_module(new), name)


def test_rss_publication_time_is_utc_and_missing_time_does_not_become_now(monkeypatch):
    import calendar
    import time
    from types import SimpleNamespace
    from src.news import news_fetcher
    stamp = time.gmtime(1700000000)
    assert news_fetcher._entry_timestamp(SimpleNamespace(published_parsed=stamp)) == calendar.timegm(stamp)
    assert news_fetcher._entry_timestamp(SimpleNamespace()) is None
    entries = [SimpleNamespace(title="EGG reports earnings", link="https://example.test/earnings")]
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(news_fetcher, "_fetch_feed", lambda *_: SimpleNamespace(feed={}, entries=entries))
    rows, _ = news_fetcher.fetch_fast_headlines_for_symbols(["EGG"], ["https://example.test/rss"])
    assert rows["EGG"] == []


def test_prep_projection_roundtrip_retains_summary_issuer_evidence(tmp_path):
    now = datetime.now(timezone.utc)
    evidence = NewsEvidence(
        symbol="EGG", headline="Company wins contract", summary="$EGG announced the award",
        company_name="Example Egg Inc.", aliases=("Example Egg",), matched_field="summary",
        match_type="ticker_token", published_at=now, fetched_at=now, age_seconds=0,
        stale=False, provider="rss_batch",
    )
    class Service:
        provider_id = "canonical_news_intelligence"
        def get_news(self, *args):
            return NewsBatchResult(evidence_by_symbol={"EGG": (evidence,)}, completed_at=now)
    projected = NewsProvider(service=Service()).get_news("EGG")
    row = projected.news_context[0]
    assert row["summary"] == evidence.summary
    assert row["company_name"] == evidence.company_name
    assert row["aliases"] == list(evidence.aliases)
    prep = {"symbols": [{"symbol": "EGG", "news_asof": now.isoformat(), "news_context": [row]}]}
    store = CanonicalNewsEvidenceStore(tmp_path / "cache.json", prep_artifact_loader=lambda: prep)
    restored = store.read([NewsCandidate("EGG")]).evidence_by_symbol["EGG"]
    assert len(restored) == 1
    assert restored[0].summary == evidence.summary
    assert restored[0].company_name == evidence.company_name
    assert restored[0].aliases == evidence.aliases


def test_prep_copy_cannot_evict_distinct_offering_at_evidence_cap(tmp_path):
    now = datetime.now(timezone.utc)
    evidence = tuple(NewsEvidence(
        symbol="EGG", evidence_id=f"rss-batch:EGG:{index}",
        headline="EGG announces offering" if index == 4 else f"EGG wins contract {index}",
        published_at=now - timedelta(minutes=index), fetched_at=now,
        age_seconds=index * 60, stale=False, provider="rss_batch", match_type="ticker_token",
        observed_source="Example News", url=f"https://example.test/{index}",
    ) for index in range(5))
    class Service:
        provider_id = "canonical_news_intelligence"
        def get_news(self, *args):
            return NewsBatchResult(evidence_by_symbol={"EGG": evidence}, completed_at=now)
    projected = NewsProvider(service=Service()).get_news("EGG")
    prep = {"symbols": [{"symbol": "EGG", "news_asof": now.isoformat(), "news_context": projected.news_context}]}
    store = CanonicalNewsEvidenceStore(tmp_path / "cache.json", prep_artifact_loader=lambda: prep)
    store.write({"EGG": evidence}, NewsRequest(max_evidence_per_symbol=5))
    restored = store.read([NewsCandidate("EGG")], NewsRequest(max_evidence_per_symbol=5))
    rows = restored.evidence_by_symbol["EGG"]
    assert len(rows) == 5
    assert {row.evidence_id for row in rows} == {row.evidence_id for row in evidence}
    from src.scanner.scanner_runner import _ross_news_context_from_evidence
    context = _ross_news_context_from_evidence("EGG", rows, None, NewsBatchResult(candidates=(NewsCandidate("EGG"),)))
    assert context["dilution_flag"] is True
    assert context["ross_catalyst_valid"] is False


@pytest.mark.parametrize("outcome", ["article", "empty", "unavailable"])
def test_prep_refresh_cadence_survives_service_restart_independent_of_freshness(tmp_path, outcome):
    set_config_overrides({"NEWS_ENABLED": True, "NEWS_REFRESH_SECONDS_PREP": 1800,
                          "NEWS_MAX_AGE_HOURS": 6.0, "NEWS_TOTAL_BUDGET_S": 8.0})
    path = tmp_path / "cache.json"
    class Retrieval:
        calls = 0
        def get_news(self, candidates, request, policy):
            self.calls += 1
            now = datetime.now(timezone.utc)
            rows = (NewsEvidence(symbol="EGG", evidence_id="rss:1", headline="EGG reports earnings",
                                 published_at=now - timedelta(minutes=10), fetched_at=now,
                                 age_seconds=600, stale=False, provider="rss_batch"),) if outcome == "article" else ()
            return NewsBatchResult(evidence_by_symbol={"EGG": rows}, completed_at=now,
                diagnostics=RetrievalDiagnostics(retrieval_status="unavailable" if outcome == "unavailable" else "available",
                                                 provider_status="offline" if outcome == "unavailable" else "ok",
                                                 provider_available=outcome != "unavailable"))
    retrieval = Retrieval()
    def provider():
        store = CanonicalNewsEvidenceStore(path, prep_artifact_loader=lambda: {})
        return NewsProvider(service=CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=retrieval))
    provider().get_news("EGG")
    cached = provider().get_news("EGG")
    assert retrieval.calls == 1
    assert cached.diagnostics["summary"]["provider_available"] is (outcome != "unavailable")
    assert cached.diagnostics["summary"]["retrieval_status"] == ("unavailable" if outcome == "unavailable" else "available")
    if outcome == "article":
        assert cached.news_context[0]["freshness"] == "fresh"
    payload = json.loads(path.read_text())
    bucket = payload["news_intelligence"]["symbols"]["EGG"]
    bucket["last_retrieval"]["completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1801)).isoformat()
    path.write_text(json.dumps(payload))
    provider().get_news("EGG")
    assert retrieval.calls == 2


def test_explicit_refresh_still_overrides_acquisition_cadence(tmp_path):
    now = datetime.now(timezone.utc)
    store = CanonicalNewsEvidenceStore(tmp_path / "cache.json", prep_artifact_loader=lambda: {})
    store.write({"EGG": ()}, retrieval_by_symbol={"EGG": {"completed_at": now.isoformat(), "retrieval_status": "available"}})
    class Retrieval:
        calls = 0
        def get_news(self, *args):
            self.calls += 1
            return NewsBatchResult()
    retrieval = Retrieval()
    service = CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=retrieval)
    service.get_news([NewsCandidate("EGG")], NewsRequest(), RetrievalPolicy(
        refresh_interval_seconds=1800, metadata={"refresh_symbols": ["EGG"]}))
    assert retrieval.calls == 1
