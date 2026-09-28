"""Offline research acquisition compatibility; existing trading defaults stay intact."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import socket

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import evidence_store, news_intelligence_service, standalone_lookup
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import (
    NewsBatchResult, NewsCandidate, NewsEvidence, NewsRequest, RetrievalDiagnostics,
    RetrievalPolicy, SourceDiagnostic,
)
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.prep_adapter import NewsProvider
from src.news.standalone_lookup import LookupSettings, lookup_news


NOW = datetime(2026, 9, 28, 20, tzinfo=timezone.utc)
REQUEST = NewsRequest(lookback_seconds=86400, freshness_seconds=86400,
                      include_generic_news=True, max_evidence_per_symbol=10)
POLICY = RetrievalPolicy(source_groups=("FAST_TRADING",), total_budget_seconds=30,
                         request_timeout_seconds=5, fallback_mode="none", refresh_interval_seconds=1800,
                         metadata={"require_compatible_acquisition": True})
CANDIDATE = NewsCandidate("ACME", company_name="Acme Industries", aliases=("Acme Holdings",),
                          metadata={"issuer_name": "Acme Industries", "identity_source": "fixture"})


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("W03 cache contract must remain offline")

    class Clock(datetime):
        current = NOW

        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(cls.current.timestamp(), tz)

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(news_intelligence_service, "datetime", Clock)
    monkeypatch.setattr(evidence_store, "datetime", Clock)
    monkeypatch.setattr(standalone_lookup, "datetime", Clock)
    set_config_overrides({"NEWS_ENABLED": True})
    yield Clock
    set_config_overrides({})


class Provider:
    def __init__(self):
        self.calls = []

    def get_news(self, candidates, request, policy):
        self.calls.append((tuple(candidates), request, policy))
        return NewsBatchResult(evidence_by_symbol={item.normalized_symbol: () for item in candidates},
            diagnostics=RetrievalDiagnostics(
                retrieval_status="available", provider_status="ok", provider_available=True,
                source_groups_queried=("FAST_TRADING",), sources_queried=("https://example.test/feed",),
                source_diagnostics=(SourceDiagnostic("https://example.test/feed", retrieval_status="available",
                                                     attempted=True, elapsed_seconds=0.25),),
                sources_attempted_count=1, elapsed_seconds=0.25,
                diagnostics={"cleanup_complete": True, "request_elapsed_seconds": 0.2}),
            started_at=NOW - timedelta(seconds=0.25), completed_at=NOW)


def service(path, provider):
    return CanonicalNewsIntelligenceService(
        evidence_store=CanonicalNewsEvidenceStore(path, prep_artifact_loader=lambda: {}),
        retrieval_provider=provider)


def test_research_acquisition_profile_and_coverage_survive_cold_warm_restart(tmp_path):
    provider = Provider()
    path = tmp_path / "news.json"
    current = service(path, provider)
    results = [reader.get_news([CANDIDATE], REQUEST, POLICY)
               for reader in (current, current, service(path, provider))]
    assert len(provider.calls) == 1
    records = [result.summary_for_symbol("ACME").diagnostics["last_retrieval"] for result in results]
    assert records[0] == records[1] == records[2]
    profile = records[0]["acquisition_profile"]
    assert profile["schema"] == "news.acquisition_profile.v1"
    assert len(profile["fingerprint"]) == 64
    assert profile["issuer"]["company_name"] == CANDIDATE.company_name
    assert profile["issuer"]["metadata"] == CANDIDATE.metadata
    assert profile["retrieval"]["source_urls_by_group"]["FAST_TRADING"]
    coverage = records[0]["coverage"]
    assert coverage["source_diagnostics"][0]["elapsed_seconds"] == 0.25
    assert coverage["sources_attempted_count"] == 1
    assert coverage["diagnostics"]["cleanup_complete"] is True
    assert records[0]["completed_at"] == NOW.isoformat()
    assert results[1].diagnostics.diagnostics["acquisition_profile_compatible_by_symbol"] == {"ACME": True}
    assert results[1].diagnostics.diagnostics["acquisition_coverage_unknown_symbols"] == []
    assert results[1].diagnostics.sources_attempted_count == 0  # Historical snapshot is separate from this call.
    assert json.loads(path.read_text())["news_intelligence"]["symbols"]["ACME"]["last_retrieval"] == records[0]


@pytest.mark.parametrize("change", ["lookback", "freshness", "cap", "events", "sources", "timeout", "budget", "fallback", "identity"])
def test_changed_research_settings_refresh_within_cadence(tmp_path, change):
    provider = Provider()
    path = tmp_path / "news.json"
    current = service(path, provider)
    current.get_news([CANDIDATE], REQUEST, POLICY)
    request, policy, candidate = REQUEST, POLICY, CANDIDATE
    if change == "lookback": request = replace(request, lookback_seconds=172800)
    if change == "freshness": request = replace(request, freshness_seconds=43200)
    if change == "cap": request = replace(request, max_evidence_per_symbol=20)
    if change == "events": request = replace(request, event_classes=("earnings",))
    if change == "sources": policy = replace(policy, source_groups=("FAST_TRADING", "PREP_EXTENDED"))
    if change == "timeout": policy = replace(policy, request_timeout_seconds=10)
    if change == "budget": policy = replace(policy, total_budget_seconds=40)
    if change == "fallback": policy = replace(policy, fallback_mode="unresolved_only")
    if change == "identity": candidate = replace(candidate, aliases=("Acme New Identity",))
    result = service(path, provider).get_news([candidate], request, policy)
    assert len(provider.calls) == 2
    assert result.diagnostics.diagnostics["acquisition_profile_mismatch_symbols"] == ["ACME"]
    assert result.diagnostics.diagnostics["acquisition_coverage_unknown_symbols"] == []
    service(path, provider).get_news([candidate], request, policy)
    assert len(provider.calls) == 2


@pytest.mark.parametrize("legacy", [False, True])
def test_cache_only_incompatible_acquisition_is_unknown_not_completed_empty(tmp_path, legacy):
    provider = Provider()
    path = tmp_path / "news.json"
    current = service(path, provider)
    current.get_news([CANDIDATE], REQUEST, POLICY)
    if legacy:
        payload = json.loads(path.read_text())
        payload["news_intelligence"]["symbols"]["ACME"]["last_retrieval"].pop("acquisition_profile", None)
        path.write_text(json.dumps(payload))
    requested = REQUEST if legacy else replace(REQUEST, lookback_seconds=172800)
    result = current.get_news([CANDIDATE], requested, replace(POLICY, network_allowed=False, refresh_mode="cache_only"))
    assert len(provider.calls) == 1
    assert result.diagnostics.diagnostics["acquisition_profile_mismatch_symbols"] == ["ACME"]
    assert result.diagnostics.diagnostics["acquisition_coverage_unknown_symbols"] == ["ACME"]
    summary = result.summary_for_symbol("ACME")
    assert summary.retrieval_status == "unknown"
    assert summary.provider_status == "coverage_unknown"
    assert summary.provider_available is None
    assert summary.diagnostics["objective_news_status"] == "coverage_unknown"
    assert result.diagnostics.retrieval_status == "unknown"


@pytest.mark.parametrize("scoped", [False, True])
def test_force_refresh_overrides_cadence_and_respects_explicit_scope(tmp_path, scoped):
    provider = Provider()
    current = service(tmp_path / "news.json", provider)
    candidates = [CANDIDATE, NewsCandidate("SECOND")]
    current.get_news(candidates, REQUEST, POLICY)
    metadata = dict(POLICY.metadata)
    if scoped: metadata["refresh_symbols"] = ["ACME"]
    current.get_news(candidates, REQUEST, replace(POLICY, refresh_mode="force_refresh", metadata=metadata))
    assert len(provider.calls) == 2
    assert [item.normalized_symbol for item in provider.calls[-1][0]] == (["ACME"] if scoped else ["ACME", "SECOND"])


def test_research_unknown_profile_does_not_suppress_refresh_without_cadence(tmp_path):
    provider = Provider()
    path = tmp_path / "news.json"
    store = CanonicalNewsEvidenceStore(path, prep_artifact_loader=lambda: {})
    now = news_intelligence_service.datetime.now(timezone.utc)
    written = store.write({"ACME": (NewsEvidence(symbol="ACME", headline="ACME reports earnings", provider="rss_batch",
                                                published_at=now - timedelta(minutes=5), fetched_at=now, stale=False),)}, REQUEST)
    assert written["cache_write_failed"] is False
    result = service(path, provider).get_news([CANDIDATE], REQUEST, replace(POLICY, refresh_interval_seconds=None))
    assert len(provider.calls) == 1
    assert result.diagnostics.diagnostics["acquisition_profile_mismatch_symbols"] == ["ACME"]


def test_prep_accepts_existing_candidates_without_losing_identity_or_string_compatibility():
    provider = Provider()
    provider.provider_id = "fixture"
    prep = NewsProvider(service=provider)
    result = prep.get_news_batch([" acme ", CANDIDATE, "SECOND", ""])
    assert list(result) == ["ACME", "SECOND"]
    assert provider.calls[0][0][0] is CANDIDATE
    assert provider.calls[0][0][1] == NewsCandidate("SECOND")
    assert prep.get_news(CANDIDATE).symbol == "ACME"
    assert provider.calls[1][0] == (CANDIDATE,)


def test_matching_cache_only_without_cadence_retains_acquisition_outcome(tmp_path):
    provider = Provider()
    path = tmp_path / "news.json"
    service(path, provider).get_news([CANDIDATE], REQUEST, POLICY)
    result = service(path, provider).get_news([CANDIDATE], REQUEST, replace(
        POLICY, refresh_interval_seconds=None, network_allowed=False, refresh_mode="cache_only"))
    assert len(provider.calls) == 1
    assert result.summary_for_symbol("ACME").retrieval_status == "available"
    assert result.diagnostics.provider_available is True
    assert result.diagnostics.retrieval_status == "available"
    assert result.diagnostics.cache_state == "hit"
    assert result.diagnostics.diagnostics["acquisition_cache_hit_symbols"] == ["ACME"]
    assert result.diagnostics.diagnostics["cadence_cache_hit_symbols"] == []


def test_acquisition_record_is_returned_when_cache_writes_are_disabled(tmp_path):
    provider = Provider()
    path = tmp_path / "news.json"
    result = service(path, provider).get_news([CANDIDATE], REQUEST, replace(POLICY, allow_cache_write=False))
    assert not path.exists()
    assert result.diagnostics.diagnostics["acquisition_coverage_unknown_symbols"] == []
    assert result.summary_for_symbol("ACME").diagnostics["last_retrieval"]["coverage"]["sources_attempted_count"] == 1


def test_scoped_refresh_leaves_incompatible_unrequested_peer_unknown(tmp_path):
    provider = Provider()
    current = service(tmp_path / "news.json", provider)
    candidates = [CANDIDATE, NewsCandidate("SECOND")]
    current.get_news(candidates, REQUEST, POLICY)
    result = current.get_news(candidates, replace(REQUEST, lookback_seconds=172800), replace(
        POLICY, refresh_mode="force_refresh", metadata={**POLICY.metadata, "refresh_symbols": ["ACME"]}))
    assert [row.normalized_symbol for row in provider.calls[-1][0]] == ["ACME"]
    assert result.summary_for_symbol("ACME").retrieval_status == "available"
    assert result.summary_for_symbol("SECOND").retrieval_status == "unknown"
    assert result.diagnostics.diagnostics["acquisition_coverage_unknown_symbols"] == ["SECOND"]
    assert result.diagnostics.retrieval_status == "partial"


def test_ordered_source_membership_changes_invalidate_research_acquisition(tmp_path, monkeypatch):
    provider = Provider()
    current = service(tmp_path / "news.json", provider)
    current.get_news([CANDIDATE], REQUEST, POLICY)
    original_urls = news_intelligence_service.get_source_group_urls
    monkeypatch.setattr(news_intelligence_service, "get_source_group_urls", lambda group: tuple(reversed(original_urls(group))))
    current.get_news([CANDIDATE], REQUEST, POLICY)
    assert len(provider.calls) == 2


def test_current_retrieval_ids_distinguish_reused_article_after_empty_refresh(tmp_path):
    class ArticleProvider(Provider):
        def get_news(self, candidates, request, policy):
            result = super().get_news(candidates, request, policy)
            if len(self.calls) == 1:
                now = news_intelligence_service.datetime.now(timezone.utc)
                return replace(result, evidence_by_symbol={"ACME": (NewsEvidence(
                    symbol="ACME", evidence_id="rss:original", headline="Acme Industries reports earnings",
                    company_name="Acme Industries", provider="rss_batch", match_type="company_name",
                    published_at=now - timedelta(hours=18), fetched_at=now, stale=False,
                ),)})
            return result

    provider = ArticleProvider()
    current = service(tmp_path / "news.json", provider)
    cold = current.get_news([CANDIDATE], REQUEST, POLICY)
    assert cold.diagnostics.diagnostics["cache_write_failed"] is False
    assert cold.diagnostics.diagnostics["retrieved_evidence_ids_by_symbol"] == {"ACME": ["rss:original"]}
    warm = current.get_news([CANDIDATE], REQUEST, POLICY)
    assert warm.diagnostics.diagnostics["retrieved_evidence_ids_by_symbol"] == {"ACME": []}
    refreshed = current.get_news([CANDIDATE], REQUEST, replace(POLICY, refresh_mode="force_refresh"))
    assert len(provider.calls) == 2
    assert [item.evidence_id for item in refreshed.evidence_for_symbol("ACME")] == ["rss:original"]
    assert refreshed.diagnostics.diagnostics["retrieved_evidence_ids_by_symbol"] == {"ACME": []}


@pytest.mark.parametrize("has_article", [False, True], ids=["empty", "retained_article"])
def test_expired_compatible_cache_only_lookup_has_unknown_coverage(tmp_path, monkeypatch, offline, has_article):
    class ArticleProvider(Provider):
        def get_news(self, candidates, request, policy):
            result = super().get_news(candidates, request, policy)
            if has_article:
                now = news_intelligence_service.datetime.now(timezone.utc)
                return replace(result, evidence_by_symbol={"ACME": (NewsEvidence(
                    symbol="ACME", evidence_id="rss:original", headline="Acme Industries reports earnings",
                    company_name="Acme Industries", provider="rss_batch", match_type="company_name",
                    published_at=now - timedelta(minutes=5), fetched_at=now, stale=False,
                ),)})
            return result

    for module in (news_intelligence_service, standalone_lookup):
        monkeypatch.setattr(module, "get_source_group_urls", lambda group: ("https://example.test/feed",))
    provider = ArticleProvider()
    settings = LookupSettings(cache_file=tmp_path / "news.json", source_groups=("FAST_TRADING",),
                              refresh_interval_seconds=1800)
    current = service(settings.cache_file, provider)
    cold = lookup_news([CANDIDATE], settings, service=current)
    assert cold["symbols"]["ACME"]["coverage_status"] == "complete"
    assert cold["symbols"]["ACME"]["outcome"] == ("matched" if has_article else "completed_no_match")
    historical = cold["diagnostics"]["diagnostics"]["last_retrieval_by_symbol"]["ACME"]
    saved = settings.cache_file.read_bytes()

    offline.current = NOW + timedelta(seconds=1801)
    for reader in (current, service(settings.cache_file, provider)):
        result = lookup_news([CANDIDATE], replace(settings, cache_mode="only"), service=reader)
        symbol = result["symbols"]["ACME"]
        details = result["diagnostics"]["diagnostics"]
        assert symbol["cache_profile_compatible"] is True
        assert symbol["coverage_status"] == "unknown"
        assert symbol["outcome"] == ("matched" if has_article else "coverage_unknown")
        assert symbol["retrieval_status"] == "unknown"
        assert symbol["provider_status"] == "coverage_unknown"
        assert symbol["provider_available"] is None
        assert details["acquisition_profile_mismatch_symbols"] == []
        assert details["acquisition_coverage_unknown_symbols"] == ["ACME"]
        assert details["acquisition_cache_hit_symbols"] == []
        assert details["last_retrieval_by_symbol"]["ACME"] == historical
        assert result["diagnostics"]["sources_attempted_count"] == 0
        assert result["diagnostics"]["retrieval_status"] == "unknown"
        assert [item["evidence_id"] for item in symbol["articles"]] == (["rss:original"] if has_article else [])
        if has_article:
            assert symbol["articles"][0]["published_at"] == cold["symbols"]["ACME"]["articles"][0]["published_at"]
            assert symbol["articles"][0]["acquisition_origin"] == "cache_or_prep"
        assert settings.cache_file.read_bytes() == saved
    assert len(provider.calls) == 1


@pytest.mark.parametrize("scoped_refresh", [False, True], ids=["cache_only", "scoped_peer_refresh"])
def test_expired_acquisition_does_not_hide_behind_fresh_or_refreshed_peer(tmp_path, offline, scoped_refresh):
    class TimedProvider(Provider):
        def get_news(self, candidates, request, policy):
            return replace(super().get_news(candidates, request, policy),
                           completed_at=news_intelligence_service.datetime.now(timezone.utc))

    provider = TimedProvider()
    current = service(tmp_path / "news.json", provider)
    cold = current.get_news([CANDIDATE], REQUEST, POLICY)
    historical = cold.summary_for_symbol("ACME").diagnostics["last_retrieval"]
    offline.current = NOW + timedelta(seconds=900)
    peer = NewsCandidate("SECOND")
    current.get_news([peer], REQUEST, POLICY)
    offline.current = NOW + timedelta(seconds=1801)
    policy = (replace(POLICY, refresh_mode="force_refresh",
                      metadata={**POLICY.metadata, "refresh_symbols": ["SECOND"]}) if scoped_refresh
              else replace(POLICY, network_allowed=False, refresh_mode="cache_only"))
    result = current.get_news([CANDIDATE, peer], REQUEST, policy)
    details = result.diagnostics.diagnostics
    assert details["acquisition_profile_compatible_by_symbol"] == {"ACME": True, "SECOND": True}
    assert details["acquisition_coverage_unknown_symbols"] == ["ACME"]
    assert details["acquisition_cache_hit_symbols"] == ([] if scoped_refresh else ["SECOND"])
    assert result.summary_for_symbol("ACME").retrieval_status == "unknown"
    assert result.summary_for_symbol("ACME").diagnostics["last_retrieval"] == historical
    assert result.summary_for_symbol("SECOND").retrieval_status == "available"
    assert result.diagnostics.retrieval_status == "partial"
    assert len(provider.calls) == (3 if scoped_refresh else 2)
