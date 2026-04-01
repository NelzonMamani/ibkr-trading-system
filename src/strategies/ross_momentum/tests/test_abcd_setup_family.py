from __future__ import annotations

from src.setup_engine.setup_families.ross_families import ABCDPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _inputs(candles: list[Candle]) -> PatternInputs:
    return PatternInputs(
        symbol="ABCDT",
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.5, premarket_low=9.6, hod=11.0, prior_close=9.8),
        indicators=IndicatorSet(ema9=10.7, ema20=10.5, vwap=10.6),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=20.0, rvol=2.5),
    )


def test_abcd_detects_valid_geometry_and_projection() -> None:
    result = ABCDPattern().evaluate(
        _inputs(
            _candles(
                [
                    (10.2, 10.30, 10.10, 10.20, 1000),
                    (10.1, 10.25, 9.90, 10.15, 1100),
                    (10.2, 10.50, 10.15, 10.40, 1200),
                    (10.5, 11.00, 10.40, 10.90, 1400),
                    (10.8, 10.80, 10.50, 10.60, 900),
                    (10.6, 10.70, 10.35, 10.45, 950),
                    (10.5, 10.95, 10.45, 10.90, 1300),
                    (10.9, 11.05, 10.90, 11.02, 1500),
                ]
            )
        )
    )
    assert result.detected is True
    assert result.rejection_reason is None
    assert result.trigger_type == "XL_ABCD_CONTINUATION"
    assert result.anchor_a_index == 1
    assert result.anchor_b_index == 3
    assert result.anchor_c_index == 5
    assert result.trigger_level == 11.0
    assert round(result.ab_length or 0.0, 4) == 1.1
    assert round(result.retracement_pct or 0.0, 4) == 0.5909
    assert round(result.d_projection or 0.0, 4) == 11.45


def test_abcd_rejects_too_shallow_retracement() -> None:
    result = ABCDPattern().evaluate(
        _inputs(
            _candles(
                [
                    (10.2, 10.30, 10.10, 10.20, 1000),
                    (10.1, 10.25, 9.90, 10.15, 1100),
                    (10.2, 10.50, 10.15, 10.40, 1200),
                    (10.5, 11.00, 10.40, 10.90, 1400),
                    (10.8, 10.82, 10.80, 10.81, 900),
                    (10.8, 10.84, 10.78, 10.80, 950),
                    (10.8, 10.90, 10.84, 10.88, 1300),
                    (10.9, 11.00, 10.88, 10.96, 1500),
                ]
            )
        )
    )
    assert result.detected is False
    assert result.rejection_reason == "RETRACEMENT_TOO_SHALLOW"


def test_abcd_rejects_too_deep_retracement() -> None:
    result = ABCDPattern().evaluate(
        _inputs(
            _candles(
                [
                    (10.2, 10.30, 10.10, 10.20, 1000),
                    (10.1, 10.25, 9.90, 10.15, 1100),
                    (10.2, 10.50, 10.15, 10.40, 1200),
                    (10.5, 11.00, 10.40, 10.90, 1400),
                    (10.8, 10.85, 10.30, 10.50, 900),
                    (10.5, 10.65, 10.10, 10.30, 950),
                    (10.4, 10.90, 10.35, 10.80, 1300),
                    (10.8, 10.95, 10.70, 10.90, 1500),
                ]
            )
        )
    )
    assert result.detected is False
    assert result.rejection_reason == "RETRACEMENT_TOO_DEEP"


def test_abcd_rejects_structure_break() -> None:
    result = ABCDPattern().evaluate(
        _inputs(
            _candles(
                [
                    (10.2, 10.30, 10.10, 10.20, 1000),
                    (10.1, 10.25, 9.90, 10.15, 1100),
                    (10.2, 10.50, 10.15, 10.40, 1200),
                    (10.5, 11.00, 10.40, 10.90, 1400),
                    (10.8, 10.90, 10.05, 10.30, 900),
                    (10.3, 10.45, 9.85, 10.05, 950),
                    (10.1, 10.50, 10.00, 10.35, 1300),
                ]
            )
        )
    )
    assert result.detected is False
    assert result.rejection_reason == "STRUCTURE_BROKEN_BELOW_A"


def test_abcd_rejects_insufficient_history() -> None:
    result = ABCDPattern().evaluate(
        _inputs(
            _candles(
                [
                    (10.2, 10.30, 10.10, 10.20, 1000),
                    (10.1, 10.25, 9.90, 10.15, 1100),
                    (10.2, 10.50, 10.15, 10.40, 1200),
                    (10.5, 11.00, 10.40, 10.90, 1400),
                    (10.8, 10.80, 10.50, 10.60, 900),
                ]
            )
        )
    )
    assert result.detected is False
    assert result.rejection_reason == "INSUFFICIENT_CANDLE_HISTORY"
