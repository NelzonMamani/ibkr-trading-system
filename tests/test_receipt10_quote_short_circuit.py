"""Offline receipt10 failure shape; never connect or obtain provider data."""
from types import SimpleNamespace

import pytest

from src.core.acquisition import AcquisitionCancelled
from src.scanner import scanner_runner as runner


def quote(flags):
    return SimpleNamespace(bid=None, ask=None, last=None, close=None, volume=None,
        vwap=None, open=None, data_quality_flags=flags, request_id=465,
        requested_market_data_type='DELAYED', returned_market_data_type='UNKNOWN',
        market_data_type_confirmed=False, timestamp_source='UNKNOWN',
        snapshot_complete=False, snapshot_evidence={'completion_reason': 'timeout'})


@pytest.mark.parametrize('flag', ['SNAPSHOT_TIMEOUT', 'MD_TIMEOUT'])
@pytest.mark.parametrize('partial', [False, True])
def test_timeout_skips_repeated_quotes_and_all_history(monkeypatch, flag, partial):
    calls = []
    item = quote([flag])
    if partial:
        item.last = 4.5  # A partial timeout was already rejected by the strict gate.
    class Provider:
        def get_quote(self, symbol):
            calls.append(('quote', symbol))
            return item
        def get_intraday_stats(self, symbol):
            calls.append(('intraday', symbol))
            return None
    def forbidden_reference(**kwargs):
        calls.append(('reference', kwargs['symbol']))
        raise AssertionError('Unusable quote must not start reference enrichment')
    monkeypatch.setattr(runner, '_resolve_reference_snapshot', forbidden_reference)
    result = runner._build_symbol_context(Provider(), 'AIOK', 'RTH', float_cache={})
    assert calls == [('quote', 'AIOK')]
    assert result['snapshot_timeout'] is True
    assert result['data_quality_flags'] == [flag]
    assert result['quote_request_id'] == 465
    assert result['returned_market_data_type'] == 'UNKNOWN'
    assert not result['market_data_type_confirmed']
    assert not result['snapshot_complete']
    assert result['snapshot_evidence'] == {'completion_reason': 'timeout'}
    assert result['enrichment_skipped_reason'] == 'SNAPSHOT_TIMEOUT'
    assert result.get('reference_price') is None
    assert result.get('rvol') is None


def test_non_timeout_still_reaches_existing_enrichment(monkeypatch):
    calls = []
    class Provider:
        def get_quote(self, symbol):
            calls.append('quote')
            return quote([])
        def get_intraday_stats(self, symbol):
            calls.append('intraday')
            return None
    def reference(**kwargs):
        calls.append('reference')
        raise RuntimeError('Existing enrichment reached')
    monkeypatch.setattr(runner, '_resolve_reference_snapshot', reference)
    with pytest.raises(RuntimeError, match='Existing enrichment reached'):
        runner._build_symbol_context(Provider(), 'AIOK', 'RTH', float_cache={})
    assert calls == ['quote', 'intraday', 'reference']


def test_operator_stop_is_not_converted_to_quote_failure():
    class Provider:
        def get_quote(self, symbol):
            raise AcquisitionCancelled()
    with pytest.raises(AcquisitionCancelled):
        runner._build_symbol_context(Provider(), 'AIOK', 'RTH', float_cache={})


def test_real_provider_skips_timeout_work_but_enriches_next_valid_candidate(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from src.core.acquisition import acquisition_scope
    from src.ibkr.market_data_client import MarketDataClient
    from src.scanner.providers.ibkr_provider import IbkrScannerProvider
    from test_ibkr_provider_contract_pipeline import DummyMarketDataClient

    md = MarketDataClient(connection_manager=SimpleNamespace(), allow_direct_connection=False)
    md.ib = SimpleNamespace(isConnected=lambda: True, qualifyContracts=lambda *cs: list(cs))
    calls, histories = [], []
    def acquire(c):
        calls.append(c.symbol)
        item = DummyMarketDataClient().snapshot_stock(c)
        item.symbol = c.symbol
        item.data_quality_flags = ['MD_TIMEOUT'] if c.symbol == 'BAD' else []
        item.timestamp_utc = datetime.now(timezone.utc).isoformat()
        item.returned_market_data_type = 'LIVE'
        item.market_data_type_confirmed = True
        item.timestamp_source = 'LAST_TRADE'
        if c.symbol == 'BAD':
            item.bid = item.ask = item.last = item.close = item.volume = None
        md.last_snapshot_debug = {'raw_fields': {}, 'timeout_occurred': c.symbol == 'BAD'}
        return item
    def history(c, **params):
        histories.append(c.symbol)
        now = datetime.now(timezone.utc)
        return [SimpleNamespace(date=(now-timedelta(days=i)).strftime('%Y%m%d'),
                                close=10., volume=1000) for i in range(1, 31)]
    monkeypatch.setattr(md, '_snapshot_stock_uncached', acquire)
    monkeypatch.setattr(md, '_daily_history_uncached', history)
    provider = object.__new__(IbkrScannerProvider)
    provider.market_data_client = md
    provider.last_scan_details = {'symbol_details': {symbol: {
        'symbol': symbol, 'conId': i, 'exchange': 'SMART', 'primaryExchange': 'NASDAQ',
        'currency': 'USD', 'localSymbol': symbol, 'tradingClass': 'SCM'}
        for i, symbol in enumerate(('BAD', 'GOOD'), 123)}}
    runner._REFERENCE_RESOLVER.reset_cycle()
    with acquisition_scope(lambda: False):
        bad = runner._build_symbol_context(provider, 'BAD', 'RTH', float_cache={})
        assert bad['snapshot_timeout'] and calls == ['BAD'] and histories == []
        good = runner._build_symbol_context(provider, 'GOOD', 'RTH', float_cache={})
    assert calls == ['BAD', 'GOOD']  # Valid exact-identity quote cache still reused.
    assert histories and set(histories) == {'GOOD'}
    assert good['last_price'] == 10.5 and good['volume'] == 5000
    assert good['pct_change'] is not None and not good['snapshot_timeout']
    assert 'enrichment_skipped_reason' not in good


def test_timeout_retains_supplied_identity_without_reference_acquisition():
    class Provider:
        last_scan_details = {'symbol_details': {'AIOK': {
            'conId': 123, 'longName': 'One Industrial Inc', 'companyName': 'One Industrial',
            'primaryExchange': 'NASDAQ', 'currency': 'USD', 'aliases': ['One Industries']}}}
        def get_quote(self, symbol):
            return quote(['SNAPSHOT_TIMEOUT'])
        def get_intraday_stats(self, symbol):
            pytest.fail('timeout enrichment continued')
    result = runner._build_symbol_context(Provider(), 'AIOK', 'RTH', float_cache={})
    assert result['con_id'] == 123 and not result['con_id_is_synthetic']
    assert result['long_name'] == 'One Industrial Inc'
    assert result['company_name'] == 'One Industrial'
    assert result['aliases'] == ['One Industries']
    assert result['primary_exchange'] == 'NASDAQ'
    assert result['snapshot_timeout'] and result.get('reference_price') is None
