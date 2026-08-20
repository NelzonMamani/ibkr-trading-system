from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import pytest

from src.config.config_resolver import set_config_overrides
from src.ibkr.market_data_client import MarketDataClient
from src.news.evidence_store import CanonicalNewsEvidenceStore, summarize_news_evidence
from src.news.news_intelligence_contract import (
    NewsBatchResult,
    NewsCandidate,
    NewsEvidence,
    NewsRequest,
    RetrievalDiagnostics,
    RetrievalPolicy,
)
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.scanner import scanner_runner


@pytest.fixture(autouse=True)
def _runtime_defaults(tmp_path: Path):
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides(
        {
            "NEWS_CACHE_FILE": str(tmp_path / "news_cache.json"),
            "NEWS_MAX_ENTRIES_PER_SYMBOL": 5,
            "NEWS_LOOKBACK_HOURS": 24.0,
            "NEWS_REQUEST_TIMEOUT_S": 5,
            "NEWS_TOTAL_BUDGET_S": 8.0,
            "NEWS_EXTENDED_TIER_RESERVE_FRACTION": 0.35,
        }
    )
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({})


def _request() -> NewsRequest:
    return NewsRequest(
        strategy_id="ross_momentum",
        freshness_seconds=60 * 60,
        max_evidence_per_symbol=5,
        need_heat=True,
        need_velocity=True,
        need_reliability=True,
    )


def _evidence(symbol: str, headline: str, *, age_seconds: float, provider: str = "rss_batch") -> NewsEvidence:
    published = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return NewsEvidence(
        symbol=symbol,
        evidence_id=f"{provider}:{symbol}:{abs(hash(headline))}",
        headline=headline,
        url=f"https://news.example/{symbol.lower()}",
        published_at=published,
        fetched_at=datetime.now(timezone.utc),
        first_seen_at=published,
        age_seconds=float(age_seconds),
        stale=age_seconds > 60 * 60,
        observed_source="PR1069 News",
        original_source="PR1069 News",
        provider=provider,
        source_group="FAST_TRADING",
        source_tier="fast",
        match_type="ticker_token",
        matched_field="title",
        verified_source=True,
        cache_state="not_checked",
        retrieval_status="available",
    )


class _FailingProvider:
    calls: list[tuple[str, ...]]

    def __init__(self) -> None:
        self.calls = []

    def get_news(
        self,
        candidates: Sequence[NewsCandidate],
        request: NewsRequest,
        retrieval_policy: RetrievalPolicy,
    ) -> NewsBatchResult:
        self.calls.append(tuple(candidate.normalized_symbol for candidate in candidates))
        raise AssertionError("network provider should not be called")


class _FreshRefreshProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def get_news(
        self,
        candidates: Sequence[NewsCandidate],
        request: NewsRequest,
        retrieval_policy: RetrievalPolicy,
    ) -> NewsBatchResult:
        symbols = tuple(candidate.normalized_symbol for candidate in candidates)
        self.calls.append(symbols)
        evidence_by_symbol = {
            symbol: (_evidence(symbol, f"{symbol} reports earnings beat and raises guidance", age_seconds=120),)
            for symbol in symbols
        }
        summaries = {
            symbol: summarize_news_evidence(
                symbol,
                evidence,
                request=request,
                retrieval_status="available",
                provider_status="available",
                provider_available=True,
                cache_state="not_checked",
            )
            for symbol, evidence in evidence_by_symbol.items()
        }
        return NewsBatchResult(
            candidates=tuple(candidates),
            evidence_by_symbol=evidence_by_symbol,
            summaries_by_symbol=summaries,
            diagnostics=RetrievalDiagnostics(
                retrieval_status="available",
                provider_status="available",
                provider_available=True,
                cache_state="not_checked",
                diagnostics={"provider_id": "fresh_refresh", "rss_sources": 1},
            ),
            request=request,
            retrieval_policy=retrieval_policy,
        )


def test_pr1069_cache_first_reuses_fresh_canonical_evidence_without_network(tmp_path: Path) -> None:
    store = CanonicalNewsEvidenceStore(tmp_path / "news_cache.json")
    store.write({"CACH": [_evidence("CACH", "CACH mentioned in morning market wrap", age_seconds=300)]}, _request())
    failing = _FailingProvider()
    service = CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=failing)

    result = service.get_news(
        [NewsCandidate("CACH")],
        _request(),
        RetrievalPolicy(refresh_mode="bounded_refresh", network_allowed=True),
    )

    assert failing.calls == []
    assert result.evidence_for_symbol("CACH")[0].cache_state == "hit"
    assert result.diagnostics.cache_state == "hit"
    assert result.diagnostics.diagnostics["cache_hit_symbols"] == ["CACH"]
    assert result.diagnostics.diagnostics["refresh_requested_count"] == 0


def test_pr1069_stale_canonical_evidence_refreshes_only_the_stale_symbol(tmp_path: Path) -> None:
    store = CanonicalNewsEvidenceStore(tmp_path / "news_cache.json")
    store.write({"STAL": [_evidence("STAL", "STAL old partnership item", age_seconds=3 * 60 * 60)]}, _request())
    refresh = _FreshRefreshProvider()
    service = CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=refresh)

    result = service.get_news(
        [NewsCandidate("STAL")],
        _request(),
        RetrievalPolicy(refresh_mode="bounded_refresh", network_allowed=True),
    )

    assert refresh.calls == [("STAL",)]
    assert result.summary_for_symbol("STAL").fresh_evidence_count >= 1  # type: ignore[union-attr]
    assert result.diagnostics.diagnostics["stale_cache_miss_symbols"] == ["STAL"]
    assert result.diagnostics.diagnostics["refresh_symbols"] == ["STAL"]
    assert result.diagnostics.diagnostics["cache_write_symbols"] == ["STAL"]


def test_pr1069_prep_evidence_is_reused_by_common_store_and_qualified_by_ross_policy(tmp_path: Path) -> None:
    prep_payload = {
        "symbols": [
            {
                "symbol": "PREP",
                "company_name": "Prep Robotics",
                "news_asof": datetime.now(timezone.utc).isoformat(),
                "news_context": [
                    {
                        "title": "PREP announces new supply contract",
                        "published_at": (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat(),
                        "url": "https://news.example/prep-contract",
                        "source": "PrepWire",
                        "catalyst_tag": "contract_order",
                    }
                ],
            }
        ]
    }
    store = CanonicalNewsEvidenceStore(tmp_path / "news_cache.json", prep_artifact_loader=lambda: prep_payload)
    service = CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=_FailingProvider())

    result = service.get_news(
        [NewsCandidate("PREP", company_name="Prep Robotics")],
        _request(),
        RetrievalPolicy(refresh_mode="cache_only", network_allowed=False),
    )
    context = scanner_runner._ross_news_contexts_from_news_intelligence_result(result)["PREP"]

    assert result.evidence_for_symbol("PREP")[0].provider == "prep_cache"
    assert result.diagnostics.diagnostics["prep_reuse_symbols"] == ["PREP"]
    assert context["news_source_mode"] == "prep_cache"
    assert context["catalyst_type"] == "CONTRACT"
    assert context["ross_catalyst_valid"] is True


def test_pr1069_scanner_migrates_to_news_intelligence_with_unresolved_only_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def headline(symbol: str, title: str, *, source_tier: str = "fast") -> scanner_runner.Headline:
        return scanner_runner.Headline(
            title=title,
            source="PR1069 Feed",
            published_ts=time.time() - 180,
            url=f"https://news.example/{symbol.lower()}",
            source_tier=source_tier,
        )

    def fake_fast(symbols, sources, **kwargs):
        calls.append(("fast", list(symbols)))
        return {
            "FAST": [headline("FAST", "FAST reports earnings beat and raises guidance")],
            "SLOW": [headline("SLOW", "SLOW mentioned in market wrap")],
        }, scanner_runner.RssFailureSummary(
            total_sources=len(sources),
            failure_count=0,
            failures_by_domain={},
                reason=None,
            tier_source_counts={"fast": len(sources)},
            tier_match_counts={"fast": 2},
            ticker_token_match_count=2,
            max_entries_per_symbol=5,
        )

    def fake_extended(symbols, sources, **kwargs):
        calls.append(("extended", list(symbols)))
        return {
            "SLOW": [headline("SLOW", "SLOW receives FDA approval", source_tier="extended")],
        }, scanner_runner.RssFailureSummary(
            total_sources=len(sources),
            failure_count=0,
            failures_by_domain={},
                reason=None,
            tier_source_counts={"extended": len(sources)},
            tier_match_counts={"extended": 1},
            ticker_token_match_count=1,
            max_entries_per_symbol=5,
        )

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["FAST", "SLOW"], "IBKR")

    assert calls == [("fast", ["FAST", "SLOW"]), ("extended", ["SLOW"])]
    assert news_by_symbol["FAST"]["ross_catalyst_valid"] is True
    assert news_by_symbol["SLOW"]["ross_catalyst_valid"] is True
    assert news_by_symbol["SLOW"]["news_source_mode"] == "rss_batch_extended"
    assert diagnostics.news_source_mode == "news_intelligence"
    assert diagnostics.refresh_symbols == ["FAST", "SLOW"]
    assert diagnostics.extended_fallback_symbol_count == 1
    assert diagnostics.source_provenance_by_symbol["SLOW"]
    assert diagnostics.heat_by_symbol["FAST"] is not None
    assert diagnostics.reliability_by_symbol["FAST"] is not None


def test_pr1069_common_news_layer_remains_ross_neutral() -> None:
    common_paths = (
        Path("src/news/evidence_store.py"),
        Path("src/news/news_intelligence_service.py"),
        Path("src/news/batch_rss_adapter.py"),
    )
    forbidden = ("CATALYST_KEYWORDS", "DILUTION_KEYWORDS", "_detect_catalyst_type", "ross_catalyst_valid")

    for path in common_paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text
    scanner_text = Path("src/scanner/scanner_runner.py").read_text(encoding="utf-8")
    assert "CATALYST_KEYWORDS" in scanner_text
    assert "def _detect_catalyst_type" in scanner_text


def test_pr1069_manager_owned_market_data_disconnect_delegates_to_connection_manager() -> None:
    class Manager:
        def __init__(self) -> None:
            self.reasons: list[str] = []

        def disconnect(self, reason: str = "manual") -> None:
            self.reasons.append(reason)

    manager = Manager()
    client = MarketDataClient(connection_manager=manager, allow_direct_connection=False)
    client.ib = object()

    client.disconnect()

    assert manager.reasons == ["market_data_client_disconnect"]
    assert client.ib is None
