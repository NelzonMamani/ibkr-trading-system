"""Offline acceptance at the service, persisted prep, and Ross consumer boundaries.

IPDN text/URL are the historical PR1079 positive-control facts, replayed from
tests/test_pr1079_globenewswire_positive_control.py. The publication instant is a
controlled fixture timestamp, not a new capture or current source-coverage claim.
No test runs a scanner cycle, contacts a provider, or connects to a broker.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import socket
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import batch_rss_adapter, evidence_store, news_fetcher, news_intelligence_service, prep_adapter
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import (
    NewsBatchResult, NewsCandidate, NewsEvidence, NewsEvidenceSummary,
    NewsRequest, RetrievalDiagnostics, RetrievalPolicy,
)
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.prep_adapter import NewsProvider
from src.news.source_groups import get_source_group_urls
from src.prep import premarket_prep
from src.prep.premarket_prep_artifact import load_canonical_premarket_prep_artifact, write_canonical_premarket_prep_artifact
from src.scanner import scanner_runner
from src.strategies.ross_momentum.policy.catalyst_policy import assess_catalyst


IPDN_TITLE = "Professional Diversity Network Launches PDN Intelligence to Advance GPU-Powered AI Infrastructure"
IPDN_URL = "https://www.globenewswire.com/news-release/2026/08/21/3349010/25762/en/professional-diversity-network-launches-pdn-intelligence-to-advance-gpu-powered-ai-infrastructure.html"
IPDN_SUMMARY = (
    "CHICAGO, Aug. 21, 2026 (GLOBE NEWSWIRE) -- Professional Diversity Network, Inc. "
    "(Nasdaq: IPDN) announced the formation of PDN Intelligence, Inc., a wholly owned "
    "subsidiary established to lead expansion into artificial intelligence infrastructure "
    "and GPU-powered computing."
)
TECHNOLOGY_RSS = "https://www.globenewswire.com/RssFeed/industry/9000-Technology/feedTitle/GlobeNewswire%20-%20Industry%20News%20on%20Technology"
FIXTURE_PUBLICATION = datetime(2026, 8, 21, 14, 0, tzinfo=timezone.utc)
REQUEST = NewsRequest(strategy_id="ross_momentum", lookback_seconds=21600, freshness_seconds=21600,
                      include_generic_news=True, max_evidence_per_symbol=5)
POLICY = RetrievalPolicy(source_groups=("FAST_TRADING",), fallback_mode="none",
                         refresh_interval_seconds=1800, total_budget_seconds=8.0)


@pytest.fixture(autouse=True)
def offline_clock(monkeypatch, tmp_path):
    class Clock(datetime):
        current = FIXTURE_PUBLICATION + timedelta(minutes=5)

        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(cls.current.timestamp(), tz=tz)

    def no_network(*args, **kwargs):
        raise AssertionError("W02 acceptance must remain offline")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    for module in (batch_rss_adapter, evidence_store, news_intelligence_service, prep_adapter,
                   premarket_prep, scanner_runner):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(time, "time", lambda: Clock.current.timestamp())
    monkeypatch.setattr(scanner_runner, "_NEWS_CACHE", {})
    set_config_overrides({"NEWS_ENABLED": True, "NEWS_CACHE_FILE": str(tmp_path / "default.json"),
                          "NEWS_MAX_AGE_HOURS": 6.0, "NEWS_LOOKBACK_HOURS": 6.0,
                          "NEWS_MAX_ENTRIES_PER_SYMBOL": 5, "NEWS_REFRESH_SECONDS_PREP": 1800,
                          "NEWS_TOTAL_BUDGET_S": 8.0})
    yield Clock
    set_config_overrides({})


def _service(path, provider=None, prep_loader=lambda: {}):
    return CanonicalNewsIntelligenceService(
        evidence_store=CanonicalNewsEvidenceStore(path, prep_artifact_loader=prep_loader),
        retrieval_provider=provider,
    )


def _ross(result):
    contexts = scanner_runner._ross_news_contexts_from_news_intelligence_result(result)
    return contexts, {symbol: assess_catalyst(mode="READ_ONLY", news_enabled=True,
                     news_available=context["news_available"], confirmed=context["ross_catalyst_valid"])
                     for symbol, context in contexts.items()}


def _serialize_prep(tmp_path, service, symbols):
    engine = premarket_prep.PreMarketPrepEngine()
    engine._news_provider = NewsProvider(service=service)
    engine.update_from_universe(symbols, session_label="PRE", reason="OFFLINE_ACCEPTANCE")
    path = tmp_path / "premarket_prep.json"
    write_canonical_premarket_prep_artifact(engine.build_artifact_payload(symbols), path)
    restored = premarket_prep.PreMarketPrepEngine()
    assert restored.hydrate_from_artifact(load_canonical_premarket_prep_artifact(path)["symbols"]) == len(symbols)
    write_canonical_premarket_prep_artifact(restored.build_artifact_payload(symbols), path)
    return path


def _rss_fixture(monkeypatch, published=FIXTURE_PUBLICATION):
    calls = []
    entry = SimpleNamespace(title=IPDN_TITLE, summary=IPDN_SUMMARY, link=IPDN_URL)
    if published is not None:
        entry.published_parsed = time.gmtime(published.timestamp())
    unrelated = SimpleNamespace(title="Malaysia launches AI research", summary="Visitors enjoy egg tarts.",
                                link="https://example.test/unrelated", published_parsed=time.gmtime(FIXTURE_PUBLICATION.timestamp()))

    def feed(url, timeout):
        calls.append(url)
        return SimpleNamespace(feed={"title": "GlobeNewswire - Industry News on Technology"},
                               entries=[entry, unrelated] if url == TECHNOLOGY_RSS else [])

    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(news_fetcher, "_fetch_feed", feed)
    return calls


def test_historical_positive_batch_survives_prep_serialization_warm_restart_and_explicit_refresh(
    monkeypatch, tmp_path, offline_clock,
):
    calls = _rss_fixture(monkeypatch)
    candidates = [NewsCandidate("IPDN", company_name="Professional Diversity Network, Inc.", aliases=("PDN",)),
                  NewsCandidate("EGG")]
    path = tmp_path / "news.json"
    service = _service(path)
    cold = service.get_news(candidates, REQUEST, POLICY)
    article = cold.evidence_for_symbol("IPDN")[0]
    assert article.headline == IPDN_TITLE and article.summary == IPDN_SUMMARY and article.url == IPDN_URL
    assert article.published_at == FIXTURE_PUBLICATION and article.age_seconds == 300
    assert article.match_type == "ticker_token" and article.matched_field == "summary"
    assert cold.evidence_for_symbol("EGG") == ()
    assert len(calls) == len(set(calls)) == len(get_source_group_urls("FAST_TRADING"))
    assert _ross(cold)[1]["IPDN"].status.value == "CONFIRMED"
    assert _ross(cold)[1]["EGG"].status.value == "ABSENT"

    offline_clock.current += timedelta(minutes=10)
    for reader in (service, _service(path)):
        warm = reader.get_news(candidates, REQUEST, POLICY)
        assert warm.diagnostics.diagnostics["cadence_cache_hit_symbols"] == ["IPDN", "EGG"]
        assert warm.evidence_for_symbol("IPDN")[0].age_seconds == 900
        assert _ross(warm)[1]["IPDN"].status.value == "CONFIRMED"
    assert len(calls) == len(set(calls))

    prep_path = _serialize_prep(tmp_path, service, ["IPDN", "EGG"])
    persisted = load_canonical_premarket_prep_artifact(prep_path)["symbols"][0]["news_context"][0]
    assert persisted["summary"] == IPDN_SUMMARY and persisted["evidence_id"] == article.evidence_id
    assert persisted["published_at"] == FIXTURE_PUBLICATION.isoformat()
    prep_only = _service(tmp_path / "restarted.json", prep_loader=lambda: load_canonical_premarket_prep_artifact(prep_path))
    restored = prep_only.get_news(candidates, REQUEST, replace(POLICY, network_allowed=False, refresh_mode="cache_only"))
    assert restored.diagnostics.diagnostics["prep_reuse_symbols"] == ["IPDN"]
    assert _ross(restored)[1]["IPDN"].status.value == "CONFIRMED"
    assert len(calls) == len(set(calls))

    refreshed = _service(path).get_news(candidates, REQUEST, replace(POLICY, metadata={"refresh_symbols": ["IPDN"]}))
    assert refreshed.diagnostics.diagnostics["refresh_symbols"] == ["IPDN"]
    assert len(calls) == 2 * len(set(calls))
    assert refreshed.evidence_for_symbol("IPDN")[0].published_at == FIXTURE_PUBLICATION


def test_captured_issuer_article_reaches_persisted_prep_and_ross_without_becoming_a_catalyst(
    monkeypatch, tmp_path, offline_clock,
):
    fixture = json.loads((Path(__file__).parent / "fixtures/w02_captured_issuer_news.json").read_text())
    published = datetime.fromisoformat(fixture["published_at"])
    offline_clock.current = datetime.fromisoformat(fixture["capture_completed_at"])
    entry = SimpleNamespace(title=fixture["headline"], summary=fixture["summary_excerpt"], link=fixture["url"],
                            published_parsed=time.gmtime(published.timestamp()))
    calls = []

    def feed(url, timeout):
        calls.append(url)
        return SimpleNamespace(feed={"title": "GlobeNewswire Finance"},
                               entries=[entry] if url == fixture["source_url"] else [])

    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(news_fetcher, "_fetch_feed", feed)
    service = _service(tmp_path / "news.json")
    candidates = [NewsCandidate(fixture["symbol"], company_name=fixture["company_name"])]
    result = service.get_news(candidates, REQUEST, POLICY)
    article, = result.evidence_for_symbol("IRON")
    assert article.headline == fixture["headline"] and article.url == fixture["url"]
    assert article.published_at == published
    assert article.age_seconds == pytest.approx((offline_clock.current - published).total_seconds())
    assert article.match_type == "ticker_token"
    assert article.stale is False
    prep_path = _serialize_prep(tmp_path, service, ["IRON"])
    restored = _service(tmp_path / "restart.json", prep_loader=lambda: load_canonical_premarket_prep_artifact(prep_path)).get_news(
        candidates, REQUEST, replace(POLICY, network_allowed=False, refresh_mode="cache_only"))
    for batch in (result, restored):
        context, decision = _ross(batch)
        assert context["IRON"]["news_present"] is True
        assert context["IRON"]["news_available"] is True
        assert context["IRON"]["news_diagnostic_status"] == "news_present_non_qualifying"
        assert decision["IRON"].status.value == "ABSENT"
    assert len(calls) == len(set(calls))


@pytest.mark.parametrize("publication", [None, FIXTURE_PUBLICATION + timedelta(hours=1), FIXTURE_PUBLICATION - timedelta(days=2)],
                         ids=["missing", "future", "stale"])
def test_public_rss_batch_rejects_unusable_publication_without_confirming(monkeypatch, tmp_path, publication):
    _rss_fixture(monkeypatch, publication)
    result = _service(tmp_path / "news.json").get_news([NewsCandidate("IPDN")], REQUEST, POLICY)
    assert result.evidence_for_symbol("IPDN") == ()
    assert result.summary_for_symbol("IPDN").fresh_evidence_count == 0
    assert _ross(result)[1]["IPDN"].satisfied is False


@pytest.mark.parametrize("publication", [None, FIXTURE_PUBLICATION + timedelta(hours=1), FIXTURE_PUBLICATION - timedelta(days=2)],
                         ids=["missing", "future", "stale"])
def test_serialized_prep_receipt_and_fresh_flags_do_not_replace_publication(tmp_path, publication):
    row = {"symbol": "IPDN", "news_asof": FIXTURE_PUBLICATION.isoformat(), "news_context": [{
        "title": IPDN_TITLE, "summary": IPDN_SUMMARY, "url": IPDN_URL,
        "source": "GlobeNewswire", "published_at": publication.isoformat() if publication else None,
        "freshness": "fresh", "catalyst_tag": "TECH_CATALYST", "fetched_at": FIXTURE_PUBLICATION.isoformat(),
    }]}
    engine = premarket_prep.PreMarketPrepEngine()
    engine.hydrate_from_artifact([row])
    prep_path = tmp_path / "prep.json"
    write_canonical_premarket_prep_artifact(engine.build_artifact_payload(["IPDN"]), prep_path)
    result = _service(tmp_path / "cache.json", prep_loader=lambda: load_canonical_premarket_prep_artifact(prep_path)).get_news(
        [NewsCandidate("IPDN")], REQUEST, replace(POLICY, network_allowed=False, refresh_mode="cache_only"))
    assert result.summary_for_symbol("IPDN").fresh_evidence_count == 0
    context, decision = _ross(result)
    assert context["IPDN"]["ross_catalyst_valid"] is False
    assert decision["IPDN"].satisfied is False


@pytest.mark.parametrize("status", ["unavailable", "timeout", "provider_error", "budget_exhausted"])
def test_public_service_unavailable_remains_unavailable_in_ross_after_restart(tmp_path, status):
    class Provider:
        calls = 0

        def get_news(self, candidates, request, policy):
            self.calls += 1
            return NewsBatchResult(evidence_by_symbol={"BAD": ()}, diagnostics=RetrievalDiagnostics(
                retrieval_status=status, provider_status="offline", provider_available=False,
                budget_exhausted=status == "budget_exhausted"))

    provider = Provider()
    path = tmp_path / "news.json"
    for service in (_service(path, provider), _service(path, provider)):
        result = service.get_news([NewsCandidate("BAD")], REQUEST, POLICY)
        context, decision = _ross(result)
        assert result.summary_for_symbol("BAD").provider_available is False
        assert context["BAD"]["news_available"] is False
        assert context["BAD"]["news_diagnostic_status"] == ("budget_exhausted" if status == "budget_exhausted" else "provider_unavailable")
        assert decision["BAD"].status.value == "DATA_UNAVAILABLE"
    assert provider.calls == 1


@pytest.mark.parametrize("budget", [False, True], ids=["failure", "budget"])
@pytest.mark.parametrize("with_summaries", [False, True], ids=["summaryless-provider", "provider-summaries"])
@pytest.mark.parametrize("with_evidence", [False, True], ids=["empty", "generic-evidence"])
def test_mixed_public_service_outcomes_reach_ross_per_symbol_and_survive_restart(tmp_path, budget, with_summaries, with_evidence):
    class Provider:
        calls = 0

        def get_news(self, candidates, request, policy):
            self.calls += 1
            now = news_intelligence_service.datetime.now(timezone.utc)
            evidence = {symbol: (NewsEvidence(
                symbol=symbol, headline=f"{symbol} company profile update", provider="rss_batch",
                published_at=now - timedelta(minutes=5), fetched_at=now, age_seconds=300, stale=False,
            ),) if with_evidence else () for symbol in ("EMPTY", "BAD")}
            summaries = {
                "EMPTY": NewsEvidenceSummary(symbol="EMPTY", retrieval_status="available", provider_status="ok", provider_available=True),
                "BAD": NewsEvidenceSummary(symbol="BAD", retrieval_status="budget_exhausted" if budget else "unavailable",
                                           provider_status="offline", provider_available=False, budget_exhausted=budget),
            }
            return NewsBatchResult(evidence_by_symbol=evidence,
                summaries_by_symbol=summaries if with_summaries else {}, diagnostics=RetrievalDiagnostics(
                    retrieval_status="partial", provider_status="mixed", provider_available=False,
                    budget_exhausted=budget, unresolved_symbols=("BAD",)))

    provider = Provider()
    path = tmp_path / "news.json"
    for service in (_service(path, provider), _service(path, provider)):
        result = service.get_news([NewsCandidate("EMPTY"), NewsCandidate("BAD")], REQUEST, POLICY)
        context, decision = _ross(result)
        assert result.diagnostics.unresolved_symbols == ("BAD",)
        assert context["EMPTY"]["news_available"] is True
        assert context["EMPTY"]["news_diagnostic_status"] == ("news_present_non_qualifying" if with_evidence else "no_recent_news")
        assert decision["EMPTY"].status.value == "ABSENT"
        assert context["BAD"]["news_available"] is False
        assert context["BAD"]["news_diagnostic_status"] == ("budget_exhausted" if budget else "provider_unavailable")
        assert decision["BAD"].status.value == "DATA_UNAVAILABLE"
    assert provider.calls == 1


def test_article_identity_and_offering_survive_service_prep_and_legacy_copies(tmp_path):
    class Provider:
        calls = 0

        def get_news(self, candidates, request, policy):
            self.calls += 1
            now = news_intelligence_service.datetime.now(timezone.utc)
            evidence = tuple(NewsEvidence(
                symbol="EGG", evidence_id=f"acceptance:EGG:{index}", provider="rss_batch",
                headline="EGG announces offering" if index == 4 else f"EGG wins contract {index}",
                url=f"https://example.test/{index}", observed_source="Offline fixture",
                published_at=now - timedelta(minutes=index + 1), fetched_at=now,
                age_seconds=(index + 1) * 60, stale=False,
            ) for index in range(5))
            return NewsBatchResult(evidence_by_symbol={"EGG": evidence}, completed_at=now,
                diagnostics=RetrievalDiagnostics(retrieval_status="available", provider_status="ok", provider_available=True))

    provider = Provider()
    path = tmp_path / "news.json"
    service = _service(path, provider)
    cold = service.get_news([NewsCandidate("EGG")], REQUEST, POLICY)
    prep_path = _serialize_prep(tmp_path, service, ["EGG"])
    payload = json.loads(path.read_text())
    prep_row = load_canonical_premarket_prep_artifact(prep_path)["symbols"][0]
    payload["symbols"] = {"EGG": {"fetched_at": prep_row["news_asof"], "news_context": [
        {key: value for key, value in row.items() if key != "evidence_id"}
        for row in prep_row["news_context"]
    ]}}
    path.write_text(json.dumps(payload))
    restarted = _service(path, provider, lambda: load_canonical_premarket_prep_artifact(prep_path))
    restored = restarted.get_news([NewsCandidate("EGG")], REQUEST, replace(POLICY, network_allowed=False, refresh_mode="cache_only"))
    assert provider.calls == 1
    assert len(restored.evidence_for_symbol("EGG")) == 5
    assert {item.evidence_id for item in restored.evidence_for_symbol("EGG")} == {
        item.evidence_id for item in cold.evidence_for_symbol("EGG")
    }
    context, decision = _ross(restored)
    assert context["EGG"]["dilution_flag"] is True
    assert context["EGG"]["ross_catalyst_valid"] is False
    assert decision["EGG"].status.value == "ABSENT"


@pytest.mark.parametrize("with_evidence", [False, True], ids=["empty", "generic-evidence"])
def test_healthy_summary_without_provider_label_does_not_inherit_failed_batch_status(tmp_path, with_evidence):
    class Provider:
        def get_news(self, candidates, request, policy):
            now = news_intelligence_service.datetime.now(timezone.utc)
            evidence = (NewsEvidence(symbol="GOOD", headline="GOOD company profile update", provider="rss_batch",
                                    published_at=now, fetched_at=now, age_seconds=0, stale=False),) if with_evidence else ()
            return NewsBatchResult(evidence_by_symbol={"GOOD": evidence, "BAD": ()}, summaries_by_symbol={
                "GOOD": NewsEvidenceSummary(symbol="GOOD", retrieval_status="available", provider_available=True),
                "BAD": NewsEvidenceSummary(symbol="BAD", retrieval_status="provider_error", provider_available=False),
            }, diagnostics=RetrievalDiagnostics(retrieval_status="partial", provider_status="provider_request_failure",
                                                provider_available=False, unresolved_symbols=("BAD",)))

    result = _service(tmp_path / "news.json", Provider()).get_news(
        [NewsCandidate("GOOD"), NewsCandidate("BAD")], REQUEST, POLICY)
    context, decision = _ross(result)
    assert context["GOOD"]["news_available"] is True
    assert context["GOOD"]["news_provider_status"] == "available"
    assert context["GOOD"]["news_diagnostic_status"] == ("news_present_non_qualifying" if with_evidence else "no_recent_news")
    assert decision["GOOD"].status.value == "ABSENT"
    assert decision["BAD"].status.value == "DATA_UNAVAILABLE"


@pytest.mark.parametrize("budget", [False, True], ids=["unavailable", "budget"])
def test_unknown_summary_keeps_explicit_symbol_failure_without_poisoning_healthy_summary(tmp_path, budget):
    class Provider:
        calls = 0

        def get_news(self, candidates, request, policy):
            self.calls += 1
            return NewsBatchResult(evidence_by_symbol={"GOOD": (), "BAD": ()}, summaries_by_symbol={
                "GOOD": NewsEvidenceSummary(symbol="GOOD", retrieval_status="available", provider_available=True),
                "BAD": NewsEvidenceSummary(symbol="BAD"),
            }, diagnostics=RetrievalDiagnostics(
                retrieval_status="budget_exhausted" if budget else "unavailable",
                provider_status="available" if budget else "provider_request_failure",
                provider_available=budget, budget_exhausted=budget, unresolved_symbols=("BAD",)))

    provider = Provider()
    path = tmp_path / "news.json"
    service = _service(path, provider)
    for reader in (service, service, _service(path, provider)):
        result = reader.get_news([NewsCandidate("GOOD"), NewsCandidate("BAD")], REQUEST, POLICY)
        assert result.summary_for_symbol("BAD").retrieval_status == ("budget_exhausted" if budget else "unavailable")
        assert result.summary_for_symbol("BAD").provider_available is False
        assert result.summary_for_symbol("BAD").budget_exhausted is budget
        assert result.summary_for_symbol("GOOD").provider_available is True
        assert result.summary_for_symbol("GOOD").budget_exhausted is False
        assert result.summary_for_symbol("BAD").diagnostics["objective_news_status"] == ("budget_exhausted" if budget else "no_recent_news")
        assert result.summary_for_symbol("GOOD").diagnostics["objective_news_status"] == "no_recent_news"
        assert result.diagnostics.unresolved_symbols == ("BAD",)
        assert result.diagnostics.budget_exhausted is budget
        context, decision = _ross(result)
        assert context["GOOD"]["news_available"] is True
        assert context["GOOD"]["news_diagnostic_status"] == "no_recent_news"
        assert decision["GOOD"].status.value == "ABSENT"
        assert context["BAD"]["news_available"] is False
        assert context["BAD"]["news_diagnostic_status"] == ("budget_exhausted" if budget else "provider_unavailable")
        assert decision["BAD"].status.value == "DATA_UNAVAILABLE"
    assert provider.calls == 1


@pytest.mark.parametrize("budget", [False, True])
def test_confirmed_persisted_evidence_retains_authority_when_explicit_refresh_is_incomplete(tmp_path, offline_clock, budget):
    class Provider:
        calls = 0

        def get_news(self, candidates, request, policy):
            self.calls += 1
            if self.calls == 1:
                now = news_intelligence_service.datetime.now(timezone.utc)
                evidence = NewsEvidence(symbol="EGG", headline="EGG wins contract", provider="rss_batch",
                                        published_at=now, fetched_at=now, age_seconds=0, stale=False)
                return NewsBatchResult(evidence_by_symbol={"EGG": (evidence,)}, diagnostics=RetrievalDiagnostics(
                    retrieval_status="available", provider_status="ok", provider_available=True))
            return NewsBatchResult(evidence_by_symbol={"EGG": ()}, diagnostics=RetrievalDiagnostics(
                retrieval_status="budget_exhausted" if budget else "provider_error", provider_status="offline",
                provider_available=False, budget_exhausted=budget))

    provider = Provider()
    service = _service(tmp_path / "news.json", provider)
    acquired = service.get_news([NewsCandidate("EGG")], REQUEST, POLICY)
    offline_clock.current += timedelta(minutes=5)
    result = service.get_news([NewsCandidate("EGG")], REQUEST, replace(POLICY, metadata={"refresh_symbols": ["EGG"]}))
    assert provider.calls == 2
    assert result.evidence_for_symbol("EGG")[0].published_at == acquired.evidence_for_symbol("EGG")[0].published_at
    assert result.evidence_for_symbol("EGG")[0].age_seconds == 300
    context, decision = _ross(result)
    assert context["EGG"]["news_available"] is False
    assert context["EGG"]["news_diagnostic_status"] == "catalyst_confirmed"
    assert decision["EGG"].status.value == "CONFIRMED"


@pytest.mark.parametrize(("provider_status", "retrieval_status"), [
    ("provider_unavailable", "unavailable"),
    ("provider_request_failure", "provider_error"),
])
def test_explicit_legacy_failure_label_survives_healthy_batch_and_cache_restart(tmp_path, provider_status, retrieval_status):
    class Provider:
        calls = 0

        def get_news(self, candidates, request, policy):
            self.calls += 1
            return NewsBatchResult(evidence_by_symbol={"GOOD": (), "BAD": ()}, summaries_by_symbol={
                "GOOD": NewsEvidenceSummary(symbol="GOOD", retrieval_status="available", provider_available=True),
                "BAD": NewsEvidenceSummary(symbol="BAD", provider_status=provider_status),
            }, diagnostics=RetrievalDiagnostics(retrieval_status="available", provider_status="available", provider_available=True))

    provider = Provider()
    path = tmp_path / "news.json"
    service = _service(path, provider)
    for reader in (service, service, _service(path, provider)):
        result = reader.get_news([NewsCandidate("GOOD"), NewsCandidate("BAD")], REQUEST, POLICY)
        assert result.summary_for_symbol("BAD").provider_status == provider_status
        assert result.summary_for_symbol("BAD").retrieval_status == retrieval_status
        assert result.summary_for_symbol("BAD").provider_available is False
        assert result.summary_for_symbol("GOOD").provider_available is True
        context, decision = _ross(result)
        assert context["BAD"]["news_available"] is False
        assert context["BAD"]["news_diagnostic_status"] == provider_status
        assert decision["BAD"].status.value == "DATA_UNAVAILABLE"
        assert context["GOOD"]["news_available"] is True
        assert decision["GOOD"].status.value == "ABSENT"
    assert provider.calls == 1
