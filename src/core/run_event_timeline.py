from datetime import datetime
from typing import Optional
import json
import hashlib

from src.core.events import SystemEvent
from src.storage.sqlite_store import SQLiteStore


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

    def _checksum_payload(self, snapshot: dict) -> str:
        """
        Build a deterministic JSON string for checksum generation.

        Only the snapshot's meaningful data is included in the checksum so
        verification is stable even after adding metadata fields like the
        checksum itself.
        """

        checksum_payload = {
            "scope": snapshot["scope"],
            "event_count": snapshot["event_count"],
            "events": snapshot["events"],
        }

        return json.dumps(
            checksum_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def generate_checksum(self, snapshot: dict) -> str:
        """
        Create a deterministic checksum for the provided snapshot.
        """

        payload = self._checksum_payload(snapshot)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

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

        required_keys = {"scope", "event_count", "events", "checksum"}
        if not required_keys.issubset(snapshot.keys()):
            raise ValueError("Snapshot missing required keys")

        if snapshot["scope"] not in {"CYCLE", "RUN"}:
            raise ValueError("Snapshot scope must be 'CYCLE' or 'RUN'")

        events = snapshot["events"]
        if not isinstance(events, list):
            raise ValueError("Snapshot events must be a list")

        if snapshot["event_count"] != len(events):
            raise ValueError("Snapshot event_count does not match events length")

        expected_checksum = self.generate_checksum(snapshot)
        if snapshot["checksum"] != expected_checksum:
            raise ValueError("Snapshot checksum does not match content")

    def export_latest_cycle_snapshot(self) -> dict:
        events = self.get_latest_cycle_events()

        snapshot = {
            "scope": "CYCLE",
            "event_count": len(events),
            "events": self.serialize_filtered(events),
        }
        snapshot["checksum"] = self.generate_checksum(snapshot)
        return snapshot

    def export_run_snapshot(self) -> dict:
        events = self.snapshot()

        snapshot = {
            "scope": "RUN",
            "event_count": len(events),
            "events": self.serialize_filtered(events),
        }
        snapshot["checksum"] = self.generate_checksum(snapshot)
        return snapshot


def build_timeline_from_storage(
    store: SQLiteStore,
    run_id: str,
    *,
    cycle_id: str | None = None,
    event_type: str | None = None,
    source: str | None = None,
) -> list[SystemEvent]:
    rows = store.fetch_events(run_id, cycle_id=cycle_id)
    events: list[SystemEvent] = []
    for row in rows:
        if event_type and row.get("event_type") != event_type:
            continue
        if source and row.get("source") != source:
            continue
        payload = row.get("payload_json")
        parsed_payload = json.loads(payload) if payload else {}
        timestamp = row.get("timestamp")
        if isinstance(timestamp, str):
            try:
                resolved_time = datetime.fromisoformat(timestamp)
            except ValueError:
                resolved_time = datetime.utcnow()
        else:
            resolved_time = datetime.utcnow()
        events.append(
            SystemEvent(
                event_type=row.get("event_type", "UNKNOWN"),
                source=row.get("source", "UNKNOWN"),
                payload=parsed_payload,
                timestamp=resolved_time,
                tick=row.get("tick"),
                seq=row.get("seq"),
            )
        )

    def _safe_tick(event: SystemEvent) -> int:
        return event.tick if event.tick is not None else 0

    def _safe_seq(event: SystemEvent) -> int:
        return event.seq if event.seq is not None else 0

    events.sort(key=lambda event: (_safe_tick(event), _safe_seq(event)))
    return events
