"""Offline consumer regressions; fixtures are not natural Ross observations."""
from copy import deepcopy

import pytest

from src.config.config_resolver import set_config_overrides
from src.scanner import scanner_runner as scanner
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


@pytest.fixture
def thresholds():
    set_config_overrides({"RUN_MODE": "READ_ONLY"})
    policy = RossMomentumPolicy().stock_selection
    result = scanner._gate_thresholds(policy, scanner._resolve_runtime_thresholds(policy))
    yield result
    set_config_overrides(None)


def context():
    return {"symbol": "FIXTURE", "session": "RTH_OPEN", "last_price": 6.0,
            "bid": 5.99, "ask": 6.01, "spread_pct": 0.0034,
            "pct_change": 15.0, "float_shares": 8_000_000,
            "rvol": 10.0, "rvol_discovery": 10.0, "rvol_phase": 10.0,
            "volume": 2_000_000, "premarket_volume": 2_000_000,
            "dollar_volume": 12_000_000, "catalyst_present": True,
            "catalyst_status": "CONFIRMED", "data_quality_flags": ["MD_STALE"],
            "requested_market_data_type": "DELAYED", "returned_market_data_type": "LIVE",
            "market_data_type_confirmed": True,
            "quote_timestamp_utc": "2026-09-28T13:00:00+00:00",
            "quote_timestamp_source": "LAST_TRADE", "quote_received_at_utc": "2026-09-28T17:30:00+00:00",
            "watchlist_eligible": True, "focus_eligible": True, "execution_eligible": True}


@pytest.mark.parametrize("gate", [scanner._evaluate_watchlist_gates, scanner._evaluate_focus_gates])
def test_stale_broker_quote_cannot_pass_consumer_gates(gate, thresholds):
    row = context()
    before = deepcopy(row)
    assert gate(row, thresholds) == "DROP_STALE_MARKET_DATA"
    assert row["focus_eligible"] is False
    assert row["execution_eligible"] is False
    for key in ("quote_timestamp_utc", "quote_received_at_utc", "quote_timestamp_source",
                "requested_market_data_type", "returned_market_data_type", "data_quality_flags",
                "catalyst_status", "volume", "rvol"):
        assert row[key] == before[key]


def test_forced_premarket_path_cannot_reintroduce_stale_quote(thresholds):
    row = context()
    row["session"] = "PRE"
    assert scanner._forced_premarket_focus_eligible(row, thresholds, session_label="PRE") is False


def test_non_stale_quote_retains_pillars_and_fail_closed_catalyst(thresholds):
    row = context()
    row["data_quality_flags"] = []
    assert scanner._evaluate_watchlist_gates(row, thresholds) is None
    assert scanner._evaluate_focus_gates(row, thresholds) is None
    row["catalyst_present"] = False
    row["catalyst_status"] = "DATA_UNAVAILABLE"
    assert scanner._evaluate_focus_gates(row, thresholds) == "DROP_NO_CATALYST"
