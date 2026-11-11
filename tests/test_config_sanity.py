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
@pytest.mark.parametrize('name,getter',[('ROSS_SYNTHETIC_REQUESTED_BASE_SIZE','get_ross_synthetic_requested_base_size'),('ROSS_SYNTHETIC_RELATIONSHIP_BASE_SIZE','get_ross_synthetic_relationship_base_size')])
def test_native_synthetic_requested_size_rejects_non_contract_values(monkeypatch,value,name,getter):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    try:
        resolver.set_config_overrides(dict(RUN_MODE='PAPER',RISK_PROFILE='SMALL',**{name:value}))
        with pytest.raises(resolver.ConfigResolutionError):
            getattr(resolver,getter)()
    finally:resolver.set_config_overrides(previous)


@pytest.mark.parametrize('environment,mode,profile',[('PRODUCTION','PAPER','SMALL'),('TEST','LIVE','SMALL'),('TEST','READ_ONLY','SMALL'),('TEST','PAPER','MICRO')])
@pytest.mark.parametrize('name,getter',[('ROSS_SYNTHETIC_REQUESTED_BASE_SIZE','get_ross_synthetic_requested_base_size'),('ROSS_SYNTHETIC_RELATIONSHIP_BASE_SIZE','get_ross_synthetic_relationship_base_size')])
def test_native_synthetic_requested_size_requires_explicit_bounded_scope(monkeypatch,environment,mode,profile,name,getter):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV',environment)
    try:
        resolver.set_config_overrides(dict(RUN_MODE=mode,RISK_PROFILE=profile,**{name:2}))
        with pytest.raises(resolver.ConfigResolutionError):
            getattr(resolver,getter)()
    finally:resolver.set_config_overrides(previous)


@pytest.mark.parametrize('name,getter',[('ROSS_SYNTHETIC_REQUESTED_BASE_SIZE','get_ross_synthetic_requested_base_size'),('ROSS_SYNTHETIC_RELATIONSHIP_BASE_SIZE','get_ross_synthetic_relationship_base_size')])
def test_native_synthetic_requested_size_default_has_no_environment_switch(monkeypatch,name,getter):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv(name,'4')
    try:
        resolver.set_config_overrides(None)
        assert getattr(resolver,getter)()==1
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


@pytest.mark.parametrize('management',[False,True])
def test_micro_cost_failure_requires_separate_explicit_synthetic_enrollment(monkeypatch,management):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    try:
        resolver.set_config_overrides(dict(ROSS_SYNTHETIC_MICRO_COST_FAILURE=True,
            ROSS_SYNTHETIC_UNIT_MANAGEMENT=management,ROSS_SYNTHETIC_UNIT_STOPS=True,
            ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=4,RUN_MODE='PAPER',RISK_PROFILE='SMALL'))
        if management:assert resolver.get_ross_synthetic_micro_cost_failure()
        else:
            with pytest.raises(resolver.ConfigResolutionError):resolver.get_ross_synthetic_micro_cost_failure()
    finally:resolver.set_config_overrides(previous)


def test_micro_cost_failure_default_and_environment_cannot_enroll(monkeypatch):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('ROSS_SYNTHETIC_MICRO_COST_FAILURE','true')
    try:
        resolver.set_config_overrides(None)
        assert not resolver.get_ross_synthetic_micro_cost_failure()
    finally:resolver.set_config_overrides(previous)


@pytest.mark.parametrize('environment,mode,profile,base',[
    ('TEST','PAPER','SMALL',1),('PRODUCTION','PAPER','SMALL',4),
    ('TEST','LIVE','SMALL',4),('TEST','READ_ONLY','SMALL',4),('TEST','PAPER','MICRO',4)])
def test_relationship_unit_profit_requires_own_synthetic_initial_scope(monkeypatch,environment,mode,profile,base):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV',environment)
    try:
        resolver.set_config_overrides(dict(RUN_MODE=mode,RISK_PROFILE=profile,
            ROSS_SYNTHETIC_RELATIONSHIP_BASE_SIZE=base,ROSS_SYNTHETIC_RELATIONSHIP_UNIT_PROFIT=True))
        with pytest.raises(resolver.ConfigResolutionError):resolver.get_ross_synthetic_relationship_unit_profit()
    finally:resolver.set_config_overrides(previous)


def test_relationship_unit_profit_default_cannot_be_enrolled_by_environment_or_standalone_flags(monkeypatch):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    monkeypatch.setenv('ROSS_SYNTHETIC_RELATIONSHIP_UNIT_PROFIT','true')
    try:
        resolver.set_config_overrides(dict(RUN_MODE='PAPER',RISK_PROFILE='SMALL',
            ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=8,ROSS_SYNTHETIC_UNIT_STOPS=True,
            ROSS_SYNTHETIC_UNIT_MANAGEMENT=True,ROSS_SYNTHETIC_MICRO_COST_FAILURE=True,
            ROSS_SYNTHETIC_RELATIONSHIP_BASE_SIZE=8))
        assert not resolver.get_ross_synthetic_relationship_unit_profit()
        resolver.set_config_overrides(dict(resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_RELATIONSHIP_UNIT_PROFIT=True))
        assert resolver.get_ross_synthetic_relationship_unit_profit()
    finally:resolver.set_config_overrides(previous)



@pytest.mark.parametrize('cost_failure',[False,True])
def test_micro_tightening_requires_separate_cost_failure_enrollment(monkeypatch,cost_failure):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    try:
        resolver.set_config_overrides(dict(ROSS_SYNTHETIC_MICRO_COST_TIGHTENING=True,
            ROSS_SYNTHETIC_MICRO_COST_FAILURE=cost_failure,ROSS_SYNTHETIC_UNIT_MANAGEMENT=True,
            ROSS_SYNTHETIC_UNIT_STOPS=True,ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=4,RUN_MODE='PAPER',RISK_PROFILE='SMALL'))
        if cost_failure:assert resolver.get_ross_synthetic_micro_cost_tightening()
        else:
            with pytest.raises(resolver.ConfigResolutionError):resolver.get_ross_synthetic_micro_cost_tightening()
    finally:resolver.set_config_overrides(previous)


def test_micro_tightening_default_and_environment_cannot_enroll(monkeypatch):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('ROSS_SYNTHETIC_MICRO_COST_TIGHTENING','true')
    try:
        resolver.set_config_overrides(None)
        assert not resolver.get_ross_synthetic_micro_cost_tightening()
    finally:resolver.set_config_overrides(previous)


def test_bull_cost_tightening_default_env_and_own_unit_enrollment(monkeypatch):
    from src.config import config_resolver as resolver
    previous=dict(resolver._CONFIG_OVERRIDES)
    monkeypatch.setenv('ROSS_SYNTHETIC_BULL_COST_TIGHTENING','true')
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    try:
        resolver.set_config_overrides(None)
        assert not resolver.get_ross_synthetic_bull_cost_tightening()
        resolver.set_config_overrides(dict(RUN_MODE='PAPER',RISK_PROFILE='SMALL',ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=4,
            ROSS_SYNTHETIC_UNIT_STOPS=True,ROSS_SYNTHETIC_UNIT_MANAGEMENT=True,ROSS_SYNTHETIC_BULL_COST_TIGHTENING=True))
        assert resolver.get_ross_synthetic_bull_cost_tightening() and not resolver.get_ross_synthetic_micro_cost_failure()
        resolver.set_config_overrides(dict(resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_UNIT_MANAGEMENT=False))
        with pytest.raises(resolver.ConfigResolutionError):resolver.get_ross_synthetic_bull_cost_tightening()
    finally:resolver.set_config_overrides(previous)
