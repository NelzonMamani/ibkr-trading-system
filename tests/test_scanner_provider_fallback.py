from __future__ import annotations

from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from scanner import scanner_runner


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


def test_scanner_fallback_on_provider_connect_failure(monkeypatch):
    def _fail_build_provider():
        raise scanner_runner.ProviderConnectionError("connect failed")

    monkeypatch.setattr(scanner_runner, "build_provider", _fail_build_provider)
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "SCANNER_DATA_SOURCE": "IBKR",
            "IBKR_FALLBACK_ENABLED": True,
        }
    )

    payload = scanner_runner.run_scanner_cycle(mode="integrated")

    diagnostics = payload.get("diagnostics", {})
    assert diagnostics.get("provider_error") == "connect failed"
    assert diagnostics.get("provider_fallback") is None
    assert diagnostics.get("symbol_count") == 0
    assert payload.get("watchlist_k_symbols") == []
