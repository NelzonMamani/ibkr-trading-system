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
        print("[EVENT_COLLECTOR] Snapshotting events")
        return list(self._events)

    def count(self):
        return len(self._events)

    def filter_by_type(self, event_type: str):
        print(
            f"[EVENT_COLLECTOR] Filtering events — type={event_type}"
        )
        return [
            e for e in self._events
            if e.event_type == event_type
        ]

    def filter_by_source(self, source: str):
        print(
            f"[EVENT_COLLECTOR] Filtering events — source={source}"
        )
        return [
            e for e in self._events
            if e.source == source
        ]
