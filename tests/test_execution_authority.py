from __future__ import annotations

from src.core_engine.events import RiskDecisionRecord
from src.execution.execution_authority import ExecutionAuthority


def _decision(symbol: str = "AAPL", intent: str = "i-1", qty: int = 10) -> RiskDecisionRecord:
    return RiskDecisionRecord(
        symbol=symbol,
        intent_id=intent,
        decision="ALLOW",
        max_position_size=qty,
        constraints=[],
        triggered_rules=[],
        rationale="ok",
        approved_quantity=qty,
        entry_price=10.0,
    )


def test_order_transitions_submitted_to_filled() -> None:
    auth = ExecutionAuthority()
    submit = auth.register_submit_request(_decision(), local_submission_id="l-1")
    assert submit.action == "SUBMITTING"
    status = auth.apply_order_status({"local_submission_id": "l-1", "order_id": 11, "status": "Submitted", "filled": 0, "remaining": 10})
    assert status is not None and status.action == "SUBMITTED"
    fill, _ = auth.apply_fill({"local_submission_id": "l-1", "order_id": 11, "exec_id": "e1", "fill_qty": 10, "cumulative_qty": 10, "fill_price": 11.0})
    assert fill is not None and fill.action == "FILLED"


def test_partial_before_full() -> None:
    auth = ExecutionAuthority()
    auth.register_submit_request(_decision(), local_submission_id="l-1")
    auth.apply_order_status({"local_submission_id": "l-1", "order_id": 11, "status": "Submitted", "filled": 0, "remaining": 10})
    part, _ = auth.apply_fill({"local_submission_id": "l-1", "order_id": 11, "exec_id": "e1", "fill_qty": 4, "cumulative_qty": 4, "fill_price": 11.0})
    full, _ = auth.apply_fill({"local_submission_id": "l-1", "order_id": 11, "exec_id": "e2", "fill_qty": 6, "cumulative_qty": 10, "fill_price": 12.0})
    assert part is not None and part.action == "PARTIALLY_FILLED"
    assert full is not None and full.action == "FILLED"


def test_duplicate_fill_is_idempotent() -> None:
    auth = ExecutionAuthority()
    auth.register_submit_request(_decision(), local_submission_id="l-1")
    auth.apply_order_status({"local_submission_id": "l-1", "order_id": 11, "status": "Submitted", "filled": 0, "remaining": 10})
    first, _ = auth.apply_fill({"local_submission_id": "l-1", "order_id": 11, "exec_id": "e1", "fill_qty": 10, "cumulative_qty": 10, "fill_price": 11.0})
    second, _ = auth.apply_fill({"local_submission_id": "l-1", "order_id": 11, "exec_id": "e1", "fill_qty": 10, "cumulative_qty": 10, "fill_price": 11.0})
    assert first is not None
    assert second is None


def test_position_opens_only_on_fill() -> None:
    auth = ExecutionAuthority()
    auth.register_submit_request(_decision(), local_submission_id="l-1")
    status = auth.apply_order_status({"local_submission_id": "l-1", "order_id": 11, "status": "Submitted", "filled": 0, "remaining": 10})
    assert status is not None
    fill, position = auth.apply_fill({"local_submission_id": "l-1", "order_id": 11, "exec_id": "e1", "fill_qty": 1, "cumulative_qty": 1, "fill_price": 10.0})
    assert fill is not None
    assert position is not None and position["action"] == "OPEN"


def test_rejected_never_opens_position() -> None:
    auth = ExecutionAuthority()
    auth.register_submit_request(_decision(), local_submission_id="l-1")
    status = auth.apply_order_status({"local_submission_id": "l-1", "order_id": 11, "status": "Inactive", "filled": 0, "remaining": 10})
    assert status is not None
    fill, position = auth.apply_fill({"local_submission_id": "l-1", "order_id": 11, "exec_id": "e1", "fill_qty": 0, "cumulative_qty": 0, "fill_price": 10.0})
    assert fill is None
    assert position is None


def test_no_synthetic_broker_id_before_ack() -> None:
    auth = ExecutionAuthority()
    event = auth.register_submit_request(_decision(), local_submission_id="l-1")
    assert event.broker_order_id is None
