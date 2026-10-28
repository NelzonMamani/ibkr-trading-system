"""Controlled clocks/transports: shortlist budget must bound acquisition waits."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from src.core import acquisition
from src.ibkr.market_data_client import MarketDataClient
from src.scanner import scanner_runner as scanner


@pytest.fixture
def clock(monkeypatch):
    value = [100.]
    timer = NS(monotonic=lambda: value[0])
    monkeypatch.setattr(acquisition, 'time', timer)
    import src.ibkr.market_data_client as md_module
    monkeypatch.setattr(md_module, 'time', timer)
    return value


def row():
    return dict(quote_timestamp_source='LAST_TRADE', symbol='ONE', con_id=123, data_quality_flags=[], eligibility_reason_codes=[],
                quote_timestamp_utc=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat())


def test_native_snapshot_wait_and_retries_share_remaining_deadline(monkeypatch, clock):
    requests, waits, cancelled = [], [], []
    ticker = NS()
    def wait(timeout):
        waits.append(timeout)
        clock[0] += timeout
    ib = NS(reqMktData=lambda *a, **kw: requests.append(a) or ticker,
            waitOnUpdate=wait, cancelMktData=lambda *a: cancelled.append(a))
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False, snapshot_timeout_seconds=5)
    monkeypatch.setattr(md, '_canonicalize_history_contract', lambda c: c)
    monkeypatch.setattr(md, '_resolve_ib_client', lambda: ib)
    with acquisition.acquisition_scope(lambda: False):
        cache = acquisition.cycle_cache()
        cache['identity'] = identity = object()
        with pytest.raises(acquisition.AcquisitionDeadlineExceeded), acquisition.acquisition_deadline(100.025):
            md.snapshot_stock(NS(symbol='ONE', conId=123), refresh=True)
        assert cache['identity'] is identity
        assert not any(isinstance(key, tuple) and key[0] == 'snapshot' for key in cache)
    assert len(requests) == len(cancelled) == 1
    assert sum(waits) == pytest.approx(.025)
    assert max(waits) < .026  # not the configured five-second timeout
    acquisition.checkpoint()  # finalization outside budget remains serviceable


def test_expired_scope_starts_no_request_and_restores_outer_scope(clock):
    with pytest.raises(acquisition.AcquisitionDeadlineExceeded), acquisition.acquisition_deadline(99.):
        pytest.fail('expired acquisition started')
    with acquisition.acquisition_deadline(101.):
        with acquisition.acquisition_deadline(None):
            assert acquisition.bounded_timeout(5.) == 1.
        with acquisition.acquisition_deadline(102.):
            assert acquisition.bounded_timeout(5.) == 1.
    assert acquisition.bounded_timeout(5.) == 5.


def test_stop_wins_over_expired_budget(clock):
    stopped = False
    with acquisition.acquisition_scope(lambda: stopped):
        with pytest.raises(acquisition.AcquisitionCancelled):
            with acquisition.acquisition_deadline(101.):
                stopped = True
                clock[0] = 102.
                acquisition.checkpoint()
        stopped = False
        acquisition.checkpoint()


def test_event_wait_is_clipped_to_budget(clock):
    waits = []
    def wait(seconds):
        waits.append(seconds)
        clock[0] += seconds
        return False
    with pytest.raises(acquisition.AcquisitionDeadlineExceeded), acquisition.acquisition_deadline(100.01):
        acquisition.wait_event(NS(wait=wait), 30.)
    assert sum(waits) == pytest.approx(.01)


def test_rebuild_expiry_does_not_publish_partial_fresh_context(monkeypatch, clock):
    original = row()
    old_stamp = original['quote_timestamp_utc']
    quote = NS(symbol='ONE', timestamp_utc=datetime.now(timezone.utc).isoformat(), timestamp_source='LAST_TRADE')
    def build(*a, **kw):
        clock[0] = 101.
        return dict(original, quote_timestamp_utc=quote.timestamp_utc, data_quality_flags=[])
    monkeypatch.setattr(scanner, '_build_symbol_context', build)
    scanner._refresh_shortlisted_quote(original, NS(refresh_quote=lambda _: quote), 'RTH', {}, deadline_s=100.01)
    assert original['quote_timestamp_utc'] == old_stamp
    assert scanner._stale_market_data_drop(original) == 'DROP_STALE_MARKET_DATA'
    acquisition.checkpoint()


def test_sequential_refreshes_share_one_absolute_deadline(monkeypatch, clock):
    originals = [row(), row()]
    quote = NS(symbol='ONE', timestamp_utc=datetime.now(timezone.utc).isoformat(), timestamp_source='LAST_TRADE')
    observed = []
    def refresh(symbol):
        observed.append(acquisition.bounded_timeout(5.))
        clock[0] += .006
        return quote
    monkeypatch.setattr(scanner, '_build_symbol_context', lambda *a, **kw: dict(row(), quote_timestamp_utc=quote.timestamp_utc))
    for original in originals:
        scanner._refresh_shortlisted_quote(original, NS(refresh_quote=refresh), 'RTH', {}, deadline_s=100.01)
    assert observed == pytest.approx([.01, .004])
    assert originals[0]['quote_timestamp_utc'] == quote.timestamp_utc
    assert scanner._stale_market_data_drop(originals[1]) == 'DROP_STALE_MARKET_DATA'


def test_async_deadline_cancels_and_joins_transport(monkeypatch):
    import time
    cleaned = []
    async def transport():
        try:
            await asyncio.sleep(30)
        finally:
            cleaned.append(True)
    async def operation():
        with acquisition.acquisition_deadline(time.monotonic() + .01):
            await acquisition.cooperative_await(transport())
    with pytest.raises(acquisition.AcquisitionDeadlineExceeded):
        asyncio.run(operation())
    assert cleaned == [True]


def test_native_history_deadline_cancels_request_without_wire_fallback(monkeypatch, clock):
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    client = native_module.IbkrClient('127.0.0.1', 7497, 999, 30, 'LIVE', True)
    monkeypatch.setattr(client, 'is_connected', lambda: True)
    monkeypatch.setattr(client, 'isConnected', lambda: True)
    requests, cancelled, waits = [], [], []
    monkeypatch.setattr(EClient, 'reqHistoricalData', lambda *args, **kwargs: requests.append(args))
    monkeypatch.setattr(EClient, 'cancelHistoricalData', lambda self, req: cancelled.append(req))
    def sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds
    monkeypatch.setattr(native_module, 'time', NS(time=lambda: clock[0], monotonic=lambda: clock[0], sleep=sleep))
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
    monkeypatch.setattr(md, '_resolve_ib_client', lambda: client)
    contract = Contract()
    contract.symbol, contract.conId = 'ONE', 123
    with acquisition.acquisition_scope(lambda: False):
        with pytest.raises(acquisition.AcquisitionDeadlineExceeded), acquisition.acquisition_deadline(100.025):
            md._request_daily_history_with_fallback(contract, lookback_days=25)
    assert len(requests) == len(cancelled) == 1
    assert cancelled == [requests[0][1]]
    assert sum(waits) == pytest.approx(.025)
    acquisition.checkpoint()
