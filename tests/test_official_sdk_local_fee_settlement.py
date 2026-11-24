"""Official owned fee callbacks through the existing local financial collector.

The retained external ACK harness never grants P02 admission or sends orders.
"""
from importlib.metadata import version
from pathlib import Path
import queue
import sys
import threading
from types import ModuleType

import pytest

from src.ibkr.mutation_audit import snapshot as mutations
from test_p02_observable_local_cooldown import (
    local_component, native_execution_client, no_external_activity, forbid_io,
    _reset_config, _observe, NOW,
)
from test_p02_local_native_guard import _source_request_encoder


pytestmark = pytest.mark.skipif(version("ibapi") != "10.50.2", reason="Official local fee profile")


@pytest.fixture
def modern_local_financial(local_component, monkeypatch, request):
    """Reuse the actual retained-owner fixture, adapting only its SDK test seams."""
    from ibapi.commission_and_fees_report import CommissionAndFeesReport
    from ibapi.connection import Connection
    from ibapi.decoder import Decoder
    from ibapi.reader import EReader
    from src.adapters.brokers.ibkr import ibkr_client as native_module

    # The legacy fixture imports the former class name at module scope. Bind
    # that test dependency to the real current class only while loading it;
    # production receives the original modern object from the actual decoder.
    legacy_name = ModuleType("ibapi.commission_report")
    legacy_name.CommissionReport = CommissionAndFeesReport
    path = Path(__file__).with_name("test_p02_financial_callback_settlement.py")
    harness = {"__name__": "official_local_fee_harness", "__file__": str(path)}
    with monkeypatch.context() as importing:
        importing.setitem(sys.modules, "ibapi.commission_report", legacy_name)
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), harness)

    original_request_encoder = harness["_source_request_encoder"]
    def request_encoder(h, patch, requested, cancelled):
        requests, cancels = original_request_encoder(h, patch, requested, cancelled)
        legacy_send = h.client.sendMsg
        # Official legacy-wire encoder supplies opcode separately. Keep its
        # actual encoder and the same no-network external request/cancel ACKs.
        patch.setattr(h.client, "sendMsg", lambda opcode, message:
            legacy_send(str(opcode) + "\0" + message))
        return requests, cancels
    harness["_source_request_encoder"] = request_encoder
    fixture = harness["financial_component"].__wrapped__(local_component, monkeypatch, request)
    h = next(fixture)
    client = h.client
    client.serverVersion_ = 180
    client.clientId = client.client_id
    client.conn = Connection("memory-only", 0)
    client.reader = EReader(client.conn, client.msg_queue)
    client.decoder = Decoder(client, 180)
    client._commission_connection_attempts = 1
    client._install_commission_decoder_witness()
    assert isinstance(client._commission_decoder_proxy, native_module._OfficialCommissionDecoderProxy)
    tasks = queue.Queue()
    def worker():
        while True:
            task = tasks.get()
            if task is None:
                return
            action, done, result = task
            try:
                result.append(action())
            except BaseException as error:
                result.append(error)
            finally:
                done.set()
    client._thread = threading.Thread(target=worker, name="owned-local-fee-decoder")
    client._thread.start()
    def run(action):
        done, result = threading.Event(), []
        tasks.put((action, done, result))
        assert done.wait(3), "Owned local fee decoder did not finish"
        if isinstance(result[0], BaseException):
            raise result[0]
        return result[0]
    h.reports = []
    consume = client._consume_commission_witness
    def consume_exact(report):
        h.reports.append(report)
        return consume(report)
    monkeypatch.setattr(client, "_consume_commission_witness", consume_exact)
    def deliver(harness_owner, execution_id, amount):
        assert harness_owner is h
        amount = h.fee_amounts[execution_id]
        if h.protobuf:
            from ibapi.protobuf.CommissionAndFeesReport_pb2 import CommissionAndFeesReport as ProtoReport
            message = ProtoReport(execId=execution_id, currency="USD")
            if amount is not None:
                message.commissionAndFees = amount
            run(lambda: client.decoder.processProtoBuf(message.SerializeToString(), 59))
        else:
            fields = ("1", execution_id, "" if amount is None else str(amount), "USD", "0", "0", "0")
            run(lambda: client.decoder.interpret(tuple(field.encode() for field in fields), 59))
        return h.reports[-1]
    harness["_report"] = deliver
    h.deliver = lambda execution_id: deliver(h, execution_id, None)
    h.close_roundtrip = lambda **kwargs: harness["_closed_roundtrip"](h, **kwargs)
    try:
        yield h
    finally:
        tasks.put(None)
        client._thread.join(3)
        assert not client._thread.is_alive()
        with pytest.raises(StopIteration):
            next(fixture)


@pytest.mark.parametrize("protobuf", [False, True])
@pytest.mark.parametrize("amounts", [(.01, .02), (0., .02), (0., 0.)])
def test_owned_modern_fees_settle_retained_financial_occurrences(modern_local_financial, protobuf, amounts):
    from ibapi.commission_and_fees_report import CommissionAndFeesReport
    h = modern_local_financial
    h.protobuf = protobuf
    h.fee_amounts = dict(zip(("controlled-entry", "controlled-stop"), amounts))
    h.close_roundtrip()
    tickets = tuple(row for row in h.client.local_intake_occurrences() if row.kind == "commissionReport")
    assert len(tickets) == 2 and all(type(report) is CommissionAndFeesReport for report in h.reports)
    frozen = tuple((ticket.semantic_payload, ticket.raw_fingerprint) for ticket in tickets)
    for ticket, amount in zip(tickets, amounts):
        report = h.engine._p02_callback_fields(ticket)["commissionReport"]
        assert report["_native_type"] == "CommissionAndFeesReport"
        assert report["commissionAndFees"] == amount and "commission" not in report
    before = h.client.local_financial_cache_snapshot()
    h.collect()
    value = _observe(h)
    assert value["available"] and value.local_condition_satisfied, (
        value["findings"], h.engine._p02_local.get("settlement_unavailable"))
    assert not h.client.local_intake_snapshot().dirty
    assert tuple((ticket.semantic_payload, ticket.raw_fingerprint) for ticket in tickets) == frozen
    assert h.client.local_financial_cache_snapshot()["executions_snapshot"] == before["executions_snapshot"]
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3
    fees = h.lifecycle.native_fee_feedback_snapshot(now=NOW, max_age_seconds=15,
        expected_source_client=h.client)
    assert fees["required"] and fees["available"]
    assert len(fees["covered_charges"]) == 2
    for amount, charge in zip(amounts, fees["covered_charges"]):
        if amount == 0:
            witness = charge["zero_commission_witness"]
            assert witness["commission_decoder_schema"] == "IBAPI_10_50_2_COMMISSION_FEES"
            assert witness["commission_field_present"] is True
            assert witness["commission_client_object_id"] == id(h.client)
    assert len(h.transport_acks) == len(h.stop_acks) == 1
    assert value.admission_authorized is False
    for stage in ("PROPOSAL", "RISK", "RESERVATION", "FINAL_NATIVE_ENTRY"):
        assert not h.engine.revalidate_p02_local_cooldown(value, assessed_at=NOW, stage=stage)
    assert mutations() == dict(place=0, modify=0, cancel=0)


@pytest.mark.parametrize("protobuf", [False, True])
def test_absent_modern_fee_stays_unknown_and_cannot_settle_local_bundle(modern_local_financial, protobuf):
    h = modern_local_financial
    h.protobuf = protobuf
    h.fee_amounts = {"controlled-entry": None, "controlled-stop": .02}
    h.close_roundtrip(fees=False)
    h.deliver("controlled-entry")
    h.deliver("controlled-stop")
    assert h.engine.native_roundtrip_fee_candidates() == {}
    h.collect()
    value = _observe(h)
    assert not value["available"] and not value.admission_authorized
    assert h.client.local_intake_snapshot().dirty
    assert len(h.storage.fetch_trade_lifecycle_events()) == 2
    report = h.client._commission_by_exec_id["controlled-entry"]["first_report"]
    assert report["commission_field_present"] is False
    assert not h.client._commission_zero_report_current(report)
    assert mutations() == dict(place=0, modify=0, cancel=0)
