"""Real SDK decoders and native READ_ONLY owners; no broker/socket activity."""
from datetime import datetime, timezone
from decimal import Decimal
from importlib.metadata import version
from types import SimpleNamespace

import pytest

from src.adapters.brokers.ibkr import ibkr_client as native_module
from src.domain.volume_evidence import native_stock_volume_rejection
from src.ibkr.market_data_client import exact_raw_volume, historical_bar_facts, average_daily_bar_volume
from src.ibkr.volume_calibration import _same_number
from test_post_pr1090_market_data_authority import native, contract


modern = pytest.mark.skipif(version("ibapi") != "10.50.2", reason="Official SDK decoder profile only")


def test_error_time_does_not_replace_code_or_leak_advanced_rejection(native, capsys):
    ticker = native.reqMktData(contract(), snapshot=True)
    native.error(ticker.reqId, 1789990000123, 2176, "Compatibility warning", "PRIVATE_REJECTION_JSON_ACCOUNT")
    assert ticker.brokerErrors[-1]["code"] == 2176
    assert native._errors[ticker.reqId] == (2176, "Compatibility warning")
    assert native._market_events[ticker.reqId].is_set()
    assert not ticker.snapshotEnd
    assert "PRIVATE_REJECTION_JSON_ACCOUNT" not in repr(native._broker_error_events)
    assert "PRIVATE_REJECTION_JSON_ACCOUNT" not in capsys.readouterr().out


def test_legacy_error_callback_still_preserves_owner_and_code(native):
    ticker = native.reqMktData(contract(), snapshot=True)
    native.error(ticker.reqId, 354, "No data")
    assert ticker.brokerErrors[-1]["code"] == 354
    assert native._errors[ticker.reqId] == (354, "No data")


@pytest.mark.parametrize("tail", [(True, "message"), (2176, 123), (2176, "message", "json", "extra")])
def test_malformed_modern_error_schema_refuses_without_owning_error(native, tail):
    ticker = native.reqMktData(contract(), snapshot=True)
    with pytest.raises(RuntimeError, match="IBKR_ERROR_CALLBACK_SCHEMA_UNSUPPORTED"):
        native.error(ticker.reqId, 1789990000123, *tail)
    assert not ticker.brokerErrors and not native._market_events[ticker.reqId].is_set()


@pytest.mark.parametrize("raw", [Decimal("9007199254740993"), Decimal("1234567.000000000000000000")])
def test_decimal_native_volume_preserves_integral_size_exactly(native, raw):
    native.serverVersion_ = 221
    target = contract()
    target.primaryExchange = "NASDAQ"
    ticker = native.reqMktData(target, snapshot=True)
    native.marketDataType(ticker.reqId, 1)
    native.tickString(ticker.reqId, 45, str(datetime.now(timezone.utc).timestamp()))
    native.tickSize(ticker.reqId, 8, raw)
    evidence = native.snapshot_volume_evidence(ticker)
    assert type(evidence["raw_value"]) is int and evidence["raw_value"] == raw
    assert native_stock_volume_rejection(evidence) is None


def test_fractional_native_volume_is_preserved_and_cannot_be_calibrated(native):
    native.serverVersion_ = 221
    target = contract()
    target.primaryExchange = "NASDAQ"
    ticker = native.reqMktData(target, snapshot=True)
    native.marketDataType(ticker.reqId, 1)
    native.tickString(ticker.reqId, 45, str(datetime.now(timezone.utc).timestamp()))
    native.tickSize(ticker.reqId, 8, Decimal("1000000.0000000000000000001"))
    evidence = native.snapshot_volume_evidence(ticker)
    assert evidence["raw_value"] == "1000000.0000000000000000001"
    assert native_stock_volume_rejection(evidence) == "ROSS_VOLUME_VALUE_INVALID"
    assert not _same_number(evidence["raw_value"], 1000000)


def test_decimal_history_preserves_counts_and_refuses_fractional_adv20():
    whole = [SimpleNamespace(date="20261123", volume=Decimal("9007199254740993"))]
    assert historical_bar_facts(whole)[0]["volume"] == 9007199254740993
    assert average_daily_bar_volume(whole, 20) == (9007199254740993, 1)
    fractional = [SimpleNamespace(date="20261123", volume=Decimal("123.0000000000000000001"))]
    assert historical_bar_facts(fractional)[0]["volume"] == "123.0000000000000000001"
    assert average_daily_bar_volume(fractional, 20) == (None, None)
    assert exact_raw_volume(Decimal("NaN")) == "NaN"
    assert exact_raw_volume(Decimal("Infinity")) == "Infinity"
    assert not _same_number(historical_bar_facts(fractional)[0]["volume"], 123)


@modern
def test_official_decoder_delivers_fractional_tick_and_scoped_snapshot_end(native):
    from ibapi.decoder import Decoder
    from ibapi.protobuf.TickSize_pb2 import TickSize
    from ibapi.protobuf.TickSnapshotEnd_pb2 import TickSnapshotEnd
    ticker = native.reqMktData(contract(), snapshot=True)
    decoder = Decoder(native, 221)
    decoder.processTickSizeMsgProtoBuf(TickSize(reqId=ticker.reqId, tickType=8, size="9007199254740993").SerializeToString())
    assert ticker.volumeRawValue == 9007199254740993
    assert not ticker.snapshotEnd
    decoder.processTickSnapshotEndMsgProtoBuf(TickSnapshotEnd(reqId=ticker.reqId).SerializeToString())
    assert ticker.snapshotEnd and native._market_events[ticker.reqId].is_set()
    native.cancelMktData(ticker.reqId)
    replacement = native.reqMktData(contract(), snapshot=True)
    decoder.processTickSizeMsgProtoBuf(TickSize(reqId=ticker.reqId, tickType=8, size="999").SerializeToString())
    assert replacement.volumeRawValue is None and not replacement.snapshotEnd


@modern
def test_official_error_decoder_keeps_2176_blocking(native, capsys):
    from ibapi.decoder import Decoder
    from ibapi.protobuf.ErrorMessage_pb2 import ErrorMessage
    ticker = native.reqMktData(contract(), snapshot=True)
    error = ErrorMessage(id=ticker.reqId, errorCode=2176, errorMsg="Compatibility warning",
                         errorTime=1789990000123, advancedOrderRejectJson="PRIVATE_REJECTION_JSON")
    Decoder(native, 221).processErrorMsgProtoBuf(error.SerializeToString())
    assert ticker.brokerErrors[-1]["code"] == 2176 and not ticker.snapshotEnd
    assert "PRIVATE_REJECTION_JSON" not in repr(native._broker_error_events)
    assert "PRIVATE_REJECTION_JSON" not in capsys.readouterr().out


@modern
@pytest.mark.parametrize("protobuf", [False, True])
@pytest.mark.parametrize("amount", [None, 0.0, 0.25])
def test_modern_commission_decoder_never_borrows_legacy_zero_presence(native, protobuf, amount):
    from ibapi.decoder import Decoder
    from ibapi.protobuf.CommissionAndFeesReport_pb2 import CommissionAndFeesReport
    decoder = Decoder(native, 221)
    if protobuf:
        message = CommissionAndFeesReport(execId="SYNTH_FEE", currency="USD")
        if amount is not None:
            message.commissionAndFees = amount
        decoder.processCommissionAndFeesReportMsgProtoBuf(message.SerializeToString())
    else:
        fields = ["1", "SYNTH_FEE", "" if amount is None else str(amount), "USD", "0", "0", "0"]
        decoder.processCommissionAndFeesReportMsg(iter(value.encode() for value in fields))
    report = native._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    assert report["commission_field_present"] is None
    assert report["commission_presence_source"] == "UNAVAILABLE"
    assert not native._commission_zero_report_current(report)
    assert native._commission_zero_disabled
    if amount == 0.25:
        assert report["amount"] == Decimal("0.25")


@modern
def test_official_constructor_rejects_execution_mode():
    with pytest.raises(RuntimeError, match="IBKR_OFFICIAL_SDK_EXECUTION_NOT_CERTIFIED"):
        native_module.IbkrClient("127.0.0.1", 7497, 71, 1, "LIVE", False)


@modern
@pytest.mark.parametrize("warning", [False, True])
@pytest.mark.parametrize("raw", ["9007199254740993", "123.0000000000000000001"])
def test_official_historical_decoder_requires_end_and_retains_exact_volume(native, monkeypatch, warning, raw):
    from ibapi.client import EClient
    from ibapi.decoder import Decoder
    from ibapi.protobuf.HistoricalData_pb2 import HistoricalData
    from ibapi.protobuf.HistoricalDataEnd_pb2 import HistoricalDataEnd
    native.serverVersion_ = 221
    monkeypatch.setattr(native, "isConnected", lambda: True)
    monkeypatch.setattr(EClient, "cancelHistoricalData", lambda *args: None)
    decoder = Decoder(native, 221)
    captured = []
    def send(owner, req_id, *args):
        message = HistoricalData(reqId=req_id)
        message.historicalDataBars.add(date="20261123", open=5, high=6, low=4, close=5,
                                       volume=raw, WAP="5", barCount=1)
        decoder.processHistoricalDataMsgProtoBuf(message.SerializeToString())
        state = native._historical_states[req_id]
        assert not state["end_received"] and state["status"] == "PENDING"
        assert state["bars"][0].volume == Decimal(raw)
        captured.append(req_id)
        if warning:
            native.error(req_id, 1789990000123, 2176, "Trimmed size")
        decoder.processHistoricalDataEndMsgProtoBuf(
            HistoricalDataEnd(reqId=req_id, startDateStr="20261123", endDateStr="20261123").SerializeToString())
    monkeypatch.setattr(EClient, "reqHistoricalData", send)
    result = native.reqHistoricalData(contract(), durationStr="20 D", barSizeSetting="1 day", whatToShow="TRADES", useRTH=1)
    assert len(captured) == 1 and not native._historical_states and not native._historical_events
    if warning:
        assert result.status == "ERROR" and result.error_code == 2176
        assert not result.completed and not result.bars and result.volume_basis is None
    else:
        assert result.completed and result.end_received and result.source_bar_count == 1
        expected = int(raw) if "." not in raw else raw
        assert result.raw_source_bars[0]["volume"] == expected
        assert type(result.raw_source_bars[0]["volume"]) is type(expected)
