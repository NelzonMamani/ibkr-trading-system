from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.engines.setup_engine import SetupEngine
from src.strategies.common.candles.candle_types import Candle


def _candle(open_p: float, high: float, low: float, close: float, minute: int) -> Candle:
    base = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    return Candle(
        open=open_p,
        high=high,
        low=low,
        close=close,
        volume=1_000.0,
        timestamp=base + timedelta(minutes=minute),
    )


def _families(setups: list[dict]) -> set[str]:
    return {str(item.get("setup_family")) for item in setups}


def test_setup_engine_distinct_priority_enforces_single_family() -> None:
    candles = [
        _candle(10.0, 10.2, 9.9, 10.1, 0),
        _candle(10.1, 10.6, 10.0, 10.55, 1),
        _candle(10.55, 10.58, 10.35, 10.4, 2),
        _candle(10.4, 10.7, 10.38, 10.66, 3),
    ]
    setups = SetupEngine().compute_setups(
        candles=candles,
        levels={
            "symbol": "XYZ",
            "pullback_high": 10.6,
            "micro_range_high": 10.6,
            "active_breakout_range": {"upper": 10.6, "lower": 10.3},
            "premarket_high": 10.6,
            "hod": 10.6,
        },
        structure={
            "trend": "UP",
            "pullback_active": True,
            "compression_active": True,
            "consolidation_active": True,
            "impulse_active": True,
            "pullback_depth": {"pct": 0.25},
        },
        session_context="RTH_OPEN",
    )
    target = _families(setups) & {"FIRST_PULLBACK", "MICRO_PULLBACK", "BULL_FLAG", "HOD_BREAK", "PREMARKET_HIGH_BREAK"}
    assert len(target) == 1


def test_first_pullback_rejects_trigger_at_hod() -> None:
    candles = [
        _candle(10.0, 10.2, 9.9, 10.1, 0),
        _candle(10.1, 10.6, 10.0, 10.55, 1),
        _candle(10.55, 10.58, 10.35, 10.4, 2),
        _candle(10.4, 10.8, 10.39, 10.75, 3),
    ]
    setups = SetupEngine().compute_setups(
        candles=candles,
        levels={"pullback_high": 10.6, "hod": 10.7},
        structure={"trend": "UP", "pullback_active": True, "pullback_depth": {"pct": 0.3}},
        session_context="MORNING_MOMENTUM",
    )
    assert "FIRST_PULLBACK" not in _families(setups)

