import pytest

from src.strategy_portfolio.allocation import (
    AllocationConfig,
    allocate,
    compute_global_risk_budget,
)
from src.strategy_portfolio.reason_codes import ReasonCode


def test_compute_global_risk_budget_pct():
    assert compute_global_risk_budget(1000.0, global_max_risk_pct=0.1) == 100.0


def test_compute_global_risk_budget_usd():
    assert compute_global_risk_budget(1000.0, global_max_risk_usd=50.0) == 50.0


def test_compute_global_risk_budget_requires_input():
    with pytest.raises(ValueError):
        compute_global_risk_budget(1000.0)


def test_allocate_with_caps_and_disabled():
    configs = [
        AllocationConfig(strategy_id="alpha", allocation_pct=0.5, max_allocation_usd=40.0),
        AllocationConfig(strategy_id="beta", allocation_pct=0.5, enabled=False),
    ]
    results = allocate(100.0, configs)
    assert results[0].budget_usd == 40.0
    assert results[0].enabled is True
    assert results[1].budget_usd == 0.0
    assert results[1].reason_codes == [ReasonCode.ALLOCATION_DISABLED.value]


def test_allocate_deterministic_across_input_order():
    configs_a = [
        AllocationConfig(strategy_id="beta", allocation_pct=0.3),
        AllocationConfig(strategy_id="alpha", allocation_pct=0.7),
    ]
    configs_b = list(reversed(configs_a))
    results_a = allocate(100.0, configs_a)
    results_b = allocate(100.0, configs_b)
    assert results_a == results_b
    assert [result.strategy_id for result in results_a] == ["alpha", "beta"]


def test_allocate_risk_bounded_when_overallocated():
    configs = [
        AllocationConfig(strategy_id="alpha", allocation_pct=0.7),
        AllocationConfig(strategy_id="beta", allocation_pct=0.7),
    ]
    results = allocate(100.0, configs)
    assert sum(result.budget_usd for result in results) == pytest.approx(100.0)
    assert results[0].budget_usd == pytest.approx(50.0)
    assert results[1].budget_usd == pytest.approx(50.0)
