from __future__ import annotations

from dataclasses import replace

from src.setup_engine.setup_families.ross_families import MomentumReclaimPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _base_inputs() -> PatternInputs:
    return PatternInputs(
        symbol="MR",
        timeframe="1m",
        candles=_candles(
            [
                (10.30, 10.34, 10.22, 10.24, 900),
                (10.24, 10.27, 10.10, 10.15, 920),
                (10.15, 10.22, 10.08, 10.12, 940),
                (10.12, 10.38, 10.11, 10.31, 1400),
            ]
        ),
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.5, premarket_low=9.9, hod=10.6, prior_close=10.0),
        indicators=IndicatorSet(ema9=10.20, ema20=10.14, vwap=10.18),
        liquidity_context=LiquidityContext(spread=0.02, float_millions=15.0, rvol=1.8),
    )


def test_momentum_reclaim_detects_valid_reclaim() -> None:
    result = MomentumReclaimPattern().evaluate(_base_inputs())
    assert result.detected is True
    assert result.setup_id == "P_MOMENTUM_RECLAIM"
    assert result.setup_family_id == "MOMENTUM_RECLAIM"
    assert result.trigger_type == "XL_MOMENTUM_RECLAIM"


def test_momentum_reclaim_requires_pullback() -> None:
    base = _base_inputs()
    inputs = replace(base, candles=_candles([(10.22, 10.26, 10.21, 10.24, 900), (10.24, 10.28, 10.22, 10.23, 920), (10.23, 10.32, 10.22, 10.30, 1100)]))
    result = MomentumReclaimPattern().evaluate(inputs)
    assert result.detected is False
    assert result.rejection_reason == "no_pullback_detected"


def test_momentum_reclaim_requires_reclaim() -> None:
    base = _base_inputs()
    inputs = replace(
        base,
        candles=_candles([(10.24, 10.28, 10.1, 10.14, 900), (10.14, 10.20, 10.11, 10.15, 950), (10.15, 10.19, 10.12, 10.16, 1000)]),
    )
    result = MomentumReclaimPattern().evaluate(inputs)
    assert result.detected is False
    assert result.rejection_reason == "no_reclaim"


def test_momentum_reclaim_rejects_weak_reclaim() -> None:
    base = _base_inputs()
    inputs = replace(
        base,
        candles=_candles([(10.24, 10.28, 10.1, 10.15, 900), (10.15, 10.20, 10.12, 10.17, 950), (10.17, 10.55, 10.12, 10.19, 1500)]),
    )
    result = MomentumReclaimPattern().evaluate(inputs)
    assert result.detected is False
    assert result.rejection_reason == "weak_reclaim"


def test_momentum_reclaim_trigger_arms_and_fires() -> None:
    evaluator = resolve_trigger_evaluator("MOMENTUM_RECLAIM")
    assert evaluator is not None
    armed = evaluator(
        {"trigger_level": 10.2, "stop_level": 10.05},
        {"candles": _candles([(10.18, 10.22, 10.1, 10.19, 900), (10.19, 10.24, 10.14, 10.18, 1000)])},
    )
    assert armed["trigger_state"] == "ARMED"
    fired = evaluator(
        {"trigger_level": 10.2, "stop_level": 10.05},
        {"candles": _candles([(10.18, 10.22, 10.1, 10.19, 900), (10.19, 10.30, 10.18, 10.25, 1200)])},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_trigger_registry_contains_momentum_reclaim() -> None:
    assert "MOMENTUM_RECLAIM" in TRIGGER_EVALUATOR_REGISTRY


def test_ross_runtime_can_consume_momentum_reclaim() -> None:
    registry = RossPatternRegistry()
    registry._patterns = [p for p in registry.patterns if getattr(p, "pattern_id", "") == "P_MOMENTUM_RECLAIM"]
    result = registry.run(_base_inputs())[0]
    assert result.setup_id == "P_MOMENTUM_RECLAIM"
    assert result.setup_family_id == "MOMENTUM_RECLAIM"
