from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_first_pullback import detect_first_pullback
from src.strategies.common.triggers.trigger_first_pullback import evaluate_first_pullback_trigger
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _inputs(*, candles: list[Candle], ema9: float = 10.1, ema20: float = 9.95) -> PatternInputs:
    return PatternInputs(
        symbol="TEST",
        timeframe="1MIN",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.3, premarket_low=9.7, hod=10.6, lod=9.8, prior_close=9.9),
        indicators=IndicatorSet(ema9=ema9, ema20=ema20, vwap=10.0),
        liquidity_context=LiquidityContext(spread=0.01, rvol=2.0, float_millions=8.0),
        news_context={},
    )


def _valid_candles() -> list[Candle]:
    return [
        Candle(9.90, 10.00, 9.88, 9.98, 1000),
        Candle(9.98, 10.15, 9.97, 10.12, 1200),
        Candle(10.12, 10.32, 10.10, 10.28, 1600),
        Candle(10.28, 10.26, 10.05, 10.10, 900),
        Candle(10.10, 10.18, 10.00, 10.02, 850),
    ]


def test_setup_detected_when_valid() -> None:
    result = detect_first_pullback(_inputs(candles=_valid_candles()))
    assert result.detected is True
    assert result.setup_id == "P_FIRST_PULLBACK"
    assert result.setup_family_id == "FIRST_PULLBACK"
    assert result.trigger_type == "PULLBACK_HIGH_BREAK"
    assert result.trigger_level is not None
    assert result.invalidation_level is not None


def test_setup_rejected_when_invalid() -> None:
    bad = _valid_candles()
    bad[-2] = Candle(10.28, 10.26, 9.85, 9.90, 900)
    result = detect_first_pullback(_inputs(candles=bad))
    assert result.detected is False
    assert result.rejection_reason == "pullback_not_controlled"


def test_trigger_fires_correctly() -> None:
    trigger = evaluate_first_pullback_trigger(
        {"setup_family_id": "FIRST_PULLBACK", "trigger_level": 10.20},
        {"candles": [{"high": 10.25, "close": 10.23}]},
    )
    assert trigger["trigger_state"] == "FIRED"
    assert trigger["trigger_type"] == "XL_FIRST_PULLBACK_BREAK"
    assert trigger["trigger_ready_now"] is True


def test_trigger_armed_when_not_ready() -> None:
    trigger = evaluate_first_pullback_trigger(
        {"setup_family_id": "FIRST_PULLBACK", "trigger_level": 10.20},
        {"candles": [{"high": 10.18, "close": 10.17}]},
    )
    assert trigger["trigger_state"] == "ARMED"
    assert trigger["trigger_type"] == "XL_FIRST_PULLBACK_BREAK"
    assert trigger["trigger_ready_now"] is False


def test_trigger_blocked_when_missing_levels() -> None:
    trigger = evaluate_first_pullback_trigger(
        {"setup_family_id": "FIRST_PULLBACK"},
        {"candles": [{"high": 10.18, "close": 10.17}]},
    )
    assert trigger["trigger_state"] == "BLOCKED"
    assert trigger["trigger_type"] == "XL_FIRST_PULLBACK_BREAK"
    assert trigger["trigger_reason"] == "missing_trigger_level"


def test_deterministic_behavior() -> None:
    inputs = _inputs(candles=_valid_candles())
    a = detect_first_pullback(inputs)
    b = detect_first_pullback(inputs)
    assert a.detected == b.detected
    assert a.trigger_level == b.trigger_level
    assert a.invalidation_level == b.invalidation_level
