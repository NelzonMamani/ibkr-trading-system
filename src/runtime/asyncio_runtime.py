from __future__ import annotations

import asyncio


def ensure_event_loop_for_thread() -> asyncio.AbstractEventLoop:
    """Ensure the current thread has an asyncio event loop.

    Python 3.14 no longer guarantees implicit loop creation for
    ``asyncio.get_event_loop()`` in threads without a loop.
    """

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

