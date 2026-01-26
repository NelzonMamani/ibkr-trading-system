from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import CupAndHandlePattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="CUP",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=30.0, rvol=1.8),
    )


def test_cup_and_handle_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.5, low=9.9, close=10.4, volume=1000),
        Candle(open=10.4, high=10.45, low=10.0, close=10.1, volume=900),
        Candle(open=10.1, high=10.2, low=9.7, close=9.8, volume=800),
        Candle(open=9.8, high=10.0, low=9.6, close=9.9, volume=850),
        Candle(open=9.9, high=10.3, low=9.8, close=10.2, volume=900),
        Candle(open=10.2, high=10.45, low=10.1, close=10.4, volume=950),
        Candle(open=10.4, high=10.45, low=10.2, close=10.3, volume=800),
        Candle(open=10.3, high=10.5, low=10.25, close=10.45, volume=1000),
    ]
    result = CupAndHandlePattern().evaluate(_inputs(candles))
    assert result.detected


def test_cup_and_handle_rejects_flat() -> None:
    candles = [
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=1000),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=900),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=800),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=850),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=900),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=950),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=800),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=1000),
    ]
    result = CupAndHandlePattern().evaluate(_inputs(candles))
    assert not result.detected
