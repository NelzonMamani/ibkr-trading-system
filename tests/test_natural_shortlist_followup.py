"""Offline probes for demonstrated natural-pass blockers; no transport."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from src.core.acquisition import AcquisitionCancelled, acquisition_scope, cycle_cache
from src.ibkr.market_data_client import MarketDataClient
from src.scanner import scanner_runner as scanner


def context(age=30, symbol='ONE'):
    return dict(symbol=symbol, quote_timestamp_utc=(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),
                data_quality_flags=[], eligibility_reason_codes=[], con_id=123, quote_timestamp_source="LAST_TRADE",
                focus_eligible=True, execution_eligible=True)


def test_explicit_refresh_retains_other_cycle_caches_and_broker_time(monkeypatch):
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
    old, new = context(), context(age=0)
    samples = [NS(timestamp_utc=x['quote_timestamp_utc'], data_quality_flags=[]) for x in (old, new)]
    calls = []
    def acquire(symbol):
        calls.append(symbol)
        return samples[len(calls)-1]
    monkeypatch.setattr(md, '_snapshot_stock_uncached', acquire)
    with acquisition_scope(lambda: False):
        cache = cycle_cache()
        cache[('qualified', 'sentinel')] = identity = object()
        cache[('history', '25 D')] = history = object()
        assert md.snapshot_stock('ONE') is samples[0]
        assert md.snapshot_stock('ONE') is samples[0]
        assert md.snapshot_stock('ONE', refresh=True) is samples[1]
        assert md.snapshot_stock('ONE') is samples[1]
        assert cache[('qualified', 'sentinel')] is identity
        assert cache[('history', '25 D')] is history
    assert calls == ['ONE', 'ONE']
    assert samples[1].timestamp_utc == new['quote_timestamp_utc']


@pytest.mark.parametrize('new_age,expected_stale', [(0, False), (30, True)])
def test_shortlist_refresh_rebuilds_then_rechecks_age(monkeypatch, new_age, expected_stale):
    original = context()
    refreshed = context(age=new_age)
    quote = NS(symbol='ONE', timestamp_utc=refreshed['quote_timestamp_utc'], timestamp_source='LAST_TRADE')
    calls = []
    provider = NS(refresh_quote=lambda symbol: calls.append(symbol) or quote)
    def rebuild(*args, **kwargs):
        assert kwargs['quote_override'] is quote
        return refreshed.copy()
    monkeypatch.setattr(scanner, '_build_symbol_context', rebuild)
    scanner._refresh_shortlisted_quote(original, provider, 'RTH', {})
    assert calls == ['ONE']
    assert original['quote_timestamp_utc'] == refreshed['quote_timestamp_utc']
    assert bool(scanner._stale_market_data_drop(original)) is expected_stale


@pytest.mark.parametrize('failure', ['exception', 'identity', 'symbol', 'missing'])
def test_failed_or_invalid_refresh_cannot_revive_stale_quote(monkeypatch, failure):
    original = context()
    old_stamp = original['quote_timestamp_utc']
    def refresh(symbol):
        if failure == 'exception':
            raise OSError('fixture transport failure')
        return NS(symbol='OTHER' if failure == 'symbol' else 'ONE', timestamp_utc=context(age=0)['quote_timestamp_utc'], timestamp_source='LAST_TRADE')
    rebuilt = context(age=0)
    if failure == 'identity':
        rebuilt['con_id'] = 456
    monkeypatch.setattr(scanner, '_build_symbol_context', lambda *a, **kw: None if failure == 'missing' else rebuilt)
    scanner._refresh_shortlisted_quote(original, NS(refresh_quote=refresh), 'RTH', {})
    assert original['quote_timestamp_utc'] == old_stamp
    assert scanner._stale_market_data_drop(original) == 'DROP_STALE_MARKET_DATA'
    assert original['focus_eligible'] is False


def test_fresh_shortlist_has_no_extra_request():
    scanner._refresh_shortlisted_quote(context(age=0), NS(refresh_quote=lambda _: pytest.fail('unnecessary request')), 'RTH', {})


def test_refresh_cancellation_is_not_provider_failure():
    stopped = False
    def refresh(_):
        nonlocal stopped
        stopped = True
        return NS(symbol='ONE')
    with pytest.raises(AcquisitionCancelled), acquisition_scope(lambda: stopped):
        scanner._refresh_shortlisted_quote(context(), NS(refresh_quote=refresh), 'RTH', {})


@pytest.mark.parametrize('bad_field,bad_value', [(None, None), ('last_price', 0.01), ('pct_change', -20), ('float_shares', 9_000_000_000)])
def test_provisional_shortlist_refresh_precedes_real_discovery_gates(monkeypatch, bad_field, bad_value):
    from src.config.config_resolver import set_config_overrides
    from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy
    set_config_overrides({'RUN_MODE':'READ_ONLY'})
    try:
        policy = RossMomentumPolicy().stock_selection
        thresholds = scanner._gate_thresholds(policy, scanner._resolve_runtime_thresholds(policy))
        original = context()
        original.update(session='RTH_OPEN', last_price=6.0, bid=5.99, ask=6.01, spread_pct=.0034,
                        pct_change=15., float_shares=8_000_000, rvol=10., rvol_discovery=10., rvol_phase=10.,
                        volume=2_000_000, premarket_volume=2_000_000, dollar_volume=12_000_000,
                        catalyst_present=True, catalyst_status='CONFIRMED', scanner_score=9999.0)
        rebuilt = dict(original, **context(age=0))
        if bad_field:
            rebuilt[bad_field] = bad_value
        requests = []
        provider = NS(refresh_quote=lambda symbol: requests.append(symbol) or NS(symbol=symbol, timestamp_utc=rebuilt['quote_timestamp_utc'], timestamp_source='LAST_TRADE'))
        monkeypatch.setattr(scanner, '_build_symbol_context', lambda *a, **kw: rebuilt.copy())
        monkeypatch.setattr(scanner, '_rank_candidates', lambda rows: list(rows))
        ledger = {}
        survivors = scanner._refresh_provisional_shortlist([original], provider, 'RTH_OPEN', {}, 1, thresholds, ledger)
        assert requests == ['ONE']
        assert bool(survivors) is (bad_field is None)
        if bad_field:
            assert ledger['ONE'].startswith('DROP_')
        else:
            assert original['scanner_score'] != 9999.0
            assert original['scanner_score'] == scanner._score_context(original)[0]
            from src.strategies.ross_momentum.strategy_policy import select_watchlist
            from dataclasses import replace
            metric = scanner._candidate_from_context(original, {'ross_catalyst_valid':True}, thresholds,
                drop_reason=None, timestamp_utc=datetime.now(timezone.utc).isoformat())
            assert all(metric.gate_checks.values()), metric.gate_checks
            competitor = replace(metric, symbol='OTHER', rank_score=metric.rank_score + 1)
            selected = select_watchlist([metric, competitor], replace(policy, watchlist_limit_k=1, session_allowlist=('RTH_OPEN',)))
            assert [item.symbol for item in selected] == ['OTHER']
            assert scanner._evaluate_watchlist_gates(survivors[0], thresholds) is None
            assert scanner._evaluate_focus_gates(survivors[0], thresholds) is None
            # Later delay never reuses the acquisition-time age decision.
            original['quote_timestamp_utc'] = context(age=30)['quote_timestamp_utc']
            assert scanner._evaluate_focus_gates(original, thresholds) == 'DROP_STALE_MARKET_DATA'
    finally:
        set_config_overrides(None)


@pytest.mark.parametrize('stamp,source', [(None, 'LAST_TRADE'), ('2026-01-01T12:00:00','LAST_TRADE'), ('invalid','LAST_TRADE'), (context(age=0)['quote_timestamp_utc'],'UNKNOWN')])
def test_refresh_cannot_replace_broker_timestamp_with_receipt(monkeypatch, stamp, source):
    row = context()
    old_stamp = row['quote_timestamp_utc']
    monkeypatch.setattr(scanner, '_build_symbol_context', lambda *a, **kw: pytest.fail('invalid authority rebuilt'))
    scanner._refresh_shortlisted_quote(row, NS(refresh_quote=lambda _: NS(symbol='ONE', timestamp_utc=stamp, timestamp_source=source)), 'RTH', {})
    assert row['quote_timestamp_utc'] == old_stamp
    assert scanner._stale_market_data_drop(row) == 'DROP_STALE_MARKET_DATA'

@pytest.mark.parametrize('initial_stale', [False, True])
@pytest.mark.parametrize('refreshed_price,refreshed_age,initial_float,expected_selected', [(6., 0, 8_000_000, True), (.01, 0, 8_000_000, False), (6., 30, 8_000_000, False), (6., 0, 200_000_000_000, False)])
def test_full_scanner_refreshes_aged_survivor_before_selection(monkeypatch, tmp_path, refreshed_price, refreshed_age, initial_float, expected_selected, initial_stale):
    """Real scanner call path, synthetic provider only; no network or runtime."""
    from dataclasses import replace
    from src.scanner.providers.mock_provider import MockScannerProvider
    from src.config.config_resolver import set_config_overrides
    from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy
    requests = []
    class Provider(MockScannerProvider):
        def get_quote(self, symbol):
            return replace(super().get_quote(symbol), last=6., bid=5.99, ask=6.01, close=5., open=5.,
                           volume=2_000_000, timestamp_utc=(datetime.now(timezone.utc)-timedelta(seconds=30 if initial_stale else 0)).isoformat(),
                           data_quality_flags=('MD_STALE',) if initial_stale else (), timestamp_source='LAST_TRADE')
        def get_previous_rth_close(self, identity):
            return 5.
        def get_prev_close(self, symbol):
            return 5.
        def get_daily_bars(self, identity, lookback_days):
            return []
        def refresh_quote(self, symbol):
            requests.append(symbol)
            return replace(self.get_quote(symbol), last=refreshed_price,
                           timestamp_utc=(datetime.now(timezone.utc)-timedelta(seconds=refreshed_age)).isoformat(),
                           data_quality_flags=())
    monkeypatch.setattr(scanner, '_is_mock_scanner_mode', lambda: False)
    monkeypatch.setattr(scanner, '_bootstrap_float_cache', lambda *a: {'ONE': {'float_value':initial_float, 'float_source':'FIXTURE'}})
    real_rank = scanner._rank_candidates
    aged = False
    def age_once(rows):
        nonlocal aged
        if rows and not aged:
            aged = True
            for row in rows:
                row['quote_timestamp_utc'] = context(age=30)['quote_timestamp_utc']
        return real_rank(rows)
    monkeypatch.setattr(scanner, '_rank_candidates', age_once)
    policy = replace(RossMomentumPolicy().stock_selection,
                     watchlist_limit_k=1, require_catalyst=False, min_volume=0, min_premarket_volume=0,
                     watchlist_rvol_min=0., focus_rvol_min=0., float_max_millions=100_000.,
                     session_allowlist=('RTH_MID',))
    set_config_overrides({'RUN_MODE':'PAPER', 'SCANNER_DATA_SOURCE':'MOCK', 'NEWS_ENABLED':False, 'ROSS_REQUIRE_NEWS':False,
                          'WATCHLIST_DIR': str(tmp_path/'watchlists')})
    scanner.reset_scanner_runtime_state()
    try:
        payload = scanner.run_scanner_cycle(mode='READONLY', provider=Provider(symbols=['ONE']), policy=policy,
                                           forced_session_label='RTH_MID', forced_session_source='TEST_OVERRIDE')
        assert requests == ([] if initial_float > 100_000_000_000 else ['ONE'])
        if initial_float > 100_000_000_000:
            assert payload['drop_ledger']['ONE'] == 'DROP_FLOAT_MAX'
        selected = [row.symbol for row in payload['watchlist_k']]
        assert ('ONE' in selected) is expected_selected
    finally:
        scanner.reset_scanner_runtime_state()
        set_config_overrides(None)


def test_expired_scanner_budget_starts_no_shortlist_requests(monkeypatch):
    row = context()
    monkeypatch.setattr(scanner, '_rank_candidates', lambda rows: rows)
    monkeypatch.setattr(scanner, '_evaluate_price_gate', lambda *a: None)
    monkeypatch.setattr(scanner, '_evaluate_watchlist_gates', lambda *a: 'DROP_STALE_MARKET_DATA')
    ledger = {}
    result = scanner._refresh_provisional_shortlist([row], NS(refresh_quote=lambda _: pytest.fail('expired budget request')),
        'RTH', {}, 1, None, ledger, runtime_bound_reached=lambda stage: True)
    assert result == [] and ledger == {'ONE':'DROP_STALE_MARKET_DATA'}
