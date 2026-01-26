from __future__ import annotations

from src.config.config_resolver import set_config_overrides
from src.scanner.scanner_contract import scanner_request_from_policy
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def test_scanner_request_ibkr_top_gainers_skips_scanner_symbols_error(capsys):
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "SCANNER_MODE": "LIVE_READONLY",
            "SCANNER_DATA_SOURCE": "MOCK",
            "SCANNER_SYMBOLS": [],
        }
    )
    try:
        policy = RossMomentumPolicy().stock_selection
        request = scanner_request_from_policy(policy)

        payload = run_scanner_cycle(
            mode="READONLY",
            policy=policy,
            scanner_request=request,
        )
        output = capsys.readouterr().out

        assert "No SCANNER_SYMBOLS provided" not in output
        diagnostics = payload.get("diagnostics", {})
        universe_request = diagnostics.get("universe_request", {})
        assert universe_request.get("source") == "IBKR_TOP_GAINERS"
    finally:
        set_config_overrides({})
