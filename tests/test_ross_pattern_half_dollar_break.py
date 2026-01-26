from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import HalfDollarBreakPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="HALF",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=9.0, rvol=1.4),
    )


def test_half_dollar_break_detects() -> None:
    candles = [
        Candle(open=9.9, high=10.0, low=9.8, close=9.95, volume=1000),
        Candle(open=9.95, high=10.6, low=9.9, close=10.55, volume=1400),
    ]
    result = HalfDollarBreakPattern().evaluate(_inputs(candles))
    assert result.detected


def test_half_dollar_break_rejects_no_break() -> None:
    candles = [
        Candle(open=9.9, high=10.0, low=9.8, close=9.95, volume=1000),
        Candle(open=9.95, high=10.0, low=9.9, close=9.98, volume=1400),
    ]
    result = HalfDollarBreakPattern().evaluate(_inputs(candles))
    assert not result.detected
