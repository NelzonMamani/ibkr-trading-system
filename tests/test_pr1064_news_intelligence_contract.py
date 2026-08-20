from __future__ import annotations

import ast
from dataclasses import fields, is_dataclass
from pathlib import Path

from src.news.news_intelligence_contract import (
    NewsBatchResult,
    NewsCandidate,
    NewsEvidence,
    NewsEvidenceSummary,
    NewsIntelligenceProvider,
    NewsRequest,
    RetrievalDiagnostics,
    RetrievalPolicy,
)


CONTRACT_MODULE = Path("src/news/news_intelligence_contract.py")
SCANNER_RUNNER = Path("src/scanner/scanner_runner.py")
NEWS_FETCHER = Path("src/news/news_fetcher.py")
RSS_REGISTRY = Path("src/news/rss_registry.py")
DOC_PATH = Path("docs/architecture/NEWS_INTELLIGENCE_CONTRACT.md")


def test_pr1064_candidate_keeps_absolute_volume_and_rvol_separate() -> None:
    candidate = NewsCandidate(
        symbol="PR64",
        absolute_share_volume=1_250_000,
        relative_volume_rvol=3.4,
    )

    assert candidate.absolute_share_volume == 1_250_000
    assert candidate.relative_volume_rvol == 3.4
    assert "absolute_share_volume" in {field.name for field in fields(NewsCandidate)}
    assert "relative_volume_rvol" in {field.name for field in fields(NewsCandidate)}


def test_pr1064_common_contract_module_does_not_import_ross_policy() -> None:
    tree = ast.parse(CONTRACT_MODULE.read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    assert all("src.strategies.ross_momentum" not in module for module in imported_modules)
    assert all("strategies.ross_momentum" not in module for module in imported_modules)


def test_pr1064_multi_symbol_batch_result_is_first_class() -> None:
    candidates = (
        NewsCandidate(symbol="AAA", company_name="Alpha Analytics"),
        NewsCandidate(symbol="BBB", company_name="Beta Biotech"),
    )
    evidence = {
        "AAA": (NewsEvidence(symbol="AAA", evidence_id="aaa-1", headline="AAA announces guidance"),),
        "BBB": (NewsEvidence(symbol="BBB", evidence_id="bbb-1", headline="BBB announces contract"),),
    }
    summaries = {
        "AAA": NewsEvidenceSummary(symbol="AAA", evidence_count=1, evidence_ids=("aaa-1",)),
        "BBB": NewsEvidenceSummary(symbol="BBB", evidence_count=1, evidence_ids=("bbb-1",)),
    }

    result = NewsBatchResult(candidates=candidates, evidence_by_symbol=evidence, summaries_by_symbol=summaries)

    assert result.symbols == ("AAA", "BBB")
    assert result.evidence_for_symbol("aaa")[0].evidence_id == "aaa-1"
    assert result.summary_for_symbol("bbb").evidence_count == 1  # type: ignore[union-attr]


def test_pr1064_single_symbol_is_batch_of_one() -> None:
    result = NewsBatchResult(
        candidates=(NewsCandidate(symbol="ONE"),),
        summaries_by_symbol={"ONE": NewsEvidenceSummary(symbol="ONE")},
    )

    assert result.symbols == ("ONE",)
    assert result.summary_for_symbol("ONE") is not None


def test_pr1064_reliability_and_heat_remain_distinct() -> None:
    evidence = NewsEvidence(
        symbol="SEP",
        source_reliability_score=0.95,
        heat_score=0.05,
        velocity_10m=0,
    )
    summary = NewsEvidenceSummary(
        symbol="SEP",
        highest_reliability_score=0.95,
        heat_score=0.05,
        velocity_10m=0,
    )

    assert evidence.source_reliability_score != evidence.heat_score
    assert summary.highest_reliability_score != summary.heat_score


def test_pr1064_freshness_and_reliability_remain_distinct() -> None:
    stale_but_reliable = NewsEvidence(
        symbol="OLD",
        age_seconds=24 * 60 * 60,
        stale=True,
        source_reliability_score=0.98,
    )

    assert stale_but_reliable.stale is True
    assert stale_but_reliable.source_reliability_score == 0.98


def test_pr1064_budget_exhaustion_is_unavailable_not_catalyst_absence() -> None:
    diagnostics = RetrievalDiagnostics(
        retrieval_status="budget_exhausted",
        provider_available=None,
        budget_exhausted=True,
        unresolved_symbols=("MISS",),
    )
    summary = NewsEvidenceSummary(
        symbol="MISS",
        retrieval_status="budget_exhausted",
        budget_exhausted=True,
        provider_available=None,
    )

    assert diagnostics.unavailable is True
    assert summary.retrieval_unavailable is True
    assert "catalyst_present" not in {field.name for field in fields(NewsEvidenceSummary)}
    assert "no_catalyst" not in {field.name for field in fields(NewsEvidenceSummary)}


def test_pr1064_unknown_optional_evidence_is_supported() -> None:
    evidence = NewsEvidence(symbol="UNK")

    assert evidence.headline is None
    assert evidence.match_confidence is None
    assert evidence.retrieval_status == "unknown"
    assert evidence.cache_state == "not_checked"


def test_pr1064_strategy_id_does_not_add_strategy_thresholds() -> None:
    request = NewsRequest(
        strategy_id="ross_momentum",
        event_classes=("earnings", "guidance"),
        freshness_seconds=21_600,
        include_generic_news=False,
    )
    request_field_names = {field.name for field in fields(NewsRequest)}

    assert request.strategy_id == "ross_momentum"
    for forbidden in (
        "price_min",
        "price_max",
        "gap_min_pct",
        "float_max_shares",
        "min_volume",
        "rvol_min",
        "focus_rvol_min",
    ):
        assert forbidden not in request_field_names


def test_pr1064_contract_shapes_are_dataclasses_and_provider_is_protocol() -> None:
    for contract in (
        NewsCandidate,
        NewsRequest,
        RetrievalPolicy,
        NewsEvidence,
        NewsEvidenceSummary,
        NewsBatchResult,
        RetrievalDiagnostics,
    ):
        assert is_dataclass(contract)

    assert getattr(NewsIntelligenceProvider, "_is_protocol", False) is True


def test_pr1064_existing_scanner_and_fetcher_wiring_was_not_replaced() -> None:
    scanner_text = SCANNER_RUNNER.read_text(encoding="utf-8")
    fetcher_text = NEWS_FETCHER.read_text(encoding="utf-8")
    registry_text = RSS_REGISTRY.read_text(encoding="utf-8")

    assert "from src.news.news_fetcher import Headline, RssFailureSummary, fetch_fast_headlines_for_symbols, fetch_headlines_for_symbols" in scanner_text
    assert "from src.news.rss_registry import RSS_FAST_TRADING, RSS_PREP_EXTENDED" in scanner_text
    assert "news_intelligence_contract" not in scanner_text
    assert "NewsIntelligenceProvider" not in scanner_text
    assert "news_intelligence_contract" not in fetcher_text
    assert 'RSS_REGISTRY = {' in registry_text


def test_pr1064_architecture_document_records_contract_scope_and_safety() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    for required in (
        "CONTRACT/SCAFFOLD ONLY",
        "NO PRODUCTION NEWS RETRIEVAL BEHAVIOR CHANGE",
        "NO ROSS THRESHOLD CHANGE",
        "NO ROSS FIVE-PILLAR REDEFINITION",
        "ABSOLUTE VOLUME AND RVOL REMAIN DISTINCT",
        "NO CATALYST BYPASS",
        "NO PAPER",
        "NO LIVE",
        "ZERO BROKER ORDER MUTATIONS",
        "PAPER_READY=NO",
        "PAPER_READINESS_GATE=FAIL",
    ):
        assert required in text
