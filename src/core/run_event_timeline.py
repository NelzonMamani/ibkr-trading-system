class RunEventTimeline:
    """
    Aggregates all SystemEvents across the entire runtime.
    Teaching-first, in-memory only.
    """

    def __init__(self):
        self._events = []

    def record(self, event):
        self._events.append(event)

    def snapshot(self):
        return list(self._events)

    def count(self) -> int:
        return len(self._events)
