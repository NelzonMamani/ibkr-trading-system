"""
System-level configuration (logging, replay, persistence).
"""

from __future__ import annotations
import os
from enum import Enum
from datetime import datetime, time
from .runtime_config import RunMode


class EventReplayMode(str, Enum):
    OFF = "OFF"
    CYCLE = "CYCLE"
    RUN = "RUN"


DEFAULT_EVENT_REPLAY_MODE: EventReplayMode = EventReplayMode.CYCLE


def get_event_replay_mode(run_mode: RunMode) -> EventReplayMode:
    """
    Resolve replay mode safely.

    RULES:
    - LIVE always forces OFF
    - SIM / PAPER allow ENV override
    """
    if run_mode == RunMode.LIVE:
        return EventReplayMode.OFF

    raw = (os.getenv("EVENT_REPLAY_MODE") or "").strip().upper()
    if not raw:
        return DEFAULT_EVENT_REPLAY_MODE

    try:
        return EventReplayMode(raw)
    except ValueError:
        print(
            f"[SYSTEM] Invalid EVENT_REPLAY_MODE='{raw}'. "
            f"Falling back to default {DEFAULT_EVENT_REPLAY_MODE}."
        )
        return DEFAULT_EVENT_REPLAY_MODE


# Sleep interval (in seconds) between orchestrator cycles. Kept short for
# demonstration while remaining safe to run locally.
CYCLE_SLEEP_SECONDS: int = 3

# Market sessions considered "open" for educational checks. The orchestrator
# does not yet act on these, but they show how we might gate behaviour.
ACTIVE_SESSIONS = ["PRE", "REGULAR", "AFTER"]


def get_current_market_session() -> str:
    """Return a simple market session indicator based on local time.

    This teaching helper uses broad time windows to map to common US equity
    sessions:
    - PRE:    04:00 - 09:30 local
    - REGULAR:09:30 - 16:00 local
    - AFTER:  16:00 - 20:00 local
    - CLOSED: all other times
    """

    now = datetime.now().time()

    pre_start = time(4, 0)
    regular_start = time(9, 30)
    regular_end = time(16, 0)
    after_end = time(20, 0)

    if pre_start <= now < regular_start:
        return "PRE"
    if regular_start <= now < regular_end:
        return "REGULAR"
    if regular_end <= now < after_end:
        return "AFTER"
    return "CLOSED"
