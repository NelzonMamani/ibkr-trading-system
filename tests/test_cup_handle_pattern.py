from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_cup_handle import detect_cup_handle
from src.strategies.common.triggers.trigger_cup_handle import evaluate_cup_handle_trigger
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles: list[Candle]) -> PatternInputs:
    return PatternInputs(
        symbol="TEST",
        timeframe="5MIN",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.2, premarket_low=9.8, hod=10.7, lod=9.8, prior_close=9.9),
        indicators=IndicatorSet(ema9=10.3, ema20=10.15, vwap=10.2),
        liquidity_context=LiquidityContext(spread=0.01, rvol=2.1, float_millions=20.0),
    )


def _valid_cup_handle() -> list[Candle]:
    return [
        Candle(10.35, 10.50, 10.30, 10.45, 1200),
        Candle(10.45, 10.52, 10.38, 10.50, 1150),
        Candle(10.50, 10.54, 10.42, 10.48, 1100),
        Candle(10.48, 10.50, 10.32, 10.36, 1080),
        Candle(10.36, 10.40, 10.12, 10.20, 980),
        Candle(10.20, 10.25, 10.05, 10.12, 920),
        Candle(10.12, 10.18, 10.02, 10.08, 900),
        Candle(10.08, 10.16, 10.01, 10.11, 890),
        Candle(10.11, 10.24, 10.08, 10.20, 910),
        Candle(10.20, 10.34, 10.17, 10.30, 940),
        Candle(10.30, 10.44, 10.28, 10.40, 960),
        Candle(10.40, 10.50, 10.37, 10.47, 970),
        Candle(10.47, 10.49, 10.41, 10.44, 820),
        Candle(10.44, 10.48, 10.42, 10.47, 1120),
    ]


def test_cup_handle_detects_valid_structure() -> None:
    result = detect_cup_handle(_inputs(_valid_cup_handle()))
    assert result.detected is True
    assert result.setup_id == "P_CUP_HANDLE"
    assert result.setup_family_id == "CUP_HANDLE"
    assert result.trigger_type == "XL_CUP_HANDLE_BREAK"


def test_cup_handle_rejects_v_shape() -> None:
    candles = _valid_cup_handle()
    candles[8] = Candle(10.11, 10.49, 10.10, 10.48, 1000)
    result = detect_cup_handle(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "v_shape_rejection"


def test_cup_handle_rejects_missing_handle() -> None:
    candles = _valid_cup_handle()
    candles[12] = Candle(10.47, 10.62, 10.45, 10.60, 1100)
    result = detect_cup_handle(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "handle_not_formed"


def test_cup_handle_rejects_handle_too_deep() -> None:
    candles = _valid_cup_handle()
    candles[12] = Candle(10.47, 10.49, 9.95, 10.00, 1300)
    candles[13] = Candle(10.00, 10.15, 9.92, 10.05, 1400)
    result = detect_cup_handle(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "handle_too_deep"


def test_cup_handle_trigger_arms_and_fires() -> None:
    armed = evaluate_cup_handle_trigger(
        {"trigger_level": 10.50, "stop_level": 10.40},
        {"candles": [{"high": 10.49, "close": 10.48}, {"high": 10.50, "close": 10.49}]},
    )
    assert armed["trigger_state"] == "ARMED"
    assert armed["trigger_ready_now"] is False

    fired = evaluate_cup_handle_trigger(
        {"trigger_level": 10.50, "stop_level": 10.40},
        {"candles": [{"high": 10.49, "close": 10.48}, {"high": 10.53, "close": 10.52}]},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_trigger_registry_contains_cup_handle() -> None:
    assert resolve_trigger_evaluator("CUP_HANDLE") is not None
