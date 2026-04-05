from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.ibkr.market_data_client import MarketDataClient
from src.scanner.providers.base import IntradayStats, QuoteData, ScannerDataProvider
from src.scanner.scanner_runner import GateThresholds, _build_symbol_context, _evaluate_watchlist_gates


class _Ticker:
    def __init__(self) -> None:
        self.bid = 10.0
        self.ask = 10.1
        self.last = 10.05
        self.lastSize = 100
        self.bidSize = 100
        self.askSize = 100
        self.volume = 10_000
        self.vwap = 10.02
        self.high = 10.2
        self.low = 9.8
        self.close = 9.9
        self.open = 9.95
        self.changePercent = 1.5
        self.time = datetime.now(timezone.utc)
        self.marketDataType = 3


class _IB:
    def __init__(self) -> None:
        self.ticker = _Ticker()

    def isConnected(self):
        return True

    def run(self, awaitable):
        return asyncio.run(awaitable)

    async def qualifyContractsAsync(self, contract):  # noqa: N802
        return [contract]

    def qualifyContracts(self, *contracts):
        return list(contracts)

    def reqMarketDataType(self, _code):
        return None

    def reqMktData(self, contract, genericTickList="", snapshot=True, regulatorySnapshot=False):
        return self.ticker

    def waitOnUpdate(self, timeout=0.2):
        return True

    def cancelMktData(self, contract):
        return None


class _Mgr:
    def __init__(self, ib):
        self._ib = ib

    def get_client(self):
        return self._ib


@dataclass(frozen=True)
class _Bar:
    date: str
    close: Optional[float]
    volume: Optional[int]


class _Provider(ScannerDataProvider):
    source_name = "TEST"

    def __init__(self, quote: QuoteData):
        self._quote = quote

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit: int, request=None) -> list[str]:
        return ["AAPL"]

    def get_quote(self, symbol: str) -> QuoteData:
        return self._quote

    def get_prev_close(self, symbol: str) -> Optional[float]:
        return None

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        return IntradayStats(
            current_intraday_volume=100_000,
            current_volume_source_label="TEST",
            average_daily_volume_20d=100_000,
            average_daily_volume_window_days=20,
            relative_volume=1.0,
            relative_volume_category=None,
            volume_velocity_5m=None,
            volume_velocity_15m=None,
            volume_data_quality_flag="TEST",
        )

    def get_float(self, symbol: str) -> Optional[int]:
        return 10_000_000

    def get_previous_rth_close(self, identity) -> Optional[float]:
        return 10.0

    def get_average_daily_volume(self, identity, window: int):
        return (100_000, 20)

    def get_daily_bars(self, identity, lookback_days: int):
        return [_Bar("2025-01-02", 10.0, 100_000)] * 20


def _thresholds() -> GateThresholds:
    return GateThresholds(
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
        min_premarket_volume=1000,
        max_float=1_000_000_000,
        spread_max_pct=5.0,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=True,
        allow_ssr=True,
        allow_unknown_float=True,
    )


def test_snapshot_attaches_effective_market_data_type_and_integrity_state():
    client = MarketDataClient(snapshot_timeout_seconds=1)
    ib = _IB()
    client.ib = ib
    client.connection_manager = _Mgr(ib)

    snap = client.snapshot_stock("AAPL")

    assert snap.market_data_type_effective == "DELAYED"
    assert snap.market_data_type_requested in {"LIVE", "DELAYED", "FROZEN", "DELAYED_FROZEN"}
    assert snap.quote_integrity_state == "VALID_DELAYED"
    assert snap.has_valid_last is True


def test_invalid_last_never_becomes_canonical_price_and_pct_is_unavailable():
    quote = QuoteData(
        symbol="AAPL",
        bid=10.0,
        ask=10.2,
        last=-1.0,
        vwap=10.1,
        open=9.8,
        high=10.3,
        low=9.7,
        close=9.9,
        change_percent=2.0,
        volume=100_000,
        timestamp_utc="2026-01-01T00:00:00Z",
        data_quality_flags=(),
        has_valid_last=False,
        has_valid_bid=True,
        has_valid_ask=True,
        quote_integrity_state="INVALID_MISSING_LAST",
        integrity_flags=("INVALID_LAST",),
    )
    context = _build_symbol_context(provider=_Provider(quote), symbol="AAPL", session_label="RTH", float_cache={})

    assert context is not None
    assert context["canonical_last_price"] is None
    assert context["pct_change"] is None
    assert context["pct_change_available"] is False
    assert context["reference_prev_close"] is not None


def test_spread_skipped_when_bid_ask_invalid():
    quote = QuoteData(
        symbol="AAPL",
        bid=-1.0,
        ask=-1.0,
        last=10.0,
        vwap=10.0,
        open=9.8,
        high=10.1,
        low=9.7,
        close=9.9,
        change_percent=1.0,
        volume=120_000,
        timestamp_utc="2026-01-01T00:00:00Z",
        data_quality_flags=(),
        has_valid_last=True,
        has_valid_bid=False,
        has_valid_ask=False,
        quote_integrity_state="INVALID_NO_BID_ASK",
        integrity_flags=("INVALID_BID_ASK",),
    )
    context = _build_symbol_context(provider=_Provider(quote), symbol="AAPL", session_label="RTH", float_cache={})

    assert context is not None
    assert context["spread"] is None
    assert context["spread_pct"] is None
    assert context["spread_available"] is False


def test_watchlist_gate_drops_invalid_quote_with_integrity_reason():
    quote = QuoteData(
        symbol="AAPL",
        bid=10.0,
        ask=10.2,
        last=None,
        vwap=None,
        open=None,
        high=None,
        low=None,
        close=9.9,
        change_percent=None,
        volume=0.0,
        timestamp_utc="2026-01-01T00:00:00Z",
        data_quality_flags=(),
        has_valid_last=False,
        has_valid_bid=True,
        has_valid_ask=True,
        quote_integrity_state="INVALID_MISSING_LAST",
        integrity_flags=("INVALID_LAST",),
    )
    context = _build_symbol_context(provider=_Provider(quote), symbol="AAPL", session_label="RTH", float_cache={})

    assert context is not None
    reason = _evaluate_watchlist_gates(context, _thresholds())
    assert reason == "DROP_INVALID_QUOTE"


def test_fractional_share_warning_not_treated_as_quote_corruption():
    client = MarketDataClient(snapshot_timeout_seconds=1)
    category = client._classify_market_data_error(2176, "Fractional shares are not supported")
    assert category == "FRACTIONAL_SHARE_WARNING"
