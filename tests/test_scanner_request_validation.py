from __future__ import annotations

from src.scanner.scanner_contract import ScannerRequest, validate_scanner_request
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy, UniverseSource


def test_validate_scanner_request_flags_missing_fields():
    request = ScannerRequest(
        strategy_name="",
        policy_name="",
        ranking_intent="",
        session_phase=None,
        universe_source=UniverseSource.IBKR_TOP_GAINERS,
        ibkr_scan_code="",
        requested_top_n=0,
        above_price=10.0,
        below_price=5.0,
        optional_symbols_override=[],
        region=None,
        instrument="",
        location_code="",
        exchanges=[""],
    )

    errors = validate_scanner_request(request)

    assert "strategy_name must be non-empty" in errors
    assert "policy_name must be non-empty" in errors
    assert "ranking_intent must be non-empty" in errors
    assert "requested_top_n must be > 0" in errors
    assert "ibkr_scan_code must be non-empty" in errors
    assert "instrument must be non-empty" in errors
    assert "location_code must be non-empty" in errors
    assert "above_price must be <= below_price" in errors
    assert "optional_symbols_override must include at least one symbol" in errors
    assert "exchanges must include at least one exchange" in errors


def test_run_scanner_cycle_rejects_invalid_request():
    policy = RossMomentumPolicy().stock_selection
    request = ScannerRequest(
        strategy_name=policy.policy_name,
        policy_name=policy.policy_name,
        ranking_intent=policy.ranking_intent,
        session_phase=None,
        universe_source=UniverseSource.IBKR_TOP_GAINERS,
        ibkr_scan_code="",
        requested_top_n=0,
        above_price=policy.price_min,
        below_price=policy.price_max,
        optional_symbols_override=None,
        region=None,
        instrument=policy.universe.instrument,
        location_code=policy.universe.location_code,
        exchanges=None,
    )

    payload = run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
    )

    diagnostics = payload.get("diagnostics", {})
    assert diagnostics.get("scanner_request_valid") is False
    assert payload.get("topn_count") == 0
    assert payload.get("symbols") == []
