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
        candles=[_candle(10.0, 0), _candle(10.5, 1)],
        levels={"hod": 10.4},
        structure={"trend": "UP"},
    )

    assert isinstance(setups, list)


def test_setup_engine_detects_premarket_high_break() -> None:
    setups = SetupEngine().compute_setups(
        candles=[_candle(9.5, 0), _candle(10.1, 1)],
        levels={"premarket_high": 10.0},
        structure={},
    )

    assert any(item["setup_family"] == "PREMARKET_HIGH_BREAK" for item in setups)


def test_setup_engine_detects_hod_break() -> None:
    setups = SetupEngine().compute_setups(
        candles=[_candle(10.0, 0), _candle(10.6, 1)],
        levels={"hod": 10.5},
        structure={},
    )

    assert any(item["setup_family"] == "HOD_BREAK" for item in setups)


def test_setup_engine_detects_ema_pullback() -> None:
    setups = SetupEngine().compute_setups(
        candles=[_candle(9.8, 0), _candle(10.0, 1)],
        levels={"ema9": 10.03},
        structure={"trend": "UP"},
    )

    assert any(item["setup_family"] == "EMA_PULLBACK" for item in setups)


def test_setup_engine_detects_vwap_reclaim() -> None:
    setups = SetupEngine().compute_setups(
        candles=[_candle(9.9, 0), _candle(10.2, 1)],
        levels={"vwap": 10.0},
        structure={},
    )

    assert any(item["setup_family"] == "VWAP_RECLAIM" for item in setups)


def test_setup_engine_handles_empty_input() -> None:
    setups = SetupEngine().compute_setups(candles=[], levels={}, structure={})

    assert setups == []
