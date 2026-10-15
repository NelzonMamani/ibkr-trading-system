"""Offline acquisition interruption and reuse. Every transport below is fake."""
import json
import threading
import time
from types import SimpleNamespace as NS

import pytest
from ibapi.client import EClient
from ibapi.contract import Contract

from src.core.acquisition import AcquisitionCancelled, acquisition_scope, checkpoint, wait_event
from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.ibkr.market_data_client import MarketDataClient
from src.scanner.providers.ibkr_provider import IbkrScannerProvider


def contract(con_id=123):
    c = Contract()
    c.symbol, c.secType, c.exchange, c.currency = 'ONE', 'STK', 'SMART', 'USD'
    c.conId, c.primaryExchange, c.localSymbol, c.tradingClass = con_id, 'NASDAQ', 'ONE', 'SCM'
    return c


def native(monkeypatch):
    client = IbkrClient('127.0.0.1', 7497, 999, 30, 'LIVE', True)
    monkeypatch.setattr(client, 'is_connected', lambda: True)
    monkeypatch.setattr(client, 'isConnected', lambda: True)
    return client


@pytest.mark.parametrize('boundary', ['contract', 'history', 'scanner', 'quote'])
def test_stop_interrupts_real_native_wait_and_cleans_market_requests(monkeypatch, tmp_path, boundary):
    client = native(monkeypatch)
    stop = tmp_path / 'STOP'
    monkeypatch.setenv('PR1090_STOP_FILE', str(stop))
    cleanup = []
    timer = None
    def request(*args, **kwargs):
        nonlocal timer
        timer = threading.Timer(.03, lambda: stop.write_text('stop'))
        timer.start()
    if boundary == 'contract':
        monkeypatch.setattr(client, 'reqContractDetails', request)
        operation = lambda: client.resolve_contract('ONE')
    elif boundary == 'history':
        monkeypatch.setattr(EClient, 'reqHistoricalData', request)
        monkeypatch.setattr(client, 'cancelHistoricalData', lambda req: cleanup.append(req))
        operation = lambda: client.reqHistoricalData(contract(), durationStr='25 D')
    elif boundary == 'scanner':
        monkeypatch.setattr(client, 'reqScannerSubscription', request)
        monkeypatch.setattr(client, 'cancelScannerSubscription', lambda req: cleanup.append(req))
        operation = lambda: client.reqScannerData(NS())
    else:
        md = MarketDataClient(connection_manager=NS(get_client=lambda: client), allow_direct_connection=False)
        monkeypatch.setattr(client, 'reqMarketDataType', lambda *a: None)
        monkeypatch.setattr(client, 'reqMktData', lambda *a, **kw: (request(), NS())[1])
        monkeypatch.setattr(client, 'cancelMktData', lambda *a: cleanup.append(a))
        operation = lambda: md.snapshot_stock(contract())
    started = time.monotonic()
    try:
        with pytest.raises(AcquisitionCancelled), acquisition_scope():
            operation()
        assert time.monotonic() - started < 1.0  # configured transport timeout is 30s
        if boundary != 'contract':
            assert len(cleanup) == 1
    finally:
        if timer:
            timer.join()
    checkpoint()  # cancellation scope is gone; cleanup cannot be cancelled


def test_interrupted_enrichment_runs_all_shutdown_hooks_and_durable_mutation_proof(monkeypatch, tmp_path):
    from test_pr1090_p1_repairs import fake_orchestrator
    from src.config import system_config
    from src.config.runtime_config import RunMode
    from src.ibkr import shutdown_evidence, mutation_audit
    instance, called = fake_orchestrator(monkeypatch)
    instance._clean_start_ready_for_trading = True
    instance.run_mode = RunMode.READ_ONLY
    instance._emit_market_session_state = lambda *a: None
    stop = tmp_path / 'STOP'
    monkeypatch.setenv('PR1090_STOP_FILE', str(stop))
    monkeypatch.setenv('PR1090_EVIDENCE_DIR', str(tmp_path))
    monkeypatch.setattr(system_config, 'get_current_market_session', lambda: 'RTH')
    monkeypatch.setattr(system_config, 'ACTIVE_SESSIONS', ['RTH'])
    # Keep real stop controller and request semantics, isolate unrelated tracing.
    instance._request_stop = lambda mode, **kw: instance.stop_controller.request_stop(mode, **kw)
    timer = None
    def interrupted_cycle():
        nonlocal timer
        timer = threading.Timer(.03, lambda: stop.write_text('stop'))
        timer.start()
        wait_event(threading.Event(), 30)
        pytest.fail('selection/execution reached after cancellation')
    instance.run_once = interrupted_cycle
    baseline = mutation_audit.snapshot()
    started = time.monotonic()
    instance.run_forever(cycle_sleep_seconds=30, max_cycles=1)
    timer.join()
    assert time.monotonic() - started < 1
    assert called == list(shutdown_evidence.REQUIRED_HOOKS)
    proof = json.loads((tmp_path / 'shutdown_evidence.json').read_text())
    assert all(row['completed'] for row in proof['hooks'])
    assert [row['event'] for row in proof['events'] if row['event'] != 'SHUTDOWN_HOOK'] == [
        'GRACEFUL_STOP_REQUESTED', 'SHUTDOWN_STARTED', 'SHUTDOWN_COMPLETE', 'TERMINAL_FLUSHED']
    assert proof['mutation_attempts'] == baseline
    assert instance._shutdown_finished


def test_stop_inside_symbol_enrichment_is_not_converted_to_missing_quote(monkeypatch):
    from src.scanner import scanner_runner as scanner
    stopped = False
    class Provider:
        def get_quote(self, symbol):
            nonlocal stopped
            stopped = True
            checkpoint()
        def get_intraday_stats(self, symbol):
            pytest.fail('continued enrichment')
    with pytest.raises(AcquisitionCancelled), acquisition_scope(lambda: stopped):
        scanner._build_symbol_context(Provider(), 'ONE', 'RTH_MID', float_cache={})


def test_exact_requests_reused_and_cycle_identity_boundaries_isolated(monkeypatch):
    from test_ibkr_provider_contract_pipeline import DummyMarketDataClient
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
    md.market_data_type = 'LIVE'
    calls = {'qualify': 0, 'quote': 0, 'history': []}
    def qualify(c):
        calls['qualify'] += 1
        return [c]
    md.ib = NS(isConnected=lambda: True, qualifyContracts=qualify)
    sample = DummyMarketDataClient().snapshot_stock(contract())
    sample.data_quality_flags = []
    def quote(c):
        calls['quote'] += 1
        md.last_snapshot_debug = {'request_id': calls['quote']}
        return sample
    def history(c, **params):
        calls['history'].append((c.conId, params))
        return [NS(date='20261014', close=10., volume=100)]
    monkeypatch.setattr(md, '_snapshot_stock_uncached', quote)
    monkeypatch.setattr(md, '_daily_history_uncached', history)
    provider = object.__new__(IbkrScannerProvider)
    provider.market_data_client = md
    provider.last_scan_details = {'symbol_details': {'ONE': {
        'conId': 123, 'exchange': 'SMART', 'currency': 'USD',
        'primaryExchange': 'NASDAQ', 'localSymbol': 'ONE', 'tradingClass': 'SCM'}}}
    with acquisition_scope(lambda: False):
        q = provider.get_quote('ONE')
        stats = provider.get_intraday_stats('ONE')
        assert q.volume == stats.current_intraday_volume
        provider.get_quote('ONE')  # resolver snapshot-close lookup
        provider.get_average_daily_volume(contract(), 20)
        assert calls['qualify'] == calls['quote'] == 1
        assert len(calls['history']) == 1
        provider.get_daily_bars(contract(), 25)
        provider.get_daily_bars(contract(), 25)
        assert len(calls['history']) == 2  # different duration is NOT interchangeable
        provider.get_daily_bars(contract(), 25, use_rth=False)
        provider.get_daily_bars(contract(), 25, end_datetime='explicit')
        provider.get_daily_bars(contract(456), 25)
        assert len(calls['history']) == 5
    with acquisition_scope(lambda: False):
        provider.get_quote('ONE')
        provider.get_intraday_stats('ONE')
        assert calls['quote'] == 2 and len(calls['history']) == 6


def test_missing_child_evidence_distinguishes_verified_binding_without_passing(monkeypatch, tmp_path):
    from src.ibkr import shutdown_evidence as shutdown
    process = NS(pid=990001, identity_verified=True, runtime_identity={
        'pid': 990001, 'creation_token': 'test'}, poll=lambda: 1)
    result = shutdown.complete_after_process_exit(tmp_path, process,
        no_runtime_remains=lambda: True, final_audit=lambda: {
            'query_completed': True, 'disconnected': True, 'open_orders_count': 0,
            'mutation_attempts': {'place': 0, 'modify': 0, 'cancel': 0}})
    evidence = json.loads((tmp_path / 'terminal_evidence.json').read_text())
    assert evidence['supervisor_runtime_identity_verified'] is True
    assert evidence['child_shutdown_identity_matched'] is False
    assert evidence['runtime_identity_verified'] is False
    assert evidence['runtime_identity_verification_reason'] == 'CHILD_SHUTDOWN_IDENTITY_MISSING_OR_MISMATCHED'


@pytest.mark.parametrize('kind', ['qualification', 'history'])
def test_async_stop_cancels_and_drains_request(monkeypatch, kind):
    import asyncio
    from src.core.acquisition import cooperative_await
    stopped = False
    cancelled = []
    async def run():
        nonlocal stopped
        loop = asyncio.get_running_loop()
        loop.call_later(.02, lambda: set_stop())
        if kind == 'qualification':
            async def pending(*args):
                try:
                    await asyncio.Future()
                finally:
                    cancelled.append('qualification')
            with acquisition_scope(lambda: stopped):
                await cooperative_await(pending())
        else:
            md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
            future = loop.create_future()
            ib = NS(client=NS(getReqId=lambda: 42, reqHistoricalData=lambda *a: None,
                              cancelHistoricalData=lambda req: cancelled.append(req)),
                    wrapper=NS(startReq=lambda *a, **kw: future,
                               _endReq=lambda req: cancelled.append(('end', req))))
            with acquisition_scope(lambda: stopped):
                await cooperative_await(md._cancellable_insync_history(ib, contract(),
                    endDateTime='', durationStr='25 D', barSizeSetting='1 day',
                    whatToShow='TRADES', useRTH=True, formatDate=1))
    def set_stop():
        nonlocal stopped
        stopped = True
    started = time.monotonic()
    with pytest.raises(AcquisitionCancelled):
        asyncio.run(run())
    assert time.monotonic() - started < 1
    assert cancelled == (['qualification'] if kind == 'qualification' else [42, ('end', 42)])


def test_float_stop_does_not_start_next_http_fallback(monkeypatch):
    from src.scanner.providers import ibkr_provider as module
    stopped = False
    calls = []
    def get(*args, **kwargs):
        nonlocal stopped
        calls.append(args)
        stopped = True
        raise module.requests.RequestException('synthetic request failure')
    monkeypatch.setattr(module.requests, 'get', get)
    with pytest.raises(AcquisitionCancelled), acquisition_scope(lambda: stopped):
        IbkrScannerProvider._fetch_yahoo_float_detailed('ONE')
    assert len(calls) == 1


def test_empty_history_keeps_same_cycle_retry(monkeypatch):
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
    answers = iter([[], [NS(date='20261014', close=10, volume=100)]])
    calls = []
    def history(*a, **kw):
        calls.append(True)
        return next(answers)
    monkeypatch.setattr(md, '_daily_history_uncached', history)
    with acquisition_scope(lambda: False):
        assert md._request_daily_history_with_fallback(contract(), lookback_days=25) == []
        assert len(md._request_daily_history_with_fallback(contract(), lookback_days=25)) == 1
        assert len(md._request_daily_history_with_fallback(contract(), lookback_days=25)) == 1
    assert len(calls) == 2
