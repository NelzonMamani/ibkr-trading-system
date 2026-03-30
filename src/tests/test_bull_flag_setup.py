from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.engines.setup_engine import SetupEngine
from src.strategies.common.candles.candle_types import Candle


def _candle(*, open_: float, high: float, low: float, close: float, volume: float, minute: int) -> Candle:
    base = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    return Candle(
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        timestamp=base + timedelta(minutes=minute),
    )


def _valid_bull_flag_candles() -> list[Candle]:
    return [
        _candle(open_=100.0, high=102.5, low=99.5, close=102.0, volume=2000, minute=0),
        _candle(open_=102.0, high=105.0, low=101.8, close=104.8, volume=2100, minute=1),
        _candle(open_=104.8, high=108.0, low=104.5, close=107.6, volume=2200, minute=2),
        _candle(open_=107.6, high=107.9, low=107.0, close=107.2, volume=1100, minute=3),
        _candle(open_=107.2, high=107.5, low=106.7, close=106.9, volume=1050, minute=4),
        _candle(open_=106.9, high=107.3, low=106.5, close=107.0, volume=1000, minute=5),
        _candle(open_=107.0, high=107.4, low=106.6, close=106.95, volume=980, minute=6),
        _candle(open_=106.95, high=107.35, low=106.55, close=107.1, volume=960, minute=7),
        _candle(open_=107.1, high=107.45, low=106.7, close=107.2, volume=940, minute=8),
        _candle(open_=107.2, high=107.5, low=106.75, close=107.3, volume=920, minute=9),
    ]


def _base_structure() -> dict:
    return {
        "trend": "UP",
        "last_impulse_leg": {"start_price": 100.0, "end_price": 107.6, "duration_bars": 3},
        "pullback": {"depth_pct": 0.3, "is_higher_low": True},
    }


def test_bull_flag_detected_for_valid_impulse_and_shallow_pullback() -> None:
    setups = SetupEngine().compute_setups(
        candles=_valid_bull_flag_candles(),
        levels={},
        structure=_base_structure(),
        symbol="UNIT",
        timeframe="M1",
    )

    detected = [s for s in setups if s.get("setup_family_id") == "BULL_FLAG" and s.get("setup_detected")]
    assert len(detected) == 1
    assert detected[0]["trigger_level"] == detected[0]["context"]["flag_high"]


def test_bull_flag_rejected_when_pullback_too_deep() -> None:
    structure = _base_structure()
    structure["pullback"] = {"depth_pct": 0.6, "is_higher_low": True}

    setups = SetupEngine().compute_setups(
        candles=_valid_bull_flag_candles(),
        levels={},
        structure=structure,
    )

    assert not any(s.get("setup_family_id") == "BULL_FLAG" and s.get("setup_detected") for s in setups)


def test_bull_flag_rejected_without_impulse() -> None:
    structure = _base_structure()
    structure["last_impulse_leg"] = None

    setups = SetupEngine().compute_setups(
        candles=_valid_bull_flag_candles(),
        levels={},
        structure=structure,
    )

    assert setups == [{"setup_family_id": "NONE", "setup_detected": False, "setup_context": {"reason": "NO_VALID_BULL_FLAG"}}]


def test_bull_flag_rejected_for_flat_consolidation_without_uptrend() -> None:
    structure = _base_structure()
    structure["trend"] = "SIDEWAYS"

    setups = SetupEngine().compute_setups(
        candles=_valid_bull_flag_candles(),
        levels={},
        structure=structure,
    )

    assert setups == [{"setup_family_id": "NONE", "setup_detected": False, "setup_context": {"reason": "NO_VALID_BULL_FLAG"}}]
