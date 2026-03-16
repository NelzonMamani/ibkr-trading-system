from __future__ import annotations

from types import SimpleNamespace
import logging

from src.scanner.providers.ibkr_provider import IbkrScannerProvider


class _DummyMarketDataClient:
    def __init__(self, responses_by_location: dict[str, list]) -> None:
        self.responses_by_location = responses_by_location
        self.requested_locations: list[str] = []
        self.connection_manager = object()

    def request_scanner_data(self, subscription):
        self.requested_locations.append(subscription.locationCode)
        return self.responses_by_location.get(subscription.locationCode, [])


class _DummySubscription:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


def _scanner_item(symbol: str):
    contract = SimpleNamespace(
        symbol=symbol,
        conId=123,
        primaryExchange="NASDAQ",
        tradingClass=symbol,
    )
    return SimpleNamespace(contractDetails=SimpleNamespace(contract=contract), rank=1)


def test_get_top_gainers_retries_with_location_fallback_chain(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client = _DummyMarketDataClient(
        {
            "STK.US.MAJOR": [],
            "STK.US.SMART": [],
            "STK.NASDAQ": [_scanner_item("AAPL")],
        }
    )
    provider = IbkrScannerProvider(market_data_client=client)
    monkeypatch.setattr(
        "src.scanner.providers.ibkr_provider.safe_import_ib_insync",
        lambda: (None, None, _DummySubscription),
    )

    symbols = provider.get_top_gainers(limit=10)

    assert symbols == ["AAPL"]
    assert client.requested_locations == ["STK.US.MAJOR", "STK.US.SMART", "STK.NASDAQ"]
    assert "[SCANNER][IBKR][SUCCESS] using_location=STK.NASDAQ symbols=1" in caplog.text


def test_get_top_gainers_logs_fatal_when_all_locations_are_empty(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client = _DummyMarketDataClient(
        {
            "STK.US.MAJOR": [],
            "STK.US.SMART": [],
            "STK.NASDAQ": [],
            "STK.NYSE": [],
        }
    )
    provider = IbkrScannerProvider(market_data_client=client)
    monkeypatch.setattr(
        "src.scanner.providers.ibkr_provider.safe_import_ib_insync",
        lambda: (None, None, _DummySubscription),
    )

    symbols = provider.get_top_gainers(limit=5)

    assert client.requested_locations == [
        "STK.US.MAJOR",
        "STK.US.SMART",
        "STK.NASDAQ",
        "STK.NYSE",
    ]
    assert len(symbols) > 0
    assert "[SCANNER][FATAL] broker returned zero rows across all fallback locations" in caplog.text
