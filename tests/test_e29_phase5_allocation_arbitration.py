from __future__ import annotations

from dataclasses import dataclass

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.core.portfolio.allocation_engine import AllocationCandidate, PortfolioAllocationEngine
from src.core.portfolio.allocation_policy import (
    ARBITRATION_APPROVE_NEW_ENTRY,
    ARBITRATION_APPROVE_SCALE_IN,
    ARBITRATION_DEFER_LOWER_PRIORITY,
    ARBITRATION_DENY_GLOBAL_PORTFOLIO_CAP,
    ARBITRATION_DENY_SCALE_IN_NOT_ALLOWED,
    ARBITRATION_DENY_STRATEGY_BUDGET,
    ARBITRATION_PASS_EXIT_REDUCTION,
)
from src.core.portfolio.budget_registry import StrategyBudgetRegistry
from src.core.portfolio.allocation_policy import StrategyCapitalBudget
from src.models.data_models import RiskDecision, TradeIntent


@dataclass
class _Trade:
    symbol: str
    strategy_name: str
    side: str
    quantity_open: int
    entry_avg_price: float


class _Lifecycle:
    def __init__(self, open_trades=None, state=None, drift=None):
        self._open = open_trades or []
        self._state = state or type("S", (), {"total_exposure": 0.0})()
        self._drift = drift or []

    def get_open_lifecycle_trades(self):
        return self._open

    def build_portfolio_state(self):
        return self._state

    def get_drift_report(self):
        return self._drift


def _engine() -> PortfolioAllocationEngine:
    registry = StrategyBudgetRegistry(
        by_strategy={
            "ross_momentum": StrategyCapitalBudget("ross_momentum", True, 500.0, 2, 1, True, True),
            "beta": StrategyCapitalBudget("beta", True, 500.0, 2, 2, False, True),
        },
        fallback_budget=StrategyCapitalBudget("default", True, 100.0, 1, 999, False, True),
    )
    return PortfolioAllocationEngine(registry)


def _candidate(candidate_id: str, strategy: str, value: float, *, classification: str = "NEW_ENTRY", confidence: float = 0.8):
    return AllocationCandidate(candidate_id, "AAPL", strategy, "LONG", value, confidence, classification, False)


def test_arbitration_priority_and_tiebreak_are_deterministic() -> None:
    set_config_overrides({"LIFECYCLE_MAX_PORTFOLIO_EXPOSURE": 150.0})
    try:
        engine = _engine()
        snapshot = engine.build_snapshot(
            total_exposure=0.0,
            kill_switch_active=False,
            drift_detected=False,
            strategy_exposure={},
            strategy_open_positions={},
        )
        decisions = engine.arbitrate(
            candidates=[
                _candidate("b", "beta", 100.0),
                _candidate("a", "ross_momentum", 100.0),
                AllocationCandidate("c", "MSFT", "ross_momentum", "LONG", 10.0, 0.8, "NEW_ENTRY", False),
            ],
            snapshot=snapshot,
        )
        assert decisions[0].candidate_id == "a"
        assert decisions[0].reason_code == ARBITRATION_APPROVE_NEW_ENTRY
        assert decisions[1].candidate_id == "c"
        assert decisions[1].approved is True
        assert decisions[2].candidate_id == "b"
        assert decisions[2].approved is False
        assert decisions[2].reason_code in {ARBITRATION_DEFER_LOWER_PRIORITY, ARBITRATION_DENY_GLOBAL_PORTFOLIO_CAP}
    finally:
        set_config_overrides(None)


def test_strategy_budget_and_scale_in_policy_enforced() -> None:
    set_config_overrides({"LIFECYCLE_MAX_PORTFOLIO_EXPOSURE": 1000.0})
    try:
        engine = _engine()
        snapshot = engine.build_snapshot(
            total_exposure=0.0,
            kill_switch_active=False,
            drift_detected=False,
            strategy_exposure={"beta": 490.0},
            strategy_open_positions={"beta": 1},
        )
        scale_denied = engine.arbitrate(
            candidates=[_candidate("x", "beta", 5.0, classification="SCALE_IN")],
            snapshot=snapshot,
        )[0]
        assert scale_denied.reason_code == ARBITRATION_DENY_SCALE_IN_NOT_ALLOWED

        budget_denied = engine.arbitrate(
            candidates=[_candidate("y", "beta", 20.0)],
            snapshot=snapshot,
        )[0]
        assert budget_denied.reason_code == ARBITRATION_DENY_STRATEGY_BUDGET
    finally:
        set_config_overrides(None)


def test_scale_out_reduction_passes_without_capacity() -> None:
    set_config_overrides({"LIFECYCLE_MAX_PORTFOLIO_EXPOSURE": 10.0})
    try:
        engine = _engine()
        snapshot = engine.build_snapshot(
            total_exposure=10.0,
            kill_switch_active=False,
            drift_detected=False,
            strategy_exposure={},
            strategy_open_positions={},
        )
        decision = engine.arbitrate(
            candidates=[AllocationCandidate("exit-1", "AAPL", "ross_momentum", "LONG", 50.0, 0.9, "SCALE_OUT_HINT", True)],
            snapshot=snapshot,
        )[0]
        assert decision.approved is True
        assert decision.reason_code == ARBITRATION_PASS_EXIT_REDUCTION
    finally:
        set_config_overrides(None)


def test_orchestrator_arbitration_persistence_failure_is_non_blocking() -> None:
    # Construct a lightweight orchestrator-like object and call the bound method directly.
    o = object.__new__(CoreOrchestrator)
    o._portfolio_allocation_engine = _engine()
    o._last_allocation_decisions = []
    o._last_allocation_snapshot = o._portfolio_allocation_engine.build_snapshot(
        total_exposure=0.0,
        kill_switch_active=False,
        drift_detected=False,
        strategy_exposure={},
        strategy_open_positions={},
    )
    o.trade_lifecycle_engine = _Lifecycle()
    o.risk_engine = type("Risk", (), {"kill_switch": type("KS", (), {"active": False})()})()
    o.storage_engine = type("Storage", (), {"store_portfolio_allocation_decisions": lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))})()

    decision = RiskDecision(
        symbol="AAPL",
        allowed=True,
        max_position_size=10,
        risk_level="LOW",
        rationale="ok",
        strategy_name="ross_momentum",
        direction="LONG",
        decision_id="d-1",
    )
    intent = TradeIntent(
        symbol="AAPL",
        direction="LONG",
        strategy_name="ross_momentum",
        confidence=0.9,
        rationale="test",
        quantity=10,
        entry_price=5.0,
    )
    filtered = CoreOrchestrator._arbitrate_portfolio_candidates(o, strategy_output=[intent], risk_output=[decision], cycle_id="c1")
    assert len(filtered) == 1
    assert filtered[0].allowed is True
