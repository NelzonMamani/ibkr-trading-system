from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.execution import order_router


@dataclass
class _StubPosition:
    symbol: str
    position: int


def _reset_router_state() -> None:
    order_router._EXECUTION_EVENT_BUFFER.clear()
    order_router._RUNTIME_ORDERS.clear()
    order_router._RUNTIME_POSITIONS.clear()
    order_router._SEEN_EXEC_IDS.clear()
    order_router._FILL_AUTHORITY_STATE = "UNKNOWN"
    order_router._UNMATCHED_CALLBACK_COUNT = 0
    order_router._RECONCILED_ORDERS_COUNT = 0
    order_router._RECONCILED_POSITIONS_COUNT = 0
    order_router._CALLBACK_DELAY_WARNINGS_COUNT = 0
    order_router._STUCK_ORDER_WARNINGS_COUNT = 0
    order_router._DUPLICATE_FILLS_IGNORED_COUNT = 0
    order_router._FILL_LINKAGE_MISMATCH_COUNT = 0


def test_callback_delay_marks_order_pending() -> None:
    _reset_router_state()
    row = order_router._upsert_order_from_submission(
        order_id=101,
        symbol="AAPL",
        side="BUY",
        total_qty=100,
        order_ref="TEST-INTENT-1",
    )
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=20)
    row.first_seen_at = stale_time.isoformat()
    order_router._check_callback_delay(now=datetime.now(timezone.utc))

    assert row.callback_pending is True
    assert row.callback_pending_since is not None
    assert order_router.runtime_lifecycle_snapshot()["callback_delay_warnings_count"] == 1


def test_passive_reconciliation_repairs_position_drift_without_fill_creation() -> None:
    _reset_router_state()
    order_router._RUNTIME_POSITIONS["AAPL"] = order_router.TrackedPosition(symbol="AAPL", qty=1, state="POSITION_OPEN")
    order_router._run_passive_position_reconciliation(positions=[_StubPosition(symbol="AAPL", position=3)])

    assert order_router._RUNTIME_POSITIONS["AAPL"].qty == 3
    assert order_router._RECONCILED_POSITIONS_COUNT == 1
    assert not order_router._EXECUTION_EVENT_BUFFER


def test_execution_stall_detection_invariant_is_hard_fail() -> None:
    text = Path("src/core/orchestrator.py").read_text(encoding="utf-8")
    assert 'RuntimeError("Execution stall detected")' in text


def test_tha_gate_and_callback_fill_authority_are_both_enforced() -> None:
    core_text = Path("src/core/orchestrator.py").read_text(encoding="utf-8")
    router_text = Path("src/execution/order_router.py").read_text(encoding="utf-8")

    assert "[PIPELINE][THA_GATE]" in core_text
    assert "fill_source=CALLBACK_ONLY" in router_text


def test_position_consistency_checks_detect_both_inconsistency_shapes(capsys) -> None:
    _reset_router_state()
    order_router._RUNTIME_ORDERS[1001] = order_router.TrackedOrder(
        broker_order_id=1001,
        order_ref="TEST-INTENT-2",
        symbol="AAPL",
        side="BUY",
        total_qty=10,
        filled_qty=10,
        remaining_qty=0,
        canonical_state="FILLED",
        broker_status="Filled",
    )
    order_router._RUNTIME_POSITIONS["MSFT"] = order_router.TrackedPosition(
        symbol="MSFT",
        qty=5,
        state="POSITION_OPEN",
    )

    order_router._check_position_consistency()
    output = capsys.readouterr().out

    assert "[POSITION][INCONSISTENT_STATE] symbol=AAPL reason=filled_without_position" in output
    assert "[POSITION][INCONSISTENT_STATE] symbol=MSFT reason=position_without_fill_history" in output


def test_execdetails_fill_dedupes_by_exec_id(capsys) -> None:
    _reset_router_state()
    order_router._upsert_order_from_submission(
        order_id=7001,
        symbol="AAPL",
        side="BUY",
        total_qty=10,
        order_ref="TEST-INTENT-DEDUP",
    )
    payload = {"event_type": "execDetails", "order_id": 7001, "symbol": "AAPL", "shares": 2, "price": 101.0, "execId": "E1"}
    order_router._on_ibkr_callback(payload)
    order_router._on_ibkr_callback(payload)
    out = capsys.readouterr().out

    assert "[FILL][DUPLICATE_IGNORED] order_id=7001 exec_id=E1 symbol=AAPL" in out
    assert order_router.runtime_lifecycle_snapshot()["duplicate_fills_ignored_count"] == 1


def test_orderstatus_reported_fill_is_not_fill_authority(capsys) -> None:
    _reset_router_state()
    row = order_router._upsert_order_from_submission(
        order_id=7101,
        symbol="MSFT",
        side="BUY",
        total_qty=5,
        order_ref="TEST-INTENT-FILL-AUTH",
    )
    order_router._on_ibkr_callback(
        {"event_type": "orderStatus", "order_id": 7101, "symbol": "MSFT", "filled": 3, "remaining": 2, "status": "Submitted"}
    )
    out = capsys.readouterr().out

    assert "[FILL_AUTHORITY][STATUS_REPORTED_FILL_IGNORED] order_id=7101 symbol=MSFT status_filled=3 tracked_filled=0" in out
    assert row.filled_qty == 0


def test_execdetails_symbol_linkage_mismatch_is_ignored(capsys) -> None:
    _reset_router_state()
    row = order_router._upsert_order_from_submission(
        order_id=7201,
        symbol="NVDA",
        side="BUY",
        total_qty=4,
        order_ref="TEST-INTENT-LINK",
    )
    order_router._on_ibkr_callback(
        {"event_type": "execDetails", "order_id": 7201, "symbol": "AMD", "shares": 2, "price": 94.0, "execId": "BAD-SYMBOL"}
    )
    out = capsys.readouterr().out

    assert "[ORDER_FILL_LINKAGE][MISMATCH] order_id=7201 tracked_symbol=NVDA callback_symbol=AMD action=fill_ignored" in out
    assert row.filled_qty == 0
    assert order_router.runtime_lifecycle_snapshot()["fill_linkage_mismatch_count"] == 1


def test_callback_delay_escalates_to_stuck_order_once(capsys) -> None:
    _reset_router_state()
    row = order_router._upsert_order_from_submission(
        order_id=7301,
        symbol="TSLA",
        side="BUY",
        total_qty=6,
        order_ref="TEST-INTENT-STUCK",
    )
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=90)
    row.first_seen_at = stale_time.isoformat()
    now = datetime.now(timezone.utc)
    order_router._check_callback_delay(now=now)
    order_router._check_callback_delay(now=now + timedelta(seconds=10))
    out = capsys.readouterr().out

    assert "[EXECUTION][STUCK_ORDER] order_id=7301 symbol=TSLA state=SUBMITTED" in out
    assert order_router.runtime_lifecycle_snapshot()["stuck_order_warnings_count"] == 1
