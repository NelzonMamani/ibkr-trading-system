from __future__ import annotations

from dataclasses import replace

from src.setup_engine.setup_families.ross_families import KeyLevelBreakPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _base_inputs() -> PatternInputs:
    return PatternInputs(
        symbol="KLB",
        timeframe="1m",
        candles=_candles(
            [
                (9.8, 9.95, 9.75, 9.9, 900),
                (9.9, 10.08, 9.88, 10.03, 1200),
            ]
        ),
        session_context=SessionContext.REGULAR,
        levels=LevelSet(
            premarket_high=10.0,
            premarket_low=9.6,
            hod=10.2,
            prior_close=9.7,
            key_levels={"PRIOR_DAY_HIGH": 10.4, "MULTI_DAY_HIGH": 10.8},
        ),
        indicators=IndicatorSet(ema9=9.95, ema20=9.9, vwap=9.97),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=10.0, rvol=2.1),
    )


def test_key_level_break_detects_premarket_high_break() -> None:
    result = KeyLevelBreakPattern().evaluate(_base_inputs())
    assert result.detected is True
    assert result.setup_id == "P_KEY_LEVEL_BREAK"
    assert result.setup_family_id == "KEY_LEVEL_BREAK"
    assert result.trigger_type == "XL_KEY_LEVEL_BREAK"
    assert result.trigger_level == 10.0


def test_level_selection_prefers_levels_above_price() -> None:
    base = _base_inputs()
    inputs = replace(
        base,
        candles=_candles([(10.0, 10.08, 9.99, 10.06, 900), (10.06, 10.16, 10.02, 10.14, 1400)]),
        levels=LevelSet(
            premarket_high=None,
            hod=None,
            prior_close=10.0,
            key_levels={"NEAR_SUPPORT": 10.05, "PRIOR_DAY_HIGH": 10.1},
        ),
    )
    result = KeyLevelBreakPattern().evaluate(inputs)
    assert result.detected is True
    assert result.trigger_level == 10.1
    assert result.setup_metadata.get("level_type") == "PRIOR_DAY_HIGH"


def test_key_level_break_detects_round_number_break() -> None:
    base = _base_inputs()
    inputs = replace(
        base,
        candles=_candles([(10.3, 10.35, 10.18, 10.2, 1000), (10.2, 10.55, 10.18, 10.52, 1400)]),
        levels=LevelSet(premarket_high=None, hod=None, prior_close=10.1, key_levels={}),
    )
    result = KeyLevelBreakPattern().evaluate(inputs)
    assert result.detected is True
    assert result.setup_metadata.get("level_type") in {"WHOLE_DOLLAR", "HALF_DOLLAR"}
    assert result.rationale_text.lower().find("level_type") >= 0


def test_key_level_break_rejects_wick_through_only() -> None:
    base = _base_inputs()
    inputs = replace(
        base,
        candles=_candles([(9.9, 9.98, 9.85, 9.96, 900), (9.96, 10.3, 9.9, 9.98, 1500)]),
    )
    result = KeyLevelBreakPattern().evaluate(inputs)
    assert result.detected is False
    assert result.rejection_reason == "wick_through_only"


def test_key_level_break_rejects_when_no_relevant_level() -> None:
    base = _base_inputs()
    inputs = replace(
        base,
        levels=LevelSet(premarket_high=None, hod=None, prior_close=None, key_levels={}),
        candles=_candles([(4.1, 4.12, 4.0, 4.08, 900), (4.08, 4.12, 4.02, 4.09, 910)]),
    )
    result = KeyLevelBreakPattern().evaluate(inputs)
    assert result.detected is False
    assert result.rejection_reason == "no_relevant_key_level"


def test_key_level_break_trigger_arms_and_fires() -> None:
    evaluator = resolve_trigger_evaluator("KEY_LEVEL_BREAK")
    assert evaluator is not None
    armed = evaluator(
        {"trigger_level": 10.0, "setup_metadata": {"level_type": "PREMARKET_HIGH"}},
        {"candles": _candles([(9.8, 9.95, 9.7, 9.9, 900), (9.9, 9.99, 9.85, 9.98, 1100)])},
    )
    assert armed["trigger_state"] == "ARMED"
    fired = evaluator(
        {"trigger_level": 10.0, "setup_metadata": {"level_type": "PREMARKET_HIGH"}},
        {"candles": _candles([(9.8, 9.95, 9.7, 9.9, 900), (9.9, 10.15, 9.88, 10.05, 1200)])},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_trigger_registry_contains_key_level_break() -> None:
    assert "KEY_LEVEL_BREAK" in TRIGGER_EVALUATOR_REGISTRY


def test_ross_runtime_can_consume_key_level_break_without_bypass() -> None:
    registry = RossPatternRegistry()
    registry._patterns = [p for p in registry.patterns if getattr(p, "pattern_id", "") == "P_KEY_LEVEL_BREAK"]
    result = registry.run(_base_inputs())[0]
    assert result.setup_id == "P_KEY_LEVEL_BREAK"
    assert result.setup_family_id == "KEY_LEVEL_BREAK"
