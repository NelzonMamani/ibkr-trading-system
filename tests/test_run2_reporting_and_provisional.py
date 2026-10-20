"""Offline proof for stale provisional acquisition and truthful empty-Focus logs."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from src.scanner import scanner_runner as scanner
from src.config.config_resolver import set_config_overrides
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


@pytest.fixture
def thresholds():
    set_config_overrides({'RUN_MODE':'READ_ONLY'})
    policy = RossMomentumPolicy().stock_selection
    yield scanner._gate_thresholds(policy, scanner._resolve_runtime_thresholds(policy))
    set_config_overrides(None)


def context():
    return dict(symbol='FIXTURE', session='RTH_OPEN', last_price=6., bid=5.99, ask=6.01, spread_pct=.0034,
                pct_change=15., float_shares=8_000_000, rvol=10., rvol_discovery=10., rvol_phase=10.,
                volume=2_000_000, premarket_volume=2_000_000, dollar_volume=12_000_000,
                catalyst_present=True, catalyst_status='CONFIRMED', data_quality_flags=['MD_STALE'],
                quote_timestamp_utc=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat())


def test_provisional_acquisition_defers_age_without_renewing_authority(thresholds):
    row = context()
    old = deepcopy(row)
    assert scanner._evaluate_watchlist_gates(row, thresholds, provisional=True) is None
    assert row['quote_timestamp_utc'] == old['quote_timestamp_utc']
    assert row['data_quality_flags'] == ['MD_STALE']
    assert scanner._evaluate_watchlist_gates(row, thresholds) == 'DROP_STALE_MARKET_DATA'
    assert scanner._evaluate_focus_gates(row, thresholds) == 'DROP_STALE_MARKET_DATA'


@pytest.mark.parametrize('changes,reason', [({'pct_change':-1},'DROP_PCT_CHANGE'),
    ({'rvol':.01,'rvol_discovery':.01,'rvol_phase':.01},'DROP_RVOL_DISCOVERY'),
    ({'float_shares':9_000_000_000},'DROP_FLOAT_MAX')])
def test_provisional_age_deferral_retains_every_other_discovery_gate(thresholds, changes, reason):
    row = context(); row.update(changes)
    assert scanner._evaluate_watchlist_gates(row, thresholds, provisional=True) == reason
    assert row['data_quality_flags'] == ['MD_STALE']

