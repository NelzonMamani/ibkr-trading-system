from __future__ import annotations

from src.scanner.scanner_runner import run_scanner_cycle


def test_scanner_contract_fields() -> None:
    payload = run_scanner_cycle(mode="test")
    required_keys = {
        "scanner_version",
        "scanner_git_sha",
        "timestamp_utc",
        "topn_count",
        "survivors_count",
        "symbols",
        "watchlist",
        "watchlist_rows",
        "focus_rows",
        "drop_ledger",
        "drop_ledger_summary",
        "cycle_state",
    }
    assert required_keys.issubset(payload.keys())
    assert isinstance(payload.get("watchlist"), list)
    assert isinstance(payload.get("focus_rows"), list)
