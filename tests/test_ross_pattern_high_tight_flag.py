from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.momentum_patterns import HighTightFlagPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="HTF",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=18.0, rvol=3.0),
    )


def test_high_tight_flag_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.6, low=9.9, close=10.5, volume=1500),
        Candle(open=10.5, high=11.2, low=10.4, close=11.0, volume=1600),
        Candle(open=11.0, high=11.6, low=10.9, close=11.5, volume=1700),
        Candle(open=11.5, high=11.7, low=11.4, close=11.6, volume=1800),
        Candle(open=11.6, high=11.7, low=11.5, close=11.6, volume=1200),
        Candle(open=11.6, high=11.65, low=11.5, close=11.55, volume=1100),
        Candle(open=11.55, high=11.6, low=11.5, close=11.55, volume=1050),
        Candle(open=11.55, high=11.6, low=11.5, close=11.58, volume=1000),
        Candle(open=11.58, high=11.7, low=11.55, close=11.68, volume=1300),
        Candle(open=11.68, high=11.8, low=11.6, close=11.75, volume=1400),
    ]
    result = HighTightFlagPattern().evaluate(_inputs(candles))
    assert result.detected


def test_high_tight_flag_rejects_small_impulse() -> None:
    candles = [
        Candle(open=10.0, high=10.2, low=9.9, close=10.1, volume=1500),
        Candle(open=10.1, high=10.3, low=10.0, close=10.2, volume=1600),
        Candle(open=10.2, high=10.3, low=10.1, close=10.25, volume=1700),
        Candle(open=10.25, high=10.3, low=10.2, close=10.28, volume=1800),
        Candle(open=10.28, high=10.3, low=10.2, close=10.25, volume=1200),
        Candle(open=10.25, high=10.3, low=10.2, close=10.24, volume=1100),
        Candle(open=10.24, high=10.3, low=10.2, close=10.25, volume=1050),
        Candle(open=10.25, high=10.3, low=10.2, close=10.26, volume=1000),
        Candle(open=10.26, high=10.3, low=10.2, close=10.25, volume=1300),
        Candle(open=10.25, high=10.3, low=10.2, close=10.26, volume=1400),
    ]
    result = HighTightFlagPattern().evaluate(_inputs(candles))
    assert not result.detected
