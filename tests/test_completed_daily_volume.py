"""Completed NY daily volume only; actual owners, memory callbacks, no I/O."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from ibapi.client import EClient

from src.adapters.brokers.ibkr import ibkr_client as native_module
from src.ibkr import market_data_client as md
from src.market_data import reference_resolver as refs
from src.market_data.candidate_identity import CandidateIdentity
from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from test_history_completion_ownership import owner, contract, prohibit_acquisition_and_mutation


NOW = datetime(2026, 11, 24, 18, 28, 55, 472578, tzinfo=timezone.utc)
# Retained market-data values; source bars are never rewritten by aggregation.
DATES = ('20261028', '20261029', '20261030', '20261102', '20261103',
         '20261104', '20261105', '20261106', '20261109', '20261110',
         '20261111', '20261112', '20261113', '20261116', '20261117',
         '20261118', '20261119', '20261120', '20261123', '20261124')
VOLUMES = (24619, 80232, 40176, 16317, 12217, 36758, 55162, 6681,
           135475, 23909, 12953, 7405, 5000, 1082863, 166425, 87075,
           5704563, 247374, 137899, 8415991)


def rows():
    return [NS(date=d, close=10., volume=Decimal(v)) for d, v in zip(DATES, VOLUMES)]


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(md, 'datetime', Clock)
    monkeypatch.setattr(native_module, 'datetime', Clock)
    monkeypatch.setattr(refs, 'get_us_eastern_now', lambda: NOW.astimezone(refs.NY_TZ))


def test_retained_series_uses_nineteen_prior_days_without_changing_source():
    source = rows()
    before = deepcopy(source)
    assert md.average_daily_bar_volume(source, 20, now=NOW) == (414900, 19)
    assert source == before
    assert len(source) == 20 and source[-1].volume == Decimal(8415991)


@pytest.mark.parametrize('stamp,expected', [
    ('2026-11-24T00:30:00+00:00', (100, 1)),  # still23Nov in NY
    ('2026-11-24T05:30:00+00:00', (200, 2)),
])
def test_cutoff_is_new_york_date_not_utc_date(stamp, expected):
    source = [NS(date='20261122', volume=100), NS(date='20261123', volume=300)]
    assert md.average_daily_bar_volume(source, 20, now=datetime.fromisoformat(stamp)) == expected


@pytest.mark.parametrize('bad_date', ['20261125', '20260230', 'unknown', '', None,
                                     '2026-11-23T00:00:00', '20261123'])
def test_ambiguous_dates_refuse_including_duplicate_prior_day(bad_date):
    source = [NS(date='20261123', volume=100), NS(date=bad_date, volume=999999)]
    assert md.average_daily_bar_volume(source, 20, now=NOW) == (None, None)


@pytest.mark.parametrize('bad', [Decimal('1.0000000000000000001'), Decimal('NaN'),
                               Decimal('Infinity'), '100', True, -1, 1.5])
def test_prior_day_nonintegral_or_unverified_volume_never_mints_average(bad):
    assert md.average_daily_bar_volume([NS(date='20261123', volume=bad)], 20, now=NOW) == (None, None)


def test_exact_large_counts_and_latest_dates_not_callback_order():
    source = [NS(date='20261123', volume=Decimal('9007199254740993')),
              NS(date='20261121', volume=10), NS(date='20261122', volume=20)]
    assert md.average_daily_bar_volume(source, 1, now=NOW) == (9007199254740993, 1)
    assert md.average_daily_bar_volume([NS(date='20261123', volume=9007199254740993)], 20, now=NOW) == (9007199254740993, 1)


def test_native_completed_request_keeps_current_bar_but_basis_excludes_it(owner, monkeypatch):
    c, source = owner.client, rows()
    def send(self, req, *args):
        for row in source:
            c.historicalData(req, row)
        c.historicalDataEnd(req, 'original-start', 'original-end')
    monkeypatch.setattr(EClient, 'reqHistoricalData', send)
    result = c.reqHistoricalData(contract(), durationStr='20 D', barSizeSetting='1 day',
                                 whatToShow='TRADES', useRTH=1, formatDate=1)
    assert result.completed and result.end_received
    assert len(result.raw_source_bars) == 20
    assert result.raw_source_bars[-1]['date'] == '20261124'
    assert result.raw_source_bars[-1]['volume'] == 8415991
    assert result.request_spec.duration_str == '20 D'
    assert (result.volume_basis['average'], result.volume_basis['sample_count']) == (414900, 19)
    assert result.volume_basis['unit'] == 'UNKNOWN'
    assert result.volume_basis['calibration_id'] is None


@pytest.mark.parametrize('bad_date', ['20261125', '20261123', '20260230'])
def test_native_completed_request_preserves_ambiguous_source_but_refuses_average(owner, monkeypatch, bad_date):
    c, source = owner.client, rows()
    source[-1].date = bad_date
    def send(self, req, *args):
        for row in source:
            c.historicalData(req, row)
        c.historicalDataEnd(req, '', '')
    monkeypatch.setattr(EClient, 'reqHistoricalData', send)
    result = c.reqHistoricalData(contract(), durationStr='20 D', barSizeSetting='1 day',
                                 whatToShow='TRADES', useRTH=1, formatDate=1)
    assert result.completed and len(result.raw_source_bars) == 20
    assert result.raw_source_bars[-1]['date'] == bad_date
    assert result.volume_basis['average'] is None and result.volume_basis['sample_count'] is None


@pytest.mark.parametrize('bad', [None, 'not-a-time', '2026-11-24T18:28:55'])
def test_native_basis_cannot_replace_missing_or_naive_completion_time(owner, monkeypatch, bad):
    c = owner.client
    from src.ibkr.market_data_client import historical_request_spec
    from src.market_data.candidate_identity import CandidateIdentity
    state = dict(status='COMPLETE_BARS', end_received=True, bars=rows(), completed_at_utc=bad,
                 volume_scope=(c.client_id, c._position_connection_epoch, c.serverVersion()),
                 contract_identity=CandidateIdentity.from_contract(contract()),
                 request_spec=historical_request_spec(end_date_time='', duration_str='20 D',
                     bar_size_setting='1 day', what_to_show='TRADES', use_rth=1, format_date=1,
                     keep_up_to_date=False, chart_options=[]))
    basis = c._historical_volume_basis(state, 991)
    assert basis['average'] is None and basis['sample_count'] is None


def test_real_provider_stats_and_reference_preserve_nineteen_day_count(monkeypatch, tmp_path):
    source = md.HistoricalDataResult('COMPLETE_BARS', tuple(rows()), True)
    client = object.__new__(md.MarketDataClient)
    client.ib = None
    monkeypatch.setattr(client, 'daily_bars_from_history', lambda *a, **kw: source)
    provider = object.__new__(IbkrScannerProvider)
    provider.market_data_client = client
    monkeypatch.setattr(provider, '_qualified_contract_for_symbol', lambda _: contract())
    monkeypatch.setattr(provider, 'get_quote', lambda _: NS(volume_evidence=None, volume=25581997))
    stats = provider.get_intraday_stats('SYNTH')
    assert (stats.average_daily_volume_20d, stats.average_daily_volume_window_days) == (414900, 19)
    resolver = refs.CanonicalReferenceResolver(refs.PersistentReferenceCache(tmp_path/'cache.json'))
    identity = CandidateIdentity.from_contract(contract())
    monkeypatch.setattr(resolver, '_qualify_history_identity', lambda *a: (identity, True))
    normalized = resolver._normalize_bars(source)
    monkeypatch.setattr(resolver, '_request_historical_daily_bars', lambda *a, **kw: normalized)
    monkeypatch.setattr(resolver, '_provider_snapshot_prev_close', lambda *a: None)
    monkeypatch.setattr(resolver, '_provider_adv20_fallback', lambda *a: (None, None))
    result = resolver.resolve(identity=identity, provider=provider, session_label='RTH_MID',
        current_volume=25581997, intraday_avg_volume_20d=stats.average_daily_volume_20d,
        intraday_average_daily_volume_window_days=stats.average_daily_volume_window_days,
        intraday_history_end_received=True, current_last_price=11., rth_open_price=None,
        rth_close_price=None, ibkr_change_pct=None, persisted_pct_change=None)
    assert result.adv20_source == 'INTRADAY_STATS'
    assert (result.avg_volume_20d, result.average_daily_volume_window_days) == (414900, 19)
    assert len(source) == 20
    from src.scanner import scanner_runner as runner
    resolver.reset_cycle()
    monkeypatch.setattr(runner, '_REFERENCE_RESOLVER', resolver)
    snapshot = runner._resolve_reference_snapshot(provider=provider, symbol='SYNTH',
        session_label='RTH_MID', scan_detail={'conId': 123, 'primaryExchange': 'NASDAQ'},
        last_price=11., current_volume=25581997, intraday_avg_volume_20d=414900,
        intraday_average_daily_volume_window_days=19, intraday_history_end_received=True,
        rth_open_price=None, rth_close_price=None, ibkr_change_pct=None, persisted_pct_change=None)
    assert snapshot['average_daily_volume_20d'] == 414900
    assert snapshot['average_daily_volume_window_days'] == 19


def test_reference_preserves_fractional_source_for_refusal(tmp_path):
    resolver = refs.CanonicalReferenceResolver(refs.PersistentReferenceCache(tmp_path/'cache.json'))
    source = [NS(date='20261123', close=10., volume=Decimal('123.00000000000000001'))]
    normalized = resolver._normalize_bars(source)
    assert normalized[0].volume == source[0].volume
    assert resolver._average_volume(normalized) == (None, None)


def test_retained_developing_day_never_matures_when_reviewed_next_day(monkeypatch, tmp_path):
    from dataclasses import replace
    source = md.HistoricalDataResult('COMPLETE_BARS', tuple(rows()), True,
        completed_at_utc=NOW.isoformat())
    later = datetime(2026, 11, 25, 18, tzinfo=timezone.utc)
    before = md.historical_bar_facts(source)
    assert md.average_daily_bar_volume(source, 20, now=later) == (414900, 19)
    resolver = refs.CanonicalReferenceResolver(refs.PersistentReferenceCache(tmp_path/'cache.json'))
    monkeypatch.setattr(refs, 'get_us_eastern_now', lambda: later.astimezone(refs.NY_TZ))
    assert resolver._average_volume(resolver._normalize_bars(source)) == (414900, 19)
    assert md.historical_bar_facts(source) == before
    invalid = replace(source, completed_at_utc='2026-11-26T18:00:00+00:00')
    assert md.average_daily_bar_volume(invalid, 20, now=later) == (None, None)


@pytest.mark.parametrize('completed', ['invalid', '2026-11-24T18:00:00',
                                     '2026-11-25T18:00:00+00:00'])
def test_unverified_source_completion_cannot_define_a_cutoff(completed):
    source = md.HistoricalDataResult('COMPLETE_BARS', tuple(rows()), True,
        completed_at_utc=completed)
    assert md.average_daily_bar_volume(source, 20, now=NOW) == (None, None)


def test_provider_aggregate_is_recomputed_from_its_owned_dated_source(monkeypatch, tmp_path):
    source = md.HistoricalDataResult('COMPLETE_BARS', tuple(rows()), True,
        completed_at_utc=NOW.isoformat())
    supplied = md.HistoricalVolumeResult(814954, 20, source)
    provider = NS(source_name='IBKR', get_average_daily_volume=lambda *a, **kw: supplied)
    resolver = refs.CanonicalReferenceResolver(refs.PersistentReferenceCache(tmp_path/'cache.json'))
    recomputed = resolver._provider_adv20_fallback(provider, CandidateIdentity.from_contract(contract()))
    assert (recomputed.average, recomputed.window) == (414900, 19)
    assert recomputed.history is source and supplied.average == 814954


def test_cycle_cache_does_not_reuse_yesterdays_completed_day_cutoff(monkeypatch, tmp_path):
    current = [NOW]
    monkeypatch.setattr(refs, 'get_us_eastern_now', lambda: current[0].astimezone(refs.NY_TZ))
    resolver = refs.CanonicalReferenceResolver(refs.PersistentReferenceCache(tmp_path/'cache.json'))
    identity = CandidateIdentity.from_contract(contract())
    source = md.HistoricalDataResult('COMPLETE_BARS', tuple(rows()), True,
        completed_at_utc=NOW.isoformat())
    requests = []
    monkeypatch.setattr(resolver, '_qualify_history_identity', lambda *a: (identity, True))
    def history(*a, **kw):
        requests.append(current[0])
        return resolver._normalize_bars(source)
    monkeypatch.setattr(resolver, '_request_historical_daily_bars', history)
    monkeypatch.setattr(resolver, '_provider_snapshot_prev_close', lambda *a: None)
    monkeypatch.setattr(resolver, '_provider_adv20_fallback', lambda *a: (None, None))
    def resolve():
        return resolver.resolve(identity=identity, provider=NS(source_name='SYNTHETIC'),
            session_label='RTH_MID', current_volume=25581997, intraday_avg_volume_20d=None,
            current_last_price=11., rth_open_price=None, rth_close_price=None,
            ibkr_change_pct=None, persisted_pct_change=None)
    first = resolve()
    assert resolve() is first and len(requests) == 1
    current[0] = datetime(2026, 11, 25, 18, tzinfo=timezone.utc)
    second = resolve()
    assert second is not first and len(requests) == 2
    assert (second.avg_volume_20d, second.average_daily_volume_window_days) == (414900, 19)


@pytest.mark.parametrize('count', [None, 0, True, 21])
def test_bare_intraday_average_cannot_claim_twenty_completed_days(monkeypatch, tmp_path, count):
    resolver = refs.CanonicalReferenceResolver(refs.PersistentReferenceCache(tmp_path/'cache.json'))
    identity = CandidateIdentity.from_contract(contract())
    monkeypatch.setattr(resolver, '_qualify_history_identity', lambda *a: (identity, True))
    source = md.HistoricalDataResult('COMPLETE_BARS', tuple(rows()), True)
    monkeypatch.setattr(resolver, '_request_historical_daily_bars',
                        lambda *a, **kw: resolver._normalize_bars(source))
    monkeypatch.setattr(resolver, '_provider_snapshot_prev_close', lambda *a: None)
    monkeypatch.setattr(resolver, '_provider_adv20_fallback', lambda *a: (None, None))
    result = resolver.resolve(identity=identity, provider=NS(source_name='IBKR'), session_label='RTH_MID',
        current_volume=25581997, intraday_avg_volume_20d=814954,
        intraday_average_daily_volume_window_days=count, intraday_history_end_received=True,
        current_last_price=11., rth_open_price=None, rth_close_price=None,
        ibkr_change_pct=None, persisted_pct_change=None)
    assert result.adv20_source == 'IBKR_DAILY_BARS'
    assert (result.avg_volume_20d, result.average_daily_volume_window_days) == (414900, 19)


@pytest.mark.parametrize('completed_before', [None, '2026-11-23'])
def test_old_cached_average_is_unverified_but_previous_close_survives(monkeypatch, tmp_path, completed_before):
    cache = refs.PersistentReferenceCache(tmp_path/'cache.json')
    resolver = refs.CanonicalReferenceResolver(cache)
    identity = CandidateIdentity.from_contract(contract())
    payload = dict(identity_key=identity.key, symbol='SYNTH', cache_trading_date='2026-11-24',
        reference_price=10., reference_source='IBKR_PREV_CLOSE', reference_resolved=True,
        reference_semantics='PREVIOUS_COMPLETED_RTH_CLOSE', reference_trading_date='2026-11-23',
        reference_is_previous_completed_session=True, historical_end_received=True,
        adv20_end_received=True, avg_volume_20d=814954, average_daily_volume_window_days=20,
        adv20_resolved=True, adv20_completed_before=completed_before)
    cache.put([identity.key], payload)
    monkeypatch.setattr(resolver, '_qualify_history_identity', lambda *a: (identity, True))
    monkeypatch.setattr(resolver, '_request_historical_daily_bars',
                        lambda *a, **kw: md.HistoricalDataResult('COMPLETE_EMPTY', (), True))
    monkeypatch.setattr(resolver, '_provider_snapshot_prev_close', lambda *a: None)
    result = resolver.resolve(identity=identity, provider=NS(source_name='IBKR'), session_label='RTH_MID',
        current_volume=25581997, intraday_avg_volume_20d=None, intraday_history_end_received=True,
        current_last_price=11., rth_open_price=None, rth_close_price=None,
        ibkr_change_pct=None, persisted_pct_change=None)
    assert result.reference_price == 10. and result.reference_source == 'PERSISTENT_CACHE_PREV_CLOSE'
    assert result.avg_volume_20d is None and result.average_daily_volume_window_days is None
    assert not result.adv20_resolved
