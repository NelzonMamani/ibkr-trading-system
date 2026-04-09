import itertools
from types import SimpleNamespace
import pytest

from src.core_engine.events import RiskDecisionRecord
from src.core_engine.state import RunMode
from src.execution import order_router


def _reset_router() -> None:
    order_router._RUNTIME_ORDERS.clear()
    order_router._RUNTIME_POSITIONS.clear()
    order_router._SEEN_EXEC_IDS.clear()
    order_router._EXECUTION_EVENT_BUFFER.clear()
    order_router._UNMATCHED_CALLBACK_COUNT = 0
    order_router._RECONCILED_ORDERS_COUNT = 0
    order_router._RECONCILED_POSITIONS_COUNT = 0
    order_router._RECON_RESYNC_NEEDED = False
    order_router._EXECUTION_TRACE_BY_INTENT.clear()
    order_router._EXECUTION_TRACE_BY_ORDER_ID.clear()
    order_router._INTENT_ID_BY_ORDER_ID.clear()
    order_router._ORDER_ID_BY_ORDER_REF.clear()
    order_router._EXECUTION_FAILURES_BY_TYPE.clear()
    order_router._UNRESOLVED_EXECUTION_RECONCILIATION_COUNT = 0
    order_router._VISIBILITY_BY_ORDER_ID.clear()
    order_router._LAST_CALLBACK_FINGERPRINT_BY_ORDER_ID.clear()
    order_router._BROKER_ERRORS_BY_ORDER_ID.clear()
    order_router._BROKER_TRUTH_FATALS = 0
    order_router._BROKER_TRUTH_CONFIRMATIONS = 0
    order_router._CONTRACT_VALIDATION_FAILURES = 0
    order_router._NEXT_VALID_ID_REBASES = 0
    order_router._NON_ORDER_UNMATCHED_CALLBACK_COUNT = 0
    order_router._CIRCUIT_BREAKER_ACTIVE = False


def _decision(symbol: str = "ABCD", qty: int = 100, side: str = "LONG") -> RiskDecisionRecord:
    row = RiskDecisionRecord(
        symbol=symbol,
        intent_id=f"{symbol}-1",
        decision="ALLOW",
        max_position_size=qty,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        approved_quantity=qty,
        entry_price=20.0,
        capital_source="IBKR_CANONICAL",
    )
    row.side = side
    return row


def test_entry_order_submitted_then_working_no_fill_yet(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    snap = order_router.runtime_lifecycle_snapshot()
    assert events[0].action == "SUBMITTED"
    assert snap["working_order_count"] == 1
    assert snap["open_position_count"] == 0
    assert snap["pending_entry_count"] == 1


def test_partial_entry_fill_opens_partial_position(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    oid = events[0].broker_order_id
    order_router._on_ibkr_callback({"event_type": "execDetails", "order_id": oid, "symbol": "ABCD", "shares": 20, "price": 21.0, "execId": "E1"})
    snap = order_router.runtime_lifecycle_snapshot()
    assert snap["partial_position_open_count"] == 1
    assert order_router._RUNTIME_POSITIONS["ABCD"].qty == 20
    assert order_router._RUNTIME_ORDERS[oid].remaining_qty == 80


def test_multiple_partial_fills_aggregate_to_full_position(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    oid = events[0].broker_order_id
    order_router._on_ibkr_callback({"event_type": "execDetails", "order_id": oid, "symbol": "ABCD", "shares": 25, "price": 21.0, "execId": "E1"})
    order_router._on_ibkr_callback({"event_type": "execDetails", "order_id": oid, "symbol": "ABCD", "shares": 75, "price": 22.0, "execId": "E2"})
    assert order_router._RUNTIME_ORDERS[oid].filled_qty == 100
    assert order_router._RUNTIME_ORDERS[oid].canonical_state == "FILLED"
    assert order_router._RUNTIME_POSITIONS["ABCD"].qty == 100


def test_exit_partial_fill_reduces_position_but_not_close(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    order_router._RUNTIME_POSITIONS["ABCD"] = order_router.TrackedPosition(symbol="ABCD", qty=50, state="POSITION_OPEN")
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision(qty=50, side="SHORT")])
    oid = events[0].broker_order_id
    order_router._on_ibkr_callback({"event_type": "execDetails", "order_id": oid, "symbol": "ABCD", "shares": 1, "price": 20.5, "execId": "X1"})
    assert order_router._RUNTIME_POSITIONS["ABCD"].qty == 49
    assert order_router._RUNTIME_POSITIONS["ABCD"].state == "POSITION_REDUCING"


def test_exit_final_fill_closes_position(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    order_router._RUNTIME_POSITIONS["ABCD"] = order_router.TrackedPosition(symbol="ABCD", qty=10, state="POSITION_OPEN")
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision(qty=10, side="SHORT")])
    oid = events[0].broker_order_id
    order_router._on_ibkr_callback({"event_type": "execDetails", "order_id": oid, "symbol": "ABCD", "shares": 10, "price": 20.1, "execId": "X2"})
    assert order_router._RUNTIME_POSITIONS["ABCD"].qty == 0
    assert order_router._RUNTIME_POSITIONS["ABCD"].state == "POSITION_CLOSED"


def test_reconciliation_does_not_apply_fill_without_callback(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    oid = events[0].broker_order_id
    order_router._RUNTIME_POSITIONS["ABCD"].qty = 0
    monkeypatch.setattr(
        order_router,
        "_fetch_ibkr_truth",
        lambda mode: (
            [SimpleNamespace(symbol="ABCD", order=SimpleNamespace(action="BUY", orderRef="ABCD-1"), contract=SimpleNamespace(symbol="ABCD"))],
            [SimpleNamespace(orderId=oid, shares=100, price=20.2)],
            [SimpleNamespace(symbol="ABCD", position=100, avgCost=20.2)],
        ),
    )
    order_router._sync_submitted_events_from_ibkr(RunMode.PAPER, events)
    assert events[0].filled_quantity == 0
    assert events[0].remaining_quantity == 100
    assert order_router._RUNTIME_ORDERS[oid].filled_qty == 0
    assert order_router._RUNTIME_POSITIONS["ABCD"].qty == 0


def test_duplicate_exec_callback_is_idempotent(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    oid = events[0].broker_order_id
    payload = {"event_type": "execDetails", "order_id": oid, "symbol": "ABCD", "shares": 10, "price": 21.0, "execId": "DUP1"}
    order_router._on_ibkr_callback(payload)
    order_router._on_ibkr_callback(payload)
    assert order_router._RUNTIME_ORDERS[oid].filled_qty == 10


def test_working_orders_persist_across_cycles(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    order_router.execute_intents(mode=RunMode.PAPER, decisions=[])
    assert order_router.runtime_lifecycle_snapshot()["working_order_count"] == 1


def test_final_decision_summary_distinguishes_submitted_vs_filled(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    oid = events[0].broker_order_id
    order_router._on_ibkr_callback({"event_type": "execDetails", "order_id": oid, "symbol": "ABCD", "shares": 100, "price": 21.2, "execId": "FIN1"})
    snap = order_router.runtime_lifecycle_snapshot()
    print(f"submitted_vs_filled=working:{snap['working_order_count']} filled:{snap['fully_filled_order_count']}")
    out = capsys.readouterr().out
    assert "submitted_vs_filled=working:0 filled:1" in out


def test_post_submission_diagnostics_delayed_then_confirmed(monkeypatch, capsys) -> None:
    _reset_router()
    order_router._RUNTIME_ORDERS[101] = order_router.TrackedOrder(
        broker_order_id=101,
        order_ref="ABCD-1",
        symbol="ABCD",
        side="BUY",
        total_qty=10,
        remaining_qty=10,
    )
    open_orders_responses = iter([[], [SimpleNamespace(orderId=101)]])
    client = SimpleNamespace(
        openOrders=lambda: next(open_orders_responses, [SimpleNamespace(orderId=101)]),
        executions=lambda: [],
    )
    manager = SimpleNamespace(get_client=lambda: client)
    tick = itertools.count(start=0, step=1)
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: False)
    monkeypatch.setattr(order_router.time, "time", lambda: float(next(tick)))
    monkeypatch.setattr(order_router.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("IBKR_ORDER_SUBMISSION_ENABLED", "true")
    monkeypatch.setenv("IBKR_READONLY_ENABLED", "false")
    order_router._post_submission_ibkr_diagnostics(
        mode=RunMode.PAPER,
        manager=manager,
        submitted_order_ids=[101],
    )
    out = capsys.readouterr().out
    assert "[IBKR][OPEN_ORDERS]" in out
    assert "[IBKR][EXEC_HISTORY]" in out
    assert "[IBKR][ORDER_STATUS]" in out
    assert "[IBKR][EXEC_DETAILS]" in out
    assert "[BROKER_TRUTH][ESCALATION_LEVEL=2] phase=POLLING" in out
    assert "[BROKER_TRUTH][CONFIRMED]" in out
    assert "[CRITICAL] IBKR_NO_FILL_CONFIRMATION" in out


def test_post_submission_broker_truth_fatal_when_no_broker_visibility(monkeypatch) -> None:
    _reset_router()
    order_router._RUNTIME_ORDERS[202] = order_router.TrackedOrder(
        broker_order_id=202,
        order_ref="ABCD-1",
        symbol="ABCD",
        side="BUY",
        total_qty=10,
        remaining_qty=10,
    )
    client = SimpleNamespace(openOrders=lambda: [], executions=lambda: [])
    manager = SimpleNamespace(get_client=lambda: client)
    tick = itertools.count(start=0, step=1)
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: False)
    monkeypatch.setattr(order_router.time, "time", lambda: float(next(tick)))
    monkeypatch.setattr(order_router.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("IBKR_ORDER_SUBMISSION_ENABLED", "true")
    monkeypatch.setenv("IBKR_READONLY_ENABLED", "false")
    with pytest.raises(RuntimeError, match="BROKER_TRUTH_NOT_CONFIRMED"):
        order_router._post_submission_ibkr_diagnostics(
            mode=RunMode.PAPER,
            manager=manager,
            submitted_order_ids=[202],
        )


def test_post_submission_test_mode_skips_ack_and_broker_truth_failures(monkeypatch, capsys) -> None:
    _reset_router()
    order_router._RUNTIME_ORDERS[303] = order_router.TrackedOrder(
        broker_order_id=303,
        order_ref="ABCD-1",
        symbol="ABCD",
        side="BUY",
        total_qty=10,
        remaining_qty=10,
    )
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    tick = itertools.count(start=0, step=1)
    monkeypatch.setattr(order_router.time, "time", lambda: float(next(tick)))
    monkeypatch.setattr(order_router.time, "sleep", lambda _seconds: None)
    order_router._post_submission_ibkr_diagnostics(
        mode=RunMode.PAPER,
        manager=None,
        submitted_order_ids=[303],
    )
    out = capsys.readouterr().out
    assert "[EXECUTION][ACK_SKIPPED_NON_LIVE]" in out
    assert "[EXECUTION][BROKER_TRUTH_SKIPPED]" in out


def test_execdetails_callback_reconciles_via_order_ref(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    oid = events[0].broker_order_id
    order_router._on_ibkr_callback(
        {"event_type": "execDetails", "orderRef": "TRADING_OS|ROSS_MOMENTUM|ABCD-1", "symbol": "ABCD", "shares": 10, "price": 21.0, "execId": "R1"}
    )
    out = capsys.readouterr().out
    assert f"[ORDER_EVENT][RECONCILED] source=orderRef order_ref=TRADING_OS|ROSS_MOMENTUM|ABCD-1 order_id={oid}" in out
    assert order_router._RUNTIME_ORDERS[oid].filled_qty == 10


def test_unmatched_callback_without_order_id_or_order_ref_does_not_fabricate_order(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    existing_order_ids = set(order_router._RUNTIME_ORDERS.keys())
    order_router._on_ibkr_callback({"event_type": "execDetails", "symbol": "ABCD", "shares": 10, "price": 21.0, "execId": "MISS1"})
    out = capsys.readouterr().out
    assert "[ORDER_EVENT][UNMATCHED]" in out
    assert "[EXECUTION][RECONCILIATION_FAILED]" in out
    assert set(order_router._RUNTIME_ORDERS.keys()) == existing_order_ids
    assert order_router._UNMATCHED_CALLBACK_COUNT >= 1
    assert order_router._UNRESOLVED_EXECUTION_RECONCILIATION_COUNT >= 1
    assert order_router._RUNTIME_ORDERS[events[0].broker_order_id].filled_qty == 0


def test_no_symbol_based_order_ref_fallback(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    order_router._on_ibkr_callback({"event_type": "execDetails", "orderRef": "ABCD", "symbol": "ABCD", "shares": 10, "price": 20.0, "execId": "SYMB1"})
    out = capsys.readouterr().out
    assert "[ORDER_EVENT][RECONCILED] source=orderRef order_ref=ABCD" not in out
    assert "[EXECUTION][RECONCILIATION_FAILED]" in out


def test_execution_cycle_emits_summary_and_failure_classification(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    _ = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    out = capsys.readouterr().out
    assert "[EXECUTION][SUMMARY]" in out
    assert "[EXECUTION][FAIL]" in out
    assert "TYPE=NO_ACK" in out or "TYPE=NO_FILL" in out or "type=NO_ACK" in out or "type=NO_FILL" in out


def test_callback_openorder_and_position_update_trace(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    oid = int(events[0].broker_order_id)
    order_router._on_ibkr_callback({"event_type": "openOrder", "order_id": oid, "symbol": "ABCD"})
    order_router._on_ibkr_callback({"event_type": "position", "order_id": oid, "symbol": "ABCD", "position": 100})
    trace = order_router._EXECUTION_TRACE_BY_ORDER_ID[oid]
    assert trace.ack_received is True
    assert trace.position_opened is True


def test_positionend_callback_not_treated_as_unmatched_order(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision()])
    order_router._on_ibkr_callback({"event_type": "positionEnd"})
    out = capsys.readouterr().out
    assert "[EXECUTION][RECONCILIATION_FAILED] event=CALLBACK callback=positionend" not in out
    assert order_router._UNRESOLVED_EXECUTION_RECONCILIATION_COUNT == 0


def test_circuit_breaker_blocks_new_submission_after_degradation(monkeypatch) -> None:
    _reset_router()
    order_router._CIRCUIT_BREAKER_ACTIVE = True
    allowed = order_router._ensure_submission_allowed(RunMode.LIVE, symbol="ABCD")
    assert allowed is False
    assert order_router._CIRCUIT_BREAKER_ACTIVE is True


def test_duplicate_working_order_logic_ignores_legacy_mismatched_intent(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    legacy_open_orders = [
        SimpleNamespace(
            symbol="ABCD",
            orderId=77,
            status="Submitted",
            order=SimpleNamespace(action="BUY", orderRef="TRADING_OS|ROSS_MOMENTUM|ABCD-LEGACY"),
        )
    ]
    monkeypatch.setattr(order_router, "_fetch_ibkr_truth", lambda _mode: (legacy_open_orders, [], []))
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision("ABCD", 100)])
    out = capsys.readouterr().out
    assert events[0].action == "SUBMITTED"
    assert "[EXECUTION][DUPLICATE_IGNORE_STALE]" in out


def test_broker_reject_code_201_dominates_terminal_state(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision("CLIK", 10)])
    oid = int(events[0].broker_order_id)
    order_router._on_ibkr_callback(
        {"event_type": "error", "order_id": oid, "symbol": "CLIK", "errorCode": 201, "errorString": "Order rejected due to permissions"}
    )
    tracked = order_router._RUNTIME_ORDERS[oid]
    assert order_router._resolve_authoritative_execution_state(tracked) == "BROKER_REJECTED"
    assert tracked.normalized_reject_reason == "PERMISSION_SMALL_CAP_OPENING_RESTRICTED"


def test_queued_for_rth_status_not_terminal_no_fill(monkeypatch) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision("RTHQ", 10)])
    oid = int(events[0].broker_order_id)
    order_router._on_ibkr_callback({"event_type": "orderStatus", "order_id": oid, "symbol": "RTHQ", "status": "PreSubmitted", "filled": 0, "remaining": 10})
    order_router._on_ibkr_callback(
        {"event_type": "error", "order_id": oid, "symbol": "RTHQ", "errorCode": 399, "errorString": "order will not be placed until 09:30 US/Eastern"}
    )
    tracked = order_router._RUNTIME_ORDERS[oid]
    assert tracked.queued_for_rth_seen is True
    assert order_router._resolve_authoritative_execution_state(tracked) == "BROKER_QUEUED_FOR_RTH"


def test_callback_enrichment_maps_missing_symbol_from_order_id(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision("ENRH", 10)])
    oid = int(events[0].broker_order_id)
    order_router._on_ibkr_callback({"event_type": "orderStatus", "order_id": oid, "status": "Submitted", "filled": 0, "remaining": 10})
    out = capsys.readouterr().out
    assert "[EXECUTION][CALLBACK_ENRICHED]" in out


def test_callback_dedup_avoids_duplicate_state_noise(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision("DEDP", 10)])
    oid = int(events[0].broker_order_id)
    payload = {"event_type": "orderStatus", "order_id": oid, "symbol": "DEDP", "status": "Submitted", "filled": 0, "remaining": 10}
    order_router._on_ibkr_callback(payload)
    order_router._on_ibkr_callback(payload)
    out = capsys.readouterr().out
    assert "[EXECUTION][CALLBACK_DEDUP]" in out


def test_cycle_emits_truth_rows_consistent_with_final_state(monkeypatch, capsys) -> None:
    _reset_router()
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision("TRTH", 10)])
    oid = int(events[0].broker_order_id)
    order_router._on_ibkr_callback({"event_type": "orderStatus", "order_id": oid, "symbol": "TRTH", "status": "Submitted", "filled": 0, "remaining": 10})
    _ = order_router.execute_intents(mode=RunMode.PAPER, decisions=[])
    out = capsys.readouterr().out
    assert "[EXECUTION][TRUTH_ROW]" in out
    assert "[EXECUTION][TRUTH_SUMMARY]" in out
