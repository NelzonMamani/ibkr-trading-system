from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import GapAndGoPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles, prior_close):
    return PatternInputs(
        symbol="GAP",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.PRE,
        levels=LevelSet(prior_close=prior_close),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=10.0, rvol=2.0),
    )


def test_gap_and_go_detects() -> None:
    candles = [
        Candle(open=10.5, high=10.9, low=10.4, close=10.85, volume=1000),
        Candle(open=10.85, high=11.1, low=10.8, close=11.05, volume=1200),
        Candle(open=11.05, high=11.3, low=11.0, close=11.25, volume=1400),
    ]
    result = GapAndGoPattern().evaluate(_inputs(candles, prior_close=10.0))
    assert result.detected


def test_gap_and_go_rejects_small_gap() -> None:
    candles = [
        Candle(open=10.05, high=10.2, low=10.0, close=10.1, volume=1000),
        Candle(open=10.1, high=10.2, low=10.05, close=10.15, volume=1200),
        Candle(open=10.15, high=10.25, low=10.1, close=10.2, volume=1400),
    ]
    result = GapAndGoPattern().evaluate(_inputs(candles, prior_close=10.0))
    assert not result.detected
