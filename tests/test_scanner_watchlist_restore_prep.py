from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from scanner import scanner_runner
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


def _relaxed_policy(*, watchlist_limit_k: int = 15):
    base = RossMomentumPolicy().stock_selection
    return replace(
        base,
        watchlist_limit_k=watchlist_limit_k,
        top_gainers_n=50,
        max_symbols_per_cycle=50,
        min_volume=0,
        min_premarket_volume=0,
        gap_min_pct=-99.0,
        watchlist_rvol_min=0.0,
        focus_rvol_min=0.0,
        require_catalyst=False,
        float_max_millions=100_000.0,
        session_allowlist=("PRE", "RTH", "AH", "OVN", "CLOSED", "WEEKEND"),
    )


def test_watchlist_keeps_all_gated_survivors_when_survivors_leq_k():
    set_config_overrides({"RUN_MODE": "PAPER", "SCANNER_DATA_SOURCE": "MOCK", "ROSS_REQUIRE_NEWS": False})
    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=_relaxed_policy(watchlist_limit_k=15),
    )

    gated = payload.get("gated_survivors_count", payload.get("survivors_count", 0))
    watchlist = payload.get("watchlist_count", len(payload.get("watchlist_k", [])))
    if 0 < gated <= 15:
        assert watchlist == gated


def test_overnight_prep_builds_watchlist_even_when_execution_disabled(monkeypatch):
    set_config_overrides({"RUN_MODE": "PAPER", "SCANNER_DATA_SOURCE": "MOCK", "ROSS_REQUIRE_NEWS": False})
    monkeypatch.setattr(scanner_runner, "resolve_watchlist_selector", lambda *_: (lambda *_args: []))

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=_relaxed_policy(watchlist_limit_k=15),
        forced_session_label="OVN",
    )

    survivors = payload.get("gated_survivors_count", payload.get("survivors_count", 0))
    assert survivors > 0
    assert len(payload.get("watchlist_k", [])) > 0


def test_weekend_closed_prep_builds_watchlist_with_valid_survivors(monkeypatch):
    set_config_overrides({"RUN_MODE": "PAPER", "SCANNER_DATA_SOURCE": "MOCK", "ROSS_REQUIRE_NEWS": False})
    monkeypatch.setattr(scanner_runner, "resolve_watchlist_selector", lambda *_: (lambda *_args: []))

    payload = scanner_runner.run_scanner_cycle(
        mode="READONLY",
        policy=_relaxed_policy(watchlist_limit_k=15),
        forced_session_label="WEEKEND",
    )

    survivors = payload.get("gated_survivors_count", payload.get("survivors_count", 0))
    assert survivors > 0
    assert len(payload.get("watchlist_k", [])) > 0


def test_true_no_survivor_case_remains_valid_empty_watchlist():
    set_config_overrides({"RUN_MODE": "PAPER", "SCANNER_DATA_SOURCE": "MOCK", "ROSS_REQUIRE_NEWS": False})
    base = RossMomentumPolicy().stock_selection
    strict = replace(
        base,
        watchlist_limit_k=15,
        top_gainers_n=50,
        max_symbols_per_cycle=50,
        gap_min_pct=10_000.0,
        session_allowlist=("PRE", "RTH", "AH", "OVN", "CLOSED", "WEEKEND"),
    )

    payload = scanner_runner.run_scanner_cycle(mode="READONLY", policy=strict, forced_session_label="OVN")

    assert payload.get("gated_survivors_count", payload.get("survivors_count", 0)) == 0
    assert payload.get("watchlist_count", len(payload.get("watchlist_k", []))) == 0
