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

    def count(self, event_type: str = None):
        if event_type is None:
            return len(self._events)
        return len([
            e for e in self._events
            if e.event_type == event_type
        ])

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

    def sum_realised_pnl(self) -> float:
        realised_pnl = 0.0
        for event in self._events:
            if event.event_type != "TRADE_CLOSED":
                continue
            payload = event.payload or {}
            realised_pnl += payload.get("realised_pnl", 0.0)
        return round(realised_pnl, 2)
