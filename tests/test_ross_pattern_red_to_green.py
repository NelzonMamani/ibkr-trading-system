from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import RedToGreenPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles, prior_close):
    return PatternInputs(
        symbol="RTG",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(prior_close=prior_close),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=11.0, rvol=1.6),
    )


def test_red_to_green_detects() -> None:
    candles = [
        Candle(open=9.8, high=10.0, low=9.7, close=9.9, volume=1000),
        Candle(open=9.9, high=10.2, low=9.85, close=10.15, volume=1200),
    ]
    result = RedToGreenPattern().evaluate(_inputs(candles, prior_close=10.0))
    assert result.detected


def test_red_to_green_rejects_no_reclaim() -> None:
    candles = [
        Candle(open=9.8, high=10.0, low=9.7, close=9.9, volume=1000),
        Candle(open=9.9, high=10.0, low=9.8, close=9.95, volume=1200),
    ]
    result = RedToGreenPattern().evaluate(_inputs(candles, prior_close=10.0))
    assert not result.detected
