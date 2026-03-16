from __future__ import annotations

from src.scanner.scanner_contract import ScannerRequest
from src.scanner.scanner_runner import _resolve_universe_symbols
from src.strategies.ross_momentum.strategy_policy import UniverseSource


class _MetadataProvider:
    source_name = "IBKR"

    def __init__(self) -> None:
        self.last_scan_details = {}

    def get_top_gainers(self, limit, request=None):
        self.last_scan_details = {
            "requested_location_code": "STK.US",
            "requested_scan_code": "TOP_PERC_GAIN",
            "selected_location_code": "STK.NASDAQ",
            "selected_scan_code": "TOP_PERC_GAIN",
            "retry_attempts": 2,
            "retry_exhausted": False,
            "returned_rows": 1,
            "symbols": ["AAPL"],
            "symbol_details": {
                "AAPL": {
                    "conId": 1,
                    "primaryExchange": "NASDAQ",
                    "tradingClass": "NMS",
                }
            },
        }
        return ["AAPL"]


def test_resolve_universe_symbols_uses_provider_fallback_metadata() -> None:
    provider = _MetadataProvider()
    diagnostics = {}
    limits = {
        "resolved_symbol_limit": 10,
        "reductions": [],
    }
    request = ScannerRequest(
        strategy_name="test",
        policy_name="test",
        ranking_intent="test",
        session_phase="RTH",
        universe_source=UniverseSource.IBKR_TOP_GAINERS,
        ibkr_scan_code="TOP_PERC_GAIN",
        requested_top_n=10,
        above_price=1,
        below_price=20,
        region="US",
        instrument="STK",
        location_code="STK.US",
        exchanges=["SMART"],
    )

    symbols = _resolve_universe_symbols(
        provider=provider,
        request=request,
        limits=limits,
        diagnostics=diagnostics,
        allow_mock_fallback=False,
    )

    assert symbols == ["AAPL"]
    assert diagnostics["ibkr_universe"]["effective_location_code"] == "STK.NASDAQ"
    assert diagnostics["ibkr_universe"]["retry_attempts"] == 2
    assert diagnostics["ibkr_universe"]["ibkr_returned_count"] > 0

from src.scanner.providers.base import IntradayStats, QuoteData
from src.scanner.scanner_runner import run_scanner_cycle


class _RuntimeMetadataProvider(_MetadataProvider):
    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_quote(self, symbol: str) -> QuoteData:
        return QuoteData(
            symbol=symbol,
            bid=10.0,
            ask=10.1,
            last=10.05,
            vwap=10.0,
            open=9.8,
            high=10.2,
            low=9.7,
            close=9.9,
            change_percent=1.5,
            volume=2_000_000,
            timestamp_utc="2026-01-01T14:30:00Z",
            data_quality_flags=(),
        )

    def get_prev_close(self, symbol: str):
        return 9.9

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        return IntradayStats(
            current_intraday_volume=2_000_000,
            current_volume_source_label="TEST",
            average_daily_volume_20d=1_000_000,
            average_daily_volume_window_days=20,
            relative_volume=2.0,
            relative_volume_category="HIGH",
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="TEST",
        )

    def get_float(self, symbol: str):
        return 10_000_000


def test_run_scanner_cycle_flow_uses_provider_metadata() -> None:
    payload = run_scanner_cycle(mode="READ_ONLY", provider=_RuntimeMetadataProvider())
    flow = payload["diagnostics"]["scanner_flow"]

    assert flow["effective_location_code"] == "STK.NASDAQ"
    assert flow["retry_attempts"] == 2
    assert flow["raw_broker_count"] > 0
