from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from config.runtime_config import RunMode, get_run_mode  # noqa: E402
from config.system_config import EventReplayMode, get_event_replay_mode  # noqa: E402


def test_module_imports_survive_phase8_precheck():
    """
    Minimal smoke check to ensure imports remain stable for Phase 8.
    """
    import main  # noqa: F401
    import core.orchestrator  # noqa: F401


def test_live_run_mode_forces_event_replay_off(monkeypatch: pytest.MonkeyPatch):
    """
    LIVE must always resolve EVENT_REPLAY_MODE to OFF, even if env requests replay.
    """

    monkeypatch.setenv("RUN_MODE", RunMode.LIVE.value)
    monkeypatch.setenv("EVENT_REPLAY_MODE", "CYCLE")

    run_mode = get_run_mode()
    replay_mode = get_event_replay_mode(run_mode)

    assert run_mode == RunMode.LIVE
    assert replay_mode == EventReplayMode.OFF


def test_sim_defaults_to_cycle_when_not_overridden(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RUN_MODE", raising=False)
    monkeypatch.delenv("EVENT_REPLAY_MODE", raising=False)
    monkeypatch.delenv("REPLAY_MODE", raising=False)

    run_mode = get_run_mode()
    replay_mode = get_event_replay_mode(run_mode)

    assert run_mode == RunMode.SIM
    assert replay_mode == EventReplayMode.CYCLE
