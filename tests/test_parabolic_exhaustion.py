from __future__ import annotations

from dataclasses import replace

from src.core.engines.decision_engine import DecisionEngine
from src.core.engines.setup_hierarchy import SUPPRESSION_REASON, apply_setup_hierarchy
from src.models.data_models import TradeIntent
from src.risk.risk_engine import RiskEngine
from src.setup_engine.setup_families.ross_families import ParabolicExhaustionPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_registry import PATTERN_DETECTORS
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _base_inputs() -> PatternInputs:
    return PatternInputs(
        symbol="PEX",
        timeframe="1m",
        candles=_candles(
            [
                (10.0, 10.1, 9.98, 10.05, 800),
                (10.05, 10.25, 10.03, 10.18, 900),
                (10.18, 10.55, 10.15, 10.45, 1100),
                (10.45, 10.95, 10.4, 10.86, 1300),
                (10.86, 11.9, 10.82, 11.45, 3200),
            ]
        ),
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.6, premarket_low=9.8, hod=11.5, prior_close=9.9),
        indicators=IndicatorSet(ema9=10.5, ema20=10.25, vwap=10.9),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=20.0, rvol=2.2),
    )


def test_detect_valid_parabolic_exhaustion() -> None:
    result = ParabolicExhaustionPattern().evaluate(_base_inputs())
    assert result.detected is True
    assert result.setup_id == "P_PARABOLIC_EXHAUSTION"
    assert result.setup_family_id == "PARABOLIC_EXHAUSTION"
    assert result.non_entry_signal is True
    assert result.signal_class == "RISK_OFF"
    assert result.trigger_mode == "EXIT_SIGNAL"


def test_rejects_normal_trend_without_extension() -> None:
    base = _base_inputs()
    inputs = replace(base, indicators=replace(base.indicators, vwap=11.15))
    result = ParabolicExhaustionPattern().evaluate(inputs)
    assert result.detected is False
    assert result.rejection_reason == "no_extreme_extension"


def test_trigger_fires_with_rejection_or_failed_continuation() -> None:
    evaluator = resolve_trigger_evaluator("PARABOLIC_EXHAUSTION")
    assert evaluator is not None
    fired = evaluator(
        {"trigger_level": 11.5},
        {"candles": _candles([(10.9, 11.4, 10.8, 11.3, 1500), (11.3, 11.55, 11.1, 11.18, 2300)])},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_no_trade_intent_candidate_selected_for_parabolic_exhaustion() -> None:
    detected = ParabolicExhaustionPattern().evaluate(_base_inputs())
    decision = DecisionEngine().compute_decision(
        symbol="PEX",
        levels={},
        structure={"trend": "UP"},
        setups=[{"setup_family": "PARABOLIC_EXHAUSTION"}],
        pattern_results=[detected],
        session_context="RTH",
    )
    assert decision["selected_pattern_id"] is None
    assert decision["decision_state"] == "CANDIDATE_REJECTED_INSUFFICIENT_QUALITY"


def test_parabolic_exhaustion_registered_and_suppresses_lower_setups() -> None:
    assert "P_PARABOLIC_EXHAUSTION" in PATTERN_DETECTORS
    assert "PARABOLIC_EXHAUSTION" in TRIGGER_EVALUATOR_REGISTRY

    dominant = ParabolicExhaustionPattern().evaluate(_base_inputs())
    lower = replace(dominant, setup_id="P_MICRO_PULLBACK", setup_family_id="MICRO_PULLBACK", non_entry_signal=False)
    out = apply_setup_hierarchy([dominant, lower], symbol="PEX")
    by_family = {item.setup_family_id: item for item in out}
    assert by_family["PARABOLIC_EXHAUSTION"].detected is True
    assert by_family["MICRO_PULLBACK"].detected is False
    assert by_family["MICRO_PULLBACK"].rejection_reason == SUPPRESSION_REASON


def test_risk_engine_blocks_intent_when_exhaustion_active() -> None:
    risk = RiskEngine()
    intent = TradeIntent(
        symbol="PEX",
        direction="LONG",
        strategy_name="RossMomentumStrategyV1",
        confidence=0.7,
        rationale="test",
        trader_type="MOMENTUM",
        decision_id="decision-1",
        setup_family_id="PARABOLIC_EXHAUSTION",
    )
    decision = risk.evaluate_trade_intent(intent)
    assert decision.allowed is False
    assert decision.reason_code == "PARABOLIC_EXHAUSTION_SUPPRESSION"
    assert decision.execution_blocked is True
