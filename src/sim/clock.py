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


class WallClock:
    """
    Real-time clock for live/paper execution cycles.

    Provides a monotonically increasing millisecond tick based on wall time.
    """

    def __init__(self) -> None:
        self._last_tick = 0

    def tick(self) -> int:
        import time

        now_ms = int(time.time() * 1000)
        if now_ms <= self._last_tick:
            now_ms = self._last_tick + 1
        self._last_tick = now_ms
        print(f"[CLOCK] tick={self._last_tick}")
        return self._last_tick

    def now(self) -> int:
        return self._last_tick
