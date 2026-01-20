from datetime import datetime

from src.core.run_event_timeline import RunEventTimeline
from src.core.events import SystemEvent
from src.events.event_schema import validate_event
from src.utils.time_utils import to_ny_time


class EventCollector:
    """
    In-memory collector for SystemEvents.
    Teaching-first, synchronous, deterministic.
    """

    def __init__(self):
        self._cycle_events = []
        self._run_timeline = RunEventTimeline()
        self._daily_realised_pnl = 0.0
        self._daily_pnl_date = None

    @staticmethod
    def _resolve_ny_date(timestamp: datetime) -> str:
        ny_time = to_ny_time(timestamp)
        return ny_time.date().isoformat()

    def _roll_daily_pnl(self, timestamp: datetime) -> None:
        resolved_date = self._resolve_ny_date(timestamp)
        if self._daily_pnl_date != resolved_date:
            self._daily_realised_pnl = 0.0
            self._daily_pnl_date = resolved_date

    def roll_daily_pnl(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.utcnow()
        self._roll_daily_pnl(timestamp)

    def clear_cycle(self):
        print("[EVENT_COLLECTOR] Clearing cycle-scoped events")
        self._cycle_events.clear()

    def record_event(self, event, include_cycle: bool = True):
        if event.event_type == "TRADE_CLOSED":
            self._roll_daily_pnl(event.timestamp)
            payload = event.payload or {}
            pnl_value = payload.get("net_realised_pnl", payload.get("realised_pnl", 0.0))
            try:
                pnl_float = float(pnl_value)
            except (TypeError, ValueError):
                pnl_float = 0.0
            self._daily_realised_pnl = round(self._daily_realised_pnl + pnl_float, 2)
        if include_cycle:
            self._cycle_events.append(event)
        self._run_timeline.record(event)

    def emit(
        self,
        event_type: str,
        source: str,
        payload: dict,
        timestamp=None,
        include_cycle: bool = True,
    ):
        validate_event(event_type, payload)
        if timestamp is None:
            event = SystemEvent(
                event_type=event_type,
                source=source,
                payload=payload,
            )
        else:
            event = SystemEvent(
                event_type=event_type,
                source=source,
                payload=payload,
                timestamp=timestamp,
            )
        self.record_event(event, include_cycle=include_cycle)
        return event

    def snapshot_cycle(self):
        return list(self._cycle_events)

    def snapshot_all(self):
        return self._run_timeline.snapshot()

    def get_events_for_replay(self, replay_mode: str):
        normalized_mode = (getattr(replay_mode, "value", replay_mode) or "").upper()
        if normalized_mode == "OFF":
            print("[REPLAY] Replay mode OFF — no events will be replayed")
            return []
        if normalized_mode == "CYCLE":
            print("[REPLAY] Replay mode CYCLE — using latest cycle events")
            return self.snapshot_cycle()
        if normalized_mode in {"RUN", "ALL"}:
            print("[REPLAY] Replay mode RUN — using all recorded events")
            return self.snapshot_all()

        print(
            f"[REPLAY] Unknown replay mode '{replay_mode}' — defaulting to OFF"
        )
        return []

    def count(self, event_type: str = None):
        all_events = self._run_timeline.snapshot()
        if event_type is None:
            return len(all_events)
        return len([
            e for e in all_events
            if e.event_type == event_type
        ])

    def filter_by_type(self, event_type: str):
        print(
            f"[EVENT_COLLECTOR] Filtering events — type={event_type}"
        )
        return [
            e for e in self._run_timeline.snapshot()
            if e.event_type == event_type
        ]

    def filter_by_source(self, source: str):
        print(
            f"[EVENT_COLLECTOR] Filtering events — source={source}"
        )
        return [
            e for e in self._run_timeline.snapshot()
            if e.source == source
        ]

    def flush_summary(self) -> dict:
        """
        Provide a summary of recorded events.

        Designed for shutdown hooks where we want a final snapshot without
        introducing heavy persistence or side effects.
        """

        summary = self._run_timeline.summary()
        print("[EVENT_COLLECTOR] Flushing event summary for shutdown", summary)
        return summary

    def sum_realised_pnl(self) -> float:
        realised_pnl = 0.0
        for event in self._run_timeline.snapshot():
            if event.event_type != "TRADE_CLOSED":
                continue
            payload = event.payload or {}
            realised_pnl += payload.get(
                "net_realised_pnl", payload.get("realised_pnl", 0.0)
            )
        return round(realised_pnl, 2)

    def daily_realised_pnl(self) -> float:
        return round(self._daily_realised_pnl, 2)

    def daily_pnl_date(self) -> str | None:
        return self._daily_pnl_date

    def cycle_count(self, event_type: str = None):
        if event_type is None:
            return len(self._cycle_events)
        return len([
            e for e in self._cycle_events
            if e.event_type == event_type
        ])

    def cycle_sum_realised_pnl(self) -> float:
        realised_pnl = 0.0
        for event in self._cycle_events:
            if event.event_type != "TRADE_CLOSED":
                continue
            payload = event.payload or {}
            realised_pnl += payload.get(
                "net_realised_pnl", payload.get("realised_pnl", 0.0)
            )
        return round(realised_pnl, 2)

    def cycle_pnl_by_trader_type(self) -> dict[str, float]:
        pnl_by_trader_type = {}
        for event in self._cycle_events:
            if event.event_type != "TRADE_CLOSED":
                continue
            payload = event.payload or {}
            trader_type = payload.get("trader_type")
            if trader_type is None:
                continue
            pnl_by_trader_type[trader_type] = (
                pnl_by_trader_type.get(trader_type, 0.0)
                + payload.get(
                    "net_realised_pnl", payload.get("realised_pnl", 0.0)
                )
            )
        return {
            trader_type: round(realised_pnl, 2)
            for trader_type, realised_pnl in pnl_by_trader_type.items()
        }

    def consecutive_losses(self) -> int:
        losses = 0
        for event in reversed(self._run_timeline.snapshot()):
            if event.event_type != "TRADE_CLOSED":
                continue
            payload = event.payload or {}
            pnl = payload.get("net_realised_pnl", payload.get("realised_pnl", 0.0))
            try:
                pnl_value = float(pnl)
            except (TypeError, ValueError):
                pnl_value = 0.0
            if pnl_value < 0:
                losses += 1
            else:
                break
        return losses

    # Backwards compatibility with earlier naming.
    def record(self, event):
        self.record_event(event)

    def snapshot_cycle_events(self):
        return self.snapshot_cycle()

    def snapshot_all_events(self):
        return self.snapshot_all()

    def clear_cycle_events(self):
        self.clear_cycle()
