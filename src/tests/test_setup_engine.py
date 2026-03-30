from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.engines.setup_engine import SetupEngine
from src.strategies.common.candles.candle_types import Candle


def _candle(close: float, minute: int) -> Candle:
    base = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    return Candle(
        open=close,
        high=close + 0.2,
        low=close - 0.2,
        close=close,
        volume=1_000.0,
        timestamp=base + timedelta(minutes=minute),
    )


def test_setup_engine_returns_list() -> None:
    setups = SetupEngine().compute_setups(
        candles=[_candle(10.0 + (idx * 0.15), idx) for idx in range(5)],
        levels={"premarket_high": 10.5, "hod": 10.5, "vwap": 10.45, "ema_9": 10.4},
        structure={"trend": "UP", "compression_active": True},
        symbol="UNIT",
        timeframe="M1",
        session_context="RTH",
        tradability_context={"rvol": 2.0, "spread": 0.02, "float_millions": 18.0},
    )

    assert isinstance(setups, list)
    assert len(setups) > 0


def test_setup_engine_detects_premarket_high_break() -> None:
    setups = SetupEngine().compute_setups(
        candles=[_candle(9.5 + (idx * 0.2), idx) for idx in range(5)],
        levels={"premarket_high": 10.0, "hod": 10.2, "vwap": 9.9, "ema_9": 9.8},
        structure={"trend": "UP"},
        session_context="RTH",
        tradability_context={"rvol": 1.8, "spread": 0.03, "float_millions": 22.0},
    )

    assert any(item["setup_family"] == "PREMARKET_HIGH_BREAK" for item in setups)


def test_setup_engine_detects_hod_break() -> None:
    setups = SetupEngine().compute_setups(
        candles=[_candle(10.0 + (idx * 0.2), idx) for idx in range(5)],
        levels={"premarket_high": 10.2, "hod": 10.5, "vwap": 10.4, "ema_9": 10.3},
        structure={"trend": "UP"},
        session_context="RTH",
        tradability_context={"rvol": 2.2, "spread": 0.02, "float_millions": 25.0},
    )

    assert any(item["setup_family"] == "HOD_BREAK" for item in setups)


def test_setup_engine_detects_micro_pullback() -> None:
    setups = SetupEngine().compute_setups(
        candles=[_candle(9.8 + (idx * 0.05), idx) for idx in range(5)],
        levels={"premarket_high": 9.9, "hod": 10.0, "vwap": 9.92, "ema_9": 9.95},
        structure={"trend": "UP", "compression_active": True},
        session_context="RTH",
        tradability_context={"rvol": 1.6, "spread": 0.01, "float_millions": 12.0},
    )

    assert any(item["setup_family"] == "MICRO_PULLBACK" for item in setups)


def test_setup_engine_detects_vwap_reclaim() -> None:
    setups = SetupEngine().compute_setups(
        candles=[_candle(close, idx) for idx, close in enumerate([10.2, 9.9, 9.8, 9.95, 10.2])],
        levels={"premarket_high": 10.3, "hod": 10.35, "vwap": 10.0, "ema_9": 9.98},
        structure={"trend": "UP"},
        session_context="RTH",
        tradability_context={"rvol": 1.9, "spread": 0.02, "float_millions": 30.0},
    )

    assert any(item["setup_family"] == "VWAP_RECLAIM_CONTINUATION" for item in setups)


def test_setup_engine_handles_empty_input() -> None:
    setups = SetupEngine().compute_setups(candles=[], levels={}, structure={})

    assert isinstance(setups, list)
