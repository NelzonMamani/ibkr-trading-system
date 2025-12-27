class EventCollector:
    """
    In-memory collector for SystemEvents.
    Teaching-first, synchronous, deterministic.
    """

    def __init__(self):
        self._events = []

    def record(self, event):
        print(f"[EVENT_COLLECTOR] Recording event: {event.event_type}")
        self._events.append(event)

    def snapshot(self):
        return list(self._events)

    def count(self):
        return len(self._events)
