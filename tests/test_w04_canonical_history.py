"""Synthetic offline history fixtures; no provider discovery or trading claim."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import socket

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import evidence_store, news_intelligence_service
from src.news.evidence_store import CanonicalNewsEvidenceStore, evidence_in_query_window
from src.news.issuer_relevance import evidence_issuer_relevance_verified
from src.news.news_intelligence_contract import (
    NewsBatchResult, NewsCandidate, NewsEvidence, NewsEvidenceSummary, NewsRequest,
    RetrievalDiagnostics, RetrievalPolicy,
)
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService, _acquisition_profile


NOW = datetime(2026, 9, 29, 20, tzinfo=timezone.utc)
START = NOW - timedelta(days=3)
END = NOW - timedelta(days=2)
CANDIDATE = NewsCandidate("ACME", company_name="Acme Industries", aliases=("Acme Holdings",))
REQUEST = NewsRequest(lookback_seconds=86400, freshness_seconds=86400, max_evidence_per_symbol=2,
                      query_start_utc=START, query_end_utc=END)
POLICY = RetrievalPolicy(source_groups=("MASSIVE_TICKER_NEWS",), provider_groups=("massive_ticker_news",),
                         total_budget_seconds=30, request_timeout_seconds=5, refresh_interval_seconds=1800,
                         metadata={"require_compatible_acquisition": True})


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("W04 canonical history must remain offline")

    class Clock(datetime):
        current = NOW

        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(cls.current.timestamp(), tz=tz)

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    for module in (evidence_store, news_intelligence_service):
        monkeypatch.setattr(module, "datetime", Clock)
    set_config_overrides({"NEWS_ENABLED": True})
    yield Clock
    set_config_overrides({})


def article(published_at, *, evidence_id="massive:fixture", symbol="ACME", **changes):
    # Datetimes come from the frozen clock class to exercise real store serialization.
    published = (news_intelligence_service.datetime.fromtimestamp(published_at.timestamp(), tz=timezone.utc)
                 if published_at is not None else None)
    return NewsEvidence(symbol=symbol, evidence_id=evidence_id, headline=f"{symbol} issuer announces product update",
                        summary="Acme Industries product update", company_name="Acme Industries",
                        provider="massive_ticker_news", match_type="company_name",
                        published_at=published, fetched_at=news_intelligence_service.datetime.now(timezone.utc),
                        original_source="Fixture Publisher", url=f"https://example.test/{evidence_id}",
                        raw={"provider_article_id": evidence_id, "provider_tickers": [symbol]}, **changes)


class Provider:
    provider_id = "massive_ticker_news"

    def __init__(self, evidence=(), details=None):
        self.calls = []
        self.evidence = evidence
        self.details = details or {"source_diagnostics": [{"source_id": "massive:ACME:page1"}],
                                   "returned_article_count": 1, "accepted_article_count": 1,
                                   "rejected_article_count": 0, "rejection_reasons": {}}

    def get_news(self, candidates, request, policy):
        self.calls.append((tuple(candidates), request, policy))
        return NewsBatchResult(candidates=tuple(candidates),
            evidence_by_symbol={item.normalized_symbol: self.evidence for item in candidates},
            summaries_by_symbol={item.normalized_symbol: NewsEvidenceSummary(
                symbol=item.normalized_symbol, retrieval_status="available", provider_status="ok",
                provider_available=True, diagnostics=self.details) for item in candidates},
            diagnostics=RetrievalDiagnostics(retrieval_status="available", provider_status="ok", provider_available=True),
            completed_at=news_intelligence_service.datetime.now(timezone.utc))


def service(path, provider):
    return CanonicalNewsIntelligenceService(
        evidence_store=CanonicalNewsEvidenceStore(path, prep_artifact_loader=lambda: {}), retrieval_provider=provider)


@pytest.mark.parametrize("start,end", [(START, None), (None, END), (START.replace(tzinfo=None), END), (END, START)])
def test_explicit_window_requires_ordered_aware_pair(start, end):
    with pytest.raises(ValueError):
        NewsRequest(query_start_utc=start, query_end_utc=end)


def test_explicit_window_normalizes_offsets_and_uses_inclusive_original_publication():
    offset = timezone(timedelta(hours=2))
    request = replace(REQUEST, query_start_utc=START.astimezone(offset), query_end_utc=END.astimezone(offset))
    assert request.query_start_utc == START and request.query_start_utc.tzinfo is timezone.utc
    assert request.query_end_utc == END and request.query_end_utc.tzinfo is timezone.utc
    assert evidence_in_query_window(article(START), request, now=NOW)
    assert evidence_in_query_window(article(END), request, now=NOW)
    assert not evidence_in_query_window(article(START - timedelta(microseconds=1)), request, now=NOW)
    assert not evidence_in_query_window(article(END + timedelta(microseconds=1)), request, now=NOW)
    assert not evidence_in_query_window(article(None), request, now=NOW)
    future_window = replace(request, query_end_utc=NOW + timedelta(hours=1))
    assert not evidence_in_query_window(article(NOW + timedelta(minutes=1)), future_window, now=NOW)


def test_historical_filter_precedes_store_and_service_caps_without_resetting_age(tmp_path, offline):
    path = tmp_path / "canonical.json"
    store = CanonicalNewsEvidenceStore(path, prep_artifact_loader=lambda: {})
    written = store.write({"ACME": (article(NOW - timedelta(minutes=1), evidence_id="newer"),)},
                          NewsRequest(max_evidence_per_symbol=1))
    assert written["cache_write_failed"] is False
    expected = article(START + timedelta(hours=1), evidence_id="historical")
    provider = Provider((expected,))
    request = replace(REQUEST, max_evidence_per_symbol=1)
    current = service(path, provider)
    cold = current.get_news([CANDIDATE], request, POLICY)
    assert cold.diagnostics.diagnostics["cache_write_failed"] is False
    historical = cold.summary_for_symbol("ACME").diagnostics["last_retrieval"]
    assert historical["completed_at"] == NOW.isoformat()
    assert historical["provider_details"] == provider.details
    offline.current = NOW + timedelta(minutes=10)
    for reader in (current, service(path, provider)):
        result = reader.get_news([CANDIDATE], request, POLICY)
        item, = result.evidence_for_symbol("ACME")
        assert item.evidence_id == "historical"
        assert item.published_at == expected.published_at
        assert item.fetched_at == NOW
        assert item.age_seconds == (offline.current - expected.published_at).total_seconds()
        assert item.stale is True
        assert item.raw == expected.raw
        assert result.summary_for_symbol("ACME").diagnostics["last_retrieval"] == historical
        assert result.summary_for_symbol("ACME").diagnostics["provider_details"] == provider.details
        assert result.diagnostics.diagnostics["acquisition_profile_compatible_by_symbol"] == {"ACME": True}
        assert result.diagnostics.diagnostics["acquisition_coverage_unknown_symbols"] == []
    assert len(provider.calls) == 1
    saved = json.loads(path.read_text())["news_intelligence"]["symbols"]["ACME"]
    assert [row["evidence_id"] for row in saved["evidence"]] == ["historical"]


def test_store_read_filters_before_cap_with_both_boundary_articles(tmp_path):
    store = CanonicalNewsEvidenceStore(tmp_path / "canonical.json", prep_artifact_loader=lambda: {})
    rows = (article(START, evidence_id="start"), article(END, evidence_id="end"),
            article(NOW - timedelta(minutes=1), evidence_id="newer"), article(None, evidence_id="undated"))
    store.write({"ACME": rows}, NewsRequest(max_evidence_per_symbol=10))
    read = store.read([CANDIDATE], REQUEST)
    assert [row.evidence_id for row in read.evidence_by_symbol["ACME"]] == ["end", "start"]
    assert read.diagnostics["query_window_rejected_by_symbol"] == {"ACME": 2}
    assert read.diagnostics.get("issuer_relevance_rejected_by_symbol", {}) == {}


@pytest.mark.parametrize("change", ["provider", "window", "page_size", "pages", "requests"])
def test_provider_and_historical_settings_invalidate_acquisition_profile(tmp_path, change):
    provider = Provider()
    path = tmp_path / "canonical.json"
    current = service(path, provider)
    current.get_news([CANDIDATE], REQUEST, POLICY)
    request, policy = REQUEST, POLICY
    if change == "provider":
        provider.provider_id = "rss_batch"
    elif change == "window":
        request = replace(request, query_start_utc=START - timedelta(hours=1))
    else:
        key, value = {"page_size": ("massive_page_size", 50), "pages": ("massive_max_pages_per_symbol", 1),
                      "requests": ("massive_max_requests", 3)}[change]
        policy = replace(policy, metadata={**policy.metadata, key: value})
    unknown = current.get_news([CANDIDATE], request, replace(policy, refresh_mode="cache_only", network_allowed=False))
    assert unknown.summary_for_symbol("ACME").retrieval_status == "unknown"
    assert unknown.diagnostics.diagnostics["acquisition_profile_mismatch_symbols"] == ["ACME"]
    assert len(provider.calls) == 1
    current.get_news([CANDIDATE], request, policy)
    assert len(provider.calls) == 2
    current.get_news([CANDIDATE], request, policy)
    assert len(provider.calls) == 2


def test_profile_records_only_provider_setting_whitelist_and_retains_rss_shape():
    policy = replace(POLICY, metadata={**POLICY.metadata, "api_key": "must-not-persist", "limiter_path": "private"})
    profile = _acquisition_profile(CANDIDATE, REQUEST, policy, provider_id="massive_ticker_news")
    assert profile["retrieval"]["provider_id"] == "massive_ticker_news"
    assert profile["retrieval"]["source_groups"] == ["MASSIVE_TICKER_NEWS"]
    assert profile["retrieval"]["provider_settings"] == {
        "massive_page_size": 100, "massive_max_pages_per_symbol": 2,
        "massive_max_requests": 5, "massive_requests_per_minute": 5,
        "publication_order": "published_utc_desc_v1",
    }
    assert profile["request"]["query_start_utc"] == START.isoformat()
    assert "must-not-persist" not in json.dumps(profile)
    assert "limiter_path" not in json.dumps(profile)
    rss = _acquisition_profile(CANDIDATE, NewsRequest(), RetrievalPolicy())
    assert "provider_id" not in rss["retrieval"]
    assert "provider_settings" not in rss["retrieval"]
    assert "query_start_utc" not in rss["request"]


@pytest.mark.parametrize("candidate,headline", [
    (NewsCandidate("EGG"), "Visitors enjoy egg tarts"),
    (NewsCandidate("MSFT", company_name="Microsoft Corporation", aliases=("Microsoft",)),
     "Microsoft releases a product update"),
])
def test_provider_ticker_association_does_not_bypass_persisted_text_relevance(tmp_path, candidate, headline):
    item = replace(article(START, symbol=candidate.symbol), headline=headline, summary="Unrelated market story",
                   company_name=None, match_type="provider_ticker_association")
    assert not evidence_issuer_relevance_verified(candidate.symbol, item, NewsBatchResult(candidates=(candidate,)))
    store = CanonicalNewsEvidenceStore(tmp_path / "canonical.json", prep_artifact_loader=lambda: {})
    store.write({candidate.symbol: (item,)}, REQUEST)
    read = store.read([candidate], REQUEST)
    assert read.evidence_by_symbol[candidate.symbol] == ()
    assert read.diagnostics["issuer_relevance_rejected_by_symbol"] == {candidate.symbol: 1}


@pytest.mark.parametrize("mode", ["use", "only"])
def test_old_massive_ordering_profile_cannot_claim_compatible_coverage(tmp_path, mode):
    import hashlib
    path = tmp_path / "canonical.json"
    expected = article(START + timedelta(hours=1))
    provider = Provider((expected,))
    current = service(path, provider)
    current.get_news([CANDIDATE], REQUEST, POLICY)
    saved = json.loads(path.read_text())
    acquisition = saved["news_intelligence"]["symbols"]["ACME"]["last_retrieval"]["acquisition_profile"]
    acquisition["retrieval"]["provider_settings"].pop("publication_order", None)
    acquisition.pop("fingerprint")
    acquisition["fingerprint"] = hashlib.sha256(json.dumps(acquisition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path.write_text(json.dumps(saved))
    old_bytes = path.read_bytes()
    provider.calls.clear()
    policy = POLICY if mode == "use" else replace(POLICY, refresh_mode="cache_only", network_allowed=False)
    result = current.get_news([CANDIDATE], REQUEST, policy)
    diagnostics = result.diagnostics.diagnostics
    assert diagnostics["acquisition_profile_mismatch_symbols"] == ["ACME"]
    if mode == "only":
        assert provider.calls == []
        assert diagnostics["acquisition_coverage_unknown_symbols"] == ["ACME"]
        assert result.summary_for_symbol("ACME").retrieval_status == "unknown"
        assert path.read_bytes() == old_bytes
    else:
        assert len(provider.calls) == 1
        assert diagnostics["acquisition_coverage_unknown_symbols"] == []
        warm = service(path, provider).get_news([CANDIDATE], REQUEST, POLICY)
        assert len(provider.calls) == 1
        assert warm.diagnostics.diagnostics["acquisition_profile_compatible_by_symbol"] == {"ACME": True}
        assert warm.evidence_for_symbol("ACME")[0].published_at == expected.published_at
    assert result.evidence_for_symbol("ACME")[0].published_at == expected.published_at
