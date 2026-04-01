from __future__ import annotations

from dataclasses import replace

from src.core.engines.setup_hierarchy import SUPPRESSION_REASON, apply_setup_hierarchy
from src.setup_engine.setup_families.breakouts import PremarketHighBreakPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_registry import PATTERN_DETECTORS
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _base_inputs() -> PatternInputs:
    return PatternInputs(
        symbol="PMH",
        timeframe="1m",
        candles=_candles([(9.9, 9.98, 9.82, 9.95, 900), (9.95, 10.08, 9.92, 10.04, 1400)]),
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=10.0, premarket_low=9.6, hod=10.2, prior_close=9.8),
        indicators=IndicatorSet(ema9=9.95, ema20=9.9, vwap=9.96),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=12.0, rvol=1.8),
    )


def test_pmh_break_detects_initial_break() -> None:
    result = PremarketHighBreakPattern().evaluate(_base_inputs())
    assert result.detected is True
    assert result.setup_id == "P_PREMARKET_HIGH_BREAK"
    assert result.setup_family_id == "PREMARKET_HIGH_BREAK"
    assert result.trigger_type == "XL_PREMARKET_HIGH_BREAK"


def test_pmh_break_detects_reclaim() -> None:
    base = _base_inputs()
    inputs = replace(
        base,
        candles=_candles([(10.02, 10.06, 9.9, 9.97, 980), (9.97, 10.05, 9.95, 10.03, 1450)]),
    )
    result = PremarketHighBreakPattern().evaluate(inputs)
    assert result.detected is True
    assert result.setup_metadata.get("pmh_path") == "reclaim"


def test_pmh_break_rejects_wick_only() -> None:
    base = _base_inputs()
    inputs = replace(base, candles=_candles([(9.92, 9.96, 9.88, 9.94, 900), (9.94, 10.2, 9.9, 9.98, 1600)]))
    result = PremarketHighBreakPattern().evaluate(inputs)
    assert result.detected is False
    assert result.rejection_reason == "wick_through_only"


def test_pmh_break_requires_pmh() -> None:
    base = _base_inputs()
    inputs = replace(base, levels=replace(base.levels, premarket_high=None))
    result = PremarketHighBreakPattern().evaluate(inputs)
    assert result.detected is False
    assert result.rejection_reason == "missing_premarket_high"


def test_trigger_arms_and_fires() -> None:
    evaluator = resolve_trigger_evaluator("PREMARKET_HIGH_BREAK")
    assert evaluator is not None
    armed = evaluator({"trigger_level": 10.0}, {"candles": _candles([(9.8, 9.95, 9.75, 9.9, 900), (9.9, 9.99, 9.86, 9.98, 1000)])})
    assert armed["trigger_state"] == "ARMED"
    fired = evaluator({"trigger_level": 10.0}, {"candles": _candles([(9.9, 9.95, 9.85, 9.94, 900), (9.94, 10.1, 9.92, 10.03, 1100)])})
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_registry_contains_pmh_break() -> None:
    assert "P_PREMARKET_HIGH_BREAK" in PATTERN_DETECTORS
    assert "PREMARKET_HIGH_BREAK" in TRIGGER_EVALUATOR_REGISTRY


def test_hierarchy_suppression_under_pmh_break() -> None:
    detected = PremarketHighBreakPattern().evaluate(_base_inputs())
    first_pullback = replace(detected, setup_id="P_FIRST_PULLBACK", setup_family_id="FIRST_PULLBACK", trigger_type="PULLBACK_HIGH_BREAK")
    out = apply_setup_hierarchy([detected, first_pullback], symbol="PMH")
    by_family = {item.setup_family_id: item for item in out}
    assert by_family["PREMARKET_HIGH_BREAK"].detected is True
    assert by_family["FIRST_PULLBACK"].detected is False
    assert by_family["FIRST_PULLBACK"].rejection_reason == SUPPRESSION_REASON
