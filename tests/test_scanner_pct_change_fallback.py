from __future__ import annotations

from typing import Optional

from src.scanner.providers.base import IntradayStats, QuoteData, ScannerDataProvider
from src.scanner.scanner_runner import GateThresholds, _build_symbol_context, _evaluate_gates


class _FallbackProvider(ScannerDataProvider):
    source_name = "TEST"

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit: int) -> list[str]:
        return ["AAPL"]

    def get_quote(self, symbol: str) -> QuoteData:
        return QuoteData(
            symbol=symbol,
            bid=109.5,
            ask=110.5,
            last=110.0,
            vwap=109.8,
            open=108.0,
            high=111.0,
            low=107.5,
            close=None,
            change_percent=None,
            volume=150000,
            timestamp_utc="2025-01-01T00:00:00Z",
            data_quality_flags=(),
        )

    def get_prev_close(self, symbol: str) -> Optional[float]:
        return 100.0

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        return IntradayStats(
            current_intraday_volume=150000,
            current_volume_source_label="TEST",
            average_daily_volume_20d=None,
            average_daily_volume_window_days=None,
            relative_volume=3.2,
            relative_volume_category=None,
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="TEST",
        )

    def get_float(self, symbol: str) -> Optional[int]:
        return None


def test_pct_change_fallback_uses_prev_close() -> None:
    provider = _FallbackProvider()
    context = _build_symbol_context(provider, "AAPL", "RTH", {})

    assert context is not None
    assert context["prev_close"] == 100.0
    assert context["pct_change"] == 10.0


def test_scanner_does_not_drop_pct_change_when_prev_close_present() -> None:
    provider = _FallbackProvider()
    context = _build_symbol_context(provider, "AAPL", "RTH", {})
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=500.0,
        min_pct_change=1.0,
        max_pct_change=None,
        watchlist_rvol_min=1.0,
        focus_rvol_min=1.0,
        focus_volume_min=1000,
        focus_volume_min_early_rth=500,
        focus_volume_min_early_rth_ratio=0.5,
        min_volume=1000,
        min_premarket_volume=0,
        max_float=1_000_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=True,
        allow_ssr=True,
        allow_unknown_float=True,
    )

    assert context is not None
    drop_reason = _evaluate_gates(context, thresholds)
    assert drop_reason != "DROP_MISSING_PCT_CHANGE"
    assert drop_reason != "DROP_PCT_CHANGE"
