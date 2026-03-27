from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.engines.level_engine import LevelEngine
from src.core.engines.setup_engine import SetupEngine
from src.core.engines.structure_engine import StructureEngine
from src.core.engines.trigger_engine import TriggerEngine


def _candles(count: int = 25) -> list[dict]:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    rows: list[dict] = []
    base = 9.5
    for i in range(count):
        open_ = base + (i * 0.04)
        close = open_ + (0.03 if i % 4 != 0 else -0.01)
        high = max(open_, close) + 0.04
        low = min(open_, close) - 0.03
        rows.append(
            {
                "timestamp": start + timedelta(minutes=i),
                "open": round(open_, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": 10000 + (i * 500),
            }
        )
    return rows


def test_shared_level_engine_emits_foundation_contract() -> None:
    candles = _candles()
    levels = LevelEngine().compute_levels(
        symbol="ABCD",
        candles=candles,
        intraday_data={"candles": candles, "last_price": candles[-1]["close"]},
        premarket_data={"candles": candles[:5]},
    )

    required_keys = {
        "premarket_high",
        "premarket_low",
        "hod",
        "lod",
        "prior_close",
        "vwap",
        "ema_9",
        "ema_20",
        "whole_dollar_levels",
        "half_dollar_levels",
        "active_breakout_range",
        "provenance",
        "missing_level_flags",
    }
    assert required_keys.issubset(levels.keys())
    assert isinstance(levels["provenance"], dict)
    assert isinstance(levels["missing_level_flags"], list)


def test_structure_setup_trigger_stack_runs_under_partial_indicator_context() -> None:
    candles = _candles()
    levels = LevelEngine().compute_levels(
        symbol="STACK",
        candles=candles,
        intraday_data={"candles": candles},
        premarket_data={"candles": candles[:4]},
    )
    structure = StructureEngine().compute_structure(candles=candles)
    setups = SetupEngine().compute_setups(
        candles=candles,
        levels=levels,
        structure=structure,
        session_context="RTH",
        tradability_context={"rvol": None, "float_millions": None},
    )
    triggers = TriggerEngine().evaluate_triggers(
        symbol="STACK",
        candles=candles,
        setups=setups,
        levels=levels,
        structure=structure,
    )

    assert isinstance(structure.get("structure_quality_flags"), list)
    assert isinstance(setups, list)
    assert len(setups) > 0
    assert len(triggers) == len(setups)
    assert all("trigger_type" in item for item in triggers)
    assert all("trigger_ready_now" in item for item in triggers)


def test_setup_engine_does_not_inject_synthetic_fallback_when_structure_is_unresolved() -> None:
    candles = _candles(count=6)
    structure = {
        "trend": "UNKNOWN",
        "pullback_active": False,
        "compression_active": False,
        "consolidation_active": False,
        "impulse_active": False,
    }
    setups = SetupEngine().compute_setups(
        candles=candles,
        levels={},
        structure=structure,
        session_context="RTH",
        tradability_context={"rvol": None},
    )
    triggers = TriggerEngine().evaluate_triggers(
        symbol="STACK",
        candles=candles,
        setups=setups,
        levels={},
        structure=structure,
    )

    assert setups == []
    assert triggers == []
