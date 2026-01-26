from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import ParabolicExhaustionPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles):
    return PatternInputs(
        symbol="PARA",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=5.0, rvol=5.0),
    )


def test_parabolic_exhaustion_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.2, low=9.9, close=10.1, volume=1000),
        Candle(open=10.1, high=10.4, low=10.0, close=10.3, volume=1100),
        Candle(open=10.3, high=10.7, low=10.2, close=10.6, volume=1300),
        Candle(open=10.6, high=11.5, low=10.5, close=11.4, volume=2000),
    ]
    result = ParabolicExhaustionPattern().evaluate(_inputs(candles))
    assert result.detected


def test_parabolic_exhaustion_rejects_flat() -> None:
    candles = [
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=1000),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=1100),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=1300),
        Candle(open=10.0, high=10.1, low=9.9, close=10.0, volume=2000),
    ]
    result = ParabolicExhaustionPattern().evaluate(_inputs(candles))
    assert not result.detected
