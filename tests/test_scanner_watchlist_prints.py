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


def test_watchlist_print_format(capsys):
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "SCANNER_DATA_SOURCE": "MOCK",
            "SCANNER_MODE": "TEACHING",
            "SCANNER_DEFAULT_SYMBOLS": ["AAPL", "TSLA"],
            "ROSS_REQUIRE_NEWS": False,
        }
    )
    scanner_runner.run_scanner_cycle(mode="READONLY")
    output = capsys.readouterr().out
    assert "[SCANNER][WATCHLIST]" in output
    assert "price=$" in output
    assert "gap=" in output
    assert "rvol=" in output
    assert "[SCANNER][FOCUS]" in output


def test_watchlist_print_suppressed_when_unchanged(capsys):
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "SCANNER_DATA_SOURCE": "MOCK",
            "SCANNER_MODE": "TEACHING",
            "SCANNER_DEFAULT_SYMBOLS": ["AAPL", "TSLA"],
            "WATCHLIST_PRINT_EVERY_N_CYCLES": 99,
        }
    )
    scanner_runner.run_scanner_cycle(mode="READONLY")
    first_output = capsys.readouterr().out
    scanner_runner.run_scanner_cycle(mode="READONLY")
    second_output = capsys.readouterr().out
    assert "[SCANNER][WATCHLIST]" in first_output
    assert "[SCANNER][WATCHLIST]" not in second_output
