"""Existing ordinary Core lifecycle through official SDK encoders/decoders.

The existing five-step ABCD tape and all application owners stay unchanged.
Only its external memory exchange is adapted to the official SDK transport
signature and public decoder. Every network entry remains denied by the same
fresh-process guard. These are synthetic compatibility proofs, not readiness.
"""
from importlib.metadata import version
import json
import shutil

import pytest

from test_native_stop_price_prerequisite import (
    _pristine_paper_loss_facts,
    _prepare_pristine_paper_cash_facts,
    supply_paper_release_volume_comparison,
    reassessment,
    lifecycle,
    forbid_io,
    no_external_activity,
    _reset_config,
)


pytestmark = pytest.mark.skipif(version("ibapi") != "10.50.2", reason="official SDK PAPER profile")


_DECODER_BOUNDARY = r'''
# Decode the supplied external facts through official public decoder owners.
# The tape is shared with the legacy joined proof; no result is manufactured.
report['official_decoder_callbacks'] = []
report['official_encoded_orders'] = []
official_pending_write = []

def official_order_status(*values):
    from ibapi.decoder import Decoder
    # The supplied handshake180 uses the official legacy-format decoder.
    Decoder(client,180).processOrderStatusMsg(iter(str(value).encode() for value in values))
    report['official_decoder_callbacks'].append(dict(kind='status',order_id=values[0]))

def official_open_order(order_id,contract,order,state):
    from ibapi.client_utils import createContractProto,createOrderProto
    from ibapi.decoder import Decoder
    from ibapi.protobuf.OpenOrder_pb2 import OpenOrder
    message = OpenOrder(orderId=order_id)
    message.contract.CopyFrom(createContractProto(contract,order))
    message.order.CopyFrom(createOrderProto(order))
    message.order.clientId = order.clientId
    message.orderState.status = state.status
    Decoder(client,221).processOpenOrderMsgProtoBuf(message.SerializeToString())
    report['official_decoder_callbacks'].append(dict(kind='open',order_id=order_id))

def official_execution(request_id,contract,execution):
    from ibapi.client_utils import createContractProto
    from ibapi.decoder import Decoder
    from ibapi.protobuf.ExecutionDetails_pb2 import ExecutionDetails
    message = ExecutionDetails(reqId=request_id)
    message.contract.CopyFrom(createContractProto(contract,None))
    for name in ('orderId','execId','time','acctNumber','exchange','side','price',
                 'permId','clientId','avgPrice','orderRef','evRule','evMultiplier','modelCode','lastLiquidity'):
        setattr(message.execution,name,getattr(execution,name))
    message.execution.shares = str(execution.shares)
    message.execution.cumQty = str(execution.cumQty)
    Decoder(client,221).processExecutionDataMsgProtoBuf(message.SerializeToString())
    report['official_decoder_callbacks'].append(dict(kind='execution',order_id=execution.orderId))
'''


_MEMORY_CONNECTION = r'''
    from ibapi import comm
    from types import MethodType
    class OfficialMemoryConnection:
        """Receives the real SDK's framed bytes; never opens a socket."""
        def __init__(self):
            self.closed = False
            self.frames = 0
        def isConnected(self):
            return not self.closed
        def disconnect(self):
            self.closed = True
        def sendMsg(self,frame):
            size,payload,remainder = comm.read_msg(bytes(frame))
            if not size or remainder or len(payload) != size:
                raise ForbiddenExternalIO('OFFICIAL_MEMORY_FRAME_INVALID')
            self.frames += 1
            send_message(payload.decode('utf-8'))
    client.conn = OfficialMemoryConnection()
    client.setConnState(EClient.CONNECTED)
    # Use the unchanged official framing method, not an encoder replacement.
    client.sendMsg = MethodType(EClient.sendMsg,client)
'''


def _replace_once(source, old, new):
    assert source.count(old) == 1, "Existing joined external boundary changed"
    return source.replace(old, new, 1)


def _official_child_source(source):
    """Adapt only existing test exchange seams; retain its hard offline guard."""
    source = _replace_once(source, "def plain(value):", _DECODER_BOUNDARY + "\ndef plain(value):")
    source = _replace_once(source,
        "    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient\n"
        "    from src.adapters.brokers.ibkr import ibkr_connection_manager as connection_module\n",
        "    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient\n"
        "    official_native_cancel = IbkrClient.cancelOrder\n"
        "    from src.adapters.brokers.ibkr import ibkr_connection_manager as connection_module\n")
    source = _replace_once(source,
        "    client = IbkrClient('offline.invalid', 7497, client_id, 1, 'LIVE', False)",
        "    client = IbkrClient('127.0.0.1', 7497, client_id, 1, 'LIVE', False)")
    source = _replace_once(source,
        "        client._managed_accounts = [account]\n        client._managed_accounts_event.set()",
        "        client.managedAccounts(account)")
    source = _replace_once(source,
        "        'offline.invalid', 7497, client_id, 1, 'LIVE', False, 'PAPER'))",
        "        '127.0.0.1', 7497, client_id, 1, 'LIVE', False, 'PAPER'))")
    source = _replace_once(source, "    client.sendMsg = send_message", _MEMORY_CONNECTION)
    source = _replace_once(source,
        "        if report['wire_attempts'][-1]['mutation']:\n"
        "            raise SyntheticWriteBoundary('COLD_CORE_SYNTHETIC_NATIVE_WRITE_ATTEMPT')",
        """        if report['wire_attempts'][-1]['mutation']:
            if len(official_pending_write) != 1:
                raise SyntheticWriteBoundary('UNOWNED_OFFICIAL_MEMORY_WRITE')
            expected = official_pending_write[0]
            if opcode != str(expected['opcode']):
                raise SyntheticWriteBoundary('WRONG_OFFICIAL_MEMORY_WRITE')
            if opcode == str(OUT.PLACE_ORDER):
                if (fields[1:5] != [str(expected['native_id']),str(expected['con_id']),expected['symbol'],'STK']
                        or fields[16:19] != [expected['action'],'1',expected['order_type']]
                        or fields[23] != expected['account']
                        or fields[26] != expected['order_ref'] or fields[28] != str(expected['parent_id'])
                        or fields[33] != str(int(expected['outside_rth']))
                        or (expected['order_type'] == 'STP' and fields[20] != str(expected['aux_price']))
                        or (expected['order_type'] == 'LMT' and fields[19] != str(expected['limit_price']))):
                    raise SyntheticWriteBoundary('OFFICIAL_ENCODED_ORDER_TERMS_CHANGED')
            elif fields[2] != str(expected['native_id']):
                raise SyntheticWriteBoundary('OFFICIAL_ENCODED_CANCEL_ID_CHANGED')
            report['official_encoded_orders'].append(dict(
                {key:value for key,value in expected.items() if key not in {'client','contract','order'}},fields=fields))
            if opcode == str(OUT.PLACE_ORDER):
                official_memory_exchange(expected['client'],expected['native_id'],expected['contract'],expected['order'])
            return""")
    source = _replace_once(source,
        "            # No SDK encoder/sendMsg call: this single instance has a provided\n"
        "            # memory-only external exchange. Global mutation barriers remain.",
        "            # The real native bridge, SDK serializer and framing have already\n"
        "            # reached this exclusively in-memory external exchange.")
    source = _replace_once(source,
        "        client.placeOrder = MethodType(memory_place_order,client)",
        "        official_memory_exchange = memory_place_order")
    source = _replace_once(source,
        "            report['sdk_attempts'].append(row)\n            return _method(self, *args, **kwargs)",
        """            report['sdk_attempts'].append(row)
            if _name == 'placeOrder':
                if official_pending_write:
                    raise SyntheticWriteBoundary('REENTRANT_OFFICIAL_MEMORY_WRITE')
                native_id,contract,native = args
                official_pending_write.append(dict(opcode=OUT.PLACE_ORDER,native_id=native_id,
                    role='entry' if native.action == 'BUY' else 'stop',symbol=contract.symbol,
                    con_id=contract.conId,account=native.account,action=native.action,
                    order_type=native.orderType,parent_id=native.parentId,order_ref=native.orderRef,
                    outside_rth=native.outsideRth,aux_price=native.auxPrice,limit_price=native.lmtPrice,
                    client=self,contract=contract,order=native))
                try:
                    return _method(self,*args,**kwargs)
                finally:
                    official_pending_write.clear()
            return _method(self,*args,**kwargs)""")
    source = _replace_once(source,
        "            shutdown['cancel_calls'].append(order_id)",
        """            official_pending_write.append(dict(opcode=OUT.CANCEL_ORDER,native_id=order_id,role='cancel'))
            try:
                official_native_cancel(client,order_id)
            finally:
                official_pending_write.clear()
            shutdown['cancel_calls'].append(order_id)""")
    source = _replace_once(source,
        "        shutdown['after'] = engine_snapshot(core.execution_engine)",
        "        shutdown['after'] = engine_snapshot(core.execution_engine)\n"
        "        shutdown['official_mutation_attempts_after'] = mutation_snapshot()")
    # Only the provided external callbacks change representation. Application
    # methods, accounting, broker queries, gates and replay handling stay real.
    source = source.replace("client.orderStatus(", "official_order_status(")
    source = source.replace("client.openOrder(", "official_open_order(")
    source = source.replace("client.execDetails(", "official_execution(")
    return source


def _run_modern_tape(monkeypatch, tmp_path, runtime_schema_template, facts):
    import test_startup_recovery_and_stop_protection as joined
    source = _official_child_source(joined._NATIVE_CORE_COLD_START_CHILD)
    monkeypatch.setattr(joined, "_NATIVE_CORE_COLD_START_CHILD", source)
    database = tmp_path / "official-ordinary.sqlite3"
    shutil.copyfile(runtime_schema_template, database)
    path = tmp_path / "official-ordinary.json"
    path.write_text(json.dumps(facts, default=str), encoding="utf-8")
    report = joined.run_native_core_cold_start(database, path, tmp_path / "official-child")
    summary = {key: report.get(key) for key in (
        "constructor_exception", "harness_exception", "cycle_exception", "stage", "evidence_dir")}
    assert report["constructor_complete"] and not report.get("harness_exception"), summary
    assert not report.get("cycle_exception"), summary
    assert not report["network_attempts"] and not report.get("native_curl_denials"), summary
    assert not report["capital_enrollment_attempts"], summary
    assert report["supervisor"]["returncode"] == 0 and report["supervisor"]["reaped"], summary
    assert not report["supervisor"]["timed_out"] and report["cleanup"]["live_threads"] == [], summary
    return report


def _ordinary_facts(reassessment, monkeypatch, tmp_path, *, release=True):
    from test_next_session_catalyst import receipt
    facts = _pristine_paper_loss_facts(reassessment, monkeypatch, tmp_path,
        candidate="ABCD", account="DU10001", bounded_entry=release)
    facts["config"].update(RISK_PROFILE="MICRO", FORCE_EXECUTION_ON_TRADE_READY=False,
        FORCE_RISK_APPROVAL_FOR_TRADE_READY=False,
        MARKET_SESSION_COVERAGE=json.dumps(receipt("2026-10-19", "2026-10-20")))
    facts["observe_pristine_native_scanner"] = True
    monkeypatch.setenv("ROSS_PAPER_RELEASE_ENABLED", "1" if release else "0")
    if release:
        supply_paper_release_volume_comparison(facts)
        monkeypatch.setenv("ROSS_PAPER_EXPECTED_ACCOUNT", facts["account"])
        monkeypatch.setenv("ROSS_PAPER_EXCLUSIVE_START_ATTESTED", "1")
        _prepare_pristine_paper_cash_facts(facts, tmp_path, monkeypatch)
    return facts


@pytest.mark.parametrize("release", [False, True], ids=["ordinary", "exclusive-release"])
@pytest.mark.parametrize("stop_observation", ["working", "missing", "rejected", "wrong-price"])
def test_official_sdk_ordinary_abcd_ack_later_fill_original_stop_and_replay(
        reassessment, monkeypatch, tmp_path, runtime_schema_template, no_external_activity,
        release, stop_observation):
    facts = _ordinary_facts(reassessment, monkeypatch, tmp_path, release=release)
    if stop_observation != "working":
        facts["paper_initial_stop_observation"] = stop_observation
        ack, filled, repeated, *_ = facts["paper_cycle_steps"]
        repeated.update(name="REPLAY_WITHOUT_VERIFIED_STOP", open_orders=[], executions=filled["executions"])
        facts["paper_cycle_steps"] = [ack, filled, repeated]
    report = _run_modern_tape(monkeypatch, tmp_path, runtime_schema_template, facts)
    buy, stop = report["synthetic_memory_dispatches"]
    root = buy["root_id"]
    assert [row["role"] for row in report["official_encoded_orders"]] == ["entry", "stop"]
    assert [row["method"] for row in report["sdk_attempts"]] == ["placeOrder", "placeOrder"]
    assert report["mutation_attempts"] == dict(place=2, modify=0, cancel=0)
    assert buy["order"]["totalQuantity"] == stop["order"]["totalQuantity"] == 1
    assert stop["order"]["auxPrice"] == 10.35 and stop["order"]["parentId"] == buy["native_id"]
    ack, filled, *later = report["cycles"]
    request = ack["engine"]["native_orders"][root]["request"]
    assert request["setup_family_id"] == "ABCD" and request["stop_loss_price"] == 10.35
    assert request["take_profit_price"] is None
    assert ack["engine"]["capital_used"] == 0 and not ack["engine"]["position_records"]
    assert ack["engine"]["capital_reserved"] == (11.50 if release else 11.0)
    assert filled["engine"]["position_records"][root]["filled_qty"] == 1
    if stop_observation != "working":
        assert not filled["result"] and not later[0]["result"]
        assert filled["engine"]["native_quarantined"] and later[0]["engine"]["native_quarantined"]
        assert not filled["engine"]["protection"][root]["protected"]
        return
    protected, closed, replayed = later
    assert filled["engine"]["protection"][root]["protected"]
    assert protected["engine"]["canonical_trades"][root]["quantity_open"] == 1
    for cycle in (closed, replayed):
        state = cycle["engine"]
        assert state["canonical_trades"][root]["quantity_open"] == 0
        assert not state["registry"] and not state["managed_positions"]
        assert state["capital_used"] == state["capital_reserved"] == 0
    assert len(closed["database"]["trade_lifecycle_events"]) == 2
    assert closed["database"]["trade_lifecycle_events"] == replayed["database"]["trade_lifecycle_events"]
    assert {row["kind"] for row in report["official_decoder_callbacks"]} == {"status", "open", "execution"}
    assert no_external_activity == []


@pytest.mark.parametrize("outcome", ["cancelled", "fill_during_cancel", "missing_terminal", "wrong_client_cancel"])
def test_official_sdk_controlled_shutdown_requires_confirmed_cancel_or_owned_protection(
        reassessment, monkeypatch, tmp_path, runtime_schema_template, no_external_activity, outcome):
    facts = _ordinary_facts(reassessment, monkeypatch, tmp_path)
    facts["paper_pending_shutdown"] = outcome
    facts["paper_shutdown_fill"] = facts["paper_cycle_steps"][1]["executions"][0]
    facts["paper_cycle_steps"] = facts["paper_cycle_steps"][:1]
    report = _run_modern_tape(monkeypatch, tmp_path, runtime_schema_template, facts)
    shutdown = report["pending_shutdown"]
    entry, *protection = report["synthetic_memory_dispatches"]
    assert shutdown["cancel_calls"] == [entry["native_id"]]
    assert shutdown["disconnected"]
    assert [row["role"] for row in report["official_encoded_orders"]] == (
        ["entry", "cancel", "stop"] if outcome == "fill_during_cancel" else ["entry", "cancel"])
    assert report["mutation_attempts"] == dict(place=1, modify=0, cancel=0)  # Taken before shutdown.
    assert shutdown["official_mutation_attempts_after"] == dict(
        place=2 if outcome == "fill_during_cancel" else 1, modify=0, cancel=1)
    assert shutdown["holds"] and all(row["connected"] and not row["shutdown_finished"] for row in shutdown["holds"])
    events = shutdown["evidence"]["events"]
    complete, = [row for row in events if row["event"] == "SHUTDOWN_COMPLETE"]
    assert complete["completed"]
    resolved, = [row for row in events if row["event"] == "PAPER_RELEASE_SHUTDOWN_RESOLVED"]
    state = shutdown["after"]
    if outcome == "fill_during_cancel":
        stop, = protection
        assert stop["order"]["auxPrice"] == 10.35 and stop["order"]["parentId"] == entry["native_id"]
        assert state["canonical_trades"][entry["root_id"]]["quantity_open"] == 1
        assert state["protection"][entry["root_id"]]["protected"]
        assert resolved["gate"] == "PAPER_RELEASE_SHUTDOWN_FILL_PROTECTED"
    else:
        assert not protection and not state["registry"] and not state["post_fill"]
        assert state["capital_reserved"] == state["capital_used"] == 0
        assert resolved["gate"] == "PAPER_RELEASE_SHUTDOWN_CANCELLED_UNFILLED"
    if outcome == "missing_terminal":
        assert len(shutdown["holds"]) == 2
    if outcome == "wrong_client_cancel":
        assert any(row["receipt"]["gate"] == "PAPER_RELEASE_SHUTDOWN_CALLBACK_SCOPE_CONFLICT"
                   for row in shutdown["holds"])
    assert no_external_activity == []
