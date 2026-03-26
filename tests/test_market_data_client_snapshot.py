from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from src.ibkr.market_data_client import MarketDataClient
from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from src.scanner.scanner_runner import _build_symbol_context
from src.config.config_resolver import set_config_overrides


class DummyTicker:
    def __init__(self) -> None:
        self.bid = None
        self.ask = None
        self.last = None
        self.lastSize = None
        self.bidSize = None
        self.askSize = None
        self.volume = None
        self.vwap = None
        self.high = None
        self.low = None
        self.close = None
        self.open = None
        self.changePercent = None
        self.time = None


class DummyIB:
    def __init__(self) -> None:
        self.wait_calls = 0
        self.cancelled = False
        self.cancel_snapshot = {}
        self.qualified = False
        self.ticker = DummyTicker()

    def isConnected(self):
        return True

    async def qualifyContractsAsync(self, contract):  # noqa: N802 - IBKR naming
        self.qualified = True
        return [contract]

    def run(self, awaitable):
        return asyncio.run(awaitable)

    def reqMktData(self, contract, genericTickList="", snapshot=True, regulatorySnapshot=False):
        return self.ticker

    def waitOnUpdate(self, timeout=0.2):
        self.wait_calls += 1
        if self.wait_calls == 2:
            self.ticker.last = 101.0
            self.ticker.close = 100.0
        if self.wait_calls == 3:
            self.ticker.volume = 12000
        return True

    def cancelMktData(self, contract):
        self.cancelled = True
        self.cancel_snapshot = {
            "last": self.ticker.last,
            "close": self.ticker.close,
            "volume": self.ticker.volume,
        }

    def qualifyContracts(self, *contracts):
        return list(contracts)


class DummyConnectionManager:
    def __init__(self, client):
        self._client = client

    def get_client(self):
        return self._client


def _client_with_dummy_ib() -> MarketDataClient:
    client = MarketDataClient(snapshot_timeout_seconds=1)
    dummy_ib = DummyIB()
    client.ib = dummy_ib
    client.connection_manager = DummyConnectionManager(dummy_ib)
    return client


def test_snapshot_waits_for_required_ticks_before_cancel():
    client = _client_with_dummy_ib()

    snapshot = client.snapshot_stock("AAPL")

    dummy = client.ib
    assert dummy.qualified is True
    assert dummy.cancelled is False
    assert snapshot.last == 101.0
    assert snapshot.close == 100.0
    assert snapshot.volume == 12000


def test_snapshot_stock_accepts_qualified_contract_without_requalification():
    client = _client_with_dummy_ib()
    contract = type("Contract", (), {
        "symbol": "AAPL",
        "conId": 123,
        "exchange": "SMART",
        "primaryExchange": "NASDAQ",
        "tradingClass": "NMS",
        "localSymbol": "AAPL",
    })()

    snapshot = client.snapshot_stock(contract)

    assert snapshot.symbol == "AAPL"
    assert client.last_snapshot_debug["contract"]["conId"] == 123
    assert client.last_snapshot_debug["contract"]["primaryExchange"] == "NASDAQ"


def test_live_snapshot_populates_pct_change_before_gating():
    client = _client_with_dummy_ib()
    provider = IbkrScannerProvider(market_data_client=client)

    context = _build_symbol_context(provider=provider, symbol="AAPL", session_label="RTH", float_cache={})

    assert context is not None
    assert context["pct_change"] is not None
    assert context["volume"] is not None


def test_snapshot_flags_delayed_frozen_and_stale():
    set_config_overrides({"IBKR_SNAPSHOT_MAX_AGE_SECONDS": 1})
    try:
        client = _client_with_dummy_ib()
        client.market_data_type = "DELAYED_FROZEN"
        client.ib.ticker.time = datetime.now(timezone.utc) - timedelta(seconds=120)

        snapshot = client.snapshot_stock("AAPL")

        assert "MD_DELAYED" in snapshot.data_quality_flags
        assert "MD_FROZEN" in snapshot.data_quality_flags
        assert "MD_STALE" in snapshot.data_quality_flags
    finally:
        set_config_overrides(None)


class HistoryDummyIB(DummyIB):
    def __init__(self) -> None:
        super().__init__()
        self.history_calls = []

    def reqHistoricalData(self, contract, endDateTime="", durationStr="3 D", barSizeSetting="1 day", whatToShow="TRADES", useRTH=True, formatDate=1):
        self.history_calls.append({"endDateTime": endDateTime, "durationStr": durationStr, "useRTH": useRTH})
        if useRTH:
            return []
        return [type("Bar", (), {"close": 99.0, "volume": 1000})()]


def test_history_helpers_retry_with_use_rth_false_when_primary_returns_zero_bars():
    client = MarketDataClient(snapshot_timeout_seconds=1)
    dummy_ib = HistoryDummyIB()
    client.ib = dummy_ib
    client.connection_manager = DummyConnectionManager(dummy_ib)

    prev_close = client.prev_close_from_history("AAPL", use_rth=True)
    avg_volume, window = client.average_daily_volume_from_history("AAPL", window=1, use_rth=True)

    assert prev_close == 99.0
    assert avg_volume == 1000
    assert window == 1
    assert dummy_ib.history_calls[0]["useRTH"] is True
    assert dummy_ib.history_calls[1]["useRTH"] is False


class FallbackDummyIB(DummyIB):
    async def qualifyContractsAsync(self, contract):  # noqa: N802 - IBKR naming
        raise RuntimeError("loop broken")


def test_snapshot_qualification_falls_back_to_sync_when_async_fails():
    client = MarketDataClient(snapshot_timeout_seconds=1)
    dummy_ib = FallbackDummyIB()
    client.ib = dummy_ib
    client.connection_manager = DummyConnectionManager(dummy_ib)

    contract = client.qualify_contract("AAPL")

    assert contract.symbol == "AAPL"
