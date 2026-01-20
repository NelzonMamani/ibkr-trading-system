from dataclasses import replace

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.core.stop_controller import StopMode
from src.sim.clock import RealClock, SimClock
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def test_orchestrator_scanner_policy_wires_strategy_values():
    base_policy = RossMomentumPolicy()
    tuned_stock = replace(
        base_policy.stock_selection,
        top_gainers_n=77,
        watchlist_limit_k=11,
        focus_limit_m=4,
    )
    tuned_policy = replace(base_policy, stock_selection=tuned_stock)

    _, scanner_policy = CoreOrchestrator._build_scanner_policy(
        "MORNING",
        strategy_policy=tuned_policy,
    )

    assert scanner_policy.top_gainers_n == 77
    assert scanner_policy.watchlist_limit_k == 11
    assert scanner_policy.focus_limit_m == 4


def test_live_micro_uses_real_clock_by_default():
    set_config_overrides({"RUN_MODE": "LIVE_MICRO"})
    try:
        orchestrator = CoreOrchestrator()
        assert isinstance(orchestrator.sim_clock, RealClock)
        assert not isinstance(orchestrator.sim_clock, SimClock)
    finally:
        set_config_overrides(None)


def test_live_micro_sim_clock_violation_triggers_safety():
    set_config_overrides({"RUN_MODE": "LIVE_MICRO"})
    try:
        orchestrator = CoreOrchestrator()
        orchestrator.sim_clock = SimClock()

        class _NonDeterministicFeed:
            pass

        orchestrator.price_feed = _NonDeterministicFeed()
        orchestrator._evaluate_runtime_safety(cycle_stage="CYCLE_START", stage_exception=None)

        assert orchestrator.stop_controller.stop_mode() == StopMode.PANIC
        violations = orchestrator.event_collector.filter_by_type("RUNTIME_SAFETY_VIOLATION")
        assert violations
        assert "Deterministic SimClock detected in LIVE/LIVE_MICRO mode" in violations[-1].payload["violations"]
    finally:
        set_config_overrides(None)
