from datetime import datetime
from typing import Optional


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

    def count_by_type(self) -> dict[str, int]:
        counts = {}
        for event in self._events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return counts

    def count_by_source(self) -> dict[str, int]:
        counts = {}
        for event in self._events:
            counts[event.source] = counts.get(event.source, 0) + 1
        return counts

    def summary(self) -> dict:
        return {
            "total": self.count(),
            "by_type": self.count_by_type(),
            "by_source": self.count_by_source(),
        }

    def serialize_event(self, event) -> dict:
        return {
            "event_type": event.event_type,
            "source": event.source,
            "payload": event.payload,
            "timestamp": event.timestamp.isoformat(),
        }

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

    def events_after(self, timestamp: datetime) -> list:
        return [
            event for event in self._events
            if event.timestamp >= timestamp
        ]

    def events_before(self, timestamp: datetime) -> list:
        return [
            event for event in self._events
            if event.timestamp <= timestamp
        ]

    def events_between(self, start: datetime, end: datetime) -> list:
        return [
            event for event in self._events
            if start <= event.timestamp <= end
        ]

    def serialize_filtered(self, events) -> list[dict]:
        return [
            self.serialize_event(event)
            for event in events
        ]

    def serialize_all(self) -> list[dict]:
        return self.serialize_filtered(self._events)

    def get_latest_cycle_start_index(self) -> Optional[int]:
        for index in range(len(self._events) - 1, -1, -1):
            if self._events[index].event_type == "CYCLE_START":
                return index
        return None

    def get_latest_cycle_events(self) -> list:
        latest_cycle_start_index = self.get_latest_cycle_start_index()
        if latest_cycle_start_index is None:
            return []
        return self._events[latest_cycle_start_index:]

    def validate_snapshot(self, snapshot: dict) -> None:
        """
        Validate the structural integrity of an exported event snapshot.

        Raises ValueError if the snapshot is invalid.
        """

        if not isinstance(snapshot, dict):
            raise ValueError("Snapshot must be a dictionary")

        required_keys = {"scope", "event_count", "events"}
        if not required_keys.issubset(snapshot.keys()):
            raise ValueError("Snapshot missing required keys")

        if snapshot["scope"] not in {"CYCLE", "RUN"}:
            raise ValueError("Snapshot scope must be 'CYCLE' or 'RUN'")

        events = snapshot["events"]
        if not isinstance(events, list):
            raise ValueError("Snapshot events must be a list")

        if snapshot["event_count"] != len(events):
            raise ValueError("Snapshot event_count does not match events length")

    def export_latest_cycle_snapshot(self) -> dict:
        events = self.get_latest_cycle_events()

        return {
            "scope": "CYCLE",
            "event_count": len(events),
            "events": self.serialize_filtered(events),
        }

    def export_run_snapshot(self) -> dict:
        events = self.snapshot()

        return {
            "scope": "RUN",
            "event_count": len(events),
            "events": self.serialize_filtered(events),
        }
