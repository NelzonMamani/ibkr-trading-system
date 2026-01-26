from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import ABCDContinuationPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="ABCD",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=14.0, rvol=2.2),
    )


def test_abcd_continuation_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.3, low=9.9, close=10.2, volume=1000),
        Candle(open=10.2, high=10.5, low=10.1, close=10.45, volume=1100),
        Candle(open=10.45, high=10.5, low=10.2, close=10.25, volume=900),
        Candle(open=10.25, high=10.6, low=10.2, close=10.55, volume=1300),
    ]
    result = ABCDContinuationPattern().evaluate(_inputs(candles))
    assert result.detected


def test_abcd_continuation_rejects_invalid_shape() -> None:
    candles = [
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=1000),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=1100),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=900),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=1300),
    ]
    result = ABCDContinuationPattern().evaluate(_inputs(candles))
    assert not result.detected
