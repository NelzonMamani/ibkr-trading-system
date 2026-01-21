from __future__ import annotations

import asyncio

from src.ibkr.market_data_client import MarketDataClient
from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from src.scanner.scanner_runner import _build_symbol_context


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


class DummyIB:
    def __init__(self) -> None:
        self.wait_calls = 0
        self.cancelled = False
        self.cancel_snapshot = {}
        self.qualified = False
        self.ticker = DummyTicker()

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


def _client_with_dummy_ib() -> MarketDataClient:
    client = MarketDataClient(snapshot_timeout_seconds=1)
    client.ib = DummyIB()
    return client


def test_snapshot_waits_for_required_ticks_before_cancel():
    client = _client_with_dummy_ib()

    snapshot = client.snapshot_stock("AAPL")

    dummy = client.ib
    assert dummy.qualified is True
    assert dummy.cancelled is True
    assert dummy.cancel_snapshot["last"] == 101.0
    assert dummy.cancel_snapshot["close"] == 100.0
    assert dummy.cancel_snapshot["volume"] == 12000
    assert snapshot.last == 101.0
    assert snapshot.close == 100.0
    assert snapshot.volume == 12000


def test_live_snapshot_populates_pct_change_before_gating():
    client = _client_with_dummy_ib()
    provider = IbkrScannerProvider(market_data_client=client)

    context = _build_symbol_context(provider, "AAPL", "RTH", {})

    assert context is not None
    assert context["pct_change"] is not None
    assert context["volume"] is not None
