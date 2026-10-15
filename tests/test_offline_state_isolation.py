"""Real allocator/persistence and owned workers; transports are always fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.market_data import float_discovery_worker as workers
from src.market_data.float_provider import FloatProvider


def client():
    return IbkrClient('offline', 0, 123, 1, 'LIVE', True)


def test_default_fixture_is_fresh_even_after_another_test_persists():
    path = Path(os.environ['IBKR_ORDER_ID_STATE_PATH'])
    assert not path.exists()
    c = client()
    assert c._last_reserved_order_id is None
    assert c._next_req_id() == 1


def test_persisted_361_rebases_requests_and_restart_without_reset():
    path = Path(os.environ['IBKR_ORDER_ID_STATE_PATH'])
    path.write_text(json.dumps({'last_reserved_order_id': 361}))
    c = client()
    assert c._next_req_id() == 362
    c.nextValidId(1)  # synthetic broker callback; never connect or submit
    assert c.reserve_order_id() == 363
    restarted = client()
    assert restarted._next_req_id() == 364
    restarted.nextValidId(1)
    assert restarted.reserve_order_id() == 365
    assert json.loads(path.read_text()) == {'last_reserved_order_id': 365}


def test_environment_path_precedes_home_default(monkeypatch, tmp_path):
    home = tmp_path / 'fake-home'
    home.mkdir()
    home_state = home / '.ibkr_order_id_state.json'
    home_state.write_text('{"last_reserved_order_id":361}')
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    monkeypatch.delenv('IBKR_ORDER_ID_STATE_PATH')
    assert client()._next_req_id() == 362
    configured = tmp_path / 'configured.json'
    configured.write_text('{"last_reserved_order_id":900}')
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(configured))
    assert client()._next_req_id() == 901
    assert home_state.read_text() == '{"last_reserved_order_id":361}'


@pytest.mark.parametrize('reverse', [False, True])
def test_six_cases_ignore_inherited_state_and_prior_allocator_tests(tmp_path, reverse):
    root = Path(__file__).resolve().parents[1]
    operator = tmp_path / 'operator.json'
    operator.write_text('{"last_reserved_order_id":361}')
    env = dict(os.environ, IBKR_ORDER_ID_STATE_PATH=str(operator))
    env['PYTHONPATH'] = os.pathsep.join([str(root / 'tests/offline'), str(root)])
    nodes = [
        'tests/test_ibkr_client_order_id_authority.py::test_next_valid_id_rebases_from_persisted_local_last',
        'tests/test_ibkr_reference_names.py::test_old_and_post_completion_order_errors_do_not_poison_name',
        'tests/test_post_pr1090_market_data_authority.py::test_native_callback_type_and_completed_fields_are_retained',
        'tests/test_offline_state_isolation.py::test_default_fixture_is_fresh_even_after_another_test_persists',
    ]
    if reverse:
        nodes.reverse()
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', *nodes], cwd=root,
                            env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '8 passed' in result.stdout
    assert operator.read_text() == '{"last_reserved_order_id":361}'


def test_fixture_cache_read_does_not_call_discovery(monkeypatch, tmp_path):
    provider = FloatProvider(cache_path=tmp_path / 'fixture.json', sqlite_path=str(tmp_path / 'fixture.db'))
    provider.record_discovery('FIXTURE', 123456, 'FIXTURE')
    monkeypatch.setattr(provider, 'provider_yahoo', lambda *a: pytest.fail('unexpected acquisition'))
    monkeypatch.setattr(provider, 'provider_finviz', lambda *a: pytest.fail('unexpected acquisition'))
    assert provider.get_float('FIXTURE') == (123456, 'FIXTURE')
    assert provider.last_cache_used


def test_background_fixture_write_and_shutdown_survive_registry_replacement(monkeypatch, tmp_path):
    worker = workers.FloatDiscoveryWorker(tmp_path / 'fixture.json', sqlite_path=str(tmp_path / 'fixture.db'))
    wrote = threading.Event()
    original = worker._provider.record_discovery
    def record(**kwargs):
        original(**kwargs)
        wrote.set()
    monkeypatch.setattr(worker._provider, 'record_discovery', record)
    monkeypatch.setattr(worker._provider, 'provider_yahoo', lambda symbol: (123456, 'FIXTURE'))
    monkeypatch.setattr(worker._provider, 'provider_finviz', lambda *a: pytest.fail('unexpected fallback'))
    worker.ensure_started()
    worker.enqueue('FIXTURE')
    assert wrote.wait(3)
    assert json.loads((tmp_path / 'fixture.json').read_text())['FIXTURE']['float'] == 123456
    monkeypatch.setattr(workers, '_WORKERS', {})
    # Deliberately leave it idle: the autouse fixture must find this constructed
    # object and stop/join it before provider monkeypatches are undone.


def test_previous_worker_did_not_escape_test_scope():
    assert not [t for t in threading.enumerate() if t.name == 'float-discovery-worker']


def test_stop_during_fixture_lookup_prevents_fallback_and_late_write(monkeypatch, tmp_path):
    worker = workers.FloatDiscoveryWorker(tmp_path / 'float.json', sqlite_path=str(tmp_path / 'fund.db'))
    entered, release = threading.Event(), threading.Event()
    def lookup(symbol):
        entered.set()
        assert release.wait(3)
        return 123456, 'FIXTURE'
    monkeypatch.setattr(worker._provider, 'provider_yahoo', lookup)
    monkeypatch.setattr(worker._provider, 'provider_finviz', lambda *a: pytest.fail('fallback after stop'))
    monkeypatch.setattr(worker._provider, 'record_discovery', lambda **kw: pytest.fail('write after stop'))
    worker.ensure_started()
    worker.enqueue('FIRST')
    assert entered.wait(3)
    worker.enqueue('QUEUED')
    try:
        assert not worker.shutdown(timeout=0)  # in-flight work is not hidden
    finally:
        release.set()
    assert worker.shutdown(timeout=3)
    assert worker._queue.unfinished_tasks == 0
    assert not worker._thread.is_alive()
    assert not worker.enqueue('LATE')


def test_repeated_shutdown_sends_only_one_wakeup(monkeypatch, tmp_path):
    worker = workers.FloatDiscoveryWorker(tmp_path / 'float.json', sqlite_path=str(tmp_path / 'fund.db'))
    received, release = threading.Event(), threading.Event()
    original = worker._queue.get
    def get(*args, **kwargs):
        item = original(*args, **kwargs)
        if item is None:
            received.set()
            assert release.wait(3)
        return item
    monkeypatch.setattr(worker._queue, 'get', get)
    worker.ensure_started()
    try:
        assert not worker.shutdown(timeout=0)
        assert received.wait(3)  # the sentinel was consumed, but exit is paused
        assert not worker.shutdown(timeout=0)
        assert not worker.shutdown(timeout=0)
    finally:
        release.set()
    assert worker.shutdown(timeout=3)
    assert worker._queue.unfinished_tasks == 0 and worker._queue.empty()
    worker.ensure_started()
    assert not worker._thread.is_alive() and not worker.enqueue('LATE')
