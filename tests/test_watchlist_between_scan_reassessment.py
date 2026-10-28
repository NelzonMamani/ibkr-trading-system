"""Canonical publication -> genuine cached shortlist -> strict quote/Focus gates."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded, acquisition_scope
from src.scanner import scanner_runner as ross
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy
from test_news_catalyst_lifecycle_audit import lifecycle, CANDIDATE
from test_pr1082_rth_watchlist_continuity import _install_runtime_harness, _row, _payload, _cadence, _age_cache


@pytest.fixture
def reassessment(lifecycle, monkeypatch):
    life = lifecycle
    from src.domain import quote_freshness
    monkeypatch.setattr(quote_freshness, 'datetime', life.clock)
    policy = replace(RossMomentumPolicy().stock_selection, spread_max_pct=1.5)
    thresholds = replace(ross._gate_thresholds(policy, ross._resolve_runtime_thresholds(policy, "RTH_OPEN")),
                         spread_max_pct=1.5)  # Explicit existing spread gate, not a production policy change.
    session = 'RTH_OPEN'
    now = life.clock.now(timezone.utc)
    row = dict(symbol='JPM', company_name=CANDIDATE.company_name, con_id=123, exchange='SMART',
               session=session, quote_timestamp_utc=(now-timedelta(seconds=30)).isoformat(),
               quote_timestamp_source='LAST_TRADE', data_quality_flags=[], eligibility_reason_codes=[],
               last_price=6., bid=5.99, ask=6.01, spread_pct=.0034, pct_change=25.,
               float_shares=8_000_000, rvol=10., rvol_discovery=10., rvol_phase=10.,
               volume=2_000_000, premarket_volume=2_000_000, dollar_volume=12_000_000,
               scanner_score=1.)
    client = object()
    calls = []
    def refresh(symbol):
        calls.append(symbol)
        return NS(symbol=symbol, timestamp_utc=life.clock.now(timezone.utc).isoformat(), timestamp_source='LAST_TRADE')
    provider = NS(source_name='IBKR', market_data_client=client, refresh_quote=refresh)
    monkeypatch.setattr(ross, '_PERSISTENT_PROVIDER', provider)
    monkeypatch.setattr(ross, 'resolve_session_diagnostics', lambda *a, **kw: NS(resolved_session=session))
    def rebuild(provider, symbol, session, **kw):
        return dict(deepcopy(row), quote_timestamp_utc=kw['quote_override'].timestamp_utc)
    monkeypatch.setattr(ross, '_build_symbol_context', rebuild)
    reads = []
    def read(candidates, request, policy):
        reads.append(candidates)
        return life.service.get_news(candidates, request, replace(policy, network_allowed=False,
                                      refresh_mode='cache_only', allow_cache_write=False))
    bundle = dict(schema='ross_scan_shortlist_v1', session=session, date=now.date().isoformat(),
                  contexts=[row], thresholds=thresholds, float_cache={}, focus_limit=3, policy=policy)
    payload = {'ross_watchlist_reassessment': bundle}
    def run(symbols=('JPM',), **kwargs):
        return ross.reassess_ross_watchlist(payload, symbols, news_maintenance=NS(read=read),
                                          market_data_client=kwargs.pop("market_data_client", client), policy=kwargs.pop("policy", policy), **kwargs)
    return NS(life=life, payload=payload, run=run, provider=provider, calls=calls, reads=reads, row=row)


def publish(case, articles=None):
    if articles is not None:
        case.life.provider.articles = articles
    return case.life.service.get_news((CANDIDATE,), case.life.request, case.life.policy)


def test_empty_focus_reconsiders_later_publication_without_http_or_discovery(reassessment):
    c = reassessment
    original = deepcopy(c.payload)
    assert c.run() == [] and c.calls == [] and c.life.provider.calls == 0
    publish(c)
    rows = c.run()
    assert [r.symbol for r in rows] == ['JPM']
    assert rows[0].catalyst_qualification_reason == 'verified_issuer_event_valid'
    assert rows[0].catalyst_evidence['evidence'][0]['published_at'] == c.life.provider.articles[0].published_at.isoformat()
    assert c.calls == ['JPM'] and c.life.provider.calls == 1
    assert c.payload == original  # No candidate receipt can renew the stored broker timestamp.
    # Successful real refresh may be reused only within the invocation; a later
    # reassessment still starts from authoritative context, never invented time.
    c.life.clock.current += timedelta(seconds=121)
    c.life.provider.failure = True
    publish(c)
    assert [r.symbol for r in c.run()] == ['JPM']
    assert c.life.provider.calls == 2


@pytest.mark.parametrize('fault', ['stale_quote', 'timeout', 'wrong_symbol', 'missing_time', 'spread', 'halt', 'float', 'rvol'])
def test_positive_event_cannot_bypass_market_gates(reassessment, fault):
    c = reassessment
    publish(c)
    original = c.provider.refresh_quote
    def refresh(symbol):
        quote = original(symbol)
        if fault == 'stale_quote': quote.timestamp_utc = c.row['quote_timestamp_utc']
        elif fault == 'timeout': raise AcquisitionDeadlineExceeded('fixture')
        elif fault == 'wrong_symbol': quote.symbol = 'OTHER'
        elif fault == 'missing_time': quote.timestamp_source = 'RECEIVED'
        return quote
    c.provider.refresh_quote = refresh
    if fault == 'spread': c.row.update(bid=4., ask=8., spread_pct=100.)
    elif fault == 'halt': c.row['halted'] = True
    elif fault == 'float': c.row['float_shares'] = 500_000_000
    elif fault == 'rvol': c.row.update(rvol=0., rvol_phase=0., rvol_discovery=0.)
    assert c.run() == []
    assert len(c.calls) == 1


@pytest.mark.parametrize('change', ['expiry', 'dilution', 'incomplete_aixi', 'lawyer'])
def test_reconsideration_does_not_loosen_catalyst_rules(reassessment, change):
    c = reassessment
    if change == 'incomplete_aixi':
        articles = (c.life.article('JPM latest SEC filing confirms its appeal against Apple ha'),)
    elif change == 'lawyer':
        articles = (c.life.article('JPM investors: law firm seeks lead plaintiff'),)
    elif change == 'dilution':
        articles = (c.life.article(), c.life.article('JPM announces registered direct offering'))
    else:
        articles = (c.life.article(),)
        c.life.clock.current = articles[0].published_at + timedelta(hours=6, microseconds=1)
    publish(c, articles)
    assert c.run() == [] and c.calls == []


@pytest.mark.parametrize('change', ['removed', 'session', 'date', 'provider'])
def test_incompatible_authority_cannot_be_reconstructed(reassessment, change):
    c = reassessment
    publish(c)
    symbols = ('OTHER',) if change == 'removed' else ('JPM',)
    if change in ('session', 'date'):
        c.payload['ross_watchlist_reassessment'][change] = 'incompatible'
    if change == 'provider': c.provider.market_data_client = object()
    assert c.run(symbols) == [] and c.calls == []


def test_stop_and_absolute_deadline_interrupt_reassessment(reassessment):
    c = reassessment
    publish(c)
    with pytest.raises(AcquisitionCancelled), acquisition_scope(lambda: True):
        c.run()
    with pytest.raises(AcquisitionDeadlineExceeded):
        c.run(deadline_s=0.)
    assert c.calls == []


def test_core_reconsiders_empty_focus_at_existing_cadence_without_new_scan(monkeypatch):
    row = _row('AAA', catalyst=True)
    core, scans, processed = _install_runtime_harness(monkeypatch, [_payload([row], focus=[])])
    assert core.run_once()
    assert _cadence(core).focus.symbols == []
    calls = []
    def reconsider(payload, symbols, **kwargs):
        calls.append((payload, symbols, kwargs))
        return [row]
    monkeypatch.setattr('src.core.orchestrator.reassess_ross_watchlist', reconsider)
    _age_cache(_cadence(core).focus, 11)
    assert core.run_once()
    assert len(scans) == 1 and len(calls) == 1
    assert calls[0][1] == ['AAA']
    assert _cadence(core).focus.symbols == ['AAA']
    assert _cadence(core).focus.authority == 'CANONICAL_WATCHLIST_REASSESSMENT'
    assert processed == [['AAA']]


@pytest.mark.parametrize('tightening', ['float', 'rvol', 'focus_limit', 'news_disabled'])
def test_current_policy_tightening_rejects_old_authority(reassessment, tightening):
    from src.config.config_resolver import set_config_overrides
    c = reassessment
    publish(c)
    policy = c.payload['ross_watchlist_reassessment']['policy']
    if tightening == 'float': policy = replace(policy, float_max_millions=1.)
    elif tightening == 'rvol': policy = replace(policy, rvol_min=999.)
    elif tightening == 'focus_limit': policy = replace(policy, focus_limit_m=0)
    else: set_config_overrides({'NEWS_ENABLED': False})
    assert c.run(policy=policy) == [] and c.calls == []


def test_reassessment_reuses_identity_but_not_prior_attempt_history(reassessment, monkeypatch):
    from src.core.acquisition import cycle_cache
    from src.ibkr.market_data_client import MarketDataClient
    from src.scanner.providers.ibkr_provider import IbkrScannerProvider
    from test_ibkr_provider_contract_pipeline import DummyMarketDataClient
    from test_natural_readonly_enrichment_stop import contract
    c = reassessment
    publish(c)
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
    md.market_data_type = 'LIVE'
    calls = dict(quote=0, history=0, qualify=0)
    def qualify(value):
        calls['qualify'] += 1
        return [value]
    md.ib = NS(isConnected=lambda: True, qualifyContracts=qualify)
    sample = DummyMarketDataClient().snapshot_stock(contract())
    sample.symbol = 'JPM'
    sample.data_quality_flags = []
    sample.timestamp_source = 'LAST_TRADE'
    sample.timestamp_utc = c.life.clock.now(timezone.utc).isoformat()
    def quote(*args):
        calls['quote'] += 1
        return sample
    def history(*args, **kwargs):
        calls['history'] += 1
        from src.ibkr.market_data_client import HistoricalDataResult
        return HistoricalDataResult('COMPLETE_BARS',(NS(date='20261019', close=5., volume=100_000),),True)
    monkeypatch.setattr(md, '_snapshot_stock_uncached', quote)
    md.ib.reqHistoricalData=history
    provider = object.__new__(IbkrScannerProvider)
    provider.market_data_client = md
    provider.last_scan_details = {'symbol_details': {'JPM': {
        'conId': 123, 'exchange': 'SMART', 'currency': 'USD',
        'primaryExchange': 'NASDAQ', 'localSymbol': 'JPM', 'tradingClass': 'SCM'}}}
    monkeypatch.setattr(ross, '_PERSISTENT_PROVIDER', provider)
    with acquisition_scope(lambda: False):
        provider.get_quote('JPM')
        provider.get_intraday_stats('JPM')
        retained = ross._shortlist_request_cache(md, ['JPM'])
        assert retained and all(k[0] != 'snapshot' for k in retained)
        assert ross._shortlist_request_cache(object(), ['JPM']) == {}
        assert ross._shortlist_request_cache(md, ['OTHER']) == {}
    c.payload['ross_watchlist_reassessment']['request_cache'] = retained
    # Identity qualification is retained; history completion/outcome cache is
    # attempt-local and must not survive into a later cached reconsideration.
    def rebuild(provider, symbol, session, **kwargs):
        provider.get_intraday_stats(symbol)
        return dict(deepcopy(c.row), quote_timestamp_utc=kwargs['quote_override'].timestamp_utc)
    monkeypatch.setattr(ross, '_build_symbol_context', rebuild)
    for _ in range(2):
        assert [r.symbol for r in c.run(market_data_client=md)] == ['JPM']
    assert calls == dict(quote=3, history=3, qualify=1)
    with acquisition_scope(lambda: False):
        cycle_cache().update(retained)
        # Different history parameters and identities remain separate requests.
        target = provider._qualified_contract_for_symbol('JPM')
        provider.get_daily_bars(target, 25)
        provider.get_daily_bars(target, 25, use_rth=False)
        provider.get_daily_bars(target, 25, end_datetime='explicit')
        assert calls['history'] == 6
    # Leaving the original TopN snapshot restores the ordinary fresh-cycle path.
    with acquisition_scope(lambda: False):
        provider.get_intraday_stats('JPM')
    assert calls == dict(quote=4, history=7, qualify=2)


def test_multiple_positive_rows_slow_tail_keeps_leader_inside_outer_deadline(reassessment, monkeypatch):
    from src.core.acquisition import bounded_timeout, checkpoint
    c = reassessment
    tail = replace(c.life.article('TAIL reports earnings beat'), symbol='TAIL', company_name='TAIL')
    c.life.store.write({'JPM': (c.life.article(),), 'TAIL': (tail,)}, c.life.request)
    bundle = c.payload['ross_watchlist_reassessment']
    bundle['contexts'].append(dict(deepcopy(c.row), symbol='TAIL', company_name='TAIL', con_id=456))
    ticks = [0.]
    origin = c.life.clock.current
    monkeypatch.setattr(ross.time, 'monotonic', lambda: ticks[0])
    monkeypatch.setattr(ross, '_rank_candidates', lambda rows: list(rows))
    calls = []
    def refresh(symbol):
        calls.append(symbol)
        ticks[0] += bounded_timeout(1. if symbol == 'JPM' else 30.)
        c.life.clock.current = origin + timedelta(seconds=ticks[0])
        checkpoint()
        return NS(symbol=symbol, timestamp_utc=c.life.clock.current.isoformat(), timestamp_source='LAST_TRADE')
    c.provider.refresh_quote = refresh
    def rebuild(provider, symbol, session, **kwargs):
        source = next(row for row in bundle['contexts'] if row['symbol'] == symbol)
        return dict(deepcopy(source), quote_timestamp_utc=kwargs['quote_override'].timestamp_utc)
    monkeypatch.setattr(ross, '_build_symbol_context', rebuild)
    rows = c.run(('JPM', 'TAIL'), deadline_s=10.)
    assert [r.symbol for r in rows] == ['JPM']
    assert calls == ['JPM', 'TAIL'] and ticks[0] == 9.
    # The real last trade is1s, not renewed to9s after the tail timed out.
    assert rows[0].last_price == 6.
    assert (c.life.clock.current-origin).total_seconds() == 9.


def test_core_real_helper_handoff_after_empty_focus(reassessment, monkeypatch):
    from src.config import config_resolver
    c = reassessment
    row = _row('JPM')
    payload = _payload([row], focus=[])
    payload.update(c.payload)
    core, scans, processed = _install_runtime_harness(monkeypatch, [payload])
    overrides = dict(config_resolver._CONFIG_OVERRIDES)
    overrides.update(NEWS_ENABLED=True, NEWS_CACHE_FILE=str(c.life.store.cache_path), ROSS_ISSUER_QUERY_ENABLED=True)
    config_resolver.set_config_overrides(overrides)
    # Use precisely the real Core's currently resolved scanner policy authority.
    _, policy = core._build_scanner_policy_for_strategy('ross_momentum', 'RTH_OPEN')
    bundle = payload['ross_watchlist_reassessment']
    bundle['policy'] = policy
    bundle['thresholds'] = ross._gate_thresholds(policy, ross._resolve_runtime_thresholds(policy, 'RTH_OPEN'))
    core.connection_manager._client = object()  # Controlled, never connected.
    c.provider.market_data_client = core.connection_manager.optional_client
    # Core resets scanner globals before its first scan. The controlled scan
    # receipt must install the same provider ownership as run_scanner_cycle.
    from src.core import orchestrator as core_module
    scanner_stub = core_module.run_scanner_cycle
    def scan(**kwargs):
        ross._PERSISTENT_PROVIDER = c.provider
        return scanner_stub(**kwargs)
    monkeypatch.setattr(core_module, 'run_scanner_cycle', scan)
    core._news_maintenance = NS(read=lambda candidates, request, policy:
        c.life.service.get_news(candidates, request, replace(policy, network_allowed=False,
                                    refresh_mode='cache_only', allow_cache_write=False)),
        set_active=lambda *args: None)
    assert core.run_once() and _cadence(core).focus.symbols == []
    assert ross._PERSISTENT_PROVIDER is c.provider
    assert c.provider.market_data_client is core.connection_manager.optional_client
    assert bundle['date'] == ross._utc_now().date().isoformat()
    publish(c)
    _age_cache(_cadence(core).focus, 11)
    assert core.run_once()
    assert len(scans) == 1
    assert _cadence(core).focus.symbols == ['JPM']
    assert processed == [['JPM']]
    assert c.life.provider.calls == 1 and c.calls == ['JPM']
