from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.additional_patterns import HaltResumeContinuationPattern
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext


def _inputs(candles, flags):
    return PatternInputs(
        symbol="HALT",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(),
        indicators=IndicatorSet(),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=6.0, rvol=4.0),
        data_quality_flags=flags,
    )


def test_halt_resume_continuation_detects() -> None:
    candles = [
        Candle(open=5.0, high=5.2, low=4.9, close=5.1, volume=5000),
        Candle(open=5.1, high=5.6, low=5.0, close=5.55, volume=8000),
    ]
    result = HaltResumeContinuationPattern().evaluate(_inputs(candles, ["HALT_RESUME"]))
    assert result.detected


def test_halt_resume_continuation_rejects_no_flag() -> None:
    candles = [
        Candle(open=5.0, high=5.2, low=4.9, close=5.1, volume=5000),
        Candle(open=5.1, high=5.2, low=5.0, close=5.15, volume=8000),
    ]
    result = HaltResumeContinuationPattern().evaluate(_inputs(candles, []))
    assert not result.detected
