from __future__ import annotations

import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.news import news_fetcher
from src.news.news_intelligence_contract import NewsBatchResult, NewsCandidate, NewsEvidence, RetrievalDiagnostics
from src.scanner import scanner_runner


# Captured Monday item rss-batch:EGG:918c1584c7937740; these are evidence
# excerpts for deterministic unit tests, never inputs to an observation.
DURIAN_TITLE = (
    "Malaysia waits until its durians are fully ripe \u2014 and fully smelly. "
    "China\u2019s $7.5 billion market looks on hungrily"
)
DURIAN_SUMMARY = "Downstairs, visitors enjoy platters and egg tarts crafted from it."


@pytest.mark.parametrize(
    ("symbol", "title", "summary"),
    [
        ("EGG", DURIAN_TITLE, DURIAN_SUMMARY),
        ("LINK", "Best Solar Stocks", "Answer Link answered 2026-09-28 Benzinga"),
        ("HOUR", "SpaceX's Starship Reaches Orbit", "It began a 10-hour mission."),
        ("CNET", "Libraries are becoming a cost-of-living hack", "According to a CNET survey."),
        ("EGG", "Egg tarts are popular", "Visitors enjoy the dessert."),
        ("EGG", "$EGGX announces earnings", "A different security."),
    ],
)
def test_observed_prose_and_publisher_mentions_are_not_issuer_matches(symbol, title, summary):
    assert news_fetcher.symbol_relevance_match(symbol, title=title, summary=summary) is None


@pytest.mark.parametrize(
    ("title", "summary", "metadata", "expected"),
    [
        ("EGG reports earnings", "", None, ("ticker_token", "title")),
        ("$EGG reports earnings", "", None, ("ticker_token", "title")),
        ("(EGG) reports earnings", "", None, ("ticker_token", "title")),
        ("Issuer reports earnings", "NASDAQ: EGG announced results", None, ("ticker_token", "summary")),
        ("Issuer reports earnings", "NYSE American: EGG announced results", None, ("ticker_token", "summary")),
        ("Issuer reports earnings", "Results from $EGG", None, ("ticker_token", "summary")),
        ("Issuer reports earnings", "Example Egg announced results", {"company_name": "Example Egg Inc."}, ("company_name", "summary")),
    ],
)
def test_explicit_ticker_and_trusted_issuer_matches_remain_supported(title, summary, metadata, expected):
    assert news_fetcher.symbol_relevance_match("EGG", title=title, summary=summary, metadata=metadata) == expected


def test_batch_provider_rejects_same_unrelated_mentions(monkeypatch):
    entries = [
        SimpleNamespace(title=DURIAN_TITLE, summary=DURIAN_SUMMARY, link="https://news.example/durian", published_parsed=time.gmtime()),
        SimpleNamespace(title="Libraries offer discounts", summary="According to a CNET survey.", link="https://news.example/libraries", published_parsed=time.gmtime()),
        SimpleNamespace(title="Best Solar Stocks", summary="Answer Link answered today", link="https://news.example/solar", published_parsed=time.gmtime()),
        SimpleNamespace(title="SpaceX reaches orbit", summary="A 10-hour mission", link="https://news.example/space", published_parsed=time.gmtime()),
    ]
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(news_fetcher, "_fetch_feed", lambda *_: SimpleNamespace(feed={"title": "captured examples"}, entries=entries))
    headlines, diagnostics = news_fetcher.fetch_fast_headlines_for_symbols(["EGG", "CNET", "LINK", "HOUR"], ["https://news.example/feed"])
    assert all(not items for items in headlines.values())
    assert diagnostics.ticker_token_match_count == 0


@pytest.mark.parametrize("title", [DURIAN_TITLE, "Retail sales rise", "Revenue doubles", "Details of the preview"])
def test_catalyst_abbreviations_do_not_match_inside_words(title):
    assert scanner_runner._detect_catalyst_type([title]) is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [("EGG launches AI infrastructure", "TECH_CATALYST"), ("EGG wins EV battery contract", "CONTRACT"),
     ("EGG launches EV platform", "EV_CATALYST"), ("EGG reports earnings", "EARNINGS"),
     ("EGG wins FDA approval", "FDA"), ("EGG expands GPU-powered computing", "TECH_CATALYST")],
)
def test_real_bounded_event_terms_keep_their_classification(title, expected):
    assert scanner_runner._detect_catalyst_type([title]) == expected


def test_cached_observed_durian_item_cannot_confirm_ross_catalyst():
    evidence = NewsEvidence(
        symbol="EGG", evidence_id="rss-batch:EGG:918c1584c7937740",
        headline=DURIAN_TITLE, summary=DURIAN_SUMMARY,
        match_type="ticker_token", matched_field="summary", provider="rss_batch",
        source_tier="extended", age_seconds=2820, stale=False, cache_state="hit",
    )
    result = NewsBatchResult(evidence_by_symbol={"EGG": (evidence,)}, diagnostics=RetrievalDiagnostics(provider_available=True))
    context = scanner_runner._ross_news_context_from_evidence("EGG", (evidence,), None, result)
    assert context["ross_catalyst_valid"] is False
    assert context["catalyst_type"] is None
    positive = replace(evidence, headline="EGG reports earnings beat")
    assert scanner_runner._ross_news_context_from_evidence("EGG", (positive,), None, result)["ross_catalyst_valid"] is True


def test_focus_summary_partitions_admitted_soft_fail_rejected_and_ranked_out():
    admitted = {"symbol": "WEAK", "focus_drop_reason": "SOFT_FAIL_VOLUME"}
    rows = [admitted, {"symbol": "NO_NEWS", "focus_drop_reason": "DROP_NO_CATALYST"},
            {"symbol": "PASS_RANKED_OUT"},
            {"symbol": "WEAK_RANKED_OUT", "focus_drop_reason": "SOFT_FAIL_VOLUME"}]
    assert scanner_runner._focus_summary_counts(rows, [admitted]) == {
        "evaluated": 4, "accepted": 1, "rejected": 1, "ranked_out": 2,
    }


@pytest.mark.parametrize("provider", ["rss_batch", "prep_cache", "legacy_news_provider_cache"])
@pytest.mark.parametrize(
    ("symbol", "title", "summary"),
    [("EGG", "Malaysia launches AI research", DURIAN_SUMMARY),
     ("HOUR", "SpaceX signs new contract", "A 10-hour mission"),
     ("LINK", "Solar firm reports earnings", "Answer Link answered today"),
     ("CNET", "Libraries sign new partnership", "According to a CNET survey.")],
)
def test_persisted_false_match_cannot_gain_authority_from_a_valid_event_word(provider, symbol, title, summary):
    evidence = NewsEvidence(
        symbol=symbol, headline=title, summary=summary, provider=provider,
        match_type="ticker_token", matched_field="summary", age_seconds=60,
        stale=False, cache_state="hit", event_class="contract_order",
    )
    result = NewsBatchResult(evidence_by_symbol={symbol: (evidence,)}, diagnostics=RetrievalDiagnostics(provider_available=True))
    context = scanner_runner._ross_news_context_from_evidence(symbol, (evidence,), None, result)
    assert context["ross_catalyst_valid"] is False
    assert context["news_count"] == 0


@pytest.mark.parametrize("metadata", [{"company_name": "Trusted Example Inc."}, {"aliases": ["Trusted Example"]}])
def test_cache_revalidation_preserves_upstream_metadata_issuer_identity(metadata):
    evidence = NewsEvidence(symbol="TRST", headline="Trusted Example signs new contract", provider="rss_batch", age_seconds=60, stale=False, cache_state="hit")
    result = NewsBatchResult(candidates=(NewsCandidate("TRST", metadata=metadata),), diagnostics=RetrievalDiagnostics(provider_available=True))
    assert scanner_runner._ross_news_context_from_evidence("TRST", (evidence,), None, result)["ross_catalyst_valid"] is True


def test_rejected_cache_match_does_not_turn_incomplete_retrieval_into_no_news():
    evidence = NewsEvidence(symbol="EGG", headline=DURIAN_TITLE, summary=DURIAN_SUMMARY, provider="rss_batch", age_seconds=60, stale=False, cache_state="hit")
    result = NewsBatchResult(diagnostics=RetrievalDiagnostics(provider_available=True, budget_exhausted=True, retrieval_status="budget_exhausted"))
    context = scanner_runner._ross_news_context_from_evidence("EGG", (evidence,), None, result)
    assert context["news_diagnostic_status"] == "budget_exhausted"
    assert context["news_available"] is False
    assert context["ross_catalyst_valid"] is False
