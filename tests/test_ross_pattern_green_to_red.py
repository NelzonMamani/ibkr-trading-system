from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import GreenToRedPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles, prior_close):
    return PatternInputs(
        symbol="GTR",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(prior_close=prior_close),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=11.0, rvol=1.6),
    )


def test_green_to_red_detects() -> None:
    candles = [
        Candle(open=10.2, high=10.3, low=10.1, close=10.25, volume=1000),
        Candle(open=10.25, high=10.26, low=9.9, close=9.95, volume=1200),
    ]
    result = GreenToRedPattern().evaluate(_inputs(candles, prior_close=10.0))
    assert result.detected


def test_green_to_red_rejects_no_fail() -> None:
    candles = [
        Candle(open=10.2, high=10.3, low=10.1, close=10.25, volume=1000),
        Candle(open=10.25, high=10.3, low=10.1, close=10.2, volume=1200),
    ]
    result = GreenToRedPattern().evaluate(_inputs(candles, prior_close=10.0))
    assert not result.detected
