from types import SimpleNamespace

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
