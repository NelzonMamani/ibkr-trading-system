"""
PY314_RUNTIME_RESTORATION

Ensure a valid asyncio event loop exists at import time
for Python 3.14+ where get_event_loop() no longer auto-creates.

This must execute before any ib_insync or eventkit import.
"""

from __future__ import annotations

import asyncio


def ensure_event_loop() -> None:
    """
    Guarantee that a usable asyncio event loop exists
    in the current thread.
    """
    try:
        asyncio.get_running_loop()
        return
    except RuntimeError:
        pass

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


# EXECUTE IMMEDIATELY ON IMPORT
ensure_event_loop()
