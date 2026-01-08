"""
Storage engine for durable persistence and audit-ready storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import json
import os
import socket
import subprocess
from typing import Any
from uuid import uuid4

from config.runtime_config import (
    get_event_replay_mode,
    get_persistence_backend,
    get_persistence_enabled,
    get_persistence_jsonl_mirror_enabled,
    get_persistence_sqlite_path,
    get_persist_flush_each_cycle,
    get_audit_hash_chain_enabled,
    get_audit_verify_on_start,
    get_run_mode,
    get_ibkr_client_id,
    get_ibkr_default_currency,
    get_ibkr_default_exchange,
    get_ibkr_host,
    get_ibkr_market_data_type,
    get_ibkr_order_translation_enabled,
    get_ibkr_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
)
from config.system_config import ACTIVE_SESSIONS, CYCLE_SLEEP_SECONDS, get_current_market_session
from models.data_models import TradeRecord
from storage.serialization import canonical_json, compute_audit_hash, to_jsonable
from storage.sqlite_store import SCHEMA_VERSION, SQLiteStore, now_iso


@dataclass
class StorageResult:
    ok: bool
    run_id: str
    cycle_id: str | None
    trade_record_id: str | None
    events_persisted: int
    warnings: list[str]
    error: str | None = None


class StorageEngine:
    """SQLite-backed storage engine with audit hash chain support."""

    def __init__(self) -> None:
        self.enabled = get_persistence_enabled(default=True)
        self.backend = get_persistence_backend(default="sqlite")
        self.sqlite_path = os.path.abspath(
            get_persistence_sqlite_path(default="data/ibkr_system.sqlite")
        )
        self.jsonl_mirror_enabled = get_persistence_jsonl_mirror_enabled(default=False)
        self.audit_hash_chain_enabled = get_audit_hash_chain_enabled(default=True)
        self.audit_verify_on_start = get_audit_verify_on_start(default=False)
        self.flush_each_cycle = get_persist_flush_each_cycle(default=True)
        self.run_id = str(uuid4())
        self._seq = 0
        self._last_hash = "GENESIS"
        self._store: SQLiteStore | None = None
        if self.enabled and self.backend == "sqlite":
            print(f"[STORAGE] SQLite path resolved to {self.sqlite_path}")
            self._store = SQLiteStore(
                self.sqlite_path,
                commit_each_write=self.flush_each_cycle,
            )
            self._store.initialize_schema()
            self._insert_run()
            if self.audit_verify_on_start:
                self._verify_latest_run()
        print("[BOOT] StorageEngine initialised")

    def _insert_run(self) -> None:
        if not self._store:
            return
        run_mode = get_run_mode()
        event_replay_mode = get_event_replay_mode(run_mode)
        run_data = {
            "run_id": self.run_id,
            "started_at": now_iso(),
            "ended_at": None,
            "hostname": socket.gethostname(),
            "user": getpass.getuser(),
            "app_version": os.getenv("APP_VERSION") or "UNKNOWN",
            "git_sha": _resolve_git_sha(),
            "run_mode": run_mode.value,
            "event_replay_mode": event_replay_mode.value,
            "resolved_config_json": canonical_json(self._resolved_config(), allow_fallback=True),
            "schema_version": SCHEMA_VERSION,
            "created_at": now_iso(),
        }
        self._store.insert_run(run_data)

    def _verify_latest_run(self) -> None:
        if not self._store:
            return
        runs = self._store.list_runs()
        if not runs:
            return
        latest_run_id = runs[-1]["run_id"]
        result = self._store.verify_audit_chain(latest_run_id)
        if result.ok:
            print(f"[AUDIT] Verified audit chain for run_id={latest_run_id}")
        else:
            print(
                "[AUDIT][WARN] Audit verification failed "
                f"run_id={latest_run_id} seq={result.first_bad_seq} reason={result.reason}"
            )

    def store_trade_record(
        self,
        trade_record: TradeRecord,
        *,
        cycle_context: dict[str, Any] | None = None,
        events: list[Any] | None = None,
    ) -> StorageResult:
        if not self.enabled:
            return StorageResult(
                ok=False,
                run_id=self.run_id,
                cycle_id=None,
                trade_record_id=None,
                events_persisted=0,
                warnings=["Persistence disabled"],
            )
        if self.backend != "sqlite" or self._store is None:
            return StorageResult(
                ok=False,
                run_id=self.run_id,
                cycle_id=None,
                trade_record_id=None,
                events_persisted=0,
                warnings=[f"Unsupported backend: {self.backend}"],
            )
        warnings: list[str] = []
        fallback_handler = lambda obj: warnings.append(
            f"Fallback serialization for type {type(obj).__name__}"
        )
        cycle_context = cycle_context or {}
        cycle_id = str(uuid4())
        tick = cycle_context.get("tick")
        session = cycle_context.get("session") or get_current_market_session()
        cycle_started_at = cycle_context.get("cycle_started_at")
        cycle_ended_at = cycle_context.get("cycle_ended_at")
        cycle_data = {
            "cycle_id": cycle_id,
            "run_id": self.run_id,
            "tick": tick,
            "session": session,
            "cycle_started_at": _ensure_iso(cycle_started_at),
            "cycle_ended_at": _ensure_iso(cycle_ended_at),
            "scanner_n": len(trade_record.scanner_output or []),
            "patterns_n": len(trade_record.pattern_output or []),
            "intents_n": len(trade_record.strategy_output or []),
            "risk_n": len(trade_record.risk_output or []),
            "exec_n": len(trade_record.execution_output or []),
            "closed_n": len(trade_record.trade_outcomes or []),
            "created_at": now_iso(),
        }
        try:
            self._store.insert_cycle(cycle_data)
            persisted_events = self._persist_events(
                cycle_id,
                events or [],
                warnings,
                fallback_handler,
            )
            trade_record_id = self._persist_trade_record(
                cycle_id,
                trade_record,
                tick,
                warnings,
                fallback_handler,
            )
            trades_persisted = self._persist_trades(
                cycle_id,
                trade_record,
                warnings,
                fallback_handler,
                cycle_ended_at,
            )
        except Exception as exc:
            print(f"[STORAGE][ERROR] Persistence failure: {exc}")
            return StorageResult(
                ok=False,
                run_id=self.run_id,
                cycle_id=cycle_id,
                trade_record_id=None,
                events_persisted=0,
                warnings=warnings,
                error=str(exc),
            )
        if not self.flush_each_cycle:
            self._store.commit()
        return StorageResult(
            ok=True,
            run_id=self.run_id,
            cycle_id=cycle_id,
            trade_record_id=trade_record_id,
            events_persisted=persisted_events,
            warnings=warnings + ([f"Trades persisted: {trades_persisted}"] if trades_persisted else []),
        )

    def _persist_events(
        self,
        cycle_id: str,
        events: list[Any],
        warnings: list[str],
        fallback_handler,
    ) -> int:
        if not events:
            return 0
        event_rows = []
        for event in events:
            self._seq += 1
            payload_json = canonical_json(
                to_jsonable(event.payload, allow_fallback=True, fallback_handler=fallback_handler),
                allow_fallback=True,
            )
            event_payload = {
                "run_id": self.run_id,
                "cycle_id": cycle_id,
                "seq": self._seq,
                "event_type": event.event_type,
                "source": event.source,
                "timestamp": _ensure_iso(event.timestamp),
                "payload": json.loads(payload_json) if payload_json else None,
            }
            prev_hash = self._last_hash if self.audit_hash_chain_enabled else None
            event_hash = (
                compute_audit_hash(self._last_hash, event_payload, allow_fallback=True)
                if self.audit_hash_chain_enabled
                else None
            )
            if self.audit_hash_chain_enabled:
                self._last_hash = event_hash
            event_rows.append(
                {
                    "event_id": str(uuid4()),
                    "run_id": self.run_id,
                    "cycle_id": cycle_id,
                    "event_type": event.event_type,
                    "source": event.source,
                    "timestamp": event_payload["timestamp"],
                    "payload_json": payload_json,
                    "seq": self._seq,
                    "prev_hash": prev_hash,
                    "event_hash": event_hash,
                    "created_at": now_iso(),
                }
            )
            if self.jsonl_mirror_enabled:
                _append_jsonl(
                    "data/events.jsonl",
                    {
                        "run_id": self.run_id,
                        "cycle_id": cycle_id,
                        "seq": self._seq,
                        "event_type": event.event_type,
                        "source": event.source,
                        "timestamp": event_payload["timestamp"],
                        "payload": event_payload["payload"],
                        "prev_hash": prev_hash,
                        "event_hash": event_hash,
                    },
                )
        self._store.insert_events(event_rows)
        return len(event_rows)

    def _persist_trade_record(
        self,
        cycle_id: str,
        trade_record: TradeRecord,
        tick: int | None,
        warnings: list[str],
        fallback_handler,
    ) -> str:
        trade_record_id = str(uuid4())
        trade_record_payload = to_jsonable(
            trade_record,
            allow_fallback=True,
            fallback_handler=fallback_handler,
        )
        trade_record_row = {
            "trade_record_id": trade_record_id,
            "run_id": self.run_id,
            "cycle_id": cycle_id,
            "tick": tick,
            "scanner_output_json": canonical_json(
                trade_record_payload.get("scanner_output"),
                allow_fallback=True,
                fallback_handler=fallback_handler,
            ),
            "pattern_output_json": canonical_json(
                trade_record_payload.get("pattern_output"),
                allow_fallback=True,
                fallback_handler=fallback_handler,
            ),
            "strategy_output_json": canonical_json(
                trade_record_payload.get("strategy_output"),
                allow_fallback=True,
                fallback_handler=fallback_handler,
            ),
            "risk_output_json": canonical_json(
                trade_record_payload.get("risk_output"),
                allow_fallback=True,
                fallback_handler=fallback_handler,
            ),
            "execution_output_json": canonical_json(
                trade_record_payload.get("execution_output"),
                allow_fallback=True,
                fallback_handler=fallback_handler,
            ),
            "trade_outcomes_json": canonical_json(
                trade_record_payload.get("trade_outcomes"),
                allow_fallback=True,
                fallback_handler=fallback_handler,
            ),
            "performance_snapshot_json": canonical_json(
                trade_record_payload.get("performance_snapshot"),
                allow_fallback=True,
                fallback_handler=fallback_handler,
            ),
            "created_at": now_iso(),
        }
        if warnings:
            print(f"[STORAGE][WARN] {warnings}")
        self._store.insert_trade_record(trade_record_row)
        return trade_record_id

    def _persist_trades(
        self,
        cycle_id: str,
        trade_record: TradeRecord,
        warnings: list[str],
        fallback_handler,
        cycle_ended_at: Any | None,
    ) -> int:
        if not trade_record.trade_outcomes:
            return 0
        trades_rows = []
        closed_at = _ensure_iso(cycle_ended_at) or now_iso()
        for outcome in trade_record.trade_outcomes:
            payload = to_jsonable(
                outcome,
                allow_fallback=True,
                fallback_handler=fallback_handler,
            )
            trades_rows.append(
                {
                    "trade_id": str(uuid4()),
                    "run_id": self.run_id,
                    "symbol": payload.get("symbol"),
                    "trader_type": payload.get("trader_type"),
                    "strategy_name": payload.get("strategy_name"),
                    "direction": payload.get("direction"),
                    "entry_tick": None,
                    "entry_price": payload.get("entry_price"),
                    "exit_tick": None,
                    "exit_price": payload.get("exit_price"),
                    "quantity": payload.get("quantity"),
                    "gross_pnl": payload.get("gross_realised_pnl"),
                    "commission": payload.get("commission"),
                    "net_pnl": payload.get("net_realised_pnl"),
                    "status": "CLOSED",
                    "pattern_name": None,
                    "opened_at": None,
                    "closed_at": closed_at,
                    "created_at": now_iso(),
                }
            )
        self._store.insert_trades(trades_rows)
        return len(trades_rows)

    def shutdown(self) -> None:
        if self._store:
            self._store.close()
        print("[STORAGE] Shutdown complete.")

    def verify_audit_chain(self, run_id: str) -> str:
        if not self._store:
            return "Persistence not enabled"
        result = self._store.verify_audit_chain(run_id)
        if result.ok:
            return "OK"
        return f"FAILED seq={result.first_bad_seq} reason={result.reason}"

    def export_run(self, run_id: str, fmt: str, out_path: str) -> list[str]:
        if not self._store:
            raise RuntimeError("Persistence not enabled")
        return self._store.export_run(run_id, fmt, out_path)

    def _resolved_config(self) -> dict[str, Any]:
        run_mode = get_run_mode()
        event_replay_mode = get_event_replay_mode(run_mode)
        return {
            "run_mode": run_mode.value,
            "event_replay_mode": event_replay_mode.value,
            "cycle_sleep_seconds": CYCLE_SLEEP_SECONDS,
            "active_sessions": ACTIVE_SESSIONS,
            "ibkr_readonly_enabled": get_ibkr_readonly_enabled(),
            "ibkr_host": get_ibkr_host(),
            "ibkr_port": get_ibkr_port(),
            "ibkr_client_id": get_ibkr_client_id(),
            "ibkr_snapshot_timeout_seconds": get_ibkr_snapshot_timeout_seconds(),
            "ibkr_market_data_type": get_ibkr_market_data_type(),
            "ibkr_order_translation_enabled": get_ibkr_order_translation_enabled(),
            "ibkr_default_exchange": get_ibkr_default_exchange(),
            "ibkr_default_currency": get_ibkr_default_currency(),
            "persistence_enabled": self.enabled,
            "persistence_backend": self.backend,
            "persistence_sqlite_path": self.sqlite_path,
            "persistence_jsonl_mirror_enabled": self.jsonl_mirror_enabled,
            "audit_hash_chain_enabled": self.audit_hash_chain_enabled,
            "audit_verify_on_start": self.audit_verify_on_start,
            "persist_flush_each_cycle": self.flush_each_cycle,
        }


def _ensure_iso(value: Any | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        resolved = value
        if resolved.tzinfo is None:
            resolved = resolved.replace(tzinfo=timezone.utc)
        return resolved.isoformat()
    return str(value)


def _append_jsonl(path: str, record: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _resolve_git_sha() -> str | None:
    override = os.getenv("GIT_SHA")
    if override:
        return override
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return None
    sha = result.stdout.strip()
    return sha if sha else None
