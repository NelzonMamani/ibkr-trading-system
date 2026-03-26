from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.engines.structure_engine import StructureEngine
from src.strategies.common.candles.candle_types import Candle


def _build_candles(highs: list[float], lows: list[float], closes: list[float]) -> list[Candle]:
    base = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for idx, (high, low, close) in enumerate(zip(highs, lows, closes)):
        candles.append(
            Candle(
                open=close,
                high=high,
                low=low,
                close=close,
                volume=1_000.0,
                timestamp=base + timedelta(minutes=idx),
            )
        )
    return candles


def test_structure_engine_returns_expected_keys() -> None:
    candles = _build_candles(
        highs=[10, 11, 13, 12, 11, 12, 15, 14, 13, 14, 16],
        lows=[8, 9, 10, 9, 8.5, 9.5, 11, 10.5, 10, 11, 12],
        closes=[9, 10, 12, 11, 10, 11, 14, 13, 12, 13, 16.5],
    )

    structure = StructureEngine().compute_structure(candles)

    assert set(structure.keys()) == {
        "trend",
        "structure_state",
        "last_higher_high",
        "last_higher_low",
        "last_lower_high",
        "last_lower_low",
        "swing_highs",
        "swing_lows",
    }


def test_structure_engine_detects_uptrend() -> None:
    candles = _build_candles(
        highs=[10, 11, 13, 12, 11, 12, 15, 14, 13, 14, 16],
        lows=[8, 9, 10, 9, 8.5, 9.5, 11, 10.5, 10, 11, 12],
        closes=[9, 10, 12, 11, 10, 11, 14, 13, 12, 13, 16.5],
    )

    structure = StructureEngine().compute_structure(candles)

    assert structure["trend"] == "UP"
    assert structure["structure_state"] == "IMPULSE"
    assert structure["last_higher_high"] == 15.0
    assert structure["last_higher_low"] == 10.0


def test_structure_engine_detects_downtrend() -> None:
    candles = _build_candles(
        highs=[22, 23, 25, 24, 23, 24, 22, 23, 21, 21, 22, 21, 20],
        lows=[20, 21, 22, 21, 18, 20, 19, 20, 18, 17, 16, 17, 18],
        closes=[21, 22, 24, 23, 19, 22, 20, 21, 19, 18, 17, 16, 15],
    )

    structure = StructureEngine().compute_structure(candles)

    assert structure["trend"] == "DOWN"
    assert structure["structure_state"] == "IMPULSE"
    assert structure["last_lower_high"] == 22.0
    assert structure["last_lower_low"] == 16.0


def test_structure_engine_returns_sideways_when_no_structure() -> None:
    candles = _build_candles(
        highs=[10, 11, 13, 12, 11, 14, 13, 12, 13, 12, 11],
        lows=[8, 9, 10, 9, 8, 9, 8.5, 8, 8.2, 8.1, 8.3],
        closes=[9, 10, 12, 11, 10, 13, 12, 11, 12, 11.5, 11],
    )

    structure = StructureEngine().compute_structure(candles)

    assert structure["trend"] == "SIDEWAYS"
    assert structure["structure_state"] == "RANGE"


def test_structure_engine_handles_empty_input() -> None:
    structure = StructureEngine().compute_structure([])

    assert structure["trend"] is None
    assert structure["structure_state"] is None
    assert structure["last_higher_high"] is None
    assert structure["last_higher_low"] is None
    assert structure["last_lower_high"] is None
    assert structure["last_lower_low"] is None
    assert structure["swing_highs"] == []
    assert structure["swing_lows"] == []
