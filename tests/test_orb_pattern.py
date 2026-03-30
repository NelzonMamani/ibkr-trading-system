from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.patterns.pattern_orb import detect_orb
from src.strategies.common.triggers.trigger_orb import evaluate_orb_trigger
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.strategy_contracts import SessionContext

_ET = ZoneInfo("US/Eastern")


def _candles(rows: list[tuple[int, int, float, float, float, float, float]]) -> list[Candle]:
    return [
        Candle(
            open=o,
            high=h,
            low=l,
            close=c,
            volume=v,
            timestamp=datetime(2026, 3, 30, hour, minute, tzinfo=_ET),
        )
        for hour, minute, o, h, l, c, v in rows
    ]


def _base_inputs() -> PatternInputs:
    return PatternInputs(
        symbol="ORB",
        timeframe="1m",
        session_context=SessionContext.REGULAR,
        candles=_candles(
            [
                (9, 30, 10.00, 10.12, 9.95, 10.05, 1000),
                (9, 31, 10.05, 10.15, 10.00, 10.11, 1100),
                (9, 32, 10.11, 10.20, 10.05, 10.17, 1200),
                (9, 33, 10.17, 10.25, 10.10, 10.20, 1300),
                (9, 34, 10.20, 10.30, 10.12, 10.23, 1400),
                (9, 35, 10.23, 10.28, 10.22, 10.27, 2200),
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


def test_valid_orb_structure_detected_before_trigger_fires() -> None:
    result = detect_orb(_base_inputs())
    assert result.detected is True
    assert result.setup_id == "P_ORB"
    assert result.stop_level == 9.95


def test_opening_range_is_time_window_not_first_five_rows() -> None:
    inputs = _base_inputs()
    rows = [
        (10, 0, 9.70, 11.90, 9.60, 11.80, 500),  # misleading high outside opening window
        (9, 30, 10.00, 10.12, 9.95, 10.05, 1000),
        (9, 31, 10.05, 10.15, 10.00, 10.11, 1100),
        (9, 32, 10.11, 10.20, 10.05, 10.17, 1200),
        (9, 33, 10.17, 10.25, 10.10, 10.20, 1300),
        (9, 34, 10.20, 10.30, 10.12, 10.23, 1400),
        (9, 35, 10.23, 10.28, 10.22, 10.27, 2200),
    ]
    result = detect_orb(replace(inputs, candles=_candles(rows)))
    assert result.detected is True
    assert result.trigger_level == 10.30


def test_missing_opening_range_timestamps_rejected() -> None:
    inputs = _base_inputs()
    rows = [Candle(open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume, timestamp=None) for c in inputs.candles]
    result = detect_orb(replace(inputs, candles=rows))
    assert result.detected is False
    assert result.rejection_reason == "missing_opening_range_timestamps"


def test_low_volume_rejected() -> None:
    inputs = _base_inputs()
    rows = [(c.timestamp.hour, c.timestamp.minute, c.open, c.high, c.low, c.close, c.volume) for c in inputs.candles]
    rows[-1] = (9, 35, 10.23, 10.28, 10.22, 10.27, 500)
    result = detect_orb(replace(inputs, candles=_candles(rows)))
    assert result.detected is False
    assert result.rejection_reason == "breakout_volume_below_opening_average"


def test_below_vwap_is_not_setup_rejection_anymore() -> None:
    inputs = _base_inputs()
    result = detect_orb(replace(inputs, indicators=IndicatorSet(ema9=10.28, ema20=10.18, vwap=10.52)))
    assert result.detected is True


def test_orb_trigger_reports_not_ready_when_not_breaking_orh() -> None:
    inputs = _base_inputs()
    rows = [(c.timestamp.hour, c.timestamp.minute, c.open, c.high, c.low, c.close, c.volume) for c in inputs.candles]
    rows[-1] = (9, 35, 10.23, 10.29, 10.21, 10.28, 2200)
    slower = replace(inputs, candles=_candles(rows))
    result = detect_orb(slower)
    assert result.detected is True
    trigger = evaluate_orb_trigger(
        {"setup_family_id": "OPENING_RANGE_BREAKOUT", "trigger_level": result.trigger_level},
        {
            "candles": slower.candles,
            "active_breakout_range": {"upper": 10.30, "lower": 9.95},
        },
    )
    assert trigger["trigger_ready_now"] is False
    assert trigger["trigger_type"] == "XL_ORB_BREAK"


def test_orb_trigger_fires_correctly() -> None:
    inputs = _base_inputs()
    rows = [(c.timestamp.hour, c.timestamp.minute, c.open, c.high, c.low, c.close, c.volume) for c in inputs.candles]
    rows[-1] = (9, 35, 10.23, 10.55, 10.22, 10.50, 2200)
    fast = replace(inputs, candles=_candles(rows))
    result = detect_orb(fast)
    trigger = evaluate_orb_trigger(
        {"setup_family_id": "OPENING_RANGE_BREAKOUT", "trigger_level": result.trigger_level},
        {"candles": fast.candles, "active_breakout_range": {"upper": 10.30, "lower": 9.95}},
    )
    assert trigger["trigger_ready_now"] is True
    assert trigger["trigger_reason"] == "break_and_hold_above_orh"
