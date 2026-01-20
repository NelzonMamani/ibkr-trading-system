from src.core.orchestrator import CoreOrchestrator
from src.strategies.ross_momentum.strategy_policy import (
    RossMomentumPolicy,
    StockSelectionSpec,
    stock_selection_policy_for_session_phase,
)


def test_ross_policy_exposes_stock_selection_spec() -> None:
    policy = RossMomentumPolicy()
    assert isinstance(policy.stock_selection, StockSelectionSpec)

    resolved = stock_selection_policy_for_session_phase(policy, "MORNING")
    assert isinstance(resolved, StockSelectionSpec)


def test_orchestrator_builds_scanner_policy_from_strategy_spec() -> None:
    strategy_policy, scanner_policy = CoreOrchestrator._build_scanner_policy("MORNING")
    assert isinstance(strategy_policy.stock_selection, StockSelectionSpec)
    assert scanner_policy.universe_source == strategy_policy.stock_selection.universe_source
    assert scanner_policy.watchlist_limit_k == strategy_policy.stock_selection.watchlist_limit_k
