"""Offline broker callback authority; no network or order operations."""
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

import pytest
from ibapi.client import EClient
from ibapi.contract import Contract, ContractDetails
from src.adapters.brokers.ibkr import ibkr_client as native_module
from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.core.acquisition import acquisition_scope
from src.ibkr import market_data_client as md
from src.market_data.market_data_snapshot_manager import MarketDataSnapshotManager


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
    monkeypatch.setattr(native, "isConnected", lambda: True)
    monkeypatch.setattr(EClient, "reqHistoricalData", lambda self, req, *args: self.historicalDataEnd(req, "", ""))
    result = native.reqHistoricalData(99, contract(), "", "1 D", "1 min", "TRADES", 1, 1, False, [])
    assert result.completed and not native._historical_events
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


@pytest.mark.parametrize("returned,confirmed,expected", [
    ("LIVE", True, "LIVE"), ("DELAYED", True, "DELAYED"),
    ("FROZEN", True, "FROZEN"), ("DELAYED_FROZEN", True, "DELAYED_FROZEN"),
    ("UNKNOWN", False, "UNKNOWN"), ("LIVE", False, "UNKNOWN"),
])
def test_focus_snapshot_translation_preserves_broker_authority(returned, confirmed, expected):
    from dataclasses import replace
    from src.market_data.market_data_snapshot_manager import MarketDataSnapshotManager
    raw = client_for(OfflineInsync(lambda ib, tick: sdk_fields(ib))).snapshot_stock(contract())
    raw = replace(raw, returned_market_data_type=returned, market_data_type_confirmed=confirmed)
    manager = MarketDataSnapshotManager(SimpleNamespace(snapshot_stock=lambda symbol: raw))
    snapshot, quality = manager.get_snapshot("AEMD")
    assert snapshot.market_data_type == snapshot.returned_market_data_type == expected
    assert snapshot.market_data_type_confirmed is confirmed
    assert snapshot.requested_market_data_type == "DELAYED"
    assert snapshot.market_timestamp_utc == datetime.fromisoformat(raw.timestamp_utc)
    assert snapshot.received_at_utc == datetime.fromisoformat(raw.received_at_utc)
    assert snapshot.market_data_type_received_at_utc == datetime.fromisoformat(raw.market_data_type_received_at_utc)
    assert snapshot.asof_utc != snapshot.market_timestamp_utc
    assert snapshot.data_quality_flags == tuple(quality.data_quality_flags)
    for name in ("timestamp_source", "request_id", "snapshot_complete", "request_started_at_utc",
                 "request_completed_at_utc", "snapshot_completed_at_utc", "completion_reason",
                 "field_availability", "field_received_at_utc", "missing_fields_observed_at_utc",
                 "broker_errors", "close", "open", "high", "low", "bid_size", "ask_size", "last_size"):
        assert getattr(snapshot, name) == getattr(raw, name)
    assert snapshot.market_data_type_confirmation_source == (
        "IBKR_MARKET_DATA_TYPE_CALLBACK" if confirmed else "UNKNOWN")


def test_focus_snapshot_translation_does_not_invent_missing_timestamps(native, monkeypatch):
    from src.market_data.market_data_snapshot_manager import MarketDataSnapshotManager
    monkeypatch.setattr(native, "resolve_contract", lambda symbol: SimpleNamespace(contract=contract()))
    snapshot, quality = MarketDataSnapshotManager(native).get_snapshot("AEMD")
    assert snapshot.market_data_type == snapshot.returned_market_data_type == "UNKNOWN"
    assert snapshot.market_timestamp_utc is None
    assert snapshot.received_at_utc is None
    assert snapshot.market_data_type_received_at_utc is None
    assert snapshot.timestamp_source == "UNKNOWN"
    assert "MD_TIMEOUT" in snapshot.data_quality_flags
    assert snapshot.snapshot_complete is False
    assert snapshot.completion_reason == "timeout"


@pytest.fixture
def source_bound_native_snapshot(native, monkeypatch):
    """Synthetic external callbacks through genuine qualification/quote owners."""
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 11, 13, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(native_module, "datetime", Clock)
    monkeypatch.setattr(md, "datetime", Clock)
    monkeypatch.setattr(native, "isConnected", lambda: True)
    native.client_id = 71
    native._position_connection_epoch = 23

    def forbidden_connect(*args, **kwargs):
        raise AssertionError("Synthetic snapshot controls must not connect")

    monkeypatch.setattr(EClient, "connect", forbidden_connect)
    facts = SimpleNamespace(qualifications=[], requests=[], before_quote=None)

    def qualify(self, req_id, requested):
        supplied = Contract()
        supplied.symbol = requested.symbol
        supplied.secType, supplied.exchange, supplied.currency = "STK", "SMART", "USD"
        supplied.primaryExchange = "NASDAQ"
        supplied.conId = {"AEMD": 123, "MSFT": 456}[requested.symbol]
        supplied.tradingClass = supplied.localSymbol = requested.symbol
        detail = ContractDetails()
        detail.contract = supplied
        facts.qualifications.append((self.client_id, self._position_connection_epoch,
                                     supplied.symbol, supplied.conId, req_id))
        self.contractDetails(req_id, detail)
        self.contractDetailsEnd(req_id)

    def quote(self, req_id, requested, *args):
        facts.requests.append((requested.symbol, requested.conId, self.client_id,
                               self._position_connection_epoch, req_id))
        if facts.before_quote is not None:
            facts.before_quote(requested.symbol)
        native_ticks(self, req_id, returned=1)
        if requested.symbol == "MSFT":
            for kind, value in ((66, 8.0), (67, 8.1), (68, 8.05), (75, 7.8)):
                self.tickPrice(req_id, kind, value, None)
        self.tickString(req_id, 45, str(Clock.now().timestamp()))

    monkeypatch.setattr(EClient, "reqContractDetails", qualify)
    monkeypatch.setattr(EClient, "reqMktData", quote)
    connection_manager = SimpleNamespace(get_client=lambda: native)
    wrapper = md.MarketDataClient(connection_manager=connection_manager,
        allow_direct_connection=False, client_id=999, market_data_type="LIVE",
        snapshot_timeout_seconds=1)
    wrapper.ib = native
    facts.native, facts.wrapper = native, wrapper
    facts.manager = MarketDataSnapshotManager(wrapper)
    return facts


def assert_native_quote_cleanup(*clients):
    for client in clients:
        assert not client._active_market_req_ids
        assert not client._ticker_by_req_id
        assert not client._market_events


def snapshot_source_identity(snapshot):
    return tuple(getattr(snapshot, name, None) for name in
                 ("con_id", "client_id", "connection_epoch", "request_id"))


def test_real_native_snapshot_source_identity_survives_focus_translation(source_bound_native_snapshot):
    facts = source_bound_native_snapshot
    with acquisition_scope():
        raw = facts.wrapper.snapshot_stock("AEMD")
        snapshot, quality = facts.manager.get_snapshot("AEMD")
    assert len(facts.qualifications) == len(facts.requests) == 1
    assert facts.qualifications[0][:4] == (71, 23, "AEMD", 123)
    request = facts.requests[0]
    assert request[:4] == ("AEMD", 123, 71, 23)
    assert facts.wrapper.client_id == 999  # Configuration is not request identity.
    assert raw.last == snapshot.last == 5.05
    assert raw.snapshot_complete and snapshot.snapshot_complete
    assert raw.request_id == snapshot.request_id == request[4]
    assert not quality.data_quality_flags
    assert_native_quote_cleanup(facts.native)
    expected = request[1:]
    assert {"raw": snapshot_source_identity(raw), "domain": snapshot_source_identity(snapshot)} == {
        "raw": expected, "domain": expected}


@pytest.mark.parametrize("scope_change", ["connection_epoch", "native_client"])
def test_snapshot_and_qualification_cache_reacquire_after_native_scope_change(
        source_bound_native_snapshot, monkeypatch, scope_change):
    facts = source_bound_native_snapshot
    clients = [facts.native]
    with acquisition_scope():
        first = facts.wrapper.snapshot_stock("AEMD")
        if scope_change == "connection_epoch":
            facts.native.connectionClosed()
            assert facts.native._position_connection_epoch == 24
            expected_scope = (71, 24)
        else:
            replacement = IbkrClient("127.0.0.1", 7497, 72, 1, "LIVE", True)
            monkeypatch.setattr(replacement, "isConnected", lambda: True)
            replacement._position_connection_epoch = 37
            facts.wrapper.ib = replacement
            clients.append(replacement)
            expected_scope = (72, 37)
        second = facts.wrapper.snapshot_stock("AEMD")
    assert_native_quote_cleanup(*clients)
    assert len(facts.requests) == 2, facts.requests
    assert len(facts.qualifications) == 2, facts.qualifications
    assert facts.qualifications[-1][:2] == expected_scope
    assert second is not first
    assert snapshot_source_identity(first) == (123, 71, 23, facts.requests[0][4])
    assert snapshot_source_identity(second) == (123, *expected_scope, facts.requests[1][4])


def test_concurrent_native_snapshot_identity_stays_with_its_own_symbol(source_bound_native_snapshot):
    facts = source_bound_native_snapshot
    first_request_started, release_first_request = threading.Event(), threading.Event()

    def before_quote(symbol):
        if symbol == "AEMD":
            first_request_started.set()
            assert release_first_request.wait(2), "Bounded synthetic AEMD request was not released"

    facts.before_quote = before_quote
    # A's native request is already owned while B qualifies, receives its own
    # callbacks and completes translation. This overwrites shared diagnostics
    # before A resumes; those diagnostics cannot authorize A's source identity.
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(facts.manager.get_snapshot, "AEMD")
        try:
            assert first_request_started.wait(2), "Synthetic AEMD request did not start"
            second = executor.submit(facts.manager.get_snapshot, "MSFT")
            msft, msft_quality = second.result(timeout=2)
        finally:
            release_first_request.set()
        aemd, aemd_quality = first.result(timeout=2)
    assert not aemd_quality.data_quality_flags and not msft_quality.data_quality_flags
    assert (aemd.symbol, aemd.last, msft.symbol, msft.last) == ("AEMD", 5.05, "MSFT", 8.05)
    assert len(facts.qualifications) == len(facts.requests) == 2
    assert_native_quote_cleanup(facts.native)
    expected = {symbol: (con_id, client_id, epoch, req_id)
                for symbol, con_id, client_id, epoch, req_id in facts.requests}
    assert expected["AEMD"][3] != expected["MSFT"][3]
    assert {"AEMD": snapshot_source_identity(aemd), "MSFT": snapshot_source_identity(msft)} == expected
