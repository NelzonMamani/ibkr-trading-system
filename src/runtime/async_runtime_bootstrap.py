from __future__ import annotations

import asyncio
from typing import Any, Tuple


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Ensure the current thread has an event loop and return it."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass

    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def install_runtime_policy() -> None:
    """Install runtime policy hooks required before async broker imports."""
    ensure_event_loop()


def safe_import_ib_insync() -> Tuple[Any, Any, Any]:
    """Safely import commonly used ib_insync symbols after runtime bootstrap."""
    install_runtime_policy()
    from ib_insync import IB, ScannerSubscription, Stock

    return IB, Stock, ScannerSubscription
