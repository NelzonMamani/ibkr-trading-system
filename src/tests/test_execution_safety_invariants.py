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
    order_router._IBKR_POSITIONS_BY_SYMBOL.clear()
    order_router._SEEN_EXEC_IDS.clear()
    order_router._FILL_AUTHORITY_STATE = "UNKNOWN"
    order_router._UNMATCHED_CALLBACK_COUNT = 0
    order_router._RECONCILED_ORDERS_COUNT = 0
    order_router._RECONCILED_POSITIONS_COUNT = 0
    order_router._RECON_RESYNC_NEEDED = False
    order_router._CALLBACK_DELAY_WARNINGS_COUNT = 0


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


def test_passive_reconciliation_detects_position_drift_without_fill_creation() -> None:
    _reset_router_state()
    order_router._RUNTIME_POSITIONS["AAPL"] = order_router.TrackedPosition(symbol="AAPL", qty=1, state="POSITION_OPEN")
    order_router.set_trading_control_mode("ISOLATED_TRADING")
    order_router._run_passive_position_reconciliation(positions=[_StubPosition(symbol="AAPL", position=3)])

    assert order_router._RUNTIME_POSITIONS["AAPL"].qty == 1
    assert order_router._RECONCILED_POSITIONS_COUNT == 0
    assert order_router._RECON_RESYNC_NEEDED is False
    assert order_router._POSITION_OWNERSHIP_BY_SYMBOL["AAPL"] == order_router.OWNERSHIP_EXTERNAL
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
    order_router._IBKR_POSITIONS_BY_SYMBOL["MSFT"] = order_router.IbkrPositionTruth(
        symbol="MSFT",
        quantity=5,
        avg_price=10.0,
    )

    order_router._check_position_consistency()
    output = capsys.readouterr().out

    assert "[POSITION][INCONSISTENT_STATE] symbol=AAPL reason=PENDING_POSITION_CONFIRMATION" in output
    assert "[POSITION][INCONSISTENT_STATE] symbol=MSFT reason=position_without_fill_history" in output


def test_ibkr_position_callback_populates_in_memory_truth_store(capsys) -> None:
    _reset_router_state()
    order_router._on_ibkr_callback(
        {"event_type": "position", "symbol": "AAPL", "position": 1, "avgCost": 2.45}
    )
    output = capsys.readouterr().out

    assert "[POSITION][SYNC] symbol=AAPL qty=1 avg_price=2.45 source=IBKR" in output
    assert order_router._IBKR_POSITIONS_BY_SYMBOL["AAPL"].quantity == 1
    assert order_router._IBKR_POSITIONS_BY_SYMBOL["AAPL"].avg_price == 2.45


def test_passive_reconciliation_emits_position_summary_and_mismatch(capsys) -> None:
    _reset_router_state()
    order_router._RUNTIME_ORDERS[2001] = order_router.TrackedOrder(
        broker_order_id=2001,
        order_ref="TEST-INTENT-3",
        symbol="AAPL",
        side="BUY",
        total_qty=1,
        filled_qty=1,
        remaining_qty=0,
        canonical_state="FILLED",
        broker_status="Filled",
        avg_fill_price=2.45,
    )
    order_router._run_passive_position_reconciliation(positions=[_StubPosition(symbol="AAPL", position=2)])
    output = capsys.readouterr().out

    assert "[POSITION][MISMATCH] symbol=AAPL expected_position=1 ibkr_position=2" in output
    assert "[POSITION][SUMMARY] total_positions=1 mismatches=1" in output
