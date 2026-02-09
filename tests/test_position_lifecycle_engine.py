from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from config.runtime_config import RunMode  # noqa: E402
from core.active_trade_registry import ActiveTrade  # noqa: E402
from core.position_lifecycle_engine import (  # noqa: E402
    LifecycleIntent,
    LifecycleTransitionError,
    PositionLifecycle,
    PositionLifecycleEngine,
    PositionState,
)


def test_canonical_transitions_allowed():
    trade = ActiveTrade(
        symbol="ABC",
        trader_type="SIM",
        entry_tick=0,
        entry_price=10.0,
        direction="LONG",
        quantity=1,
        strategy_name="Test",
        stop_loss_price=9.0,
    )

    trade.transition_state(PositionState.OPEN, tick=0, reason="Open", reason_code="TEST")
    trade.transition_state(PositionState.SCALING_IN, tick=1, reason="Add", reason_code="TEST")
    trade.transition_state(PositionState.OPEN, tick=2, reason="Scale complete", reason_code="TEST")
    trade.transition_state(PositionState.REDUCING, tick=3, reason="Reduce", reason_code="TEST")
    trade.transition_state(PositionState.OPEN, tick=4, reason="Reduce complete", reason_code="TEST")
    trade.transition_state(PositionState.CLOSING, tick=5, reason="Exit", reason_code="TEST")
    trade.transition_state(PositionState.CLOSED, tick=6, reason="Closed", reason_code="TEST")

    assert trade.state == PositionState.CLOSED


def test_invalid_transition_rejected_with_reason_code():
    trade = ActiveTrade(
        symbol="XYZ",
        trader_type="SIM",
        entry_tick=0,
        entry_price=20.0,
        direction="LONG",
        quantity=1,
        strategy_name="Test",
        stop_loss_price=19.0,
    )

    try:
        trade.transition_state(PositionState.CLOSED, tick=1, reason="Invalid close")
    except Exception as exc:
        assert getattr(exc, "reason_code", None) == "INVALID_TRANSITION"
    else:
        raise AssertionError("Expected invalid transition to be rejected.")


def test_lifecycle_intents_across_modes():
    engine = PositionLifecycleEngine()
    position = PositionLifecycle(symbol="AAA", trader_type="SIM")

    sim_result = engine.apply_intent(
        position,
        LifecycleIntent.OPEN,
        requested_quantity=4,
        run_mode=RunMode.SIM,
        reason="Sim open",
    )
    assert sim_result.accepted is True
    assert position.state == PositionState.OPEN
    assert position.quantity == 2
    assert sim_result.transitions[0].fill_status == "PARTIAL"

    paper_position = PositionLifecycle(symbol="BBB", trader_type="PAPER")
    paper_result = engine.apply_intent(
        paper_position,
        LifecycleIntent.OPEN,
        requested_quantity=1,
        run_mode=RunMode.PAPER,
        reason="Paper open",
    )
    assert paper_result.accepted is True
    assert paper_result.transitions[0].fill_latency_ms == 750
    assert paper_position.quantity == 1

    read_only_position = PositionLifecycle(symbol="CCC", trader_type="READ_ONLY")
    read_only_result = engine.apply_intent(
        read_only_position,
        LifecycleIntent.OPEN,
        requested_quantity=1,
        run_mode=RunMode.READ_ONLY,
        reason="Read-only open",
    )
    assert read_only_result.accepted is True
    assert read_only_result.transitions[0].execution_blocked is True
    assert read_only_position.state == PositionState.OPEN

    live_position = PositionLifecycle(symbol="DDD", trader_type="LIVE")
    denied_result = engine.apply_intent(
        live_position,
        LifecycleIntent.OPEN,
        requested_quantity=1,
        run_mode=RunMode.LIVE,
        reason="Live open",
        risk_approved=False,
    )
    assert denied_result.accepted is False
    assert denied_result.rejection_reason_code == "RISK_APPROVAL_REQUIRED"

    approved_result = engine.apply_intent(
        live_position,
        LifecycleIntent.OPEN,
        requested_quantity=1,
        run_mode=RunMode.LIVE,
        reason="Live open approved",
        risk_approved=True,
    )
    assert approved_result.accepted is True
    assert live_position.state == PositionState.OPEN


def test_invalid_intent_rejected():
    engine = PositionLifecycleEngine()
    position = PositionLifecycle(symbol="EEE", trader_type="SIM")
    result = engine.apply_intent(
        position,
        LifecycleIntent.ADD,
        requested_quantity=1,
        run_mode=RunMode.SIM,
        reason="Invalid add",
    )
    assert result.accepted is False
    assert result.rejection_reason_code == "INVALID_STATE"
