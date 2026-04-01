from __future__ import annotations

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_registry import resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def test_ross_registry_surfaces_abcd_result() -> None:
    registry = RossPatternRegistry()
    registry._patterns = [pattern for pattern in registry.patterns if getattr(pattern, "pattern_id", "") == "P_ABCD"]
    inputs = PatternInputs(
        symbol="ABCDT",
        timeframe="1m",
        candles=_candles(
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
        ),
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.5, premarket_low=9.6, hod=11.0, prior_close=9.8),
        indicators=IndicatorSet(ema9=10.7, ema20=10.5, vwap=10.6),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=20.0, rvol=2.5),
    )
    result = registry.run(inputs)[0]
    assert result.setup_family_id == "ABCD"
    assert result.detected is True
    assert result.trigger_type == "XL_ABCD_CONTINUATION"
    assert result.trigger_level is not None


def test_abcd_trigger_registry_mapping_fires() -> None:
    evaluator = resolve_trigger_evaluator("ABCD")
    assert evaluator is not None
    payload = evaluator(
        {"trigger_level": 11.0},
        {"candles": _candles([(10.9, 11.1, 10.8, 11.05, 1000)])},
    )
    assert payload["trigger_type"] == "XL_ABCD_CONTINUATION"
    assert payload["trigger_state"] == "FIRED"
    assert payload["trigger_ready_now"] is True
