from __future__ import annotations

from src.core.engines.trigger_engine import TriggerEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_micro_pullback import detect_micro_pullback
from src.strategies.common.triggers.trigger_micro_pullback import evaluate_micro_pullback_trigger
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategies.strategy_contracts import SessionContext


def _inputs(*, candles: list[Candle], ema9: float = 10.05) -> PatternInputs:
    return PatternInputs(
        symbol="TEST",
        timeframe="1MIN",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.3, premarket_low=9.9, hod=10.4, lod=9.8, prior_close=9.95),
        indicators=IndicatorSet(ema9=ema9, ema20=9.95, vwap=10.02),
        liquidity_context=LiquidityContext(spread=0.01, rvol=2.1, float_millions=8.0),
        news_context={},
    )


def _valid_candles() -> list[Candle]:
    return [
        Candle(9.90, 10.02, 9.88, 10.00, 1100),
        Candle(10.00, 10.24, 9.99, 10.20, 1800),
        Candle(10.20, 10.36, 10.18, 10.34, 1700),
        Candle(10.34, 10.30, 10.22, 10.24, 950),
        Candle(10.24, 10.28, 10.21, 10.26, 900),
    ]


def test_micro_pullback_setup_detected_when_valid() -> None:
    result = detect_micro_pullback(_inputs(candles=_valid_candles()))
    assert result.detected is True
    assert result.setup_id == "P_MICRO_PULLBACK"
    assert result.setup_family_id == "MICRO_PULLBACK"
    assert result.trigger_type == "XL_MICRO_PULLBACK"
    assert result.trigger_level is not None
    assert result.invalidation_level is not None


def test_micro_pullback_setup_rejected_when_invalid() -> None:
    candles = _valid_candles()
    candles[-2] = Candle(10.34, 10.30, 9.90, 9.95, 950)
    result = detect_micro_pullback(_inputs(candles=candles))
    assert result.detected is False
    assert result.rejection_reason in {"pullback_too_deep", "pullback_lost_continuation_support"}


def test_micro_pullback_pattern_deterministic_behavior() -> None:
    inputs = _inputs(candles=_valid_candles())
    a = detect_micro_pullback(inputs)
    b = detect_micro_pullback(inputs)
    assert a.detected == b.detected
    assert a.trigger_level == b.trigger_level
    assert a.invalidation_level == b.invalidation_level


def test_micro_pullback_trigger_fires_correctly() -> None:
    trigger = evaluate_micro_pullback_trigger(
        {"trigger_level": 10.20, "invalidation_level": 10.05},
        {"candles": [{"high": 10.24, "close": 10.22}]},
    )
    assert trigger["trigger_state"] == "FIRED"
    assert trigger["trigger_ready_now"] is True
    assert trigger["trigger_reason"] == "micro_pullback_break_fired"
    assert trigger["execution_refinement_mode"] == "FAST_MICRO_PULLBACK"


def test_micro_pullback_trigger_armed_when_not_ready() -> None:
    trigger = evaluate_micro_pullback_trigger(
        {"trigger_level": 10.20, "invalidation_level": 10.05},
        {"candles": [{"high": 10.19, "close": 10.18}]},
    )
    assert trigger["trigger_state"] == "ARMED"
    assert trigger["trigger_reason"] == "micro_pullback_armed"


def test_micro_pullback_trigger_blocked_when_levels_missing() -> None:
    missing_trigger = evaluate_micro_pullback_trigger(
        {"invalidation_level": 10.05},
        {"candles": [{"high": 10.19, "close": 10.18}]},
    )
    assert missing_trigger["trigger_state"] == "BLOCKED"
    assert missing_trigger["trigger_reason"] == "missing_trigger_level"

    missing_invalidation = evaluate_micro_pullback_trigger(
        {"trigger_level": 10.20},
        {"candles": [{"high": 10.19, "close": 10.18}]},
    )
    assert missing_invalidation["trigger_state"] == "BLOCKED"
    assert missing_invalidation["trigger_reason"] == "missing_invalidation_level"


def test_trigger_engine_routes_micro_pullback_and_preserves_payload() -> None:
    candles = [{"high": 10.24, "close": 10.22, "low": 10.12}]
    out = TriggerEngine().evaluate_triggers(
        symbol="TEST",
        candles=candles,
        setups=[
            {
                "setup_family_id": "MICRO_PULLBACK",
                "setup_name": "Micro Pullback",
                "required_trigger_types": ["XL_MICRO_PULLBACK"],
                "trigger_level": 10.2,
                "invalidation_level": 10.05,
                "setup_detected": True,
            }
        ],
        levels={},
        structure={},
    )
    assert len(out) == 1
    assert out[0]["trigger_state"] == "FIRED"
    assert out[0]["trigger_ready_now"] is True
    assert out[0]["trigger_price_reference"] == 10.2
    assert out[0]["invalidation_price_reference"] == 10.05
    assert out[0]["execution_refinement_mode"] == "FAST_MICRO_PULLBACK"


def test_strategy_trade_rejects_missing_trigger_entry_or_stop(capsys) -> None:
    pattern = type("Pattern", (), {"pattern_id": "P_MICRO_PULLBACK"})()
    blocked = RossMomentumStrategyV1._build_trade_from_pattern(
        pattern,
        type("Inputs", (), {"candles": [], "levels": None, "indicators": None, "last_price": 10.0, "symbol": "TEST"})(),
        selected_trigger={"trigger_price_reference": None, "invalidation_price_reference": None},
    )
    assert blocked is None
    assert "[TRADE][REJECT] symbol=TEST reason=missing_trigger_entry_or_stop" in capsys.readouterr().out


def test_strategy_execution_refinement_is_carried_to_intent() -> None:
    strategy = RossMomentumStrategyV1()
    assert "MICRO_PULLBACK" in strategy._trusted_setup_families
    pattern = type("Pattern", (), {"pattern_id": "P_MICRO_PULLBACK", "confidence": 0.72})()
    intent = strategy._build_trade_intent(
        symbol="TEST",
        best_pattern=pattern,
        setup_family="MICRO_PULLBACK",
        trigger_ready=True,
        entry=10.2,
        stop=10.05,
        execution_refinement_mode="FAST_MICRO_PULLBACK",
    )
    assert intent is not None
    assert intent.execution_refinement_mode == "FAST_MICRO_PULLBACK"


def test_strategy_execution_mode_classification() -> None:
    strategy = RossMomentumStrategyV1()
    assert strategy._classify_execution_mode("RTH_OPEN") == "EARLY_FAST"
    assert strategy._classify_execution_mode("RTH_MID") == "NORMAL_INTRADAY"
    assert strategy._classify_execution_mode("RTH_LATE") == "LATE_SESSION"
