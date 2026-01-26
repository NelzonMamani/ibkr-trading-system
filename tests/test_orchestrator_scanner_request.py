from config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.strategies.ross_momentum.strategy_policy import UniverseSource


def test_orchestrator_builds_scanner_request_from_policy():
    _, stock_policy = CoreOrchestrator._build_scanner_policy("PREMARKET")
    request = CoreOrchestrator._build_scanner_request(stock_policy)

    assert request.universe_source == UniverseSource.IBKR_TOP_GAINERS
    assert request.requested_top_n == stock_policy.top_gainers_n


def test_orchestrator_scanner_policy_statistical_overrides_defaults():
    set_config_overrides({"SELECTED_STRATEGY": "statistical_intraday_momentum"})
    _, stock_policy = CoreOrchestrator._build_scanner_policy("PREMARKET")

    assert stock_policy.price_max == 200.0
    assert stock_policy.gap_min_pct == 0.0
    assert stock_policy.rvol_min == 1.0


def test_orchestrator_scanner_policy_ross_defaults():
    set_config_overrides({"SELECTED_STRATEGY": "ross_momentum"})
    _, stock_policy = CoreOrchestrator._build_scanner_policy("PREMARKET")

    assert stock_policy.price_max == 20.0
    assert stock_policy.gap_min_pct == 10.0
    assert stock_policy.rvol_min == 5.0


def teardown_module():
    set_config_overrides({})
