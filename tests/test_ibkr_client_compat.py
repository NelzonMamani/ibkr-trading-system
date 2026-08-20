from __future__ import annotations

import threading
import time

from ibapi.client import EClient
from ibapi.contract import Contract, ContractDetails

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.market_data.market_snapshot_enricher import MarketSnapshotEnricher


class DummyConnectionManager:
    def __init__(self, client):
        self._client = client

    def get_client(self):
        return self._client


def _build_client() -> IbkrClient:
    return IbkrClient(
        host="127.0.0.1",
        port=4001,
        client_id=1,
        snapshot_timeout_seconds=1,
        market_data_type="DELAYED",
        readonly_enabled=True,
    )


def test_qualify_contracts_compatibility(monkeypatch):
    client = _build_client()

    def fake_resolve(symbol: str, exchange: str = "SMART", currency: str = "USD"):
        resolved = Contract()
        resolved.symbol = symbol
        resolved.secType = "STK"
        resolved.exchange = exchange
        resolved.currency = currency
        resolved.conId = 12345
        resolved.primaryExchange = "NASDAQ"
        resolved.tradingClass = symbol
        resolved.localSymbol = symbol

        details = ContractDetails()
        details.contract = resolved
        return details

    monkeypatch.setattr(client, "resolve_contract", fake_resolve)

    requested = Contract()
    requested.symbol = "AAPL"
    requested.secType = "STK"
    requested.exchange = "SMART"
    requested.currency = "USD"

    qualified = client.qualifyContracts(requested)

    assert len(qualified) == 1
    assert qualified[0].symbol == "AAPL"
    assert qualified[0].conId == 12345
    assert qualified[0].primaryExchange == "NASDAQ"


def test_req_mkt_data_compatibility_wrapper(monkeypatch):
    client = _build_client()
    captured = {}

    def fake_req_mkt_data(self, req_id, contract, generic_tick_list, snapshot, regulatory_snapshot, options):
        captured["args"] = (req_id, contract.symbol, generic_tick_list, snapshot, regulatory_snapshot, options)

    def fake_cancel_mkt_data(self, req_id):
        captured["cancel_req_id"] = req_id

    monkeypatch.setattr(EClient, "reqMktData", fake_req_mkt_data)
    monkeypatch.setattr(EClient, "cancelMktData", fake_cancel_mkt_data)

    contract = Contract()
    contract.symbol = "MSFT"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"

    ticker = client.reqMktData(contract, genericTickList="", snapshot=True, regulatorySnapshot=False)
    req_id = captured["args"][0]

    client.tickPrice(req_id, 1, 100.5, None)
    client.tickPrice(req_id, 2, 101.0, None)
    client.tickPrice(req_id, 4, 100.8, None)
    client.tickSize(req_id, 8, 500)

    assert captured["args"][1:] == ("MSFT", "", True, False, [])
    assert client.waitOnUpdate(timeout=0.01) is True
    assert ticker.bid == 100.5
    assert ticker.ask == 101.0
    assert ticker.last == 100.8
    assert ticker.volume == 500.0

    client.cancelMktData(contract)
    assert captured["cancel_req_id"] == req_id


def test_snapshot_enricher_uses_ib_style_req_mkt_data_without_signature_error(monkeypatch):
    client = _build_client()

    def fake_resolve(symbol: str, exchange: str = "SMART", currency: str = "USD"):
        resolved = Contract()
        resolved.symbol = symbol
        resolved.secType = "STK"
        resolved.exchange = exchange
        resolved.currency = currency
        resolved.conId = 555
        details = ContractDetails()
        details.contract = resolved
        return details

    def fake_req_mkt_data(self, req_id, contract, generic_tick_list, snapshot, regulatory_snapshot, options):
        self.tickPrice(req_id, 4, 123.45, None)
        self.tickPrice(req_id, 1, 123.4, None)
        self.tickPrice(req_id, 2, 123.5, None)
        self.tickSize(req_id, 8, 2000)

    monkeypatch.setattr(client, "resolve_contract", fake_resolve)
    monkeypatch.setattr(EClient, "reqMktData", fake_req_mkt_data)
    monkeypatch.setattr(EClient, "cancelMktData", lambda self, req_id: None)

    enricher = MarketSnapshotEnricher(connection_manager=DummyConnectionManager(client), batch_timeout_seconds=0.5)
    snapshots = enricher.fetch_snapshots(["AAPL"])
    diag = enricher.last_fetch_diagnostics["AAPL"]

    assert diag["qualified_ok"] is True
    assert diag["snapshot_received"] is True
    assert "reqMktData:" not in str(diag.get("exception") or "")
    assert snapshots["AAPL"]["last_price"] == 123.45
    assert snapshots["AAPL"]["bid"] == 123.4
    assert snapshots["AAPL"]["ask"] == 123.5
    assert snapshots["AAPL"]["volume"] == 2000.0


def test_req_historical_data_returns_bars_when_data_arrives_before_end_signal(monkeypatch):
    client = _build_client()
    client.snapshot_timeout_seconds = 0.2

    contract = Contract()
    contract.symbol = "AAPL"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"

    def fake_req_historical_data(
        self,
        req_id,
        _contract,
        end_date_time,
        duration_str,
        bar_size_setting,
        what_to_show,
        use_rth,
        format_date,
        keep_up_to_date,
        chart_options,
    ):
        def deliver():
            time.sleep(0.05)
            client.historicalData(req_id, {"close": 123.45})

        threading.Thread(target=deliver, daemon=True).start()

    monkeypatch.setattr(EClient, "reqHistoricalData", fake_req_historical_data)

    bars = client.reqHistoricalData(contract)

    assert bars == [{"close": 123.45}]


def test_disconnect_skips_join_when_called_from_network_thread(monkeypatch):
    client = _build_client()
    client._thread = threading.current_thread()

    monkeypatch.setattr(EClient, "disconnect", lambda self: None)

    client.disconnect()


def test_run_loop_treats_shutdown_self_join_error_as_normal_exit(monkeypatch, capsys):
    client = _build_client()
    client._stop_event.set()

    def raise_self_join(_self):
        raise RuntimeError("cannot join current thread")

    monkeypatch.setattr(EClient, "run", raise_self_join)

    client._run_loop()

    assert "Network loop error" not in capsys.readouterr().out
