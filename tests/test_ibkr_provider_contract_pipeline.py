from __future__ import annotations

from types import SimpleNamespace

from src.scanner.candidate_identity import CandidateIdentity
from src.scanner.providers.ibkr_provider import IbkrScannerProvider


class DummyMarketDataClient:
    def __init__(self) -> None:
        self.connection_manager = object()
        self.snapshot_calls = []
        self.history_calls = []
        self.last_snapshot_debug = {}

    def connect(self):
        return None

    def disconnect(self):
        return None

    def qualifyContracts(self, *contracts):
        return list(contracts)

    def qualify_contract(self, symbol: str):
        return None

    def snapshot_stock(self, contract_or_symbol):
        self.snapshot_calls.append(contract_or_symbol)
        self.last_snapshot_debug = {
            "contract": {
                "symbol": getattr(contract_or_symbol, "symbol", None),
                "conId": getattr(contract_or_symbol, "conId", None),
                "exchange": getattr(contract_or_symbol, "exchange", None),
                "primaryExchange": getattr(contract_or_symbol, "primaryExchange", None),
            },
            "raw_fields": {"last": 10.5, "bid": 10.4, "ask": 10.6, "close": 10.0, "volume": 5000},
            "waited_seconds": 0.4,
            "timeout_occurred": False,
        }
        return SimpleNamespace(
            symbol=getattr(contract_or_symbol, "symbol", "AIM"),
            bid=10.4,
            ask=10.6,
            last=10.5,
            vwap=None,
            open=None,
            high=None,
            low=None,
            close=10.0,
            change_percent=None,
            volume=5000,
            timestamp_utc="2026-03-18T00:00:00Z",
            data_quality_flags=["MD_TIMEOUT"],
        )

    def daily_bars_from_history(self, contract_or_symbol, *, lookback_days: int = 25, use_rth: bool = True, end_datetime: str = ""):
        self.history_calls.append(contract_or_symbol)
        return [SimpleNamespace(date="2026-03-17", close=10.0, volume=1000)]


def test_provider_get_daily_bars_uses_identity_backed_contract():
    client = DummyMarketDataClient()
    provider = IbkrScannerProvider(market_data_client=client)
    identity = CandidateIdentity(
        symbol="AIM",
        con_id=321,
        exchange="SMART",
        primary_exchange="NASDAQ",
        trading_class="AIM",
        currency="USD",
        local_symbol="AIM",
    )

    bars = provider.get_daily_bars(identity, lookback_days=25)

    assert len(bars) == 1
    contract = client.history_calls[0]
    assert contract.conId == 321
    assert contract.primaryExchange == "NASDAQ"


def test_provider_get_quote_uses_symbol_metadata_backed_contract_and_renames_timeout_flag():
    client = DummyMarketDataClient()
    provider = IbkrScannerProvider(market_data_client=client)
    provider.last_scan_details = {
        "symbol_details": {
            "AIM": {
                "conId": 654,
                "exchange": "SMART",
                "primaryExchange": "NASDAQ",
                "tradingClass": "AIM",
                "localSymbol": "AIM",
                "currency": "USD",
            }
        }
    }

    quote = provider.get_quote("AIM")

    contract = client.snapshot_calls[0]
    assert contract.conId == 654
    assert contract.primaryExchange == "NASDAQ"
    assert quote.last == 10.5
    assert "CONTRACT_QUALIFY_FAILED" not in quote.data_quality_flags
    assert "SNAPSHOT_TIMEOUT" in quote.data_quality_flags


class DummyConnectionManager:
    def __init__(self, client):
        self._client = client
        self.calls = 0

    def get_market_data_client(self):
        self.calls += 1
        return self._client


def test_provider_uses_connection_manager_market_data_client_factory():
    client = DummyMarketDataClient()
    manager = DummyConnectionManager(client)

    provider = IbkrScannerProvider(connection_manager=manager)

    assert provider.market_data_client is client
    assert manager.calls == 1
