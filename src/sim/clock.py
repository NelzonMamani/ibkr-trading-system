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
