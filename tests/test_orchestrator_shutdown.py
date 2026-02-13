import pytest

from core.orchestrator import CoreOrchestrator
from core.stop_controller import StopMode
from src.config.config_resolver import set_config_overrides


@pytest.fixture(autouse=True)
def _non_live_runtime(monkeypatch):
    monkeypatch.setenv("RUN_MODE", "READ_ONLY")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    set_config_overrides({"RUN_MODE": "READ_ONLY", "EXECUTION_ENABLED": False})
    yield
    set_config_overrides(None)


def test_run_loop_honours_existing_stop_request(monkeypatch):
    orchestrator = CoreOrchestrator()
    orchestrator.stop_controller.request_stop(
        StopMode.GRACEFUL, reason="pre-stop", source="test"
    )

    orchestrator.run_forever(max_cycles=1, cycle_sleep_seconds=0)
    event_types = [event.event_type for event in orchestrator.event_collector.snapshot_all()]

    assert "SHUTDOWN_STARTED" in event_types
    assert "SHUTDOWN_COMPLETE" in event_types
    assert "CYCLE_START" not in event_types


def test_keyboard_interrupt_escalates_to_panic():
    orchestrator = CoreOrchestrator()

    orchestrator._handle_keyboard_interrupt()
    assert orchestrator.stop_controller.stop_mode() == StopMode.GRACEFUL
    assert orchestrator.stop_controller.stop_reason() == "KeyboardInterrupt"

    orchestrator._handle_keyboard_interrupt()
    assert orchestrator.stop_controller.stop_mode() == StopMode.PANIC
    assert orchestrator.stop_controller.stop_reason() == "KeyboardInterrupt (escalation)"


def test_shutdown_hooks_continue_after_failure():
    orchestrator = CoreOrchestrator()

    class FailingEngine:
        def shutdown(self):
            raise RuntimeError("boom")

    class RecordingEngine:
        def __init__(self):
            self.called = False

        def shutdown(self):
            self.called = True

    orchestrator.execution_engine = FailingEngine()
    orchestrator.trade_exit_engine = RecordingEngine()
    orchestrator.storage_engine = RecordingEngine()
    orchestrator._request_stop(
        StopMode.GRACEFUL,
        reason="test shutdown",
        source="unit-test",
    )

    orchestrator._shutdown(StopMode.GRACEFUL)
    event_types = [event.event_type for event in orchestrator.event_collector.snapshot_all()]

    assert orchestrator.trade_exit_engine.called is True
    assert orchestrator.storage_engine.called is True
    assert "SHUTDOWN_HOOK_FAILED" in event_types
    assert "SHUTDOWN_COMPLETE" in event_types
