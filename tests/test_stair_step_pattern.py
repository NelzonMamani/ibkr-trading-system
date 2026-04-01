from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_trend_continuation_stair_step import detect_trend_continuation_stair_step
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles: list[Candle], *, rvol: float = 1.8) -> PatternInputs:
    return PatternInputs(
        symbol="STEP",
        timeframe="1MIN",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.2, premarket_low=9.8, hod=11.0, prior_close=9.9),
        indicators=IndicatorSet(ema9=10.65, ema20=10.45, vwap=10.5),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=18.0, rvol=rvol),
        news_context={"macd": 0.3},
    )


def _valid_candles() -> list[Candle]:
    return [
        Candle(10.00, 10.12, 9.98, 10.10, 1000),
        Candle(10.10, 10.30, 10.06, 10.25, 1200),
        Candle(10.25, 10.24, 10.12, 10.16, 900),
        Candle(10.16, 10.42, 10.14, 10.38, 1300),
        Candle(10.38, 10.36, 10.24, 10.30, 860),
        Candle(10.30, 10.62, 10.28, 10.58, 1400),
        Candle(10.58, 10.56, 10.34, 10.40, 820),
        Candle(10.40, 10.64, 10.38, 10.61, 1450),
    ]


def test_detects_valid_stair_step() -> None:
    result = detect_trend_continuation_stair_step(_inputs(_valid_candles()))
    assert result.detected is True
    assert result.setup_id == "P_TREND_CONTINUATION_STAIR_STEP"
    assert result.setup_family_id == "TREND_CONTINUATION_STAIR_STEP"
    assert result.signal_class == "ENTRY"
    assert result.trigger_mode == "BREAKOUT_CONTINUATION"
    assert result.setup_metadata["higher_low_sequence_count"] >= 2


def test_rejects_no_higher_low_sequence() -> None:
    candles = _valid_candles()
    candles[4] = Candle(10.38, 10.44, 10.41, 10.43, 860)
    candles[5] = Candle(10.43, 10.62, 10.40, 10.58, 1400)
    candles[-2] = Candle(10.58, 10.56, 10.35, 10.40, 900)
    result = detect_trend_continuation_stair_step(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "no_higher_low_sequence"


def test_rejects_deep_pullback() -> None:
    candles = _valid_candles()
    candles[-2] = Candle(10.58, 10.56, 10.16, 10.20, 900)
    candles[-1] = Candle(10.20, 10.50, 10.18, 10.45, 950)
    result = detect_trend_continuation_stair_step(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "pullback_too_deep"


def test_rejects_low_volume_context() -> None:
    result = detect_trend_continuation_stair_step(_inputs(_valid_candles(), rvol=1.0))
    assert result.detected is False
    assert result.rejection_reason == "invalid_inputs"
