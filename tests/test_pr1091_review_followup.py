from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.news.news_intelligence_contract import NewsBatchResult, NewsCandidate, NewsEvidence, NewsEvidenceSummary, RetrievalDiagnostics
from src.scanner import scanner_runner


@pytest.fixture(autouse=True)
def clean_context_cache(monkeypatch):
    monkeypatch.setattr(scanner_runner, "_NEWS_CACHE", {})


@pytest.mark.parametrize(
    ("title", "expected"),
    [("EGG wins contracts", "CONTRACT"), ("EGG expands partnerships", "CONTRACT"),
     ("Broker upgrades EGG", "ANALYST_ACTION"), ("Broker upgraded EGG", "ANALYST_ACTION"),
     ("Broker downgrades EGG", "ANALYST_ACTION"), ("EGG launches electric vehicles", "EV_CATALYST"),
     ("EGG launches semiconductors", "TECH_CATALYST"), ("EGG issues press releases", "PRESS_RELEASE")],
)
def test_established_event_vocabulary_keeps_ordinary_inflections(title, expected):
    assert scanner_runner._detect_catalyst_type([title]) == expected


def _item(**overrides):
    return replace(NewsEvidence(
        symbol="EGG", evidence_id="stable-id", headline="Issuer wins contract",
        summary="NASDAQ: EGG issued this announcement", provider="rss_batch",
        match_type="ticker_token", age_seconds=60, stale=False,
        original_source="Example Wire", source_domain="news.example", url="https://news.example/item",
        published_at=datetime.fromtimestamp(1000, timezone.utc),
    ), **overrides)


def _result(items, *, candidate=None, summary=None, diagnostics=None):
    return NewsBatchResult(
        candidates=(candidate or NewsCandidate("EGG"),), evidence_by_symbol={"EGG": tuple(items)},
        summaries_by_symbol={"EGG": summary or NewsEvidenceSummary("EGG")},
        diagnostics=diagnostics or RetrievalDiagnostics(provider_available=True),
    )


def _context(result):
    return scanner_runner._ross_news_contexts_from_news_intelligence_result(result)["EGG"]


def test_summary_change_with_same_evidence_id_invalidates_cached_positive():
    item = _item()
    assert _context(_result([item]))["ross_catalyst_valid"] is True
    changed = replace(item, summary="The issuer is EGGX. Visitors enjoy egg tarts.")
    assert _context(_result([changed]))["ross_catalyst_valid"] is False


def test_case_sensitive_title_change_invalidates_cached_positive():
    item = _item(headline="EGG wins contract", summary="")
    assert _context(_result([item]))["ross_catalyst_valid"] is True
    assert _context(_result([replace(item, headline="Egg wins contract")]))["ross_catalyst_valid"] is False


def test_trusted_issuer_metadata_change_invalidates_cached_positive():
    item = _item(headline="Example Foods wins contract", summary="")
    first = _result([item], candidate=NewsCandidate("EGG", metadata={"company_name": "Example Foods"}))
    changed = _result([item], candidate=NewsCandidate("EGG", metadata={"company_name": "Another Issuer"}))
    assert _context(first)["ross_catalyst_valid"] is True
    assert _context(changed)["ross_catalyst_valid"] is False


def test_mutated_metadata_mapping_cannot_mutate_the_saved_cache_identity():
    metadata = {"company_name": "Example Foods"}
    result = _result([_item(headline="Example Foods wins contract", summary="")], candidate=NewsCandidate("EGG", metadata=metadata))
    assert _context(result)["ross_catalyst_valid"] is True
    metadata["company_name"] = "Another Issuer"
    assert _context(result)["ross_catalyst_valid"] is False


def test_changed_retrieval_budget_status_invalidates_cached_context():
    result = _result([_item()])
    assert _context(result)["news_available"] is True
    changed = replace(result, diagnostics=RetrievalDiagnostics(provider_available=True, budget_exhausted=True))
    assert _context(changed)["news_available"] is False


def test_rejected_items_cannot_inflate_remaining_context_metrics_or_provenance(monkeypatch):
    monkeypatch.setattr(scanner_runner.time, "time", lambda: 1060.0)
    valid = _item(
        velocity_5m=4, velocity_10m=4, velocity_30m=4, velocity_60m=4,
        heat_score=90, hotness_score=90, independent_source_count=4,
        source_credibility_score=1.0, source_reliability_score=1.0,
    )
    unrelated = tuple(replace(valid, evidence_id=f"irrelevant-{n}", summary="Visitors enjoy egg tarts.", original_source=f"Irrelevant {n}", source_domain=f"unrelated{n}.example") for n in range(3))
    summary = NewsEvidenceSummary("EGG", evidence_count=4, fresh_evidence_count=4, velocity_5m=4, velocity_10m=4, velocity_30m=4, velocity_60m=4, independent_source_count=4, budget_exhausted=True, retrieval_status="budget_exhausted")
    diagnostics = RetrievalDiagnostics(provider_available=True, budget_exhausted=True, diagnostics={
        "source_provenance_by_symbol": {"EGG": [{"source": "Example Wire"}, {"source": "Irrelevant 0"}]},
        "match_types_by_symbol": {"EGG": ["ticker_token", "wrong_match"]},
    })
    context = _context(_result([valid, *unrelated], summary=summary, diagnostics=diagnostics))
    assert context["news_count"] == 1
    assert context["news_intelligence_evidence_ids"] == ("stable-id",)
    assert context["velocity_5m"] == context["velocity_10m"] == context["velocity_30m"] == context["velocity_60m"] == 1
    assert context["attention_tier"] == "T1"
    assert context["news_independent_source_count"] == 1
    assert context["news_heat_score"] < 90
    assert context["news_hotness_score"] < 90
    assert context["news_top_source_credibility_score"] == 0
    assert context["news_source_reliability_score"] == 0
    assert [row["source"] for row in context["news_intelligence_source_provenance"]] == ["Example Wire"]
    assert context["news_intelligence_match_types"] == ["ticker_token"]
    assert context["news_available"] is False
    assert context["ross_catalyst_valid"] is True  # Valid retained evidence; incomplete retrieval remains reported.
