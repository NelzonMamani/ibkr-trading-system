from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_orb import _ORB_RANGE_LOCK, detect_orb
from src.strategies.common.triggers.trigger_orb import evaluate_orb_trigger
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]]) -> list[Candle]:
    start = datetime(2026, 3, 30, 14, 30, tzinfo=timezone.utc)
    out: list[Candle] = []
    for idx, (o, h, l, c, v) in enumerate(rows):
        out.append(Candle(open=o, high=h, low=l, close=c, volume=v, timestamp=start + timedelta(minutes=idx)))
    return out


def _base_inputs() -> PatternInputs:
    return PatternInputs(
        symbol="ORB",
        timeframe="1m",
        session_context=SessionContext.REGULAR,
        candles=_candles(
            [
                (10.00, 10.12, 9.95, 10.05, 1000),
                (10.05, 10.15, 10.00, 10.11, 1100),
                (10.11, 10.20, 10.05, 10.17, 1200),
                (10.17, 10.25, 10.10, 10.20, 1300),
                (10.20, 10.30, 10.12, 10.23, 1400),
                (10.23, 10.45, 10.22, 10.42, 2200),
            ]
        ),
        levels=LevelSet(
            premarket_high=10.45,
            premarket_low=9.80,
            hod=10.30,
            lod=9.95,
            key_levels={"OPENING_RANGE_HIGH": 10.30, "OPENING_RANGE_LOW": 9.95},
        ),
        indicators=IndicatorSet(ema9=10.28, ema20=10.18, vwap=10.24),
        liquidity_context=LiquidityContext(spread=0.003, rvol=2.1, float_millions=18.0),
        news_context={"session_phase": "MORNING", "macd": 0.25, "last_pullback_low": 10.12},
    )


def test_valid_breakout_detected() -> None:
    _ORB_RANGE_LOCK.clear()
    result = detect_orb(_base_inputs())
    assert result.detected is True
    assert result.setup_id == "P_ORB"
    assert result.trigger_level == 10.30
    assert result.stop_level == 9.95


def test_no_break_rejected() -> None:
    inputs = _base_inputs()
    rows = [(c.open, c.high, c.low, c.close, c.volume) for c in inputs.candles]
    rows[-1] = (10.23, 10.29, 10.19, 10.26, 2200)
    result = detect_orb(replace(inputs, candles=_candles(rows)))
    assert result.detected is False
    assert result.rejection_reason == "no_break_above_orh"


def test_no_hold_rejected() -> None:
    inputs = _base_inputs()
    rows = [(c.open, c.high, c.low, c.close, c.volume) for c in inputs.candles]
    rows[-1] = (10.23, 10.55, 10.18, 10.29, 2200)
    result = detect_orb(replace(inputs, candles=_candles(rows)))
    assert result.detected is False
    assert result.rejection_reason == "no_hold_above_orh"


def test_low_volume_rejected() -> None:
    inputs = _base_inputs()
    rows = [(c.open, c.high, c.low, c.close, c.volume) for c in inputs.candles]
    rows[-1] = (10.23, 10.45, 10.22, 10.42, 900)
    result = detect_orb(replace(inputs, candles=_candles(rows)))
    assert result.detected is False
    assert result.rejection_reason == "breakout_volume_below_opening_average"


def test_below_vwap_rejected() -> None:
    inputs = _base_inputs()
    result = detect_orb(replace(inputs, indicators=IndicatorSet(ema9=10.28, ema20=10.18, vwap=10.52)))
    assert result.detected is False
    assert result.rejection_reason == "price_below_vwap"


def test_orb_trigger_fires_correctly() -> None:
    inputs = _base_inputs()
    trigger = evaluate_orb_trigger(
        {"setup_family_id": "OPENING_RANGE_BREAKOUT", "trigger_level": 10.30},
        {
            "candles": inputs.candles,
        },
    )
    assert trigger["trigger_ready_now"] is True
    assert trigger["trigger_type"] == "XL_ORB_BREAK"
    assert trigger["trigger_state"] == "FIRED"


def test_orb_trigger_armed_uses_pattern_trigger_level_only() -> None:
    inputs = _base_inputs()
    rows = [(c.open, c.high, c.low, c.close, c.volume) for c in inputs.candles]
    rows[-1] = (10.23, 10.30, 10.22, 10.29, 2200)
    candles = _candles(rows)
    trigger = evaluate_orb_trigger(
        {"setup_family_id": "OPENING_RANGE_BREAKOUT", "trigger_level": 10.30},
        {
            "candles": candles,
            "active_breakout_range": {"upper": 10.10, "lower": 9.90},
            "key_levels": {"OPENING_RANGE_HIGH": 10.10},
        },
    )
    assert trigger["trigger_ready_now"] is False
    assert trigger["trigger_state"] == "ARMED"
    assert trigger["trigger_reason"] == "orb_trigger_armed"


def test_orb_trigger_blocked_when_missing_orh() -> None:
    inputs = _base_inputs()
    trigger = evaluate_orb_trigger(
        {"setup_family_id": "OPENING_RANGE_BREAKOUT"},
        {"candles": inputs.candles},
    )
    assert trigger["trigger_ready_now"] is False
    assert trigger["trigger_state"] == "BLOCKED"
    assert trigger["trigger_reason"] == "missing_orh"


def test_orb_range_lock_prevents_late_mutation() -> None:
    _ORB_RANGE_LOCK.clear()
    inputs = _base_inputs()
    first = detect_orb(inputs)
    assert first.detected is True
    rows = [(c.open, c.high, c.low, c.close, c.volume) for c in inputs.candles]
    rows[4] = (10.20, 11.50, 9.50, 10.23, 1400)
    second = detect_orb(replace(inputs, candles=_candles(rows)))
    assert second.detected is True
    assert second.trigger_level == first.trigger_level
    assert second.stop_level == first.stop_level


def test_orb_rejects_when_not_near_orh() -> None:
    inputs = _base_inputs()
    rows = [(c.open, c.high, c.low, c.close, c.volume) for c in inputs.candles]
    rows[-2] = (10.20, 10.25, 10.10, 10.20, 1400)
    result = detect_orb(replace(inputs, candles=_candles(rows)))
    assert result.detected is False
    assert result.rejection_reason == "price_not_near_orh"


def test_orb_rejects_when_opening_window_timestamps_missing() -> None:
    inputs = _base_inputs()
    candles = [replace(c, timestamp=None) for c in inputs.candles]
    levels = replace(inputs.levels, key_levels={})
    result = detect_orb(replace(inputs, candles=candles, levels=levels))
    assert result.detected is False
    assert result.rejection_reason == "missing_opening_range_timestamps"


def test_orb_trade_structure_requires_canonical_orh_orl() -> None:
    pattern = type("Pattern", (), {"pattern_id": "P_ORB"})()
    trade = RossMomentumStrategyV1._build_trade_from_pattern(
        pattern,
        type("Inputs", (), {"candles": [], "levels": None, "indicators": None, "last_price": 10.0})(),
        selected_trigger={"trigger_price_reference": 10.3, "invalidation_price_reference": 9.95},
    )
    assert trade == (10.3, 9.95)
    blocked = RossMomentumStrategyV1._build_trade_from_pattern(
        pattern,
        type("Inputs", (), {"candles": [], "levels": None, "indicators": None, "last_price": 10.0})(),
        selected_trigger={"trigger_price_reference": None, "invalidation_price_reference": None},
    )
    assert blocked is None
