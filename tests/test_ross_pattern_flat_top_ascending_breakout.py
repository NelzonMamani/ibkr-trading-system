from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import FlatTopBreakoutPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="FLT",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=20.0, rvol=1.7),
    )


def test_flat_top_breakout_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.5, low=9.9, close=10.3, volume=1000),
        Candle(open=10.3, high=10.5, low=10.1, close=10.4, volume=1100),
        Candle(open=10.4, high=10.5, low=10.2, close=10.45, volume=1200),
        Candle(open=10.45, high=10.5, low=10.3, close=10.48, volume=1300),
        Candle(open=10.48, high=10.5, low=10.35, close=10.49, volume=1400),
        Candle(open=10.49, high=10.7, low=10.45, close=10.65, volume=1500),
    ]
    result = FlatTopBreakoutPattern().evaluate(_inputs(candles))
    assert result.detected


def test_flat_top_breakout_rejects_no_break() -> None:
    candles = [
        Candle(open=10.0, high=10.5, low=9.9, close=10.3, volume=1000),
        Candle(open=10.3, high=10.5, low=10.1, close=10.4, volume=1100),
        Candle(open=10.4, high=10.5, low=10.2, close=10.45, volume=1200),
        Candle(open=10.45, high=10.5, low=10.3, close=10.48, volume=1300),
        Candle(open=10.48, high=10.5, low=10.35, close=10.49, volume=1400),
        Candle(open=10.49, high=10.5, low=10.45, close=10.48, volume=1500),
    ]
    result = FlatTopBreakoutPattern().evaluate(_inputs(candles))
    assert not result.detected
