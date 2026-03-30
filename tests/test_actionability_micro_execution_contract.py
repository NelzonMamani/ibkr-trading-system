from __future__ import annotations

from src.core.engines.trigger_engine import TriggerEngine
from src.core_engine.events import ExecutionEvent, PatternSummary, RiskDecisionRecord, TradeIntentRecord
from src.core_engine.orchestrator import _emit_final_decisions
from src.core_engine.state import RunMode
from src.execution.order_router import execute_intents
from src.risk.risk_audit import AccountSnapshot, evaluate_trade_intents


def test_trigger_engine_breakout_reports_actionable_reason() -> None:
    triggers = TriggerEngine().evaluate_triggers(
        symbol="ABCD",
        candles=[{"close": 10.2, "high": 10.3, "low": 9.9}],
        setups=[
            {
                "setup_family_id": "FLAT_TOP_BREAKOUT",
                "setup_detected": True,
                "required_trigger_types": ["BREAKOUT_HIGH"],
                "trigger_level": 10.0,
            }
        ],
        levels={"hod": 10.0},
        structure={"is_actionable": True},
    )
    assert triggers[0]["trigger_ready_now"] is True
    assert triggers[0]["trigger_reason"] == "breakout_already_through_level"


def test_paper_micro_mode_sizes_to_one_share(capsys) -> None:
    decisions = evaluate_trade_intents(
        intents=[
            TradeIntentRecord(
                symbol="MCRO",
                intent_id="MCRO-1",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price=25.0,
            )
        ],
        mode=RunMode.PAPER,
        health_status=None,
        account=AccountSnapshot(available_funds=50_000, source="PAPER", canonical=True, broker_connection_state="SIMULATED"),
    )
    out = capsys.readouterr().out
    assert decisions[0].approved_quantity == 1
    assert decisions[0].sizing_basis == "MICRO_TEST_MODE"
    assert "[RISK][SIZING] symbol=MCRO mode=PAPER sizing_basis=MICRO_TEST_MODE approved_quantity=1" in out


def test_execution_dispatch_uses_approved_quantity_and_is_truthful(capsys) -> None:
    events = execute_intents(
        mode=RunMode.PAPER,
        decisions=[
            RiskDecisionRecord(
                symbol="MCRO",
                intent_id="MCRO-1",
                decision="ALLOW",
                max_position_size=1,
                constraints=[],
                triggered_rules=[],
                rationale="ok",
                approved_quantity=1,
            )
        ],
    )
    out = capsys.readouterr().out
    assert events[0].action == "SUBMITTED"
    assert "qty=1" in events[0].detail
    assert "[EXECUTION][DISPATCH] symbol=MCRO dispatch=SIMULATED" in out


def test_final_decision_emits_one_terminal_line_per_symbol(capsys) -> None:
    _emit_final_decisions(
        focus=["ABCD"],
        pattern_summaries=[PatternSummary(symbol="ABCD", best_setup="P_GAP_GO", confidence=0.8, rationale="r", all_patterns=[])],
        intents=[TradeIntentRecord(symbol="ABCD", intent_id="1", setup_id="P_GAP_GO", side="LONG", entry="x", stop="y", rationale="r")],
        risk_decisions=[RiskDecisionRecord(symbol="ABCD", intent_id="1", decision="ALLOW", max_position_size=1, constraints=[], triggered_rules=[], rationale="ok", approved_quantity=1)],
        execution_events=[ExecutionEvent(symbol="ABCD", intent_id="1", action="SUBMITTED", detail="submitted qty=1")],
    )
    out = capsys.readouterr().out
    assert out.count("[ROSS][FINAL_DECISION] symbol=ABCD") == 1
    assert "outcome=ORDER_SUBMITTED" in out


def test_selected_setup_family_maps_to_trigger_candidate() -> None:
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1

    selected = RossMomentumStrategyV1._select_trigger_candidate(
        setup_family_id="ORB",
        trigger_candidates=[
            {"setup_family_id": "OPENING_RANGE_BREAKOUT", "trigger_type": "BREAKOUT_HIGH", "trigger_ready_now": True},
        ],
    )
    assert selected is not None
    assert selected["trigger_type"] == "BREAKOUT_HIGH"
