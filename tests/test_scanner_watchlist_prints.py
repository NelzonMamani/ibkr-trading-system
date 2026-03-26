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
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    set_config_overrides({})
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
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
    if "EMPTY WATCHLIST (valid)" not in output:
        assert "price=$" in output
        assert ("gap=" in output) or ("gap_pct_resolved=" in output)
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


def test_focus_print_rows_match_focus_symbols_order(capsys):
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "SCANNER_DATA_SOURCE": "MOCK",
            "SCANNER_MODE": "TEACHING",
            "SCANNER_DEFAULT_SYMBOLS": ["AAPL", "TSLA", "MSFT"],
            "ROSS_REQUIRE_NEWS": False,
        }
    )
    payload = scanner_runner.run_scanner_cycle(mode="READONLY")
    output = capsys.readouterr().out

    focus_symbols = payload.get("focus_m_symbols", [])
    lines = output.splitlines()
    try:
        idx = next(i for i, line in enumerate(lines) if line.startswith("[SCANNER][FOCUS]"))
    except StopIteration:
        idx = -1
    focus_rows = []
    if idx >= 0:
        for line in lines[idx + 1 :]:
            if line.startswith("["):
                continue
            if line.strip():
                focus_rows.append(line)
            if len(focus_rows) >= len(focus_symbols):
                break
    printed_symbols = [line.split()[0] for line in focus_rows[: len(focus_symbols)]]
    assert printed_symbols == focus_symbols
