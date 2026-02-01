from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from src.config.runtime_config import RunMode, get_run_mode
from src.core.run_event_timeline import build_timeline_from_storage
from src.events.event_invariants import check_invariants, EventInvariantError
from src.events.event_schema import EventSchemaError, validate_event
from src.storage.sqlite_store import SQLiteStore


@dataclass
class _ReplayState:
    last_perf_snapshot: Optional[dict[str, Any]] = None
    last_strategy_snapshot: Optional[list[dict[str, Any]]] = None


class ReplayEngine:
    """
    Deterministic, read-only event replay engine.

    Replay relies solely on the event payloads that were emitted during the live
    cycle. No registries or runtime state are mutated during replay.
    """

    def __init__(self) -> None:
        self._state = _ReplayState()

    def replay(self, events: Iterable[Any]) -> None:
        print("[REPLAY] Starting deterministic event replay")
        self._state.last_perf_snapshot = None
        self._state.last_strategy_snapshot = None

        ordered_events = sorted(events or [], key=lambda e: e.timestamp)
        for event in ordered_events:
            self._log_event(event)
            if getattr(event, "event_type", None) == "PERF_SNAPSHOT":
                self._record_perf_snapshot(event.payload)
            if getattr(event, "event_type", None) == "STRATEGY_PERF_SNAPSHOT":
                self._record_strategy_snapshot(event.payload)

        self._log_performance_summary()
        self._log_strategy_summary()
        try:
            check_invariants(ordered_events)
            print("[REPLAY][INVARIANTS] OK")
        except EventInvariantError as exc:
            print(f"[REPLAY][INVARIANTS] FAILED: {exc}")
        print("[REPLAY] Replay complete")

    def replay_from_storage(
        self,
        store: SQLiteStore,
        run_id: str,
        *,
        cycle_id: str | None = None,
    ) -> list[Any]:
        run_mode = get_run_mode()
        if run_mode not in {RunMode.SIM, RunMode.PAPER}:
            raise RuntimeError(
                "Replay is disabled outside SIM/PAPER mode "
                f"(current={run_mode.value})"
            )
        events = build_timeline_from_storage(store, run_id, cycle_id=cycle_id)
        for event in events:
            try:
                validate_event(event.event_type, event.payload)
            except EventSchemaError as exc:
                raise EventSchemaError(
                    f"Replay schema validation failed for {event.event_type}: {exc}"
                ) from exc
        self.replay(events)
        return events

    def _log_event(self, event: Any) -> None:
        print(
            f"[REPLAY] {event.timestamp} | "
            f"{event.event_type} | {event.source} | "
            f"{event.payload}"
        )

    def _record_perf_snapshot(self, payload: Any) -> None:
        if isinstance(payload, dict):
            self._state.last_perf_snapshot = payload

    def _record_strategy_snapshot(self, payload: Any) -> None:
        if isinstance(payload, dict):
            strategies = payload.get("strategies")
            if isinstance(strategies, list):
                self._state.last_strategy_snapshot = strategies

    def _log_performance_summary(self) -> None:
        if not self._state.last_perf_snapshot:
            print("[REPLAY][PERF] No PERF_SNAPSHOT events encountered during replay")
            return

        snapshot = self._state.last_perf_snapshot
        total_trades = int(snapshot.get("total_trades", 0))
        win_rate = float(snapshot.get("win_rate", 0.0))
        gross_pnl = float(snapshot.get("gross_pnl", 0.0))

        print("[REPLAY][PERF] Final performance snapshot reconstructed from events")
        print(
            "[REPLAY][PERF] "
            f"total_trades={total_trades} "
            f"win_rate={win_rate:.2f} "
            f"gross_pnl={gross_pnl:.2f}"
        )

    def _log_strategy_summary(self) -> None:
        if not self._state.last_strategy_snapshot:
            print("[REPLAY][STRATEGY] No STRATEGY_PERF_SNAPSHOT events encountered during replay")
            return

        print("[REPLAY][STRATEGY] Reconstructed strategy snapshot from events")
        for strategy in sorted(
            self._state.last_strategy_snapshot,
            key=lambda item: item.get("strategy_name", ""),
        ):
            strategy_name = strategy.get("strategy_name", "UNKNOWN")
            total_trades = int(strategy.get("total_trades", 0))
            win_rate = float(strategy.get("win_rate", 0.0))
            gross_pnl = float(strategy.get("gross_pnl", 0.0))
            print(
                f"[REPLAY][STRATEGY] "
                f"{strategy_name} "
                f"trades={total_trades} "
                f"win_rate={win_rate:.2f} "
                f"gross_pnl={gross_pnl:.2f}"
            )
