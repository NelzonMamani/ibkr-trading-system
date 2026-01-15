from core.stop_controller import StopController, StopMode


def test_stop_controller_escalates_to_panic_and_updates_reason():
    controller = StopController()

    controller.request_stop(StopMode.GRACEFUL, reason="first", source="unit")
    assert controller.is_stop_requested() is True
    assert controller.stop_mode() == StopMode.GRACEFUL
    assert controller.stop_reason() == "first"
    assert controller.stop_source() == "unit"

    controller.request_stop(StopMode.PANIC, reason="escalated", source="unit-2")
    assert controller.stop_mode() == StopMode.PANIC
    assert controller.stop_reason() == "escalated"
    assert controller.stop_source() == "unit-2"


def test_circuit_breakers_latch_and_require_reset():
    controller = StopController()

    state = controller.trip_breaker(
        breaker_id="DAILY_LOSS_LIMIT",
        reason="Daily loss limit breached",
        source="unit",
    )
    assert controller.is_breaker_tripped() is True
    assert state.breaker_id == "DAILY_LOSS_LIMIT"

    latched = controller.trip_breaker(
        breaker_id="DAILY_LOSS_LIMIT",
        reason="Should remain latched",
        source="unit-2",
    )
    assert latched == state

    assert controller.reset_breakers(open_positions=1, reason="blocked", source="unit") is False
    assert controller.is_breaker_tripped() is True

    assert controller.reset_breakers(open_positions=0, reason="reset", source="unit") is True
    assert controller.is_breaker_tripped() is False
