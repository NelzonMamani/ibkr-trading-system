from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from src.scanner import scanner_runner
from src.scanner.candidate_identity import CandidateIdentity
from src.scanner.providers.base import IntradayStats, QuoteData, ScannerDataProvider
from src.scanner.reference_resolver import CanonicalReferenceResolver, HistoricalDailyBar, PersistentReferenceCache
from src.scanner.scanner_runner import GateThresholds, _build_symbol_context, _evaluate_gates, _score_context, reset_scanner_runtime_state


@dataclass(frozen=True)
class _Bar:
    date: str
    close: Optional[float]
    volume: Optional[int]


class _BaseProvider(ScannerDataProvider):
    source_name = "TEST"

    def __init__(self, *, last: float = 110.0, close: Optional[float] = None, volume: int = 150_000, adv20: Optional[int] = 100_000):
        self._last = last
        self._close = close
        self._volume = volume
        self._adv20 = adv20

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit: int) -> list[str]:
        return ["AAPL"]

    def get_quote(self, symbol: str) -> QuoteData:
        return QuoteData(
            symbol=symbol,
            bid=self._last - 0.5,
            ask=self._last + 0.5,
            last=self._last,
            vwap=self._last - 0.2,
            open=self._last - 2.0,
            high=self._last + 1.0,
            low=self._last - 3.0,
            close=self._close,
            change_percent=None,
            volume=self._volume,
            timestamp_utc="2025-01-01T00:00:00Z",
            data_quality_flags=(),
        )

    def get_prev_close(self, symbol: str) -> Optional[float]:
        return None

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        return IntradayStats(
            current_intraday_volume=self._volume,
            current_volume_source_label="TEST",
            average_daily_volume_20d=self._adv20,
            average_daily_volume_window_days=20 if self._adv20 is not None else None,
            relative_volume=3.2 if self._adv20 else None,
            relative_volume_category=None,
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="TEST",
        )

    def get_float(self, symbol: str) -> Optional[int]:
        return 10_000_000

    def get_daily_bars(self, identity, lookback_days: int):
        return []


class _DailyBarProvider(_BaseProvider):
    def get_daily_bars(self, identity, lookback_days: int):
        return [_Bar("2025-01-01", 100.0, 120_000)] * 20


class _WeakSnapshotProvider(_BaseProvider):
    pass


@pytest.fixture(autouse=True)
def _reset_scanner_state() -> None:
    reset_scanner_runtime_state()
    scanner_runner._REFERENCE_RESOLVER.reset_cycle()
    yield
    reset_scanner_runtime_state()
    scanner_runner._REFERENCE_RESOLVER.reset_cycle()


def _thresholds(*, require_catalyst: bool = False) -> GateThresholds:
    return GateThresholds(
        min_price=1.0,
        max_price=500.0,
        min_pct_change=1.0,
        max_pct_change=None,
        watchlist_rvol_min=1.0,
        focus_rvol_min=2.0,
        focus_volume_min=1_000,
        focus_volume_min_early_rth=500,
        focus_volume_min_early_rth_ratio=0.5,
        min_volume=1_000,
        min_premarket_volume=50_000,
        max_float=1_000_000_000,
        spread_max_pct=5.0,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=require_catalyst,
        allow_halts=True,
        allow_ssr=True,
        allow_unknown_float=True,
    )


def test_pct_change_fallback_uses_prev_close() -> None:
    provider = _DailyBarProvider()
    context = _build_symbol_context(provider, "AAPL", "RTH", {})

    assert context is not None
    assert context["prev_close"] == 100.0
    assert context["pct_change"] == 10.0
    assert context["reference_source"] == "IBKR_DAILY_BARS"
    assert context["reference_quality_tier"] == "PRIMARY"
    assert context["pct_change_qualification_usable"] is True


def test_cached_close_fallback_is_degraded_but_qualification_usable(tmp_path: Path) -> None:
    cache = PersistentReferenceCache(tmp_path / "reference_cache.json")
    provider = _DailyBarProvider()
    identity = CandidateIdentity.from_mapping({
        "symbol": "AAPL",
        "conId": 101,
        "secType": "STK",
        "exchange": "SMART",
        "primaryExchange": "NASDAQ",
        "currency": "USD",
        "localSymbol": "AAPL",
    })

    initial = CanonicalReferenceResolver(cache=cache).resolve(
        identity=identity,
        provider=provider,
        session_label="PRE",
        current_volume=150_000,
        intraday_avg_volume_20d=None,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )
    second = CanonicalReferenceResolver(cache=cache).resolve(
        identity=identity,
        provider=provider,
        session_label="PRE",
        current_volume=150_000,
        intraday_avg_volume_20d=None,
        current_last_price=110.0,
        rth_open_price=108.0,
        rth_close_price=None,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )

    assert initial.reference_source == "IBKR_DAILY_BARS"
    assert second.reference_source == "CACHED_CLOSE_FALLBACK"
    assert second.reference_quality_tier == "SECONDARY"
    assert second.qualification_usable_reference is True


def test_snapshot_last_price_fallback_is_continuity_only_in_pre() -> None:
    provider = _WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None)
    context = _build_symbol_context(provider, "AAPL", "PRE", {})

    assert context is not None
    assert context["reference_source"] == "SNAPSHOT_LAST_PRICE_FALLBACK"
    assert context["reference_quality_tier"] == "WEAK"
    assert context["pct_change"] == 0.0
    assert context["pct_change_qualification_usable"] is False
    assert context["watchlist_eligible"] is True
    assert context["execution_eligible"] is False
    assert "PCT_CHANGE_CONTINUITY_ONLY" in context["eligibility_reason_codes"]


def test_pre_missing_pct_change_does_not_hard_drop_when_continuity_only() -> None:
    provider = _WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None)
    context = _build_symbol_context(provider, "AAPL", "PRE", {})
    assert context is not None

    drop_reason = _evaluate_gates(context, _thresholds())
    assert drop_reason != "DROP_MISSING_PCT_CHANGE"
    assert context["degraded_data_profile"] in {"MULTI_FACTOR_DEGRADED", "UNQUALIFIED_CONTINUITY_ONLY"}


def test_pre_missing_rvol_bypass_requires_strong_anchor() -> None:
    provider = _DailyBarProvider()
    context = _build_symbol_context(provider, "AAPL", "PRE", {})
    assert context is not None
    context["rvol"] = None
    context["scanner_rvol"] = None
    context["rvol_phase"] = None
    context["rvol_discovery"] = None
    context["rvol_status"] = "UNKNOWN"
    context["premarket_volume"] = 200_000
    context["volume"] = 200_000
    context["spread_pct"] = 1.0

    assert _evaluate_gates(context, _thresholds()) is None
    assert context["degraded_rvol_gate_bypass"] is True
    assert "PRE_RVOL_BYPASS_APPLIED" in context["eligibility_reason_codes"]


def test_pre_missing_rvol_without_strong_anchor_is_rejected() -> None:
    provider = _WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None)
    context = _build_symbol_context(provider, "AAPL", "PRE", {})
    assert context is not None
    context["rvol"] = None
    context["scanner_rvol"] = None
    context["rvol_phase"] = None
    context["rvol_discovery"] = None
    context["rvol_status"] = "UNKNOWN"
    context["premarket_volume"] = 200_000
    context["volume"] = 200_000
    context["spread_pct"] = 1.0

    assert _evaluate_gates(context, _thresholds()) == "DROP_MISSING_RVOL"


def test_fully_qualified_symbol_outranks_degraded_symbol() -> None:
    qualified = _build_symbol_context(_DailyBarProvider(), "AAPL", "PRE", {})
    degraded = _build_symbol_context(_WeakSnapshotProvider(last=110.0, close=None, volume=180_000, adv20=None), "MSFT", "PRE", {})
    assert qualified is not None and degraded is not None

    qualified_score, _ = _score_context(qualified)
    degraded_score, _ = _score_context(degraded)

    assert qualified_score > degraded_score
    assert degraded["execution_eligible"] is False
