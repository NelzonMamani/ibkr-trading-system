from __future__ import annotations

from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from scanner import scanner_runner
from scanner.scanner_contract import scanner_request_from_policy
from dataclasses import replace

from strategies.ross_momentum.strategy_policy import RossMomentumPolicy, select_watchlist


@pytest.fixture(autouse=True)
def _reset_scanner_state():
    scanner_runner._PREV_WATCHLIST.clear()
    scanner_runner._WATCHLIST_HASH = None
    scanner_runner._LAST_SESSION_LABEL = None
    scanner_runner._SCAN_CYCLE_COUNT = 0
    scanner_runner._LAST_PRINT_CYCLE = 0
    set_config_overrides({})
    yield
    set_config_overrides({})


def test_scanner_uses_strategy_ranking_for_ross():
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "SCANNER_MODE": "LIVE_READONLY",
            "SCANNER_DATA_SOURCE": "MOCK",
        }
    )
    policy = replace(
        RossMomentumPolicy().stock_selection,
        session_allowlist=("PRE", "REG", "AFTER", "OVN"),
    )
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum")

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
    )

    ranked = select_watchlist(payload.get("candidate_metrics", []), policy=policy)
    ranked_symbols = [row.symbol for row in ranked]
    watchlist_symbols = [row.symbol for row in payload.get("watchlist_k", [])]
    assert watchlist_symbols == ranked_symbols
