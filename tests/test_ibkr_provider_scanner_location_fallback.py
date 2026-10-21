from __future__ import annotations

from types import SimpleNamespace
import logging
import pytest
from src.config.runtime_config import RunMode

from src.scanner.providers.ibkr_provider import IbkrScannerProvider


class _DummyMarketDataClient:
    def __init__(self, responses_by_location: dict[str, list]) -> None:
        self.responses_by_location = responses_by_location
        self.requested_locations: list[str] = []
        self.requested_rows: list[int] = []
        self.connection_manager = object()

    def request_scanner_data(self, subscription):
        self.requested_locations.append(subscription.locationCode)
        self.requested_rows.append(subscription.numberOfRows)
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
    assert client.requested_rows == [10, 10, 10]
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

    assert client.requested_locations[:4] == [
        "STK.US.MAJOR",
        "STK.US.SMART",
        "STK.NASDAQ",
        "STK.NYSE",
    ]
    assert client.requested_rows
    assert set(client.requested_rows) == {5}
    assert len(client.requested_locations) > 4
    assert symbols == []
    assert "[SCANNER][FATAL] broker returned zero rows across all fallback locations" in caplog.text


@pytest.mark.parametrize("mode,scanner,enabled,configured", [
    (RunMode.READ_ONLY,"LIVE_READONLY",False,[]),
    (RunMode.READ_ONLY,"TEACHING",True,["INJECT"]),
    (RunMode.LIVE,"TEACHING",True,["INJECT"]),
    (RunMode.SIM,"TEACHING",False,["INJECT"]),
    (RunMode.PAPER,"LIVE_READONLY",True,["INJECT"]),
    (RunMode.SIM,"TEACHING",True,[]),
    (RunMode.PAPER,"TEACHING",True,["FIXTURE"]),
])
def test_empty_broker_preserved_except_explicit_teaching(monkeypatch,mode,scanner,enabled,configured):
    import src.scanner.providers.ibkr_provider as module
    monkeypatch.setattr(module,"safe_import_ib_insync",lambda:(None,None,_DummySubscription))
    monkeypatch.setattr(module,"get_run_mode",lambda:mode)
    monkeypatch.setattr(module,"get_scanner_mode",lambda:scanner)
    monkeypatch.setattr(module,"get_ibkr_fallback_enabled",lambda:enabled)
    monkeypatch.setattr(module,"get_scanner_symbols",lambda **kwargs:configured)
    client=_DummyMarketDataClient({})
    provider=IbkrScannerProvider(market_data_client=client)
    symbols=provider.get_top_gainers(2)
    allowed=enabled and scanner=="TEACHING" and mode in {RunMode.SIM,RunMode.PAPER}
    assert symbols == ((configured or ["AAPL","MSFT"])[:2] if allowed else [])
    assert provider.last_scan_details['returned_rows']==0
    assert provider.last_scan_details['symbols']==[]  # Never relabel teaching as broker facts.


def test_natural_universe_resolution_keeps_empty_broker_result(monkeypatch):
    import src.scanner.providers.ibkr_provider as module
    from src.scanner.scanner_runner import _resolve_universe_symbols
    from src.scanner.scanner_contract import ScannerRequest
    from src.strategies.ross_momentum.strategy_policy import UniverseSource
    monkeypatch.setattr(module,"safe_import_ib_insync",lambda:(None,None,_DummySubscription))
    monkeypatch.setattr(module,"get_run_mode",lambda:RunMode.READ_ONLY)
    monkeypatch.setattr(module,"get_ibkr_fallback_enabled",lambda:False)
    monkeypatch.setattr(module,"get_scanner_symbols",lambda **kwargs:["INJECT"])
    provider=IbkrScannerProvider(market_data_client=_DummyMarketDataClient({}))
    request=ScannerRequest('ross_momentum','ROSS_MOMENTUM','GAINERS','RTH',
        UniverseSource.IBKR_TOP_GAINERS,'TOP_PERC_GAIN',50)
    diagnostics={}
    assert _resolve_universe_symbols(provider=provider,request=request,
        limits={'resolved_symbol_limit':50},diagnostics=diagnostics,allow_mock_fallback=False)==[]
    assert diagnostics['ibkr_universe']['ibkr_returned_count']==0
