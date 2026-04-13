from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core_engine.state import RunMode
from src.core_engine.events import ExecutionEvent as OrchestratorExecutionEvent, RiskDecisionRecord
from src.execution.fill_authority import (
    FillAuthorityVerdict,
    build_execution_records,
    classify_execution_delays,
    evaluate_fill_authority,
)
from src.core_engine.orchestrator import _apply_fill_authority_entry_guard


def _as_of() -> datetime:
    return datetime.now(timezone.utc)


def test_no_orders_is_healthy() -> None:
    records = build_execution_records({}, _as_of())
    delays = classify_execution_delays(records, _as_of(), run_mode=RunMode.PAPER)
    verdict = evaluate_fill_authority(records, delays, run_mode=RunMode.PAPER)
    assert verdict.healthy is True
    assert verdict.block_position_updates is False


def test_order_with_execdetails_is_healthy() -> None:
    now = _as_of()
    rows = {
        101: {
            "broker_order_id": 101,
            "symbol": "AAPL",
            "total_qty": 10,
            "filled_qty": 10,
            "avg_fill_price": 200.0,
            "canonical_state": "FILLED",
            "first_seen_at": (now - timedelta(seconds=1)).isoformat(),
            "last_update_at": now.isoformat(),
        }
    }
    records = build_execution_records(rows, now)
    delays = classify_execution_delays(records, now, run_mode=RunMode.PAPER)
    verdict = evaluate_fill_authority(records, delays, run_mode=RunMode.PAPER)
    assert verdict.healthy is True
    assert verdict.missing_exec_count == 0


def test_order_without_execdetails_gets_pending_or_delayed(monkeypatch) -> None:
    monkeypatch.setenv("EXEC_CALLBACK_DELAY_WARN_SECONDS", "2")
    monkeypatch.setenv("EXEC_CALLBACK_DELAY_STALL_SECONDS", "9")
    now = _as_of()
    rows = {
        102: {
            "broker_order_id": 102,
            "symbol": "MSFT",
            "total_qty": 5,
            "filled_qty": 0,
            "avg_fill_price": None,
            "canonical_state": "WORKING",
            "first_seen_at": (now - timedelta(seconds=3)).isoformat(),
            "last_update_at": now.isoformat(),
        }
    }
    records = build_execution_records(rows, now)
    delays = classify_execution_delays(records, now, run_mode=RunMode.PAPER)
    assert delays[0].state in {"PENDING_CALLBACK", "DELAYED"}


def test_stalled_execution_blocks_new_entries(monkeypatch) -> None:
    monkeypatch.setenv("EXEC_CALLBACK_DELAY_WARN_SECONDS", "1")
    monkeypatch.setenv("EXEC_CALLBACK_DELAY_STALL_SECONDS", "2")
    now = _as_of()
    rows = {
        103: {
            "broker_order_id": 103,
            "symbol": "NVDA",
            "total_qty": 10,
            "filled_qty": 0,
            "avg_fill_price": None,
            "canonical_state": "WORKING",
            "first_seen_at": (now - timedelta(seconds=8)).isoformat(),
            "last_update_at": now.isoformat(),
        }
    }
    records = build_execution_records(rows, now)
    delays = classify_execution_delays(records, now, run_mode=RunMode.PAPER)
    verdict = evaluate_fill_authority(records, delays, run_mode=RunMode.PAPER)
    assert verdict.stalled_exec_count == 1
    assert verdict.block_new_entries is True


def test_sim_mode_always_healthy() -> None:
    now = _as_of()
    records = build_execution_records({}, now)
    delays = classify_execution_delays(records, now, run_mode=RunMode.SIM)
    verdict = evaluate_fill_authority(records, delays, run_mode=RunMode.SIM)
    assert delays == []
    assert verdict.healthy is True
    assert verdict.block_new_entries is False


def test_orchestrator_guard_blocks_new_intents_for_stalled_execution() -> None:
    decision = RiskDecisionRecord(
        symbol="AAPL",
        intent_id="intent-1",
        decision="ALLOW",
        max_position_size=10,
        constraints=[],
        triggered_rules=[],
        rationale="test",
        approved_quantity=10,
    )
    verdict = FillAuthorityVerdict(
        healthy=False,
        missing_exec_count=0,
        delayed_exec_count=0,
        stalled_exec_count=1,
        block_position_updates=True,
        block_new_entries=True,
        rationale="execution_stalled",
    )
    blocked = _apply_fill_authority_entry_guard(decision, mode=RunMode.PAPER, verdict=verdict)
    assert isinstance(blocked, OrchestratorExecutionEvent)
    assert blocked.action == "BLOCKED"


def test_no_fake_fills_generated_from_order_status_only() -> None:
    now = _as_of()
    rows = {
        104: {
            "broker_order_id": 104,
            "symbol": "TSLA",
            "total_qty": 20,
            "filled_qty": 0,
            "avg_fill_price": None,
            "canonical_state": "FILLED",
            "first_seen_at": (now - timedelta(seconds=1)).isoformat(),
            "last_update_at": now.isoformat(),
        }
    }
    records = build_execution_records(rows, now)
    assert records[104].filled_qty == 0
    assert records[104].has_exec_details is False
    verdict = evaluate_fill_authority(records, classify_execution_delays(records, now, run_mode=RunMode.PAPER), run_mode=RunMode.PAPER)
    assert verdict.missing_exec_count == 1
