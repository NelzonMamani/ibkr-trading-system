from src.core.orchestrator import CoreOrchestrator
from src.strategies.ross_momentum.strategy_policy import UniverseSource


def test_orchestrator_builds_scanner_request_from_policy():
    _, stock_policy = CoreOrchestrator._build_scanner_policy("PREMARKET")
    request = CoreOrchestrator._build_scanner_request(
        stock_policy,
        strategy_name="ross_momentum",
        session_phase="PREMARKET",
    )

    assert request.universe_source == UniverseSource.IBKR_TOP_GAINERS
    assert request.requested_top_n == stock_policy.top_gainers_n
    assert request.instrument == "STK"
    assert request.location_code == "STK.US"
    assert request.ibkr_scan_code == "TOP_PERC_GAIN"
    assert request.above_price == stock_policy.price_min
    assert request.below_price == stock_policy.price_max
