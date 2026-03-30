from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.engines.setup_engine import SetupEngine
from src.strategies.common.candles.candle_types import Candle


def _candles() -> list[Candle]:
    start = datetime(2026, 1, 6, 9, 30, tzinfo=timezone.utc)
    rows: list[Candle] = []
    prices = [9.80, 9.90, 9.96, 10.05]
    for i, close in enumerate(prices):
        rows.append(
            Candle(
                open=close - 0.03,
                high=close + 0.05,
                low=close - 0.06,
                close=close,
                volume=150_000 + (i * 10_000),
                timestamp=start + timedelta(minutes=i),
            )
        )
    return rows


def test_setup_engine_delegates_to_pattern_registry_and_returns_detected_setups(capsys) -> None:
    setups = SetupEngine().compute_setups(
        symbol="TEST",
        timeframe="1m",
        candles=_candles(),
        levels={"premarket_high": 10.0, "hod": 10.0, "vwap": 9.95},
        structure={"structure_quality_flags": []},
        session_context="PRE",
        tradability_context={"spread": 0.02, "rvol": 2.0, "float_millions": 20.0},
    )

    captured = capsys.readouterr().out

    assert len(setups) > 0
    assert "[SETUP_ENGINE][CALL] symbol=TEST" in captured
    assert "[SETUP][INVOKE]" in captured
    assert "[SETUP][RESULT]" in captured
    assert "[SETUP_ENGINE][RESULT] symbol=TEST setups=" in captured
