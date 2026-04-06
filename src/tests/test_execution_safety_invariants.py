from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

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
    order_router._RECENT_EXEC_IDS.clear()
    order_router._FILL_AUTHORITY_STATE = "UNKNOWN"
    order_router._UNMATCHED_CALLBACK_COUNT = 0
    order_router._RECONCILED_ORDERS_COUNT = 0
    order_router._RECONCILED_POSITIONS_COUNT = 0
    order_router._CALLBACK_DELAY_WARNINGS_COUNT = 0
    order_router._STARTUP_RECON_COMPLETED = False
    order_router._RECOVERY_STATE_LOADED = False
    order_router._RECON_CYCLE_INDEX = 0
    order_router._RECON_RESYNC_NEEDED = False


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


def test_fill_gap_detection_sets_resync_flag_and_logs(capsys) -> None:
    _reset_router_state()
    order_router._RUNTIME_POSITIONS["AAPL"] = order_router.TrackedPosition(symbol="AAPL", qty=1, state="POSITION_OPEN")
    order_router._run_passive_position_reconciliation(positions=[_StubPosition(symbol="AAPL", position=4)])
    output = capsys.readouterr().out

    assert "[FILL][GAP_DETECTED] symbol=AAPL expected_qty=4 actual_qty=1" in output
    assert order_router._RECON_RESYNC_NEEDED is True
    assert order_router._RUNTIME_POSITIONS["AAPL"].qty == 4


def test_startup_reconciliation_loads_positions_open_orders_and_exec_history() -> None:
    _reset_router_state()
    open_order = SimpleNamespace(
        orderId=77,
        contract=SimpleNamespace(symbol="MSFT"),
        order=SimpleNamespace(action="BUY", totalQuantity=10, orderRef="INTENT-77"),
    )
    execution = SimpleNamespace(
        execution=SimpleNamespace(execId="000abc", orderId=77, shares=5, price=101.25),
        orderId=77,
    )
    position = SimpleNamespace(symbol="MSFT", position=5, avgCost=100.0)
    original_fetch = order_router._fetch_ibkr_truth
    try:
        order_router._fetch_ibkr_truth = lambda mode, include_executions=False: ([open_order], [execution], [position])
        order_router._startup_reconciliation(order_router.RunMode.PAPER)
    finally:
        order_router._fetch_ibkr_truth = original_fetch

    assert order_router._STARTUP_RECON_COMPLETED is True
    assert "MSFT" in order_router._RUNTIME_POSITIONS
    assert order_router._RUNTIME_POSITIONS["MSFT"].qty == 5
    assert 77 in order_router._RUNTIME_ORDERS
    assert "000abc" in order_router._RECENT_EXEC_IDS
