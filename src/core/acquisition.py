"""Cooperative cancellation for acquisition on the owning runtime thread.

Cancellation is control flow, not provider failure: broad data-error handlers
must not convert it to missing data or start fallback requests. Shutdown runs
outside this scope so stop requests cannot interrupt required finalizers.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
import os
import time


class AcquisitionCancelled(BaseException):
    pass


_state = ContextVar("acquisition_state", default=None)


def checkpoint():
    state = _state.get()
    if state is not None and state["stop"]():
        raise AcquisitionCancelled()


def _file_stop():
    path = os.environ.get("PR1090_STOP_FILE")
    return bool(path and Path(path).is_file())


@contextmanager
def acquisition_scope(stop=None):
    parent = _state.get()
    token = _state.set({"stop": stop or (parent["stop"] if parent else _file_stop), "cache": {}})
    try:
        checkpoint()
        yield
        checkpoint()
    finally:
        _state.reset(token)


def acquisition_cycle(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with acquisition_scope():
            return function(*args, **kwargs)
    return wrapped


def cycle_cache():
    state = _state.get()
    return state["cache"] if state is not None else None


def wait_event(event, timeout):
    deadline = time.monotonic() + max(0, timeout)
    while True:
        checkpoint()
        remaining = deadline - time.monotonic()
        if event.wait(min(0.1, max(0, remaining))):
            checkpoint()
            return True
        if remaining <= 0:
            return False


def contract_key(contract):
    if isinstance(contract, str):
        return ("symbol", contract.upper())
    return tuple(getattr(contract, field, None) for field in (
        "conId", "symbol", "secType", "exchange", "primaryExchange",
        "currency", "localSymbol", "tradingClass"))


async def cooperative_await(awaitable):
    """Keep async transports on their event loop; never abandon worker threads."""
    import asyncio
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            checkpoint()
            await asyncio.wait({task}, timeout=0.1)
        checkpoint()
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
