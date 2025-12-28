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
