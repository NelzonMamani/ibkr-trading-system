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
        symbol="STACK",
        timeframe="M1",
        session_context="RTH",
        tradability_context={"rvol": 1.5, "spread": 0.03, "float_millions": 15.0},
    )
    triggers = TriggerEngine().evaluate_triggers(
        symbol="STACK",
        candles=candles,
        setups=setups,
        levels={},
        structure=structure,
    )

    assert isinstance(setups, list)
    assert triggers == []


def test_trigger_engine_ignores_setups_that_are_not_detected() -> None:
    candles = _candles(count=6)
    triggers = TriggerEngine().evaluate_triggers(
        symbol="STACK",
        candles=candles,
        setups=[
            {
                "setup_family_id": "HOD_BREAK",
                "setup_name": "High Of Day Break",
                "required_trigger_types": ["HOD_BREAK"],
                "trigger_level": candles[-1]["close"] - 0.01,
                "setup_detected": False,
            }
        ],
        levels={"hod": candles[-1]["close"] - 0.01},
        structure={},
    )

    assert triggers == []


def test_trigger_engine_never_emits_confidence_gate_trigger_type() -> None:
    candles = _candles(count=6)
    triggers = TriggerEngine().evaluate_triggers(
        symbol="STACK",
        candles=candles,
        setups=[
            {
                "setup_family_id": "HOD_BREAK",
                "setup_name": "High Of Day Break",
                "required_trigger_types": ["CONFIDENCE_GATE"],
                "trigger_level": candles[-1]["close"] - 0.01,
                "setup_detected": True,
            }
        ],
        levels={"hod": candles[-1]["close"] - 0.01},
        structure={},
    )
    assert triggers
    assert triggers[0]["trigger_type"] != "CONFIDENCE_GATE"
