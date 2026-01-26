from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import MomentumReclaimPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles, vwap):
    return PatternInputs(
        symbol="REC",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(vwap=vwap),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=18.0, rvol=2.0),
    )


def test_momentum_reclaim_detects() -> None:
    candles = [
        Candle(open=10.0, high=10.1, low=9.9, close=9.95, volume=1000),
        Candle(open=9.95, high=10.2, low=9.9, close=10.15, volume=1300),
    ]
    result = MomentumReclaimPattern().evaluate(_inputs(candles, vwap=10.0))
    assert result.detected


def test_momentum_reclaim_rejects_no_cross() -> None:
    candles = [
        Candle(open=10.0, high=10.1, low=9.9, close=10.05, volume=1000),
        Candle(open=10.05, high=10.1, low=10.0, close=10.08, volume=1300),
    ]
    result = MomentumReclaimPattern().evaluate(_inputs(candles, vwap=10.0))
    assert not result.detected
