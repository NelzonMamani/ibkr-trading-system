from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import WholeDollarBreakPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="WHOLE",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=9.0, rvol=1.4),
    )


def test_whole_dollar_break_detects() -> None:
    candles = [
        Candle(open=9.8, high=10.0, low=9.7, close=9.9, volume=1000),
        Candle(open=9.9, high=11.1, low=9.9, close=11.05, volume=1400),
    ]
    result = WholeDollarBreakPattern().evaluate(_inputs(candles))
    assert result.detected


def test_whole_dollar_break_rejects_no_break() -> None:
    candles = [
        Candle(open=9.8, high=10.0, low=9.7, close=9.9, volume=1000),
        Candle(open=9.9, high=10.0, low=9.8, close=9.98, volume=1400),
    ]
    result = WholeDollarBreakPattern().evaluate(_inputs(candles))
    assert not result.detected
