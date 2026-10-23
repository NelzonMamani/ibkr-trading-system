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
