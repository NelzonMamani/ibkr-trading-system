"""Offline broker callback authority; no network or order operations."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from ibapi.client import EClient
from ibapi.contract import Contract
from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.ibkr import market_data_client as md


def contract():
    c = Contract()
    c.symbol, c.secType, c.exchange, c.currency, c.conId = "AEMD", "STK", "SMART", "USD", 123
    return c


@pytest.fixture
def native(monkeypatch):
    monkeypatch.setattr(EClient, "reqMktData", lambda *args, **kwargs: None)
    monkeypatch.setattr(EClient, "reqMarketDataType", lambda *args: None)
    monkeypatch.setattr(EClient, "cancelMktData", lambda *args: None)
    return IbkrClient("127.0.0.1", 7497, 1, 0.01, "DELAYED", True)


def client_for(ib):
    client = md.MarketDataClient.__new__(md.MarketDataClient)
    client.market_data_type = "DELAYED"
    client.snapshot_timeout_seconds = 0.1
    client._recent_error_codes = {}
    client._resolve_ib_client = lambda: ib
    client._canonicalize_history_contract = lambda value: value
    return client


def native_ticks(ib, req_id, *, returned=1, ended=True, missing=False):
    if returned is not None:
        ib.marketDataType(req_id, returned)
    for kind, value in [(66, -1 if missing else 5.0), (67, -1 if missing else 5.1), (68, 5.05), (75, 4.8)]:
        ib.tickPrice(req_id, kind, value, None)
    ib.tickSize(req_id, 74, 0)
    ib.tickString(req_id, 88, "1789990000")
    if ended:
        ib.tickSnapshotEnd(req_id)


@pytest.mark.parametrize("returned", [1, 2, 3, 4, None])
def test_native_callback_type_and_completed_fields_are_retained(native, monkeypatch, returned):
    monkeypatch.setattr(native, "resolve_contract", lambda symbol: SimpleNamespace(contract=contract()))
    def send(self, req_id, *args):
        native_ticks(self, req_id, returned=returned)
    monkeypatch.setattr(EClient, "reqMktData", send)
    snapshot = native.get_market_snapshot("AEMD")
    assert snapshot.requested_market_data_type == "DELAYED"
    assert snapshot.returned_market_data_type == {1:"LIVE", 2:"FROZEN", 3:"DELAYED", 4:"DELAYED_FROZEN", None:"UNKNOWN"}[returned]
    assert snapshot.market_data_type_confirmed is (returned is not None)
    assert snapshot.request_id == 1
    assert snapshot.snapshot_complete is True
    assert snapshot.snapshot_completed_at_utc is not None
    assert snapshot.request_started_at_utc <= snapshot.request_completed_at_utc
    assert snapshot.field_availability["bid"] is True
    assert snapshot.field_received_at_utc["bid"]
    assert snapshot.volume == 0
    assert snapshot.market_timestamp_utc == datetime.fromtimestamp(1789990000, timezone.utc)
    assert not native._active_market_req_ids


def test_partial_price_does_not_end_snapshot_or_replace_last_with_close(native):
    ticker = native.reqMktData(contract(), snapshot=True)
    native.tickPrice(ticker.reqId, 9, 4.8, None)
    assert ticker.last is None
    assert ticker.close == 4.8
    assert ticker.snapshotEnd is False
    assert not native._market_events[ticker.reqId].is_set()


def test_completed_snapshot_cleans_up_without_redundant_wire_cancel(native, monkeypatch):
    cancels = []
    monkeypatch.setattr(EClient, "cancelMktData", lambda self, req_id: cancels.append(req_id))
    ticker = native.reqMktData(contract(), snapshot=True)
    native.tickSnapshotEnd(ticker.reqId)
    native.cancelMktData(ticker.reqId)
    assert cancels == []
    assert ticker.reqId not in native._ticker_by_req_id
    native.tickPrice(ticker.reqId, 4, 999, None)
    assert ticker.last is None


def test_native_missing_sentinels_and_request_error_are_truthful(native, monkeypatch):
    monkeypatch.setattr(native, "resolve_contract", lambda symbol: SimpleNamespace(contract=contract()))
    def send(self, req_id, *args):
        native_ticks(self, req_id, ended=False, missing=True)
        self.error(req_id, 10197, "Competing session")
    monkeypatch.setattr(EClient, "reqMktData", send)
    result = native.get_market_snapshot("AEMD")
    assert result.bid is None and result.ask is None
    assert result.snapshot_complete is False
    assert result.completion_reason == "broker_error"
    assert result.snapshot_completed_at_utc is None
    assert result.missing_fields_observed_at_utc["bid"] == result.request_completed_at_utc
    assert result.broker_errors[0]["req_id"] == result.request_id
    assert result.broker_errors[0]["symbol"] == "AEMD"
    assert result.broker_errors[0]["timestamp_utc"]
    assert "MD_CONFLICT_10197" in result.data_quality_flags


def test_native_timeout_is_not_snapshot_completion(native, monkeypatch):
    monkeypatch.setattr(native, "resolve_contract", lambda symbol: SimpleNamespace(contract=contract()))
    result = native.get_market_snapshot("AEMD")
    assert result.snapshot_complete is False
    assert result.returned_market_data_type == "UNKNOWN"
    assert result.completion_reason == "timeout"
    assert "MD_TIMEOUT" in result.data_quality_flags
    assert result.market_timestamp_utc is None


def test_historical_integer_request_retains_contract_context(native, monkeypatch):
    monkeypatch.setattr(EClient, "reqHistoricalData", lambda *args, **kwargs: None)
    native.reqHistoricalData(99, contract(), "", "1 D", "1 min", "TRADES", 1, 1, False, [])
    native.error(99, 200, "No security definition")
    assert native._broker_error_events[-1]["symbol"] == "AEMD"
    assert native._broker_error_events[-1]["request_type"] == "HISTORICAL_DATA"


class OfflineInsync:
    def __init__(self, steps):
        IB, _, _ = md.safe_import_ib_insync()
        self.sdk = IB()
        self.wrapper = self.sdk.wrapper
        self.steps = steps
        self.requested = []
        self.cancelled = []
        self.req_id = 0
        self.tick = 0
    def reqMarketDataType(self, mode):
        self.requested.append(mode)
    def reqMktData(self, c, **kwargs):
        self.req_id += 1
        self.tick = 0
        return self.wrapper.startTicker(self.req_id, c, "mktData")
    def waitOnUpdate(self, timeout):
        self.tick += 1
        self.steps(self, self.tick)
    def cancelMktData(self, c):
        ticker = self.wrapper.tickers[id(c)]
        self.cancelled.append(self.wrapper.endTicker(ticker, "mktData"))


def sdk_fields(ib, *, confirmed=True, complete=True, missing=False):
    w, req = ib.wrapper, ib.req_id
    if confirmed:
        w.marketDataType(req, 1)
    for kind, value in [(1,-1 if missing else 5.0), (2,-1 if missing else 5.1), (4,5.05), (9,4.8)]:
        w.priceSizeTick(req, kind, value, 1)
    w.tickSize(req, 8, 0)
    w.tickString(req, 45, "1789990000")
    if complete:
        w.tickSnapshotEnd(req)


def test_installed_sdk_callback_authority_survives_cleanup():
    ib = OfflineInsync(lambda ib, tick: sdk_fields(ib))
    client = client_for(ib)
    result = client.snapshot_stock(contract())
    assert result.requested_market_data_type == "DELAYED" and result.returned_market_data_type == "LIVE"
    assert result.market_data_type_confirmation_source == "IBKR_MARKET_DATA_TYPE_CALLBACK"
    assert result.market_data_type_received_at_utc
    assert result.request_id == 1 and result.snapshot_complete
    assert result.request_started_at_utc <= result.snapshot_completed_at_utc <= result.request_completed_at_utc
    assert result.field_received_at_utc["bid"]
    assert result.timestamp_source == "LAST_TRADE"
    assert ib.cancelled == []
    assert ib.wrapper.reqId2Ticker == {}


def test_sdk_default_live_is_not_confirmation_and_retries_are_isolated():
    def step(ib, tick):
        if ib.req_id == 1:
            sdk_fields(ib, confirmed=False, missing=True)
        else:
            ib.wrapper.marketDataType(1, 4)  # Late callback for ended request.
            sdk_fields(ib, confirmed=False, missing=True)
    ib = OfflineInsync(step)
    result = client_for(ib).snapshot_stock(contract())
    assert result.returned_market_data_type == "UNKNOWN"
    assert result.market_data_type_confirmed is False
    assert result.bid is None and result.ask is None
    assert len(result.snapshot_attempts) == 2
    assert [row["request_id"] for row in result.snapshot_attempts] == [1, 2]
    assert all(row["returned_market_data_type"] == "UNKNOWN" for row in result.snapshot_attempts)


def test_full_fields_without_snapshot_end_are_not_complete():
    ib = OfflineInsync(lambda ib, tick: sdk_fields(ib, complete=False))
    result = client_for(ib).snapshot_stock(contract())
    assert result.snapshot_complete is False
    assert result.snapshot_completed_at_utc is None
    assert result.completion_reason == "required_fields"
    assert "MD_SNAPSHOT_INCOMPLETE" in result.data_quality_flags
    assert "MD_TIMEOUT" not in result.data_quality_flags
    assert ib.cancelled == [1]


def test_sdk_timeout_and_missing_field_times(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(md.time, "monotonic", lambda: clock[0])
    def step(ib, tick):
        ib.wrapper.marketDataType(ib.req_id, 1)
        ib.wrapper.priceSizeTick(ib.req_id, 4, 5.0, 1)
        clock[0] += 0.1
    result = client_for(OfflineInsync(step)).snapshot_stock(contract())
    assert result.completion_reason == "timeout"
    assert "MD_TIMEOUT" in result.data_quality_flags
    assert result.snapshot_complete is False
    assert result.field_availability["bid"] is False
    assert result.missing_fields_observed_at_utc["bid"] == result.request_completed_at_utc
    assert result.timestamp_utc is None


def test_snapshot_end_at_deadline_is_observed(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(md.time, "monotonic", lambda: clock[0])
    def step(ib, tick):
        clock[0] += 0.1
        sdk_fields(ib)
    result = client_for(OfflineInsync(step)).snapshot_stock(contract())
    assert result.snapshot_complete is True
    assert "MD_TIMEOUT" not in result.data_quality_flags


def test_sdk_broker_error_retains_request_symbol_and_timestamp():
    def step(ib, tick):
        ib.wrapper.error(ib.req_id, 10197, "Competing session", "")
        sdk_fields(ib, missing=True)
    result = client_for(OfflineInsync(step)).snapshot_stock(contract())
    assert "MD_CONFLICT_10197" in result.data_quality_flags
    assert result.broker_errors[0]["req_id"] == result.request_id
    assert result.broker_errors[0]["symbol"] == "AEMD"
    assert result.broker_errors[0]["timestamp_utc"]
