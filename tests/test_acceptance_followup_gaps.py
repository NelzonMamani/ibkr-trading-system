"""Synthetic acceptance-gap probes; no broker/provider transport."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import json
import threading
import time
from types import SimpleNamespace as NS

import pytest

from src.core.acquisition import AcquisitionCancelled, acquisition_scope
from src.ibkr.market_data_client import MarketDataClient


def test_cached_quote_ages_without_reacquisition(monkeypatch):
    import src.ibkr.market_data_client as module
    now = datetime(2026, 10, 16, 14, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(module, 'get_config', lambda key: 15)
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
    sample = NS(timestamp_source="LAST_TRADE", timestamp_utc=now.isoformat(), data_quality_flags=[])
    calls = []
    monkeypatch.setattr(md, '_snapshot_stock_uncached', lambda c: (calls.append(c), sample)[1])
    with acquisition_scope(lambda: False):
        first = md.snapshot_stock('ONE')
        assert 'MD_STALE' not in first.data_quality_flags
        now += timedelta(seconds=16)
        reused = md.snapshot_stock('ONE')
        assert reused is first and len(calls) == 1
        assert reused.timestamp_utc == sample.timestamp_utc
        assert 'MD_STALE' in reused.data_quality_flags


def test_runtime_scanner_reset_stops_float_workers(monkeypatch):
    from src.scanner import scanner_runner as scanner
    from src.market_data import float_discovery_worker as floats
    stopped = []
    monkeypatch.setattr(floats, '_WORKERS', {('cache', 'db'): NS(shutdown=lambda timeout: stopped.append(timeout) or True)})
    monkeypatch.setattr(scanner, '_PERSISTENT_PROVIDER', None)
    scanner.reset_scanner_runtime_state()
    assert len(stopped) == 1 and stopped[0] <= 3
    assert not floats._WORKERS


def test_news_return_after_stop_discards_partial_result(monkeypatch):
    from src.scanner import scanner_runner as scanner
    stopped = False
    def news(*args):
        nonlocal stopped
        stopped = True
        return {'ONE': {'synthetic': True}}, NS()
    monkeypatch.setattr(scanner, '_enrich_news_context_impl', news)
    with pytest.raises(AcquisitionCancelled), acquisition_scope(lambda: stopped):
        scanner._enrich_news_context(['ONE'], 'IBKR')


def test_stop_prevents_cached_quote_return(monkeypatch):
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
    sample = NS(timestamp_source="LAST_TRADE", timestamp_utc=datetime.now(timezone.utc).isoformat(), data_quality_flags=[])
    monkeypatch.setattr(md, '_snapshot_stock_uncached', lambda c: sample)
    stopped = False
    with pytest.raises(AcquisitionCancelled), acquisition_scope(lambda: stopped):
        md.snapshot_stock('ONE')
        stopped = True
        md.snapshot_stock('ONE')


def test_worker_timeout_keeps_truth_and_still_disconnects_provider(monkeypatch):
    from src.scanner import scanner_runner as scanner
    from src.market_data import float_discovery_worker as floats
    calls = []
    worker = NS(shutdown=lambda timeout: False)
    monkeypatch.setattr(floats, '_WORKERS', {('cache', 'db'): worker})
    monkeypatch.setattr(scanner, '_PERSISTENT_PROVIDER', NS(disconnect=lambda: calls.append('disconnect')))
    with pytest.raises(RuntimeError, match='worker shutdown incomplete'):
        scanner.reset_scanner_runtime_state(suppress_disconnect_errors=False)
    assert calls == ['disconnect']
    assert floats._WORKERS[('cache', 'db')] is worker


def test_previously_fresh_context_is_rechecked_at_selection(monkeypatch):
    from src.scanner import scanner_runner as scanner
    now = datetime(2026, 10, 16, 14, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr(scanner, 'datetime', Clock)
    monkeypatch.setattr(scanner, 'get_config', lambda key: 15)
    row = {'quote_timestamp_source': 'LAST_TRADE', 'quote_timestamp_utc': now.isoformat(), 'data_quality_flags': []}
    original = row['quote_timestamp_utc']
    assert scanner._stale_market_data_drop(row) is None
    now += timedelta(seconds=16)
    assert scanner._stale_market_data_drop(row) == 'DROP_STALE_MARKET_DATA'
    assert row['quote_timestamp_utc'] == original
    assert row['focus_eligible'] is False and row['execution_ready'] is False


@pytest.mark.parametrize('age,stale', [(15, False), (15.001, True)])
def test_reuse_preserves_age_threshold_and_all_authority(monkeypatch, age, stale):
    import src.ibkr.market_data_client as module
    stamp = datetime(2026, 10, 16, 14, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return stamp + timedelta(seconds=age)
    monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(module, 'get_config', lambda key: 15)
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
    sample = NS(timestamp_source="LAST_TRADE", timestamp_utc=stamp.isoformat(), data_quality_flags=['MD_DELAYED'],
        requested_market_data_type='LIVE', returned_market_data_type='DELAYED',
        market_data_type_confirmed=True, request_id=42, snapshot_complete=True,
        received_at_utc=(stamp + timedelta(seconds=age)).isoformat(),
        snapshot_evidence={'field_received_at_utc': {'last': stamp.isoformat()}})
    before = deepcopy(vars(sample))
    debug = {'request_id': 42, 'returned_market_data_type': 'DELAYED'}
    calls = []
    def acquire(c):
        calls.append(c)
        md.last_snapshot_debug = debug
        return sample
    monkeypatch.setattr(md, '_snapshot_stock_uncached', acquire)
    with acquisition_scope(lambda: False):
        md.snapshot_stock('ONE')
        result = md.snapshot_stock('ONE')
        assert result is sample and len(calls) == 1
        assert ('MD_STALE' in result.data_quality_flags) is stale
        assert md.last_snapshot_debug is debug
        assert {k: v for k, v in vars(result).items() if k != 'data_quality_flags'} == {
            k: v for k, v in before.items() if k != 'data_quality_flags'}
        assert 'MD_DELAYED' in result.data_quality_flags
    with acquisition_scope(lambda: False):
        md.snapshot_stock('ONE')
    assert len(calls) == 2


@pytest.mark.parametrize('stamp', [None, 'invalid', '2026-10-16T14:00:00'])
def test_cache_cannot_use_new_receipt_to_invent_market_timestamp(monkeypatch, stamp):
    md = MarketDataClient(connection_manager=NS(), allow_direct_connection=False)
    sample = NS(timestamp_source="LAST_TRADE", timestamp_utc=stamp, received_at_utc=datetime.now(timezone.utc).isoformat(),
                data_quality_flags=[])
    monkeypatch.setattr(md, '_snapshot_stock_uncached', lambda c: sample)
    with acquisition_scope(lambda: False):
        md.snapshot_stock('ONE')
        result = md.snapshot_stock('ONE')
        assert result.timestamp_utc == stamp
        assert result.data_quality_flags == ['MD_TIMESTAMP_UNKNOWN']


@pytest.mark.parametrize('gate', ['watchlist', 'focus', 'forced_premarket'])
def test_aged_context_cannot_pass_any_scanner_consumer(monkeypatch, gate):
    from src.scanner import scanner_runner as scanner
    monkeypatch.setattr(scanner, 'get_config', lambda key: 15)
    row = {'symbol': 'ONE', 'quote_timestamp_source': 'LAST_TRADE', 'quote_timestamp_utc': (datetime.now(timezone.utc)-timedelta(seconds=16)).isoformat(),
           'quote_received_at_utc': datetime.now(timezone.utc).isoformat(), 'data_quality_flags': []}
    before = row['quote_timestamp_utc']
    if gate == 'forced_premarket':
        assert not scanner._forced_premarket_focus_eligible(row, NS(), session_label='PRE')
    else:
        check = scanner._evaluate_watchlist_gates if gate == 'watchlist' else scanner._evaluate_focus_gates
        assert check(row, NS()) == 'DROP_STALE_MARKET_DATA'
    assert row['quote_timestamp_utc'] == before
    assert not row['watchlist_eligible'] and not row['focus_eligible'] and not row['execution_eligible']


def test_all_workers_stop_before_shared_join_budget_is_spent(monkeypatch):
    from src.market_data import float_discovery_worker as floats
    now = [0.0]
    calls = []
    def shutdown(name, timeout):
        calls.append((name, timeout))
        if timeout:
            now[0] += min(timeout, 2.5)
        return False
    monkeypatch.setattr(floats, 'time', NS(monotonic=lambda: now[0]))
    monkeypatch.setattr(floats, '_WORKERS', {
        ('A','db'): NS(shutdown=lambda timeout: shutdown('A', timeout)),
        ('B','db'): NS(shutdown=lambda timeout: shutdown('B', timeout))})
    assert not floats.shutdown_float_discovery_workers(timeout=3)
    assert calls == [('A',0), ('B',0), ('A',3), ('B',0.5)]
    assert now[0] == 3 and len(floats._WORKERS) == 2


def test_worker_exception_keeps_other_cleanup_and_provider_disconnect(monkeypatch):
    from src.scanner import scanner_runner as scanner
    from src.market_data import float_discovery_worker as floats
    called = []
    def failed(timeout):
        called.append('failed')
        raise RuntimeError('synthetic worker error')
    monkeypatch.setattr(floats, '_WORKERS', {
        ('A','db'): NS(shutdown=failed),
        ('B','db'): NS(shutdown=lambda timeout: called.append('other') or True)})
    monkeypatch.setattr(scanner, '_PERSISTENT_PROVIDER', NS(disconnect=lambda: called.append('disconnect')))
    with pytest.raises(RuntimeError, match='worker shutdown incomplete'):
        scanner.reset_scanner_runtime_state(suppress_disconnect_errors=False)
    assert called == ['failed', 'other', 'disconnect']
    assert set(floats._WORKERS) == {('A','db')}


def test_runtime_stop_joins_real_fixture_worker_and_prevents_late_writes(monkeypatch, tmp_path):
    from src.market_data import float_discovery_worker as floats
    worker = floats.get_float_discovery_worker(tmp_path/'float.json')
    entered, release = threading.Event(), threading.Event()
    def lookup(symbol):
        entered.set()
        assert release.wait(3)
        return 123456, 'FIXTURE'
    monkeypatch.setattr(worker._provider, 'provider_yahoo', lookup)
    monkeypatch.setattr(worker._provider, 'provider_finviz', lambda *a: pytest.fail('fallback after stop'))
    monkeypatch.setattr(worker._provider, 'record_discovery', lambda **kw: pytest.fail('late persistence'))
    worker.enqueue('ONE')
    assert entered.wait(1)
    started = time.monotonic()
    try:
        assert not floats.shutdown_float_discovery_workers(timeout=.02)
        assert time.monotonic()-started < .5
        assert len(floats._WORKERS) == 1
        with pytest.raises(RuntimeError, match='shutdown is pending'):
            floats.get_float_discovery_worker(tmp_path/'float.json')
        assert not worker.enqueue('QUEUED')
    finally:
        release.set()
    assert floats.shutdown_float_discovery_workers(timeout=1)
    assert not floats._WORKERS and not worker._thread.is_alive()
    assert worker._queue.unfinished_tasks == 0


def test_no_new_worker_can_be_created_during_registry_shutdown(monkeypatch, tmp_path):
    from src.market_data import float_discovery_worker as floats
    observed = []
    def shutdown(timeout):
        with pytest.raises(RuntimeError, match='workers are shutting down'):
            floats.get_float_discovery_worker(tmp_path/'other.json')
        observed.append(True)
        return True
    monkeypatch.setattr(floats, '_WORKERS', {('A','db'): NS(shutdown=shutdown)})
    assert floats.shutdown_float_discovery_workers()
    assert observed == [True] and not floats._WORKERS


def test_failed_runtime_worker_hook_keeps_remaining_hooks_and_mutation_proof(monkeypatch, tmp_path):
    from src.ibkr import shutdown_evidence as shutdown
    from src.market_data import float_discovery_worker as floats
    from src.core.stop_controller import StopMode
    from test_pr1090_p1_repairs import fake_orchestrator
    real_reset = shutdown.reset_scanner
    instance, called = fake_orchestrator(monkeypatch)
    def reset():
        called.append('scanner_reset')
        real_reset()
    monkeypatch.setattr(shutdown, 'reset_scanner', reset)
    monkeypatch.setattr(floats, '_WORKERS', {('A','db'): NS(shutdown=lambda timeout: False)})
    monkeypatch.setenv('PR1090_EVIDENCE_DIR', str(tmp_path))
    instance._shutdown(StopMode.GRACEFUL)
    proof = json.loads((tmp_path/'shutdown_evidence.json').read_text())
    assert called == list(shutdown.REQUIRED_HOOKS)
    assert next(row for row in proof['hooks'] if row['hook']=='scanner_reset')['completed'] is False
    assert proof['mutation_attempts'] == {'place':0, 'modify':0, 'cancel':0}
    assert proof['events'][-1]['event'] == 'TERMINAL_FLUSHED'


def test_blocked_constructor_cannot_hold_shutdown_lock_or_start_after_stop(monkeypatch, tmp_path):
    from src.market_data import float_discovery_worker as floats
    entered, release = threading.Event(), threading.Event()
    original = floats.FloatDiscoveryWorker.__init__
    started = []
    failures = []
    def constructor(self, *args, **kwargs):
        entered.set()
        assert release.wait(3)
        original(self, *args, **kwargs)
    monkeypatch.setattr(floats.FloatDiscoveryWorker, '__init__', constructor)
    monkeypatch.setattr(floats.FloatDiscoveryWorker, 'ensure_started', lambda self: started.append(self))
    def acquire():
        try:
            floats.get_float_discovery_worker(tmp_path/'float.json')
        except RuntimeError as exc:
            failures.append(str(exc))
    owner = threading.Thread(target=acquire)
    owner.start()
    assert entered.wait(1)
    before = time.monotonic()
    try:
        assert not floats.shutdown_float_discovery_workers(timeout=.02)
        assert time.monotonic()-before < .5
        assert floats._WORKER_BUILDERS  # Pending initialization is not clean.
        with pytest.raises(RuntimeError, match='shutdown is pending'):
            floats.get_float_discovery_worker(tmp_path/'other.json')
    finally:
        release.set()
        owner.join(timeout=2)
    assert not owner.is_alive() and failures
    assert not started and not floats._WORKERS and not floats._WORKER_BUILDERS
    assert floats.shutdown_float_discovery_workers(timeout=0)
