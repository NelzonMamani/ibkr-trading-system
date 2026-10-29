from __future__ import annotations

from dataclasses import MISSING, fields
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


@pytest.mark.parametrize("populated", [True, False])
def test_watchlist_print_format(capsys, populated):
    # Formatting has no authority to create a natural candidate. Test both
    # legitimate inputs directly instead of depending on wall-clock selection.
    metrics = scanner_runner.CandidateMetrics
    values = {"symbol": "SYNTH", "session_label": "RTH", "last_price": 5.0,
              "gap_pct": 25.0, "gap_pct_resolved": 25.0, "rvol": 3.0, "data_quality_ok": True}
    candidate = metrics(**{field.name: values.get(field.name) for field in fields(metrics)
                           if field.default is MISSING and field.default_factory is MISSING})
    rows = [candidate] if populated else []
    scanner_runner._print_watchlist_and_focus(rows, rows, session_label="RTH")
    output = capsys.readouterr().out
    assert "[SCANNER][WATCHLIST]" in output
    assert "[SCANNER][FOCUS]" in output
    assert output.count("count=" + str(len(rows))) == 2
    if populated:
        assert output.count("SYNTH session=") == 2
        assert output.count("price=$5.00") == 2
        assert output.count("gap=25.00%") == 2
        assert output.count("rvol=3.00 ") == 2
    else:
        assert len(output.splitlines()) == 2
        assert "price=$" not in output and "rvol=" not in output


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
