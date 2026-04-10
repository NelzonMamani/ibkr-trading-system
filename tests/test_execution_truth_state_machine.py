from __future__ import annotations

from types import SimpleNamespace

from src.core_engine.events import RiskDecisionRecord
from src.core_engine.state import RunMode
from src.execution import order_router


def _decision(symbol: str = "TRTH", intent_id: str = "TRTH-1") -> RiskDecisionRecord:
    return RiskDecisionRecord(
        symbol=symbol,
        intent_id=intent_id,
        decision="ALLOW",
        max_position_size=10,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        approved_quantity=10,
        entry_price=25.0,
    )


def test_execution_truth_transition_blocks_non_broker_fill_mutation() -> None:
    truth = order_router._create_execution_truth(
        order_ref="TRADING_OS|ROSS_MOMENTUM|TRTH-1",
        broker_order_id=1,
        symbol="TRTH",
        intent_id="TRTH-1",
        side="BUY",
        submitted_qty=10,
    )

    assert order_router._update_truth_field(truth=truth, field_name="filled_qty", value=5, source="LOCAL") is False
    assert truth.filled_qty == 0


def test_execution_truth_invalid_transition_is_rejected() -> None:
    truth = order_router._create_execution_truth(
        order_ref="TRADING_OS|ROSS_MOMENTUM|TRTH-2",
        broker_order_id=2,
        symbol="TRTH",
        intent_id="TRTH-2",
        side="BUY",
        submitted_qty=10,
    )

    assert order_router._transition_execution_truth_state(truth=truth, next_state="FILLED", source="LOCAL") is False
    assert truth.execution_state == "CREATED"


def test_duplicate_open_position_blocks_at_final_boundary(monkeypatch, capsys) -> None:
    order_router._RUNTIME_POSITIONS.clear()
    order_router._RUNTIME_POSITIONS["DUPX"] = order_router.TrackedPosition(symbol="DUPX", qty=100, state="POSITION_OPEN")
    monkeypatch.setattr(order_router, "_fetch_ibkr_truth", lambda _mode: ([], [SimpleNamespace()], [SimpleNamespace(symbol="DUPX", position=100)]))

    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision(symbol="DUPX", intent_id="DUPX-1")])
    out = capsys.readouterr().out

    assert events[0].action == "BLOCKED"
    assert events[0].detail == "reason=DUPLICATE_POSITION"
    assert "[EXECUTION][HARD_BLOCK] symbol=DUPX reason=DUPLICATE_POSITION" in out


def test_fill_authority_state_is_deterministic_no_intents() -> None:
    events = order_router.execute_intents(mode=RunMode.READ_ONLY, decisions=[])
    assert events == []
    assert order_router.fill_authority_state() == "NO_INTENTS"


def test_callback_normalization_updates_truth_and_logs_raw(capsys) -> None:
    order_router._RUNTIME_ORDERS.clear()
    order_router._EXECUTION_TRUTH_BY_ORDER_ID.clear()
    order_router._upsert_order_from_submission(order_id=77, symbol="TRTH", side="BUY", total_qty=10, order_ref="TRADING_OS|ROSS_MOMENTUM|TRTH-77", intent_id="TRTH-77")
    truth = order_router._create_execution_truth(
        order_ref="TRADING_OS|ROSS_MOMENTUM|TRTH-77",
        broker_order_id=77,
        symbol="TRTH",
        intent_id="TRTH-77",
        side="BUY",
        submitted_qty=10,
    )
    order_router._transition_execution_truth_state(truth=truth, next_state="SUBMITTED", source="LOCAL")

    order_router._on_ibkr_callback({"event_type": "execDetails", "order_id": 77, "symbol": "TRTH", "shares": 10, "price": 22.2, "execId": "X-77"})
    out = capsys.readouterr().out

    assert "[IBKR][CALLBACK_RAW] event=execdetails" in out
    assert "[EXECUTION][CALLBACK_NORMALIZED] event=execDetails" in out
    assert order_router._EXECUTION_TRUTH_BY_ORDER_ID[77].execution_state == "FILLED"
