from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.breakout_patterns import PremarketHighBreakPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles, pm_high):
    return PatternInputs(
        symbol="PMH",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=pm_high),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=12.0, rvol=2.2),
    )


def test_premarket_high_break_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.2, low=9.9, close=10.1, volume=1000),
        Candle(open=10.1, high=10.6, low=10.0, close=10.55, volume=1300),
    ]
    result = PremarketHighBreakPattern().evaluate(_inputs(candles, pm_high=10.3))
    assert result.detected


def test_premarket_high_break_rejects_below() -> None:
    candles = [
        Candle(open=10.0, high=10.2, low=9.9, close=10.1, volume=1000),
        Candle(open=10.1, high=10.25, low=10.0, close=10.2, volume=1300),
    ]
    result = PremarketHighBreakPattern().evaluate(_inputs(candles, pm_high=10.3))
    assert not result.detected
