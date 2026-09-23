from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.news.evidence_store import EvidenceStoreReadResult
from src.news.news_intelligence_contract import (
    NewsBatchResult, NewsCandidate, NewsEvidence, NewsRequest,
    RetrievalDiagnostics, RetrievalPolicy, SourceDiagnostic,
)
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService


class _Store:
    def __init__(self, evidence=(), *, cache_fields=None):
        self.evidence = evidence
        self.cache_fields = cache_fields or {}
        self.writes = []

    def read(self, candidates, request):
        return EvidenceStoreReadResult(
            evidence_by_symbol={item.normalized_symbol: self.evidence for item in candidates},
            summaries_by_symbol={},
            diagnostics={"cache_miss_symbols": [item.normalized_symbol for item in candidates], **self.cache_fields},
        )

    def write(self, evidence, request):
        self.writes.append(evidence)
        return {"cache_write_failed": False}


class _Provider:
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        self.calls = []

    def get_news(self, candidates, request, policy):
        self.calls.append((candidates, request, policy))
        return NewsBatchResult(
            candidates=tuple(candidates),
            evidence_by_symbol={item.normalized_symbol: () for item in candidates},
            summaries_by_symbol={},
            diagnostics=self.diagnostics,
            request=request,
            retrieval_policy=policy,
        )


def _get(service, *, symbols=(" aemd ",), policy=None):
    return service.get_news(
        [NewsCandidate(symbol=value) for value in symbols],
        NewsRequest(freshness_seconds=3600, max_evidence_per_symbol=5),
        policy or RetrievalPolicy(refresh_mode="bounded_refresh", total_budget_seconds=8.0),
    )


def _record(capsys):
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("[NEWS][RETRIEVAL_DIAGNOSTICS] ")]
    assert len(lines) == 1
    return json.loads(lines[0].split(" ", 1)[1]), lines[0]


def test_http_failure_is_recorded_without_promoting_unavailable_evidence(capsys):
    failure = RetrievalDiagnostics(
        retrieval_status="provider_error", provider_status="provider_request_failure",
        provider_available=False, sources_attempted_count=1, total_budget_seconds=8.0,
        source_diagnostics=(SourceDiagnostic(
            source_id="https://news.example/rss", retrieval_status="provider_error",
            attempted=True, failure_reason="HTTP_401",
        ),),
    )
    provider = _Provider(failure)
    result = _get(CanonicalNewsIntelligenceService(evidence_store=_Store(), retrieval_provider=provider))
    record, _ = _record(capsys)
    assert record["symbols"] == ["AEMD"]
    assert record["provider_invoked"] is True
    assert record["request_mode"] == "bounded_refresh"
    assert record["sources"][0]["failure_code"] == "HTTP_401"
    assert record["sources"][0]["http_status"] == 401
    assert record["summaries"]["AEMD"]["retrieval_unavailable"] is True
    assert "provider_unavailable" in record["summaries"]["AEMD"]["unavailability_reasons"]
    assert record["provider_available"] is False
    assert datetime.fromisoformat(record["started_at_utc"]).tzinfo is not None
    assert datetime.fromisoformat(record["completed_at_utc"]) >= datetime.fromisoformat(record["started_at_utc"])
    assert result.evidence_by_symbol == {"AEMD": ()}
    assert result.diagnostics.unavailable is True
    assert result.summary_for_symbol("AEMD").provider_available is False
    assert provider.diagnostics is failure


def test_empty_budget_exhaustion_records_sources_and_cache_miss(capsys):
    provider = _Provider(RetrievalDiagnostics(
        retrieval_status="budget_exhausted", provider_status="available", provider_available=True,
        budget_exhausted=True, total_budget_seconds=8.0, elapsed_seconds=8.0,
        unresolved_symbols=("AEMD",), sources_attempted_count=1, sources_skipped_due_to_budget_count=1,
        source_diagnostics=(SourceDiagnostic(
            source_id="https://news.example/rss", retrieval_status="budget_exhausted",
            attempted=False, failure_reason="deadline_exhausted_before_attempt", budget_exhausted=True,
        ),),
    ))
    result = _get(CanonicalNewsIntelligenceService(evidence_store=_Store(), retrieval_provider=provider))
    record, _ = _record(capsys)
    assert record["budget_exhausted"] is True
    assert record["sources_skipped_due_to_budget"] == 1
    assert record["cache"]["cache_miss_symbols"] == ["AEMD"]
    assert record["summaries"]["AEMD"]["evidence_count"] == 0
    assert record["summaries"]["AEMD"]["budget_exhausted"] is True
    assert "budget_exhausted" in record["summaries"]["AEMD"]["unavailability_reasons"]
    assert result.evidence_by_symbol == {"AEMD": ()}
    assert result.diagnostics.unavailable is True


@pytest.mark.parametrize("prep_reused", [False, True])
def test_fresh_cache_or_prep_reuse_records_no_provider_call(capsys, prep_reused):
    evidence = NewsEvidence(
        symbol="AEMD", headline="PRIVATE_HEADLINE_BODY", evidence_id="fixture",
        published_at=datetime.now(timezone.utc), age_seconds=0, stale=False, cache_state="hit",
    )
    store = _Store((evidence,), cache_fields={
        "cache_hit_symbols": ["AEMD"], "cache_miss_symbols": [],
        "prep_reuse_symbols": ["AEMD"] if prep_reused else [],
    })
    provider = _Provider(RetrievalDiagnostics())
    result = _get(CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=provider))
    record, text = _record(capsys)
    assert record["provider_invoked"] is False
    assert record["cache"]["cache_hit_symbols"] == ["AEMD"]
    assert record["cache"]["prep_reuse_symbols"] == (["AEMD"] if prep_reused else [])
    assert record["summaries"]["AEMD"]["evidence_count"] == 1
    assert "PRIVATE_HEADLINE_BODY" not in text
    assert result.evidence_for_symbol("AEMD")[0].headline == "PRIVATE_HEADLINE_BODY"
    assert not provider.calls
    assert not store.writes


def test_diagnostics_drop_auth_query_fragment_raw_payload_and_error_text(capsys):
    source_url = "https://user_secret:password_secret@news.example/rss?api_key=query_secret#fragment_secret"
    failure_text = "HTTP 401 Authorization: Bearer bearer_secret"
    provider = _Provider(RetrievalDiagnostics(
        retrieval_status="provider_error", provider_status="provider_request_failure",
        provider_available=False,
        source_diagnostics=(SourceDiagnostic(
            source_id=source_url, attempted=True, failure_reason=failure_text,
        ),),
        diagnostics={"Authorization": "raw_secret", "headline": "body_secret"},
    ))
    store = _Store(cache_fields={"cache_file": "path_secret", "cache_read_error": "error with token=cache_secret"})
    result = _get(CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=provider))
    record, text = _record(capsys)
    assert record["sources"][0]["source"] == "https://news.example/rss"
    assert record["sources"][0]["failure_code"] == "REDACTED"
    assert record["cache"]["cache_read_error"] == "REDACTED"
    assert "_secret" not in text
    assert result.diagnostics.source_diagnostics[0].source_id == source_url
    assert result.diagnostics.source_diagnostics[0].failure_reason == failure_text


def test_cache_only_empty_result_emits_once_without_network_or_evidence(capsys):
    provider = _Provider(RetrievalDiagnostics())
    result = _get(
        CanonicalNewsIntelligenceService(evidence_store=_Store(), retrieval_provider=provider),
        policy=RetrievalPolicy(refresh_mode="cache_only", network_allowed=False),
    )
    record, _ = _record(capsys)
    assert record["provider_invoked"] is False
    assert record["network_allowed"] is False
    assert record["request_mode"] == "cache_only"
    assert record["sources"] == []
    assert result.evidence_for_symbol("AEMD") == ()
    assert not provider.calls


def test_no_candidates_emits_no_symbols_record_without_provider(capsys):
    provider = _Provider(RetrievalDiagnostics())
    result = _get(CanonicalNewsIntelligenceService(evidence_store=_Store(), retrieval_provider=provider), symbols=())
    record, _ = _record(capsys)
    assert record["symbols"] == []
    assert record["provider_status"] == "no_symbols"
    assert record["provider_invoked"] is False
    assert result.evidence_by_symbol == {}
    assert not provider.calls


@pytest.mark.parametrize("reason", ["feedparser_missing", "deadline_exhausted", "no_sources"])
def test_final_provider_reason_and_refresh_path_are_preserved(capsys, reason):
    provider = _Provider(RetrievalDiagnostics(
        retrieval_status="provider_error", provider_status="provider_request_failure",
        provider_available=False, diagnostics={"failure_reason": reason},
    ))
    result = _get(CanonicalNewsIntelligenceService(evidence_store=_Store(), retrieval_provider=provider))
    record, _ = _record(capsys)
    assert record["provider_failure_reason"] == reason
    assert record["refresh_allowed"] is True
    assert record["refresh_symbols"] == ["AEMD"]
    assert record["cache"]["read_attempted"] is True
    assert record["cache"]["write_attempted"] is True
    from src.scanner.scanner_runner import _empty_news_context_from_summary
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_catalyst
    context = _empty_news_context_from_summary("AEMD", result.summary_for_symbol("AEMD"), result)
    decision = assess_catalyst(mode="READ_ONLY", news_enabled=True,
                              news_available=context["news_available"], confirmed=None)
    assert decision.status.value == "DATA_UNAVAILABLE"
    assert decision.satisfied is False


def test_successful_empty_retrieval_does_not_become_a_provider_failure(capsys):
    provider = _Provider(RetrievalDiagnostics(
        retrieval_status="available", provider_status="available", provider_available=True,
    ))
    result = _get(CanonicalNewsIntelligenceService(evidence_store=_Store(), retrieval_provider=provider))
    record, _ = _record(capsys)
    assert record["provider_failure_reason"] is None
    assert record["summaries"]["AEMD"]["objective_news_status"] == "no_recent_news"
    assert record["summaries"]["AEMD"]["retrieval_unavailable"] is False
    assert record["summaries"]["AEMD"]["fresh_evidence_count"] == 0
    from src.scanner.scanner_runner import _empty_news_context_from_summary
    from src.strategies.ross_momentum.policy.catalyst_policy import assess_catalyst
    context = _empty_news_context_from_summary("AEMD", result.summary_for_symbol("AEMD"), result)
    decision = assess_catalyst(mode="READ_ONLY", news_enabled=True,
                              news_available=context["news_available"], confirmed=False)
    assert decision.status.value == "ABSENT"
    assert decision.satisfied is False
