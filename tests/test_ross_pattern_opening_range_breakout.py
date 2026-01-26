from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.breakout_patterns import OpeningRangeBreakoutPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="ORB",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=12.0, rvol=1.5),
    )


def test_opening_range_breakout_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.2, low=9.9, close=10.1, volume=1000),
        Candle(open=10.1, high=10.3, low=10.0, close=10.2, volume=1100),
        Candle(open=10.2, high=10.35, low=10.1, close=10.3, volume=1200),
        Candle(open=10.3, high=10.4, low=10.2, close=10.35, volume=1300),
        Candle(open=10.35, high=10.45, low=10.3, close=10.4, volume=1400),
        Candle(open=10.4, high=10.6, low=10.35, close=10.55, volume=2000),
    ]
    result = OpeningRangeBreakoutPattern().evaluate(_inputs(candles))
    assert result.detected


def test_opening_range_breakout_rejects_no_break() -> None:
    candles = [
        Candle(open=10.0, high=10.2, low=9.9, close=10.1, volume=1000),
        Candle(open=10.1, high=10.3, low=10.0, close=10.2, volume=1100),
        Candle(open=10.2, high=10.35, low=10.1, close=10.3, volume=1200),
        Candle(open=10.3, high=10.4, low=10.2, close=10.35, volume=1300),
        Candle(open=10.35, high=10.45, low=10.3, close=10.4, volume=1400),
        Candle(open=10.4, high=10.45, low=10.35, close=10.4, volume=1000),
    ]
    result = OpeningRangeBreakoutPattern().evaluate(_inputs(candles))
    assert not result.detected
