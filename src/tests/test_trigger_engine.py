from src.core.engines.trigger_engine import TriggerEngine


def test_trigger_engine_fires_on_first_new_high() -> None:
    candles = [
        {"open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1},
        {"open": 10.1, "high": 10.25, "low": 10.0, "close": 10.2},
        {"open": 10.2, "high": 10.24, "low": 10.05, "close": 10.1},
        {"open": 10.1, "high": 10.4, "low": 10.08, "close": 10.22},
    ]
    setups = [
        {
            "setup_family_id": "FIRST_PULLBACK",
            "setup_name": "First Pullback",
            "required_trigger_types": ["PULLBACK_HIGH_BREAK"],
            "trigger_level": 10.3,
            "invalidation_anchor": "pullback_low",
            "quality_flags": [],
        }
    ]
    structure = {"pullback_depth": {"anchor_low": 9.9}}
    levels = {"hod": 10.3}

    triggers = TriggerEngine().evaluate_triggers(
        symbol="TEST",
        candles=candles,
        setups=setups,
        levels=levels,
        structure=structure,
    )

    assert len(triggers) == 1
    assert triggers[0]["trigger_ready_now"] is True
    assert triggers[0]["trigger_reason"] == "FIRST_NEW_HIGH"


def test_trigger_engine_blocks_without_new_high_or_breakout_close() -> None:
    candles = [
        {"open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1},
        {"open": 10.1, "high": 10.25, "low": 10.0, "close": 10.2},
        {"open": 10.2, "high": 10.22, "low": 10.05, "close": 10.15},
    ]
    setups = [
        {
            "setup_family_id": "HOD_BREAK",
            "setup_name": "HOD Break",
            "required_trigger_types": ["HOD_BREAK"],
            "trigger_level": 10.3,
            "invalidation_anchor": "prior_pivot_low",
            "quality_flags": [],
        }
    ]

    triggers = TriggerEngine().evaluate_triggers(
        symbol="TEST",
        candles=candles,
        setups=setups,
        levels={"hod": 10.3},
        structure={"pullback_depth": {"anchor_low": 9.9}},
    )

    assert len(triggers) == 1
    assert triggers[0]["trigger_ready_now"] is False
    assert triggers[0]["trigger_reason"] == "BREAKOUT_NOT_CLEARED"
