from __future__ import annotations

from dataclasses import replace

from src.core.engines.setup_hierarchy import SUPPRESSION_REASON, apply_setup_hierarchy
from src.setup_engine.setup_families.ross_families import MomentumReclaimPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_registry import PATTERN_DETECTORS
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _base_inputs() -> PatternInputs:
    return PatternInputs(
        symbol="MR",
        timeframe="1m",
        candles=_candles([(10.3, 10.34, 10.2, 10.22, 900), (10.22, 10.24, 10.08, 10.12, 880), (10.12, 10.18, 10.05, 10.08, 850), (10.08, 10.36, 10.06, 10.33, 1200)]),
        session_context=SessionContext.REGULAR,
        levels=LevelSet(hod=10.36, prior_close=10.1),
        indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.18),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=10.0, rvol=1.9),
    )


def test_momentum_reclaim_detects_reclaim_confirmation() -> None:
    result = MomentumReclaimPattern().evaluate(_base_inputs())
    assert result.detected is True
    assert result.setup_id == "P_MOMENTUM_RECLAIM"
    assert result.setup_family_id == "P_MOMENTUM_RECLAIM"


def test_registry_contains_momentum_reclaim() -> None:
    assert "P_MOMENTUM_RECLAIM" in PATTERN_DETECTORS
    assert "MOMENTUM_RECLAIM" in TRIGGER_EVALUATOR_REGISTRY


def test_momentum_reclaim_trigger_contract_fields() -> None:
    evaluator = resolve_trigger_evaluator("MOMENTUM_RECLAIM")
    assert evaluator is not None
    payload = evaluator(
        {"trigger_level": 10.2, "invalidation_level": 10.18},
        {"vwap": 10.18, "candles": _candles([(10.1, 10.2, 10.05, 10.12, 800), (10.12, 10.35, 10.1, 10.31, 1200)])},
    )
    assert "trigger_state" in payload
    assert "trigger_ready_now" in payload
    assert "trigger_reason" in payload
    assert payload["trigger_state"] == "FIRED"
    assert payload["trigger_ready_now"] is True


def test_hierarchy_suppression_under_momentum_reclaim() -> None:
    detected = MomentumReclaimPattern().evaluate(_base_inputs())
    micro_pullback = replace(
        detected,
        setup_id="P_MICRO_PULLBACK",
        setup_family_id="MICRO_PULLBACK",
        trigger_type="PULLBACK_HIGH_BREAK",
    )
    out = apply_setup_hierarchy([detected, micro_pullback], symbol="MR")
    by_family = {item.setup_family_id: item for item in out}
    assert by_family["P_MOMENTUM_RECLAIM"].detected is True
    assert by_family["MICRO_PULLBACK"].detected is False
    assert by_family["MICRO_PULLBACK"].rejection_reason == SUPPRESSION_REASON
