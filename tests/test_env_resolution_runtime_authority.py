from __future__ import annotations

import sys

import pytest

from src.config.config_resolver import get_config_record, get_config_resolution_trace, set_config_overrides
from src.config.runtime_config import RunMode
from src.core.managers.runtime_mode_manager import RuntimeModeManager
from src.core.orchestrator import CoreOrchestrator, RuntimeSafetyError


@pytest.fixture(autouse=True)
def _clear_overrides():
    set_config_overrides(None)
    yield
    set_config_overrides(None)


def test_env_resolution_derives_ibkr_flags_from_execution_authority(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUN_MODE", "PAPER")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("IBKR_READONLY_ENABLED", "true")
    monkeypatch.setenv("IBKR_ORDER_SUBMISSION_ENABLED", "false")
    monkeypatch.setenv("IBKR_ORDER_TRANSLATION_ENABLED", "false")

    readonly = get_config_record("IBKR_READONLY_ENABLED")
    submission = get_config_record("IBKR_ORDER_SUBMISSION_ENABLED")
    translation = get_config_record("IBKR_ORDER_TRANSLATION_ENABLED")

    assert readonly.value is False
    assert readonly.source == "DERIVED"
    assert submission.value is True
    assert submission.source == "DERIVED"
    assert translation.value is True
    assert translation.source == "DERIVED"


def test_live_execution_disabled_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUN_MODE", "LIVE")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")

    with pytest.raises(Exception, match="LIVE mode with execution disabled"):
        RuntimeModeManager.resolve()


def test_live_execution_ignores_submission_config_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUN_MODE", "LIVE")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("IBKR_READONLY_ENABLED", "false")
    monkeypatch.setenv("IBKR_ORDER_TRANSLATION_ENABLED", "true")
    monkeypatch.setenv("IBKR_ORDER_SUBMISSION_ENABLED", "false")
    monkeypatch.setenv("IBKR_API_WRITE_ALLOWED", "true")

    orchestrator = CoreOrchestrator()

    assert orchestrator.execution_enabled is True


def test_startup_banner_and_orchestrator_agree(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setenv("RUN_MODE", "LIVE")
    monkeypatch.setenv("SCANNER_MODE", "LIVE_READONLY")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")

    import src.main as main_module

    class _StubOrchestrator:
        def __init__(self):
            self.runtime_mode_manager = RuntimeModeManager.resolve()

        def run_forever(self, max_cycles=None):
            return None

    monkeypatch.setattr(main_module, "CoreOrchestrator", _StubOrchestrator)
    monkeypatch.setattr(sys, "argv", ["main.py", "--cycles", "0"])

    main_module.main()
    output = capsys.readouterr().out
    trace = get_config_resolution_trace(
        [
            "RUN_MODE",
            "SCANNER_MODE",
            "EXECUTION_ENABLED",
            "IBKR_READONLY_ENABLED",
            "IBKR_ORDER_SUBMISSION_ENABLED",
            "IBKR_ORDER_TRANSLATION_ENABLED",
        ]
    )

    assert "[CONFIG] Runtime mode manager: mode=LIVE live_like=True allow_orders=True" in output
    assert trace["EXECUTION_ENABLED"]["source"] == "ENV"
    assert trace["IBKR_READONLY_ENABLED"]["source"] == "DERIVED"
    assert trace["IBKR_ORDER_SUBMISSION_ENABLED"]["source"] == "DERIVED"
    assert trace["IBKR_ORDER_TRANSLATION_ENABLED"]["source"] == "DERIVED"
