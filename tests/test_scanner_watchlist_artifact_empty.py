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
from strategies.ross_momentum.strategy_policy import RossMomentumPolicy


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


def test_watchlist_artifact_written_when_universe_empty(monkeypatch):
    def _fail_build_provider():
        raise scanner_runner.ProviderConnectionError("connect failed")

    monkeypatch.setattr(scanner_runner, "build_provider", _fail_build_provider)
    set_config_overrides(
        {
            "RUN_MODE": "LIVE_READ_ONLY",
            "SCANNER_DATA_SOURCE": "IBKR",
            "SCANNER_MODE": "LIVE_READONLY",
        }
    )
    watchlist_dir = Path("output/watchlists")
    watchlist_dir.mkdir(parents=True, exist_ok=True)
    for existing in watchlist_dir.glob("watchlist_RossMomentum_*"):
        existing.unlink()

    policy = RossMomentumPolicy().stock_selection
    request = scanner_request_from_policy(policy, strategy_name="ross_momentum")

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
    )

    assert payload.get("watchlist_k_symbols") == []
    files = list(watchlist_dir.glob("watchlist_RossMomentum_*"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "watchlist_empty_reason" in content
