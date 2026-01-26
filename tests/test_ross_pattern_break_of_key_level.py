from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import BreakOfKeyLevelPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles, level):
    return PatternInputs(
        symbol="KEY",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(key_levels={"PDH": level}),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=12.0, rvol=2.0),
    )


def test_break_of_key_level_detects() -> None:
    candles = [
        Candle(open=9.8, high=10.0, low=9.7, close=9.9, volume=1000),
        Candle(open=9.9, high=10.2, low=9.85, close=10.15, volume=1500),
    ]
    result = BreakOfKeyLevelPattern().evaluate(_inputs(candles, level=10.0))
    assert result.detected


def test_break_of_key_level_rejects_no_break() -> None:
    candles = [
        Candle(open=9.8, high=10.0, low=9.7, close=9.9, volume=1000),
        Candle(open=9.9, high=10.0, low=9.85, close=9.95, volume=1500),
    ]
    result = BreakOfKeyLevelPattern().evaluate(_inputs(candles, level=10.0))
    assert not result.detected
