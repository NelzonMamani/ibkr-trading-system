from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import FirstPullbackPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="FPB",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=15.0, rvol=2.0),
    )


def test_first_pullback_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.5, low=9.9, close=10.4, volume=1000),
        Candle(open=10.4, high=10.8, low=10.3, close=10.7, volume=1200),
        Candle(open=10.7, high=10.75, low=10.5, close=10.55, volume=900),
        Candle(open=10.55, high=10.6, low=10.4, close=10.45, volume=800),
        Candle(open=10.45, high=10.9, low=10.4, close=10.85, volume=1400),
        Candle(open=10.85, high=11.0, low=10.8, close=10.95, volume=1500),
    ]
    result = FirstPullbackPattern().evaluate(_inputs(candles))
    assert result.detected


def test_first_pullback_rejects_no_breakout() -> None:
    candles = [
        Candle(open=10.0, high=10.5, low=9.9, close=10.4, volume=1000),
        Candle(open=10.4, high=10.8, low=10.3, close=10.7, volume=1200),
        Candle(open=10.7, high=10.75, low=10.5, close=10.55, volume=900),
        Candle(open=10.55, high=10.6, low=10.4, close=10.45, volume=800),
        Candle(open=10.45, high=10.6, low=10.4, close=10.5, volume=1400),
        Candle(open=10.5, high=10.6, low=10.4, close=10.55, volume=1500),
    ]
    result = FirstPullbackPattern().evaluate(_inputs(candles))
    assert not result.detected
