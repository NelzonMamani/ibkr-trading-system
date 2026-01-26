from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.momentum_patterns import BullFlagPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="BFL",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(ema20=10.4),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=20.0, rvol=2.0),
    )


def test_bull_flag_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.4, low=9.9, close=10.3, volume=1400),
        Candle(open=10.3, high=10.8, low=10.2, close=10.7, volume=1500),
        Candle(open=10.7, high=11.0, low=10.6, close=10.9, volume=1600),
        Candle(open=10.9, high=10.95, low=10.7, close=10.8, volume=1200),
        Candle(open=10.8, high=10.9, low=10.7, close=10.75, volume=1100),
        Candle(open=10.75, high=10.85, low=10.7, close=10.8, volume=1150),
        Candle(open=10.8, high=10.9, low=10.75, close=10.85, volume=1200),
        Candle(open=10.85, high=11.05, low=10.8, close=11.0, volume=1700),
    ]
    result = BullFlagPattern().evaluate(_inputs(candles))
    assert result.detected


def test_bull_flag_rejects_wide_flag() -> None:
    candles = [
        Candle(open=10.0, high=10.4, low=9.9, close=10.3, volume=1400),
        Candle(open=10.3, high=10.8, low=10.2, close=10.7, volume=1500),
        Candle(open=10.7, high=11.0, low=10.6, close=10.9, volume=1600),
        Candle(open=10.9, high=11.2, low=10.2, close=10.3, volume=1200),
        Candle(open=10.3, high=10.8, low=10.0, close=10.7, volume=1100),
        Candle(open=10.7, high=10.9, low=10.1, close=10.2, volume=1150),
        Candle(open=10.2, high=10.6, low=10.0, close=10.4, volume=1200),
        Candle(open=10.4, high=10.6, low=10.1, close=10.2, volume=1700),
    ]
    result = BullFlagPattern().evaluate(_inputs(candles))
    assert not result.detected
