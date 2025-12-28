class EventCollector:
    """
    In-memory collector for SystemEvents.
    Teaching-first, synchronous, deterministic.
    """

    def __init__(self):
        self._cycle_events = []
        self._all_events = []

    def clear_cycle(self):
        print("[EVENT_COLLECTOR] Clearing cycle-scoped events")
        self._cycle_events.clear()

    def record_event(self, event):
        self._cycle_events.append(event)
        self._all_events.append(event)

    def snapshot_cycle(self):
        return list(self._cycle_events)

    def snapshot_all(self):
        return list(self._all_events)

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
        if event_type is None:
            return len(self._all_events)
        return len([
            e for e in self._all_events
            if e.event_type == event_type
        ])

    def filter_by_type(self, event_type: str):
        print(
            f"[EVENT_COLLECTOR] Filtering events — type={event_type}"
        )
        return [
            e for e in self._all_events
            if e.event_type == event_type
        ]

    def filter_by_source(self, source: str):
        print(
            f"[EVENT_COLLECTOR] Filtering events — source={source}"
        )
        return [
            e for e in self._all_events
            if e.source == source
        ]

    def sum_realised_pnl(self) -> float:
        realised_pnl = 0.0
        for event in self._all_events:
            if event.event_type != "TRADE_CLOSED":
                continue
            payload = event.payload or {}
            realised_pnl += payload.get("realised_pnl", 0.0)
        return round(realised_pnl, 2)

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
            realised_pnl += payload.get("realised_pnl", 0.0)
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
                + payload.get("realised_pnl", 0.0)
            )
        return {
            trader_type: round(realised_pnl, 2)
            for trader_type, realised_pnl in pnl_by_trader_type.items()
        }

    # Backwards compatibility with earlier naming.
    def record(self, event):
        self.record_event(event)

    def snapshot_cycle_events(self):
        return self.snapshot_cycle()

    def snapshot_all_events(self):
        return self.snapshot_all()

    def clear_cycle_events(self):
        self.clear_cycle()
