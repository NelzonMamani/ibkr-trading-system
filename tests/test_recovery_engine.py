from __future__ import annotations

from datetime import datetime, timezone

from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.orchestrator import CoreOrchestrator
from src.execution.position_truth import (
    NormalizedBrokerPosition,
    PositionMismatch,
    PositionTruthSnapshot,
)
from src.execution.recovery_engine import apply_recovery_actions, build_recovery_plan


def _as_of() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot(*mismatches: PositionMismatch) -> PositionTruthSnapshot:
    as_of = _as_of()
    return PositionTruthSnapshot(
        broker_positions={
            "AAPL": NormalizedBrokerPosition(
                symbol="AAPL",
                quantity=100,
                avg_cost=100.0,
                market_price=None,
                market_value=None,
                source="ibkr.positions",
                as_of=as_of,
            )
        },
        system_positions={},
        mismatches=list(mismatches),
        matched_symbols=[],
        unknown_symbols=[],
        snapshot_status="MISMATCH" if mismatches else "HEALTHY",
        as_of=as_of,
    )


def test_broker_only_creates_auto_attach_action() -> None:
    plan = build_recovery_plan(
        _snapshot(
            PositionMismatch(
                symbol="AAPL",
                broker_quantity=100,
                system_quantity=0,
                mismatch_type="BROKER_ONLY_POSITION",
                severity="CRITICAL",
                rationale="x",
            )
        ),
        {"healthy": False},
        {"execution_stalled": False},
    )
    assert any(a.action_type == "ATTACH_BROKER_POSITION" and a.safe_to_auto_apply for a in plan.actions)


def test_system_only_requires_manual_intervention() -> None:
    plan = build_recovery_plan(
        _snapshot(
            PositionMismatch(
                symbol="AAPL",
                broker_quantity=0,
                system_quantity=100,
                mismatch_type="SYSTEM_ONLY_POSITION",
                severity="CRITICAL",
                rationale="x",
            )
        ),
        {"healthy": False},
        {"execution_stalled": False},
    )
    action = next(a for a in plan.actions if a.action_type == "MARK_SYSTEM_POSITION_INVALID")
    assert action.requires_manual_intervention is True
    assert action.safe_to_auto_apply is False


def test_execution_stalled_is_flagged() -> None:
    plan = build_recovery_plan(_snapshot(), {"healthy": False}, {"execution_stalled": True, "stalled_symbols": ["AAPL"]})
    assert any(a.action_type == "FLAG_EXECUTION_STALLED" for a in plan.actions)


def test_quantity_mismatch_is_flagged() -> None:
    plan = build_recovery_plan(
        _snapshot(
            PositionMismatch(
                symbol="AAPL",
                broker_quantity=100,
                system_quantity=50,
                mismatch_type="QUANTITY_MISMATCH",
                severity="WARNING",
                rationale="x",
            )
        ),
        {"healthy": False},
        {"execution_stalled": False},
    )
    assert any(a.action_type == "FLAG_QUANTITY_MISMATCH" for a in plan.actions)


def test_no_mismatches_creates_no_action() -> None:
    plan = build_recovery_plan(_snapshot(), {"healthy": True}, {"execution_stalled": False})
    assert len(plan.actions) == 1
    assert plan.actions[0].action_type == "NO_ACTION"


def test_orchestrator_applies_only_safe_recovery_actions() -> None:
    orch = CoreOrchestrator.__new__(CoreOrchestrator)
    orch.trade_registry = ActiveTradeRegistry()
    orch._latest_position_truth_snapshot = _snapshot(
        PositionMismatch(
            symbol="AAPL",
            broker_quantity=100,
            system_quantity=0,
            mismatch_type="BROKER_ONLY_POSITION",
            severity="CRITICAL",
            rationale="x",
        ),
        PositionMismatch(
            symbol="MSFT",
            broker_quantity=0,
            system_quantity=100,
            mismatch_type="SYSTEM_ONLY_POSITION",
            severity="CRITICAL",
            rationale="x",
        ),
    )

    plan = build_recovery_plan(
        orch._latest_position_truth_snapshot,
        {"healthy": False},
        {"execution_stalled": False},
    )
    apply_recovery_actions(plan, orch)

    trades = orch.trade_registry.snapshot()
    assert len(trades) == 1
    assert trades[0].symbol == "AAPL"
    assert getattr(trades[0], "recovery_tag", "") == "broker_attached"
