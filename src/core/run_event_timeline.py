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

    def filter_by_type(self, event_type: str):
        return [
            event
            for event in self._events
            if event.event_type == event_type
        ]

    def filter_by_source(self, source: str):
        return [
            event
            for event in self._events
            if event.source == source
        ]

    def filter_by_symbol(self, symbol: str):
        return [
            event
            for event in self._events
            if getattr(event, "symbol", None) == symbol
        ]
