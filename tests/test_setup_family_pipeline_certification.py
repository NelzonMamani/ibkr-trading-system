from __future__ import annotations

from src.core.engines.decision_engine import DecisionEngine
from src.core.pipeline_audit import PipelineAudit, TerminalOutcome
from src.models.data_models import TradeIntent
from src.risk.risk_engine import RiskEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_hod_break import evaluate_hod_break_trigger
from src.strategies.common.triggers.trigger_parabolic_exhaustion import evaluate_parabolic_exhaustion_trigger
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def test_hod_break_pipeline_certifies_trigger_to_intent() -> None:
    candles = _candles([(10.48, 10.51, 10.46, 10.51, 1000), (10.51, 10.56, 10.50, 10.531, 1700)])
    trigger = evaluate_hod_break_trigger(
        {"setup_family_id": "HOD_BREAK", "trigger_level": 10.52, "invalidation_level": 10.40, "stop_level": 10.40},
        {"candles": candles, "rvol": 1.3},
    )
    assert trigger["trigger_state"] == "FIRED"

    decision = DecisionEngine().compute_decision(
        symbol="HODX",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "HOD_BREAK"}],
        pattern_results=[
            {
                "setup_id": "P_HOD_BREAK",
                "setup_family_id": "HOD_BREAK",
                "pattern_name": "High of Day Break",
                "detected": True,
                "confidence": 0.8,
                "trigger_level": 10.52,
                "invalidation_level": 10.40,
                "direction": "LONG",
            }
        ],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] == "P_HOD_BREAK"
    assert trigger["trigger_ready_now"] is True


def test_parabolic_exhaustion_pipeline_stays_non_entry_and_risk_blocked() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="PXS",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "PARABOLIC_EXHAUSTION"}],
        pattern_results=[
            {
                "setup_id": "P_PARABOLIC_EXHAUSTION",
                "setup_family_id": "PARABOLIC_EXHAUSTION",
                "pattern_name": "Parabolic Exhaustion",
                "detected": True,
                "confidence": 0.9,
                "direction": "LONG",
                "non_entry_signal": True,
                "signal_class": "RISK_OFF",
                "trigger_mode": "EXIT_SIGNAL",
                "risk_flags": ["EXIT_SIGNAL", "RISK_OFF"],
            }
        ],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] is None

    intent = TradeIntent(
        symbol="PXS",
        direction="LONG",
        strategy_name="RossMomentumStrategyV1",
        confidence=0.8,
        rationale="suppressed",
        trader_type="MOMENTUM",
        decision_id="d1",
        setup_family_id="PARABOLIC_EXHAUSTION",
    )
    risk = RiskEngine().evaluate_trade_intent(intent)
    assert risk.execution_blocked is True
    assert risk.reason_code == "PARABOLIC_EXHAUSTION_SUPPRESSION"

    trigger = evaluate_parabolic_exhaustion_trigger(
        {"trigger_level": 11.5},
        {"candles": _candles([(10.9, 11.4, 10.8, 11.3, 1500), (11.3, 11.55, 11.1, 11.18, 2300)])},
    )
    assert trigger["trigger_state"] == "FIRED"


def test_interaction_hod_break_suppressed_when_parabolic_exhaustion_present() -> None:
    decision = DecisionEngine().compute_decision(
        symbol="MIXD",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "HOD_BREAK"}, {"setup_family": "PARABOLIC_EXHAUSTION"}],
        pattern_results=[
            PatternResult(
                setup_id="P_HOD_BREAK",
                pattern_name="High of Day Break",
                pattern_family=PatternFamily.BREAKOUT,
                detected=True,
                direction=Direction.LONG,
                confidence=0.8,
                setup_quality_tags=[],
                setup_family_id="HOD_BREAK",
                trigger_level=10.52,
                invalidation_level=10.4,
            ),
            PatternResult(
                setup_id="P_PARABOLIC_EXHAUSTION",
                pattern_name="Parabolic Exhaustion",
                pattern_family=PatternFamily.EXHAUSTION,
                detected=True,
                direction=Direction.LONG,
                confidence=0.9,
                setup_quality_tags=[],
                setup_family_id="PARABOLIC_EXHAUSTION",
                non_entry_signal=True,
                signal_class="RISK_OFF",
                trigger_mode="EXIT_SIGNAL",
                risk_flags=["EXIT_SIGNAL", "RISK_OFF"],
            ),
        ],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] is None

    risk = RiskEngine().evaluate_trade_intent(
        TradeIntent(
            symbol="MIXD",
            direction="LONG",
            strategy_name="RossMomentumStrategyV1",
            confidence=0.8,
            rationale="blocked by risk-off suppression",
            trader_type="MOMENTUM",
            decision_id="d2",
            setup_family_id="PARABOLIC_EXHAUSTION",
        )
    )
    assert risk.allowed is False
    assert risk.execution_blocked is True


def test_terminal_outcome_exists_for_every_symbol() -> None:
    audit = PipelineAudit("cert-cycle")
    audit.mark_kept(["HODX", "PXS"])
    audit.record("HODX", TerminalOutcome.TRADE_INTENT_CREATED, "TRIGGER_FIRED_INTENT_CREATED", "intent")
    audit.record("PXS", TerminalOutcome.RISK_BLOCKED, "BLOCKED_BY_RISK", "risk")
    assert audit.contract_violations() == []
