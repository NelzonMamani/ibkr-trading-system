from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.momentum_patterns import MicroPullbackPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="MPB",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(ema9=10.5),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=12.0, rvol=2.5),
    )


def test_micro_pullback_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.6, low=9.9, close=10.5, volume=1500),
        Candle(open=10.5, high=10.9, low=10.4, close=10.85, volume=1600),
        Candle(open=10.7, high=11.3, low=10.6, close=11.1, volume=900),
        Candle(open=10.95, high=10.96, low=10.85, close=10.9, volume=850),
        Candle(open=10.9, high=10.92, low=10.82, close=10.87, volume=800),
        Candle(open=10.87, high=11.2, low=10.86, close=11.15, volume=1700),
    ]
    result = MicroPullbackPattern().evaluate(_inputs(candles))
    assert result.detected


def test_micro_pullback_rejects_large_pullback() -> None:
    candles = [
        Candle(open=10.0, high=10.6, low=9.9, close=10.5, volume=1500),
        Candle(open=10.5, high=10.7, low=10.4, close=10.6, volume=1600),
        Candle(open=10.6, high=10.65, low=10.0, close=10.1, volume=900),
        Candle(open=10.1, high=10.2, low=9.9, close=10.0, volume=850),
        Candle(open=10.0, high=10.2, low=9.95, close=10.05, volume=1700),
        Candle(open=10.05, high=10.1, low=9.9, close=10.0, volume=1800),
    ]
    result = MicroPullbackPattern().evaluate(_inputs(candles))
    assert not result.detected
