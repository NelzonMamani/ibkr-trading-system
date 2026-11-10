from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from config.runtime_config import (  # noqa: E402
    EventReplayMode,
    RunMode,
    get_event_replay_mode,
    get_run_mode,
)
from config.config_resolver import set_config_overrides  # noqa: E402


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

    set_config_overrides(None)
    monkeypatch.setenv("RUN_MODE", RunMode.LIVE.value)
    monkeypatch.setenv("EVENT_REPLAY_MODE", "CYCLE")

    run_mode = get_run_mode()
    replay_mode = get_event_replay_mode(run_mode)

    assert run_mode == RunMode.LIVE
    assert replay_mode == EventReplayMode.OFF


def test_sim_defaults_to_cycle_when_not_overridden(monkeypatch: pytest.MonkeyPatch):
    set_config_overrides(None)
    monkeypatch.delenv("RUN_MODE", raising=False)
    monkeypatch.delenv("EVENT_REPLAY_MODE", raising=False)
    monkeypatch.delenv("REPLAY_MODE", raising=False)

    run_mode = get_run_mode()
    replay_mode = get_event_replay_mode(run_mode)

    assert run_mode == RunMode.LIVE
    assert replay_mode == EventReplayMode.OFF


def test_unknown_run_mode_rejected(monkeypatch: pytest.MonkeyPatch):
    set_config_overrides(None)
    monkeypatch.setenv("RUN_MODE", "LIVE_MICRO")
    with pytest.raises(Exception, match="RUN_MODE must be one of"):
        get_run_mode()


def test_read_only_execution_disabled(monkeypatch: pytest.MonkeyPatch):
    set_config_overrides(None)
    monkeypatch.setenv("RUN_MODE", RunMode.READ_ONLY.value)
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    from config.runtime_config import execution_allowed  # noqa: E402

    assert execution_allowed(RunMode.READ_ONLY) is False


@pytest.mark.parametrize('value',[True,2.5,'2',0,9])
def test_native_synthetic_requested_size_rejects_non_contract_values(monkeypatch,value):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    try:
        resolver.set_config_overrides(dict(RUN_MODE='PAPER',RISK_PROFILE='SMALL',ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=value))
        with pytest.raises(resolver.ConfigResolutionError):
            resolver.get_ross_synthetic_requested_base_size()
    finally:resolver.set_config_overrides(previous)


@pytest.mark.parametrize('environment,mode,profile',[('PRODUCTION','PAPER','SMALL'),('TEST','LIVE','SMALL'),('TEST','READ_ONLY','SMALL'),('TEST','PAPER','MICRO')])
def test_native_synthetic_requested_size_requires_explicit_bounded_scope(monkeypatch,environment,mode,profile):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV',environment)
    try:
        resolver.set_config_overrides(dict(RUN_MODE=mode,RISK_PROFILE=profile,ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=2))
        with pytest.raises(resolver.ConfigResolutionError):
            resolver.get_ross_synthetic_requested_base_size()
    finally:resolver.set_config_overrides(previous)


def test_native_synthetic_requested_size_default_has_no_environment_switch(monkeypatch):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('ROSS_SYNTHETIC_REQUESTED_BASE_SIZE','4')
    try:
        resolver.set_config_overrides(None)
        assert resolver.get_ross_synthetic_requested_base_size()==1
    finally:resolver.set_config_overrides(previous)


@pytest.mark.parametrize('scope',[{},dict(ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=4,RUN_MODE='LIVE',RISK_PROFILE='SMALL'),dict(ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=4,RUN_MODE='PAPER',RISK_PROFILE='MICRO')])
def test_unit_stops_require_explicit_synthetic_sizing_scope(monkeypatch,scope):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    try:
        resolver.set_config_overrides(dict(scope,ROSS_SYNTHETIC_UNIT_STOPS=True))
        with pytest.raises(resolver.ConfigResolutionError):resolver.get_ross_synthetic_unit_stops()
    finally:resolver.set_config_overrides(previous)


def test_unit_stops_have_no_environment_enrollment(monkeypatch):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('ROSS_SYNTHETIC_UNIT_STOPS','true')
    try:
        resolver.set_config_overrides(None)
        assert not resolver.get_ross_synthetic_unit_stops()
    finally:resolver.set_config_overrides(previous)


@pytest.mark.parametrize('units',[False,True])
def test_unit_management_requires_explicit_prior_synthetic_scope(monkeypatch,units):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    try:
        resolver.set_config_overrides(dict(ROSS_SYNTHETIC_UNIT_MANAGEMENT=True,
            ROSS_SYNTHETIC_UNIT_STOPS=units,ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=4,
            RUN_MODE='PAPER',RISK_PROFILE='SMALL'))
        if units:assert resolver.get_ross_synthetic_unit_management()
        else:
            with pytest.raises(resolver.ConfigResolutionError):resolver.get_ross_synthetic_unit_management()
    finally:resolver.set_config_overrides(previous)


def test_unit_management_has_no_environment_enrollment(monkeypatch):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('ROSS_SYNTHETIC_UNIT_MANAGEMENT','true')
    try:
        resolver.set_config_overrides(None)
        assert not resolver.get_ross_synthetic_unit_management()
    finally:resolver.set_config_overrides(previous)
