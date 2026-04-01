from src.core.engines.trigger_engine import TriggerEngine


def _evaluate_with_price(last_price: float) -> dict:
    engine = TriggerEngine()
    results = engine.evaluate_triggers(
        symbol="XYZ",
        candles=[{"close": last_price, "high": last_price, "low": last_price - 0.1}],
        setups=[
            {
                "setup_detected": True,
                "setup_family_id": "GAP_GO",
                "required_trigger_types": ["CONFIDENCE_GATE", "BREAKOUT_HIGH"],
                "trigger_level": 10.0,
            }
        ],
        levels={"hod": 10.0, "premarket_high": 10.0},
        structure={"is_actionable": True},
    )
    assert len(results) == 1
    return results[0]


def test_trigger_ready_but_not_fired_when_price_below_trigger_level() -> None:
    trigger = _evaluate_with_price(9.9)

    assert trigger["trigger_ready_now"] is True
    assert trigger["trigger_fired"] is False
    assert trigger["trigger_event_emitted"] is False
    assert trigger["trigger_type"] == "BREAKOUT_HIGH"


def test_trigger_fired_when_price_reaches_trigger_level() -> None:
    trigger = _evaluate_with_price(10.0)

    assert trigger["trigger_ready_now"] is True
    assert trigger["trigger_fired"] is True
    assert trigger["trigger_event_emitted"] is True
    assert trigger["trigger_type"] == "BREAKOUT_HIGH"
