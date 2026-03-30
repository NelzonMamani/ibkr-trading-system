from __future__ import annotations

from src.core.engines.trigger_engine import TriggerEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_flat_top_breakout import detect_flat_top_breakout
from src.strategies.common.triggers.trigger_flat_top_breakout import evaluate_flat_top_breakout_trigger
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategies.strategy_contracts import SessionContext


def _inputs(
    candles: list[Candle],
    *,
    rvol: float = 2.0,
    spread: float = 0.005,
    ema9: float = 10.18,
    ema20: float = 10.11,
    vwap: float = 10.14,
) -> PatternInputs:
    return PatternInputs(
        symbol="FLAT",
        timeframe="1MIN",
        candles=candles,
        session_context=SessionContext.REGULAR,
        levels=LevelSet(premarket_high=10.25, premarket_low=9.9, hod=10.2, lod=9.95),
        indicators=IndicatorSet(ema9=ema9, ema20=ema20, vwap=vwap),
        liquidity_context=LiquidityContext(spread=spread, rvol=rvol, float_millions=18.0),
        news_context={},
    )


def _valid_flat_top_candles(*, breakout_close: float = 10.20, breakout_high: float = 10.22) -> list[Candle]:
    return [
        Candle(10.00, 10.12, 9.98, 10.10, 1200),
        Candle(10.10, 10.21, 10.03, 10.15, 1300),
        Candle(10.15, 10.19, 10.07, 10.16, 1100),
        Candle(10.16, 10.21, 10.10, 10.18, 1250),
        Candle(10.18, 10.20, 10.12, 10.17, 1175),
        Candle(10.17, breakout_high, 10.13, breakout_close, 1600),
    ]


def test_valid_flat_top_breakout_detected() -> None:
    result = detect_flat_top_breakout(_inputs(_valid_flat_top_candles()))
    assert result.detected is True
    assert result.setup_id == "P_FLAT_TOP_BREAKOUT"
    assert result.setup_family_id == "FLAT_TOP_BREAKOUT"
    assert result.trigger_type == "BREAKOUT_HIGH"
    assert result.trigger_level is not None
    assert result.invalidation_level is not None
    assert result.invalidation_level < result.trigger_level


def test_reject_when_resistance_not_flat() -> None:
    candles = [
        Candle(10.00, 10.10, 9.98, 10.05, 1200),
        Candle(10.05, 10.16, 10.01, 10.10, 1300),
        Candle(10.10, 10.22, 10.04, 10.14, 1100),
        Candle(10.14, 10.28, 10.08, 10.19, 1250),
        Candle(10.19, 10.34, 10.12, 10.25, 1175),
        Candle(10.25, 10.40, 10.16, 10.32, 1600),
    ]
    result = detect_flat_top_breakout(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason in {"resistance_not_flat", "insufficient_resistance_touches"}


def test_reject_when_insufficient_touches() -> None:
    candles = _valid_flat_top_candles()
    candles[1] = Candle(10.10, 10.18, 10.03, 10.12, 1300)
    candles[3] = Candle(10.16, 10.16, 10.10, 10.14, 1250)
    candles[4] = Candle(10.14, 10.15, 10.11, 10.13, 1175)
    result = detect_flat_top_breakout(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason == "insufficient_resistance_touches"


def test_reject_when_structure_under_resistance_is_weak() -> None:
    candles = [
        Candle(10.00, 10.20, 9.96, 10.08, 1200),
        Candle(10.08, 10.20, 9.90, 10.02, 1300),
        Candle(10.02, 10.19, 9.84, 9.96, 1100),
        Candle(9.96, 10.20, 9.78, 9.90, 1250),
        Candle(9.90, 10.19, 9.72, 9.86, 1175),
        Candle(9.86, 10.20, 9.70, 9.82, 1600),
    ]
    result = detect_flat_top_breakout(_inputs(candles))
    assert result.detected is False
    assert result.rejection_reason in {"lows_not_rising", "pullback_too_loose", "no_supportive_pressure_under_resistance"}


def test_reject_when_liquidity_is_invalid() -> None:
    low_rvol = detect_flat_top_breakout(_inputs(_valid_flat_top_candles(), rvol=0.8))
    assert low_rvol.detected is False
    assert low_rvol.rejection_reason == "rvol_below_threshold"

    wide_spread = detect_flat_top_breakout(_inputs(_valid_flat_top_candles(), spread=0.05))
    assert wide_spread.detected is False
    assert wide_spread.rejection_reason == "spread_too_wide"


def test_trigger_fires_when_break_and_close_above_resistance() -> None:
    trigger = evaluate_flat_top_breakout_trigger(
        {"trigger_level": 10.2, "invalidation_level": 10.1},
        {"candles": [{"high": 10.25, "close": 10.22}]},
    )
    assert trigger["trigger_state"] == "FIRED"
    assert trigger["trigger_ready_now"] is True
    assert trigger["trigger_reason"] == "flat_top_break_confirmed"
    assert trigger["trigger_price_reference"] == 10.2
    assert trigger["invalidation_price_reference"] == 10.1


def test_trigger_armed_when_setup_valid_but_not_broken() -> None:
    trigger = evaluate_flat_top_breakout_trigger(
        {"trigger_level": 10.2, "invalidation_level": 10.1},
        {"candles": [{"high": 10.19, "close": 10.18}]},
    )
    assert trigger["trigger_state"] == "ARMED"
    assert trigger["trigger_ready_now"] is False
    assert trigger["trigger_reason"] == "flat_top_breakout_armed"


def test_trigger_blocked_when_trigger_level_missing() -> None:
    trigger = evaluate_flat_top_breakout_trigger(
        {"invalidation_level": 10.1},
        {"candles": [{"high": 10.19, "close": 10.18}]},
    )
    assert trigger["trigger_state"] == "BLOCKED"
    assert trigger["trigger_ready_now"] is False
    assert trigger["trigger_reason"] == "missing_trigger_level"


def test_pattern_is_deterministic() -> None:
    inputs = _inputs(_valid_flat_top_candles())
    a = detect_flat_top_breakout(inputs)
    b = detect_flat_top_breakout(inputs)
    assert a.detected == b.detected
    assert a.confidence == b.confidence
    assert a.trigger_level == b.trigger_level
    assert a.invalidation_level == b.invalidation_level


def test_ross_trade_structure_uses_trigger_and_invalidation_for_flat_top() -> None:
    pattern = type("Pattern", (), {"pattern_id": "P_FLAT_TOP_BREAKOUT"})()
    trade = RossMomentumStrategyV1._build_trade_from_pattern(
        pattern,
        type("Inputs", (), {"candles": [], "levels": None, "indicators": None, "last_price": 10.0, "symbol": "FLAT"})(),
        selected_trigger={"trigger_price_reference": 10.2, "invalidation_price_reference": 10.1},
    )
    assert trade == (10.2, 10.1)

    blocked = RossMomentumStrategyV1._build_trade_from_pattern(
        pattern,
        type("Inputs", (), {"candles": [], "levels": None, "indicators": None, "last_price": 10.0, "symbol": "FLAT"})(),
        selected_trigger={"trigger_price_reference": None, "invalidation_price_reference": None},
    )
    assert blocked is None


def test_trigger_engine_routes_flat_top_breakout_and_preserves_references() -> None:
    out = TriggerEngine().evaluate_triggers(
        symbol="FLAT",
        candles=[{"high": 10.25, "close": 10.22, "low": 10.12}],
        setups=[
            {
                "setup_family_id": "FLAT_TOP_BREAKOUT",
                "setup_name": "Flat Top Breakout",
                "required_trigger_types": ["BREAKOUT_HIGH"],
                "trigger_level": 10.2,
                "invalidation_level": 10.1,
                "setup_detected": True,
            }
        ],
        levels={},
        structure={},
    )
    assert len(out) == 1
    assert out[0]["setup_family_id"] == "FLAT_TOP_BREAKOUT"
    assert out[0]["trigger_state"] == "FIRED"
    assert out[0]["trigger_type"] == "BREAKOUT_HIGH"
    assert out[0]["trigger_price_reference"] == 10.2
    assert out[0]["invalidation_price_reference"] == 10.1


def test_ross_trust_consumption_includes_flat_top_breakout() -> None:
    strategy = RossMomentumStrategyV1()
    assert "FLAT_TOP_BREAKOUT" in strategy._trusted_setup_families
    assert strategy._resolve_trust_family("P_FLAT_TOP_BREAKOUT") == "FLAT_TOP_BREAKOUT"
