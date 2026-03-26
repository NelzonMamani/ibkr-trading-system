from __future__ import annotations

from datetime import datetime, timezone

from src.core.engines.level_engine import LevelEngine
from src.strategies.common.candles.candle_types import Candle


def _candles() -> list[Candle]:
    base = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    return [
        Candle(open=9.8, high=10.2, low=9.7, close=10.0, volume=1000.0, timestamp=base),
        Candle(open=10.0, high=10.6, low=9.9, close=10.4, volume=2000.0, timestamp=base.replace(minute=31)),
        Candle(open=10.4, high=10.5, low=10.1, close=10.2, volume=1500.0, timestamp=base.replace(minute=32)),
        Candle(open=10.2, high=11.2, low=10.0, close=10.8, volume=1700.0, timestamp=base.replace(minute=33)),
        Candle(open=10.8, high=11.0, low=9.3, close=10.0, volume=1600.0, timestamp=base.replace(minute=34)),
        Candle(open=10.0, high=10.7, low=9.9, close=10.3, volume=1400.0, timestamp=base.replace(minute=35)),
        Candle(open=10.3, high=10.8, low=10.1, close=10.6, volume=1300.0, timestamp=base.replace(minute=36)),
    ]


def _premarket() -> list[Candle]:
    base = datetime(2026, 1, 5, 13, 20, tzinfo=timezone.utc)
    return [
        Candle(open=9.1, high=9.4, low=9.0, close=9.2, volume=800.0, timestamp=base),
        Candle(open=9.2, high=9.8, low=9.1, close=9.7, volume=1200.0, timestamp=base.replace(minute=25)),
        Candle(open=9.7, high=9.75, low=9.3, close=9.5, volume=500.0, timestamp=base.replace(minute=28)),
    ]


def test_level_engine_returns_required_fields() -> None:
    levels = LevelEngine().compute_levels(
        symbol="TEST",
        candles=_candles(),
        intraday_data={"candles": _candles(), "last_price": 10.6},
        premarket_data={"candles": _premarket()},
    )

    assert set(levels.keys()) == {
        "symbol",
        "premarket_high",
        "premarket_low",
        "hod",
        "lod",
        "vwap",
        "ema9",
        "ema20",
        "whole_levels",
        "half_levels",
        "support_levels",
        "resistance_levels",
        "computed_at",
    }
    assert levels["symbol"] == "TEST"


def test_level_engine_handles_missing_premarket_data() -> None:
    levels = LevelEngine().compute_levels(
        symbol="TEST",
        candles=_candles(),
        intraday_data={"candles": _candles(), "last_price": 10.6},
        premarket_data={},
    )
    assert levels["premarket_high"] is None
    assert levels["premarket_low"] is None


def test_level_engine_computes_vwap() -> None:
    candles = _candles()
    levels = LevelEngine().compute_levels(
        symbol="TEST",
        candles=candles,
        intraday_data={"candles": candles, "last_price": 10.6},
        premarket_data={"candles": _premarket()},
    )

    expected = round(
        sum((((c.high + c.low + c.close) / 3.0) * c.volume) for c in candles)
        / sum(c.volume for c in candles),
        6,
    )
    assert levels["vwap"] == expected


def test_level_engine_computes_ema_values() -> None:
    levels = LevelEngine().compute_levels(
        symbol="TEST",
        candles=_candles(),
        intraday_data={"candles": _candles(), "last_price": 10.6},
        premarket_data={"candles": _premarket()},
    )

    assert isinstance(levels["ema9"], float)
    assert isinstance(levels["ema20"], float)


def test_level_engine_produces_non_empty_key_levels() -> None:
    levels = LevelEngine().compute_levels(
        symbol="TEST",
        candles=_candles(),
        intraday_data={"candles": _candles(), "last_price": 10.6},
        premarket_data={"candles": _premarket()},
    )

    assert levels["whole_levels"]
    assert levels["half_levels"]
    assert levels["resistance_levels"]
    assert levels["support_levels"]
