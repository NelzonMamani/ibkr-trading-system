from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

from src.config.runtime_config import get_persistence_sqlite_path
from src.market_data.float_provider import FloatProvider


@dataclass(frozen=True)
class FloatDiscoveryResult:
    symbol: str
    value: Optional[int]
    source: str
    cache_used: bool = False
    fallback_used: bool = False
    failures: tuple[tuple[str, str], ...] = ()


class FloatDiscoveryWorker:
    """Background float discovery queue that never blocks scanner cycles."""

    def __init__(self, cache_path: str | Path, ttl_days: int = 7, sqlite_path: str | None = None) -> None:
        self._cache_path = Path(cache_path)
        self._provider = FloatProvider(cache_path=self._cache_path, ttl_days=ttl_days, sqlite_path=sqlite_path)
        self._queue: Queue[str | None] = Queue()
        self._queued: set[str] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def ensure_started(self) -> None:
        with self._lock:
            if self._stop.is_set() or (self._thread is not None and self._thread.is_alive()):
                return
            self._thread = threading.Thread(target=self._worker_loop, name="float-discovery-worker", daemon=True)
            self._thread.start()

    def shutdown(self, timeout: float = 3) -> bool:
        """Cancel queued work and join owned work; never hide a surviving thread."""
        with self._lock:
            first_stop = not self._stop.is_set()
            self._stop.set()
            thread = self._thread
            if first_stop:
                while True:
                    try:
                        symbol = self._queue.get_nowait()
                    except Empty:
                        break
                    self._queued.discard(symbol)
                    self._queue.task_done()
                if thread is not None and thread.is_alive():
                    self._queue.put(None)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0, timeout))
        return thread is None or not thread.is_alive()

    def enqueue(self, symbol: str) -> bool:
        normalized = str(symbol or "").upper().strip()
        if not normalized:
            return False
        with self._lock:
            if self._stop.is_set() or normalized in self._queued:
                return False
            self._queued.add(normalized)
            self._queue.put(normalized)
            return True

    def discover_now(self, symbol: str) -> FloatDiscoveryResult:
        """Bounded foreground lookup used by READ_ONLY scanner proof cycles."""
        normalized = str(symbol or "").upper().strip()
        if not normalized:
            return FloatDiscoveryResult(symbol="", value=None, source="UNKNOWN")
        value, source = self._provider.get_float(normalized)
        return FloatDiscoveryResult(
            symbol=normalized,
            value=int(value) if value is not None and value > 0 else None,
            source=str(source or "UNKNOWN"),
            cache_used=bool(getattr(self._provider, "last_cache_used", False)),
            fallback_used=bool(getattr(self._provider, "last_fallback_used", False)),
            failures=tuple(getattr(self._provider, "last_float_failures", []) or ()),
        )

    def _worker_loop(self) -> None:
        while True:
            try:
                symbol = self._queue.get(timeout=1.0)
            except Empty:
                continue

            try:
                if symbol is None:
                    return
                if not self._stop.is_set():
                    self._discover_and_cache(symbol)
            finally:
                with self._lock:
                    self._queued.discard(symbol)
                self._queue.task_done()

    def _discover_and_cache(self, symbol: str) -> None:
        for provider_name, provider_fn in (
            ("YAHOO", self._provider.provider_yahoo),
            ("FINVIZ", self._provider.provider_finviz),
        ):
            if self._stop.is_set():
                return
            value, reason = provider_fn(symbol)
            if self._stop.is_set():
                return
            if value is not None and value > 0:
                self._provider.record_discovery(symbol=symbol, value=int(value), source=provider_name)
                print(
                    "[FLOAT][DISCOVERY_WORKER] "
                    f"symbol={symbol} provider={provider_name} result=SUCCESS value={int(value)}"
                )
                return
            print(
                "[FLOAT][DISCOVERY_WORKER] "
                f"symbol={symbol} provider={provider_name} result=FAIL reason={reason or 'UNKNOWN'}"
            )


_WORKERS: dict[tuple[str, str], FloatDiscoveryWorker] = {}
_WORKERS_LOCK = threading.RLock()
_WORKERS_CHANGED = threading.Condition(_WORKERS_LOCK)
_WORKERS_SHUTTING_DOWN = False
_WORKERS_GENERATION = 0
_WORKER_BUILDERS: dict[object, int] = {}


def shutdown_float_discovery_workers(timeout: float = 3) -> bool:
    """Retire owned runtime workers within one shared join budget.

    Keep surviving workers registered so incomplete cleanup remains observable.
    """
    global _WORKERS_SHUTTING_DOWN, _WORKERS_GENERATION
    deadline = time.monotonic() + max(0, timeout)
    with _WORKERS_LOCK:
        if _WORKERS_SHUTTING_DOWN:
            return False  # Another owner is still completing cleanup.
        _WORKERS_SHUTTING_DOWN = True
        _WORKERS_GENERATION += 1  # In-flight constructors cannot start later.
        owned = tuple(_WORKERS.items())
    retired = set()
    failed = set()
    try:
        # Signal ALL owners before spending the shared budget waiting on any
        # one of them. One failed worker must not suppress the others' cleanup.
        for key, worker in owned:
            try:
                if worker.shutdown(timeout=0):
                    retired.add(key)
            except Exception as exc:
                failed.add(key)
                print(f"[FLOAT][SHUTDOWN] completed=False error_type={type(exc).__name__}")
        for key, worker in owned:
            if key in retired or key in failed:
                continue
            try:
                if worker.shutdown(timeout=max(0, deadline - time.monotonic())):
                    retired.add(key)
            except Exception as exc:
                print(f"[FLOAT][SHUTDOWN] completed=False error_type={type(exc).__name__}")
        with _WORKERS_CHANGED:
            while _WORKER_BUILDERS:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                _WORKERS_CHANGED.wait(timeout=remaining)
            builders_done = not _WORKER_BUILDERS
        return len(retired) == len(owned) and builders_done
    finally:
        with _WORKERS_LOCK:
            for key, worker in owned:
                if key in retired and _WORKERS.get(key) is worker:
                    _WORKERS.pop(key)
            _WORKERS_SHUTTING_DOWN = False


def get_float_discovery_worker(cache_path: str | Path) -> FloatDiscoveryWorker:
    cache_path = Path(cache_path).resolve()
    sqlite_path = str(Path(get_persistence_sqlite_path()).resolve())
    resolved = (str(cache_path), sqlite_path)
    with _WORKERS_LOCK:
        if _WORKERS_SHUTTING_DOWN:
            raise RuntimeError("Float discovery workers are shutting down")
        if any(generation != _WORKERS_GENERATION for generation in _WORKER_BUILDERS.values()):
            raise RuntimeError("Float discovery worker shutdown is pending")
        worker = _WORKERS.get(resolved)
        if worker is not None:
            if worker._stop.is_set():
                raise RuntimeError("Float discovery worker shutdown is pending")
            worker.ensure_started()
            return worker
        generation = _WORKERS_GENERATION
        token = object()
        _WORKER_BUILDERS[token] = generation
    candidate = None
    try:
        # SQLite/cache initialization can block. Never hold the ownership lock
        # across it: shutdown must be able to signal other workers immediately.
        candidate = FloatDiscoveryWorker(cache_path=cache_path, sqlite_path=sqlite_path)
        with _WORKERS_LOCK:
            if _WORKERS_SHUTTING_DOWN or generation != _WORKERS_GENERATION:
                raise RuntimeError("Float discovery workers are shutting down")
            worker = _WORKERS.get(resolved)
            if worker is None:
                worker = candidate
                _WORKERS[resolved] = worker
            if worker._stop.is_set():
                raise RuntimeError("Float discovery worker shutdown is pending")
            worker.ensure_started()
            return worker
    finally:
        # A lost concurrent constructor or stale generation never owns a thread.
        try:
            with _WORKERS_LOCK:
                owns_candidate = candidate is _WORKERS.get(resolved)
            if candidate is not None and not owns_candidate:
                candidate.shutdown(timeout=0)
        finally:
            with _WORKERS_CHANGED:
                _WORKER_BUILDERS.pop(token, None)
                _WORKERS_CHANGED.notify_all()
