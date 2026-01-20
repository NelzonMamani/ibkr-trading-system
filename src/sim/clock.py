from __future__ import annotations

from datetime import datetime, timezone


class SimClock:
    """
    Deterministic simulation clock.
    Advances exactly one tick per orchestrator cycle.
    """

    def __init__(self, start_tick: int = 0):
        self._tick = start_tick

    def tick(self) -> int:
        self._tick += 1
        print(f"[CLOCK] tick={self._tick}")
        return self._tick

    def now(self) -> int:
        return self._tick


class RealClock:
    """
    Real-time clock for LIVE/LIVE_MICRO modes.

    Uses timezone-aware UTC timestamps to avoid deterministic ticks.
    """

    def __init__(self) -> None:
        self._last_tick: int | None = None

    def tick(self) -> int:
        now_tick = int(datetime.now(timezone.utc).timestamp())
        self._last_tick = now_tick
        print(f"[CLOCK] tick={now_tick}")
        return now_tick

    def now(self) -> int:
        if self._last_tick is None:
            self._last_tick = int(datetime.now(timezone.utc).timestamp())
        return self._last_tick
