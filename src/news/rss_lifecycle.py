"""Opt-in observation and bounded cleanup for one canonical RSS lookup.

Retrieval outcomes remain immutable. Completing a worker during cleanup never
adds its articles to the result that the deadline-bounded fetcher returned.
"""
from __future__ import annotations

from concurrent.futures import wait
from contextlib import contextmanager
import math
import threading
import time
from typing import Any, Iterator


_source_context = threading.local()


def current_source_timing() -> dict[str, Any] | None:
    return getattr(_source_context, "timing", None)


@contextmanager
def capture_source_timing(enabled: bool) -> Iterator[dict[str, Any]]:
    previous = current_source_timing()
    timing: dict[str, Any] = {}
    _source_context.timing = timing if enabled else None
    try:
        yield timing
    finally:
        _source_context.timing = previous


class RssFetchLifecycle:
    """Tracks only the futures and executors belonging to this lookup.

    completed_count counts completed calls, not stopped pool threads. Only
    cleanup_complete=True proves all observed futures and pool workers ended.
    None means executor thread state is unavailable. Response closure is reported
    independently per source; injected transports have unknown phase/close facts.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sources: list[dict[str, Any]] = []
        self._futures: dict[int, Any] = {}
        self._executors: list[Any] = []
        self._cleanup_elapsed_seconds = 0.0

    def register_executor(self, executor: Any) -> None:
        with self._lock:
            self._executors.append(executor)

    def source_submitted(self, source_id: str, source_tier: str, submitted_at_s: float) -> int:
        with self._lock:
            index = len(self._sources)
            self._sources.append({
                "source_id": source_id, "source_tier": source_tier,
                "submitted_at_s": submitted_at_s, "started_at_s": None,
                "completed_at_s": None, "worker_completed_at_s": None,
                "cleanup_completed_at_s": None,
                "request_elapsed_seconds": None, "parse_elapsed_seconds": None,
                "http_status": None, "response_closed": None,
                "feed_item_count": None, "elapsed_seconds": None,
                "failure_reason": None, "cleanup_error": None,
                "cancellation_requested": False, "cancellation_succeeded": None,
            })
            return index

    def register_future(self, index: int, future: Any) -> None:
        with self._lock:
            self._futures[index] = future

    def source_started(self, index: int, started_at_s: float) -> None:
        with self._lock:
            self._sources[index]["started_at_s"] = started_at_s

    def source_completed(self, index: int, observation: dict[str, Any]) -> None:
        with self._lock:
            self._sources[index].update(observation)
            self._sources[index]["worker_completed_at_s"] = time.monotonic()

    def source_cleanup_completed(self, index: int, observation: dict[str, Any]) -> None:
        with self._lock:
            self._sources[index].update(observation)
            self._sources[index]["cleanup_completed_at_s"] = time.monotonic()

    def cancellation_requested(self, index: int, succeeded: bool) -> None:
        with self._lock:
            self._sources[index].update(cancellation_requested=True, cancellation_succeeded=bool(succeeded))

    def _state(self) -> tuple[list[dict[str, Any]], dict[int, Any], list[Any]]:
        with self._lock:
            return [dict(row) for row in self._sources], dict(self._futures), list(self._executors)

    @staticmethod
    def _workers(executors: list[Any]) -> tuple[list[threading.Thread], bool]:
        workers: set[threading.Thread] = set()
        observable = True
        for executor in executors:
            # CPython ThreadPoolExecutor exposes its owned threads here. This is
            # observation only: no global thread enumeration or executor rewrite.
            threads = getattr(executor, "_threads", None)
            if threads is None:
                observable = False
            else:
                try:
                    workers.update(tuple(threads))
                except RuntimeError:
                    observable = False  # A concurrent submit changed the pool snapshot.
        return list(workers), observable

    def snapshot(self) -> dict[str, Any]:
        sources, futures, executors = self._state()
        completed = cancelled = unfinished = running = 0
        for index, row in enumerate(sources):
            future = futures.get(index)
            if future is not None and future.cancelled():
                row["state"] = "cancelled"
                cancelled += 1
            elif future is not None and future.done():
                row["state"] = "completed"
                completed += 1
            else:
                row["state"] = "running" if future is not None and future.running() else "pending"
                unfinished += 1
                running += row["state"] == "running"
        workers, observable = self._workers(executors)
        alive = sum(worker.is_alive() for worker in workers)
        response_cleanup_failures = sum(row["response_closed"] is False for row in sources)
        return {
            "submitted_count": len(sources), "completed_count": completed,
            "cancelled_count": cancelled, "unfinished_count": unfinished,
            "running_count": running,
            "cancellation_requested_count": sum(row["cancellation_requested"] for row in sources),
            "cancellation_succeeded_count": sum(row["cancellation_succeeded"] is True for row in sources),
            "worker_count": len(workers) if observable else None,
            "alive_worker_count": alive if observable else None,
            "cleanup_complete": (unfinished == 0 and alive == 0 and response_cleanup_failures == 0) if observable else None,
            "response_cleanup_failures_count": response_cleanup_failures,
            "cleanup_elapsed_seconds": self._cleanup_elapsed_seconds,
            "sources": sources,
        }

    def wait_for_cleanup(self, timeout_seconds: float) -> dict[str, Any]:
        timeout = float(timeout_seconds)
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("cleanup timeout must be finite and non-negative")
        started = time.monotonic()
        deadline = started + timeout
        _, futures, executors = self._state()
        pending = [future for future in futures.values() if not future.done()]
        if pending and timeout > 0:
            wait(pending, timeout=timeout)
        workers, _ = self._workers(executors)
        for worker in workers:
            remaining = max(0.0, deadline - time.monotonic())
            if worker is not threading.current_thread() and worker.is_alive() and remaining > 0:
                worker.join(timeout=remaining)
        with self._lock:
            self._cleanup_elapsed_seconds += max(0.0, time.monotonic() - started)
        return self.snapshot()
