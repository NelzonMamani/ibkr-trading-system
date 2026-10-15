from __future__ import annotations

import asyncio
import pytest


@pytest.fixture(autouse=True)
def _force_test_execution_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_ENV", "TEST")


@pytest.fixture(scope="session", autouse=True)
def _session_event_loop_bootstrap():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def _isolate_process_mutation_evidence(monkeypatch):
    # Each test models an independent runtime; production counters have no reset API.
    import weakref
    from src.ibkr import mutation_audit
    monkeypatch.setattr(mutation_audit, "_counts", {"place": 0, "modify": 0, "cancel": 0})
    monkeypatch.setattr(mutation_audit, "_seen", weakref.WeakKeyDictionary())


@pytest.fixture(autouse=True)
def _isolate_allocator_persistence(monkeypatch, tmp_path):
    # A new client is not a fresh allocator when it reads the operator's saved
    # order high-water mark. Tests may explicitly override this private path to
    # exercise restart/rebase behavior, but never read/write the operator file.
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path / 'order-state.json'))


@pytest.fixture(autouse=True)
def _isolate_float_workers(monkeypatch, tmp_path):
    from src.market_data import float_discovery_worker as workers
    monkeypatch.setenv('SCANNER_FLOAT_CACHE_FILE', str(tmp_path / 'float.json'))
    monkeypatch.setenv('PERSISTENCE_SQLITE_PATH', str(tmp_path / 'fundamentals.sqlite3'))
    monkeypatch.setattr(workers, '_WORKERS', {})
    created = []
    original = workers.FloatDiscoveryWorker.__init__

    def tracked(self, *args, **kwargs):
        original(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(workers.FloatDiscoveryWorker, '__init__', tracked)
    yield
    # Track objects, not just the registry: individual tests can replace it.
    # This finalizer runs before monkeypatch restores provider fixtures.
    escaped = [worker for worker in created if not worker.shutdown(timeout=3)]
    assert not escaped, 'Float discovery worker survived test teardown'
