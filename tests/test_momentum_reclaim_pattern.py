from __future__ import annotations

from src.setup_engine.setup_families.ross_families import MomentumReclaimPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.triggers.trigger_registry import TRIGGER_EVALUATOR_REGISTRY, resolve_trigger_evaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    return [Candle(open=o, high=h, low=l, close=c, volume=v) for o, h, l, c, v in rows]


def _base_inputs() -> PatternInputs:
    return PatternInputs(
        symbol="MR",
        timeframe="1m",
        candles=_candles(
            [
                (10.3, 10.34, 10.2, 10.22, 900),
                (10.22, 10.24, 10.08, 10.12, 880),
                (10.12, 10.18, 10.05, 10.08, 850),
                (10.08, 10.36, 10.06, 10.33, 1200),
            ]
        ),
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=10.5, premarket_low=9.8, hod=10.8, prior_close=9.9, key_levels={}),
        indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.18),
        liquidity_context=LiquidityContext(spread=0.01, float_millions=20.0, rvol=1.8),
    )


def test_momentum_reclaim_detected_contract_ids_and_trigger_type() -> None:
    result = MomentumReclaimPattern().evaluate(_base_inputs())
    assert result.detected is True
    assert result.setup_id == "P_MOMENTUM_RECLAIM"
    assert result.setup_family_id == "MOMENTUM_RECLAIM"
    assert result.trigger_type == "XL_MOMENTUM_RECLAIM"


def test_momentum_reclaim_trigger_requires_reclaim_cross() -> None:
    evaluator = resolve_trigger_evaluator("MOMENTUM_RECLAIM")
    assert evaluator is not None

    armed = evaluator(
        {"trigger_level": 10.2, "invalidation_level": 10.05},
        {"candles": _candles([(10.1, 10.18, 10.0, 10.15, 900), (10.15, 10.25, 10.1, 10.19, 920)])},
    )
    assert armed["trigger_type"] == "XL_MOMENTUM_RECLAIM"
    assert armed["trigger_state"] == "ARMED"
    assert armed["trigger_ready_now"] is False

    fired = evaluator(
        {"trigger_level": 10.2, "invalidation_level": 10.05},
        {"candles": _candles([(10.1, 10.18, 10.0, 10.19, 900), (10.18, 10.28, 10.15, 10.22, 920)])},
    )
    assert fired["trigger_state"] == "FIRED"
    assert fired["trigger_ready_now"] is True


def test_momentum_reclaim_trigger_contract_fields_present() -> None:
    evaluator = resolve_trigger_evaluator("MOMENTUM_RECLAIM")
    payload = evaluator(
        {"trigger_level": 10.2, "invalidation_level": 10.05},
        {"candles": _candles([(10.1, 10.18, 10.0, 10.19, 900), (10.18, 10.28, 10.15, 10.22, 920)])},
    )
    required = {
        "trigger_type",
        "trigger_state",
        "trigger_ready_now",
        "trigger_reason",
        "trigger_price_reference",
        "invalidation_price_reference",
    }
    assert required.issubset(payload.keys())


def test_trigger_registry_contains_momentum_reclaim() -> None:
    assert "MOMENTUM_RECLAIM" in TRIGGER_EVALUATOR_REGISTRY
