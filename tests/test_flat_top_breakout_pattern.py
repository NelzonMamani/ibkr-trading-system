from __future__ import annotations

from src.core.engines.trigger_engine import TriggerEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_flat_top_breakout import detect_flat_top_breakout
from src.strategies.common.triggers.trigger_flat_top_breakout import evaluate_flat_top_breakout_trigger
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext


def _inputs(*, candles: list[Candle], spread: float = 0.01, rvol: float = 2.0) -> PatternInputs:
    return PatternInputs(
        symbol="FTOP",
        timeframe="1MIN",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(hod=10.27, lod=9.8, premarket_high=10.1, premarket_low=9.7, prior_close=9.9),
        indicators=IndicatorSet(ema9=10.12, ema20=10.02, vwap=10.08),
        liquidity_context=LiquidityContext(spread=spread, float_millions=12.0, rvol=rvol),
        news_context={},
    )


def _valid_candles() -> list[Candle]:
    return [
        Candle(10.02, 10.18, 9.99, 10.14, 1000),
        Candle(10.14, 10.19, 10.05, 10.16, 1050),
        Candle(10.16, 10.20, 10.08, 10.17, 1020),
        Candle(10.17, 10.19, 10.10, 10.18, 1100),
        Candle(10.18, 10.30, 10.14, 10.27, 1600),
    ]


def test_flat_top_breakout_detects_valid_structure() -> None:
    result = detect_flat_top_breakout(_inputs(candles=_valid_candles()))
    assert result.detected is True
    assert result.setup_id == "P_FLAT_TOP_BREAKOUT"
    assert result.setup_family_id == "FLAT_TOP_BREAKOUT"
    assert result.trigger_type == "BREAKOUT_HIGH"
    assert result.trigger_level is not None
    assert result.invalidation_level is not None


def test_flat_top_breakout_rejects_non_flat_resistance() -> None:
    candles = _valid_candles()
    candles[1] = Candle(10.14, 10.24, 10.05, 10.16, 1050)
    result = detect_flat_top_breakout(_inputs(candles=candles))
    assert result.detected is False
    assert result.rejection_reason == "resistance_not_flat"


def test_flat_top_breakout_rejects_insufficient_touches() -> None:
    candles = [
        Candle(10.02, 10.159, 9.99, 10.14, 1000),
        Candle(10.14, 10.19, 10.05, 10.16, 1050),
        Candle(10.16, 10.15, 10.08, 10.14, 1020),
        Candle(10.17, 10.19, 10.10, 10.18, 1100),
        Candle(10.18, 10.30, 10.14, 10.27, 1600),
    ]
    result = detect_flat_top_breakout(_inputs(candles=candles))
    assert result.detected is False
    assert result.rejection_reason == "insufficient_touches"


def test_flat_top_breakout_rejects_weak_structure_under_resistance() -> None:
    candles = _valid_candles()
    candles[0] = Candle(10.02, 10.18, 9.65, 10.10, 1000)
    candles[1] = Candle(10.10, 10.19, 9.70, 10.11, 1000)
    candles[2] = Candle(10.11, 10.20, 9.75, 10.13, 1000)
    candles[3] = Candle(10.13, 10.19, 9.70, 10.14, 1000)
    result = detect_flat_top_breakout(_inputs(candles=candles))
    assert result.detected is False
    assert result.rejection_reason == "weak_structure_under_resistance"


def test_flat_top_breakout_rejects_liquidity_failures() -> None:
    wide_spread = detect_flat_top_breakout(_inputs(candles=_valid_candles(), spread=0.07))
    low_rvol = detect_flat_top_breakout(_inputs(candles=_valid_candles(), rvol=0.8))
    assert wide_spread.detected is False
    assert wide_spread.rejection_reason == "liquidity_spread_too_wide"
    assert low_rvol.detected is False
    assert low_rvol.rejection_reason == "liquidity_rvol_too_low"


def test_flat_top_breakout_pattern_is_deterministic() -> None:
    inputs = _inputs(candles=_valid_candles())
    a = detect_flat_top_breakout(inputs)
    b = detect_flat_top_breakout(inputs)
    assert a.detected == b.detected
    assert a.trigger_level == b.trigger_level
    assert a.invalidation_level == b.invalidation_level


def test_flat_top_trigger_fires_when_breaks_above_level() -> None:
    trigger = evaluate_flat_top_breakout_trigger(
        {"trigger_level": 10.20, "invalidation_level": 10.05},
        {"candles": [{"high": 10.24, "close": 10.22}]},
    )
    assert trigger["trigger_state"] == "FIRED"
    assert trigger["trigger_ready_now"] is True
    assert trigger["trigger_reason"] == "breakout_already_through_level"


def test_flat_top_trigger_arms_when_not_yet_broken() -> None:
    trigger = evaluate_flat_top_breakout_trigger(
        {"trigger_level": 10.20, "invalidation_level": 10.05},
        {"candles": [{"high": 10.19, "close": 10.18}]},
    )
    assert trigger["trigger_state"] == "ARMED"
    assert trigger["trigger_ready_now"] is False


def test_flat_top_trigger_blocks_when_trigger_level_missing() -> None:
    trigger = evaluate_flat_top_breakout_trigger(
        {"invalidation_level": 10.05},
        {"candles": [{"high": 10.24, "close": 10.22}]},
    )
    assert trigger["trigger_state"] == "BLOCKED"
    assert trigger["trigger_reason"] == "missing_trigger_level"


def test_flat_top_trigger_missing_invalidation_does_not_block() -> None:
    trigger = evaluate_flat_top_breakout_trigger(
        {"trigger_level": 10.20},
        {"candles": [{"high": 10.24, "close": 10.22}]},
    )
    assert trigger["trigger_state"] == "FIRED"
    assert trigger["trigger_ready_now"] is True
    assert "MISSING_INVALIDATION_REFERENCE" in set(trigger["trigger_quality_flags"])


def test_trigger_engine_routes_flat_top_through_registry() -> None:
    out = TriggerEngine().evaluate_triggers(
        symbol="TEST",
        candles=[{"high": 10.24, "close": 10.22, "low": 10.15}],
        setups=[
            {
                "setup_family_id": "FLAT_TOP_BREAKOUT",
                "setup_name": "Flat Top Breakout",
                "required_trigger_types": ["BREAKOUT_HIGH"],
                "trigger_level": 10.2,
                "setup_detected": True,
            }
        ],
        levels={"hod": 10.2},
        structure={"is_actionable": True},
    )
    assert len(out) == 1
    assert out[0]["trigger_state"] == "FIRED"
    assert out[0]["trigger_ready_now"] is True
    assert "MISSING_INVALIDATION_REFERENCE" in set(out[0]["trigger_quality_flags"])


def test_trigger_engine_has_no_flat_top_special_case_branch() -> None:
    source = TriggerEngine._is_ready.__code__.co_consts
    assert "setup_family == \"FLAT_TOP_BREAKOUT\"" not in str(source)
