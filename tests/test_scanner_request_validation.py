from __future__ import annotations

from dataclasses import replace

from src.config.config_resolver import set_config_overrides
from src.scanner.scanner_contract import scanner_request_from_policy, validate_scanner_request
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def test_validate_scanner_request_flags_invalid_top_n():
    policy = RossMomentumPolicy().stock_selection
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum")
    invalid = replace(request, requested_top_n=0)

    errors = validate_scanner_request(invalid)

    assert any("requested_top_n" in error for error in errors)


def test_scanner_cycle_rejects_invalid_request():
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "SCANNER_MODE": "TEACHING",
            "SCANNER_DATA_SOURCE": "MOCK",
        }
    )
    try:
        policy = RossMomentumPolicy().stock_selection
        request = scanner_request_from_policy(policy, strategy_name="ross_momentum")
        invalid = replace(request, requested_top_n=0)

        payload = run_scanner_cycle(
            mode="READONLY",
            policy=policy,
            scanner_request=invalid,
        )

        diagnostics = payload.get("diagnostics", {})
        assert diagnostics.get("scanner_request_errors")
        assert payload.get("watchlist_k_symbols") == []
    finally:
        set_config_overrides({})
