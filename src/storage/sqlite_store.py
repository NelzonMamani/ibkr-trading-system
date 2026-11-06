from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import hashlib
import weakref
from uuid import uuid4
import os
import sqlite3
from typing import Any, Iterable

from src.storage.serialization import compute_audit_hash


SCHEMA_VERSION = 8


@dataclass
class AuditVerificationResult:
    ok: bool
    first_bad_seq: int | None
    reason: str


class _CapitalWriterRejected(RuntimeError):
    pass


class _CapitalWriter:
    """Issuer-private live-process capability. Public DB identity grants nothing."""
    __slots__ = ()

    def __reduce__(self):
        raise TypeError('CAPITAL_WRITER_NOT_SERIALIZABLE')

    def __copy__(self):
        raise TypeError('CAPITAL_WRITER_NOT_TRANSFERABLE')

    def __deepcopy__(self, memo):
        raise TypeError('CAPITAL_WRITER_NOT_TRANSFERABLE')


class SQLiteStore:
    def __init__(self, path: str, *, commit_each_write: bool = True) -> None:
        self.path = path
        self._capital_writers = {}
        self.commit_each_write = commit_each_write
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.connection.close()

    def initialize_schema(self) -> None:
        # Refuse future base schemas before any DDL or schema stamp.
        if self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='schema_meta'").fetchone():
            version = self.connection.execute('SELECT MAX(version) FROM schema_meta').fetchone()[0]
            if version is not None and version > SCHEMA_VERSION:
                raise RuntimeError('STORAGE_FUTURE_SCHEMA_UNSUPPORTED')
        if self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='capital_owner_state'").fetchone():
            if os.environ.get('EXECUTION_ENV') != 'TEST':
                raise RuntimeError('CAPITAL_OPERATIONAL_ACCESS_UNFENCED')
            if self.connection.execute("SELECT 1 FROM capital_owner_state WHERE NOT ((schema_version=1 AND fence='SYNTHETIC_ONLY_V1') OR (schema_version=2 AND fence='SYNTHETIC_ONLY_V2')) LIMIT 1").fetchone():
                raise RuntimeError('CAPITAL_EXTENSION_SCHEMA_UNSUPPORTED')
        cursor = self.connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                version INTEGER PRIMARY KEY,
                applied_at_utc TEXT
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT,
                started_at_utc TEXT,
                ended_at TEXT,
                ended_at_utc TEXT,
                hostname TEXT,
                user TEXT,
                app_version TEXT,
                git_sha TEXT,
                run_mode TEXT,
                effective_run_mode TEXT,
                event_replay_mode TEXT,
                resolved_config_json TEXT,
                config_fingerprint TEXT,
                schema_version INTEGER,
                system_version TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS cycles (
                cycle_id TEXT PRIMARY KEY,
                run_id TEXT,
                tick INTEGER,
                session TEXT,
                market_session TEXT,
                cycle_started_at TEXT,
                cycle_ended_at TEXT,
                scanner_n INTEGER,
                scanner_candidates_count INTEGER,
                patterns_n INTEGER,
                patterns_count INTEGER,
                signals_count INTEGER,
                intents_n INTEGER,
                intents_count INTEGER,
                risk_n INTEGER,
                risk_decisions_count INTEGER,
                exec_n INTEGER,
                execution_results_count INTEGER,
                closed_n INTEGER,
                trade_outcomes_count INTEGER,
                warnings_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT,
                cycle_id TEXT,
                tick INTEGER,
                event_type TEXT,
                source TEXT,
                timestamp TEXT,
                payload_json TEXT,
                schema_version INTEGER,
                payload_hash TEXT,
                seq INTEGER,
                prev_hash TEXT,
                event_hash TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id),
                FOREIGN KEY(cycle_id) REFERENCES cycles(cycle_id)
            );
            CREATE TABLE IF NOT EXISTS position_lifecycle_transitions (
                transition_id TEXT PRIMARY KEY,
                run_id TEXT,
                symbol TEXT,
                trader_type TEXT,
                strategy_owner TEXT,
                entry_source TEXT,
                entry_intent_id TEXT,
                entry_order_id TEXT,
                stop_loss_price REAL,
                active_stop_order_id TEXT,
                pending_stop_order_intent TEXT,
                emergency_stop_exception TEXT,
                trailing_stop_price REAL,
                from_state TEXT,
                to_state TEXT,
                intent TEXT,
                reason_code TEXT,
                reason TEXT,
                mode TEXT,
                requested_quantity INTEGER,
                filled_quantity INTEGER,
                quantity_before INTEGER,
                quantity_after INTEGER,
                fill_status TEXT,
                execution_blocked INTEGER,
                fill_latency_ms INTEGER,
                transition_seq INTEGER,
                timestamp TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS trade_lifecycle_trades (
                lifecycle_trade_id TEXT PRIMARY KEY,
                run_id TEXT,
                symbol TEXT,
                side TEXT,
                strategy_name TEXT,
                status TEXT,
                opened_at TEXT,
                closed_at TEXT,
                quantity_open INTEGER,
                quantity_closed INTEGER,
                entry_avg_price REAL,
                exit_avg_price REAL,
                stop_price REAL,
                target_price REAL,
                target_quantity INTEGER,
                target_type TEXT,
                gross_realized_pnl REAL,
                realized_pnl_by_exit_reason_json TEXT,
                unrealized_pnl REAL,
                last_mark_price REAL,
                source_order_ids_json TEXT,
                source_execution_ids_json TEXT,
                reconciliation_flags_json TEXT,
                drift_flags_json TEXT,
                notes_json TEXT,
                take_profit_events_json TEXT,
                updated_at TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS trade_lifecycle_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT,
                lifecycle_trade_id TEXT,
                symbol TEXT,
                side TEXT,
                event_type TEXT,
                quantity INTEGER,
                price REAL,
                timestamp TEXT,
                order_id TEXT,
                execution_id TEXT,
                source TEXT,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id),
                FOREIGN KEY(lifecycle_trade_id) REFERENCES trade_lifecycle_trades(lifecycle_trade_id)
            );
            CREATE TABLE IF NOT EXISTS trade_lifecycle_reconciliation_events (
                reconciliation_id TEXT PRIMARY KEY,
                run_id TEXT,
                lifecycle_trade_id TEXT,
                symbol TEXT,
                status TEXT,
                finding_type TEXT,
                details_json TEXT,
                timestamp TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id),
                FOREIGN KEY(lifecycle_trade_id) REFERENCES trade_lifecycle_trades(lifecycle_trade_id)
            );
            CREATE TABLE IF NOT EXISTS trade_lifecycle_summaries (
                summary_id TEXT PRIMARY KEY,
                run_id TEXT,
                payload_json TEXT,
                timestamp TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS stop_authority_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT,
                timestamp TEXT,
                event_type TEXT,
                symbol TEXT,
                lifecycle_trade_id TEXT,
                position_id TEXT,
                strategy_owner TEXT,
                entry_order_id TEXT,
                entry_intent_id TEXT,
                active_stop_order_id TEXT,
                pending_stop_order_intent TEXT,
                stop_price REAL,
                previous_stop_price REAL,
                quantity INTEGER,
                status TEXT,
                reason TEXT,
                recovery_classification TEXT,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS capital_audit_events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT,
                event_type TEXT,
                decision_id TEXT,
                reservation_id TEXT,
                trade_id TEXT,
                intent_id TEXT,
                order_id TEXT,
                symbol TEXT,
                strategy_id TEXT,
                run_mode TEXT,
                status TEXT,
                requested_quantity INTEGER,
                approved_quantity INTEGER,
                requested_notional REAL,
                approved_notional REAL,
                reserved_capital REAL,
                exposure_before REAL,
                exposure_after REAL,
                reason TEXT,
                payload_json TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS strategy_allocation_audit_events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT,
                event_type TEXT,
                decision_id TEXT,
                reservation_id TEXT,
                trade_id TEXT,
                intent_id TEXT,
                order_id TEXT,
                strategy_id TEXT,
                symbol TEXT,
                run_mode TEXT,
                status TEXT,
                requested_quantity INTEGER,
                approved_quantity INTEGER,
                requested_notional REAL,
                approved_notional REAL,
                strategy_capital_limit REAL,
                reserved_capital REAL,
                used_exposure REAL,
                reason TEXT,
                global_capital_decision_id TEXT,
                payload_json TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS trade_records (
                trade_record_id TEXT PRIMARY KEY,
                run_id TEXT,
                cycle_id TEXT,
                tick INTEGER,
                scanner_output_json TEXT,
                pattern_output_json TEXT,
                strategy_output_json TEXT,
                decision_output_json TEXT,
                risk_output_json TEXT,
                execution_output_json TEXT,
                trade_outcomes_json TEXT,
                performance_snapshot_json TEXT,
                regime_snapshot_json TEXT,
                regime_policy_decision_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id),
                FOREIGN KEY(cycle_id) REFERENCES cycles(cycle_id)
            );
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                run_id TEXT,
                symbol TEXT,
                trader_type TEXT,
                strategy_name TEXT,
                direction TEXT,
                entry_tick INTEGER,
                entry_price REAL,
                exit_tick INTEGER,
                exit_price REAL,
                quantity INTEGER,
                gross_pnl REAL,
                commission REAL,
                net_pnl REAL,
                status TEXT,
                pattern_name TEXT,
                opened_at TEXT,
                closed_at TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS execution_results (
                execution_result_id TEXT PRIMARY KEY,
                run_id TEXT,
                cycle_id TEXT,
                symbol TEXT,
                trader_type TEXT,
                status TEXT,
                attempted INTEGER,
                direction TEXT,
                requested_quantity INTEGER,
                filled_quantity INTEGER,
                remaining_quantity INTEGER,
                fill_status TEXT,
                entry_price REAL,
                exit_price REAL,
                gross_realised_pnl REAL,
                commission REAL,
                net_realised_pnl REAL,
                slippage_applied REAL,
                rejection_reason TEXT,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id),
                FOREIGN KEY(cycle_id) REFERENCES cycles(cycle_id)
            );
            CREATE TABLE IF NOT EXISTS trade_outcomes (
                trade_outcome_id TEXT PRIMARY KEY,
                run_id TEXT,
                cycle_id TEXT,
                symbol TEXT,
                trader_type TEXT,
                strategy_name TEXT,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                quantity INTEGER,
                gross_realised_pnl REAL,
                commission REAL,
                net_realised_pnl REAL,
                duration_ticks INTEGER,
                outcome TEXT,
                closed_at TEXT,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id),
                FOREIGN KEY(cycle_id) REFERENCES cycles(cycle_id)
            );
            CREATE TABLE IF NOT EXISTS performance_snapshots (
                performance_snapshot_id TEXT PRIMARY KEY,
                run_id TEXT,
                cycle_id TEXT,
                tick INTEGER,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id),
                FOREIGN KEY(cycle_id) REFERENCES cycles(cycle_id)
            );
            CREATE TABLE IF NOT EXISTS watchlists (
                watchlist_id TEXT PRIMARY KEY,
                strategy_name TEXT,
                asof_date TEXT,
                session_phase TEXT,
                created_at_utc TEXT,
                symbols_json TEXT,
                focus_json TEXT,
                watchlist_hash TEXT,
                metrics_json TEXT
            );
            CREATE TABLE IF NOT EXISTS learning_runs (
                run_id TEXT PRIMARY KEY,
                started_at_utc TEXT,
                completed_at_utc TEXT,
                ok INTEGER,
                error TEXT,
                strategy_name TEXT,
                window_start_utc TEXT,
                window_end_utc TEXT,
                inputs_hash TEXT,
                outputs_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS learning_reports (
                report_id TEXT PRIMARY KEY,
                run_id TEXT,
                report_type TEXT,
                asof_date_ny TEXT,
                strategy_name TEXT,
                payload_json TEXT,
                summary_text TEXT
            );
            CREATE TABLE IF NOT EXISTS policy_proposals (
                proposal_id TEXT PRIMARY KEY,
                created_at_utc TEXT,
                strategy_name TEXT,
                baseline_policy_version TEXT,
                min_trades_required INTEGER,
                trades_used INTEGER,
                proposal_json TEXT,
                diff_json TEXT,
                rationale_json TEXT,
                status TEXT,
                approved_by TEXT,
                approved_at_utc TEXT,
                rejection_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS trade_admission_rows (
                admission_row_id TEXT PRIMARY KEY,
                run_id TEXT,
                symbol TEXT,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS trade_blocker_rows (
                blocker_row_id TEXT PRIMARY KEY,
                run_id TEXT,
                symbol TEXT,
                blocker_category TEXT,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS trade_analytics_rows (
                analytics_row_id TEXT PRIMARY KEY,
                run_id TEXT,
                trade_id TEXT,
                symbol TEXT,
                realized_pnl REAL,
                exit_reason TEXT,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS cycle_summary_rows (
                cycle_summary_row_id TEXT PRIMARY KEY,
                run_id TEXT,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            """
        )
        self._ensure_columns(
            "runs",
            {
                "started_at_utc": "TEXT",
                "ended_at_utc": "TEXT",
                "effective_run_mode": "TEXT",
                "config_fingerprint": "TEXT",
                "system_version": "TEXT",
            },
        )
        self._ensure_columns(
            "cycles",
            {
                "tick": "INTEGER",
                "market_session": "TEXT",
                "scanner_candidates_count": "INTEGER",
                "patterns_count": "INTEGER",
                "signals_count": "INTEGER",
                "intents_count": "INTEGER",
                "risk_decisions_count": "INTEGER",
                "execution_results_count": "INTEGER",
                "trade_outcomes_count": "INTEGER",
                "warnings_json": "TEXT",
            },
        )
        self._ensure_columns(
            "events",
            {
                "tick": "INTEGER",
                "schema_version": "INTEGER",
                "payload_hash": "TEXT",
            },
        )
        self._ensure_columns(
            "position_lifecycle_transitions",
            {
                "strategy_owner": "TEXT",
                "entry_source": "TEXT",
                "entry_intent_id": "TEXT",
                "entry_order_id": "TEXT",
                "stop_loss_price": "REAL",
                "active_stop_order_id": "TEXT",
                "pending_stop_order_intent": "TEXT",
                "emergency_stop_exception": "TEXT",
                "trailing_stop_price": "REAL",
                "remaining_quantity": "INTEGER",
            },
        )
        self._ensure_columns(
            "trade_lifecycle_reconciliation_events",
            {
                "classification": "TEXT",
                "severity": "TEXT",
                "source": "TEXT",
            },
        )
        self._ensure_columns(
            "trade_lifecycle_trades",
            {
                "target_price": "REAL",
                "target_quantity": "INTEGER",
                "target_type": "TEXT",
                "realized_pnl_by_exit_reason_json": "TEXT",
                "take_profit_events_json": "TEXT",
            },
        )
        self._ensure_columns(
            "trade_records",
            {
                "tick": "INTEGER",
                "regime_snapshot_json": "TEXT",
                "regime_policy_decision_json": "TEXT",
            },
        )
        self._ensure_columns(
            "performance_snapshots",
            {
                "tick": "INTEGER",
            },
        )
        self._ensure_columns(
            "policy_proposals",
            {
                "rejection_reason": "TEXT",
            },
        )
        cursor.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_cycles_run_id ON cycles(run_id);
            CREATE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq);
            CREATE INDEX IF NOT EXISTS idx_events_run_tick ON events(run_id, tick);
            CREATE INDEX IF NOT EXISTS idx_events_cycle_id ON events(cycle_id);
            CREATE INDEX IF NOT EXISTS idx_lifecycle_run_seq
                ON position_lifecycle_transitions(run_id, transition_seq);
            CREATE INDEX IF NOT EXISTS idx_lifecycle_symbol
                ON position_lifecycle_transitions(symbol, trader_type);
            CREATE INDEX IF NOT EXISTS idx_tle_trades_symbol_status
                ON trade_lifecycle_trades(symbol, status);
            CREATE INDEX IF NOT EXISTS idx_tle_events_trade_time
                ON trade_lifecycle_events(lifecycle_trade_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_tle_events_symbol_time
                ON trade_lifecycle_events(symbol, timestamp);
            CREATE INDEX IF NOT EXISTS idx_tle_reconcile_symbol_time
                ON trade_lifecycle_reconciliation_events(symbol, timestamp);
            CREATE INDEX IF NOT EXISTS idx_stop_authority_trade_time
                ON stop_authority_events(lifecycle_trade_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_stop_authority_symbol_time
                ON stop_authority_events(symbol, timestamp);
            CREATE INDEX IF NOT EXISTS idx_capital_audit_decision ON capital_audit_events(decision_id);
            CREATE INDEX IF NOT EXISTS idx_capital_audit_symbol_time ON capital_audit_events(symbol, timestamp);
            CREATE INDEX IF NOT EXISTS idx_strategy_alloc_audit_decision ON strategy_allocation_audit_events(decision_id);
            CREATE INDEX IF NOT EXISTS idx_strategy_alloc_audit_strategy_time ON strategy_allocation_audit_events(strategy_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_trade_records_run_id ON trade_records(run_id);
            CREATE INDEX IF NOT EXISTS idx_trades_run_id ON trades(run_id);
            CREATE INDEX IF NOT EXISTS idx_execution_results_run_id ON execution_results(run_id);
            CREATE INDEX IF NOT EXISTS idx_trade_outcomes_run_id ON trade_outcomes(run_id);
            CREATE INDEX IF NOT EXISTS idx_performance_snapshots_run_id ON performance_snapshots(run_id);
            CREATE INDEX IF NOT EXISTS idx_watchlists_strategy_date ON watchlists(strategy_name, asof_date);
            CREATE INDEX IF NOT EXISTS idx_learning_reports_date ON learning_reports(strategy_name, asof_date_ny);
            CREATE INDEX IF NOT EXISTS idx_policy_proposals_strategy ON policy_proposals(strategy_name, created_at_utc);
            CREATE INDEX IF NOT EXISTS idx_trade_admission_run_symbol ON trade_admission_rows(run_id, symbol);
            CREATE INDEX IF NOT EXISTS idx_trade_blocker_run_symbol ON trade_blocker_rows(run_id, symbol);
            CREATE INDEX IF NOT EXISTS idx_trade_analytics_run_symbol ON trade_analytics_rows(run_id, symbol);
            CREATE INDEX IF NOT EXISTS idx_cycle_summary_rows_run_id ON cycle_summary_rows(run_id);
            """
        )
        self._record_schema_version()
        self.connection.commit()

    def insert_run(self, run_data: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO runs (
                run_id, started_at, started_at_utc, ended_at, ended_at_utc, hostname, user, app_version,
                git_sha, run_mode, effective_run_mode, event_replay_mode, resolved_config_json,
                config_fingerprint, schema_version, system_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_data["run_id"],
                run_data.get("started_at"),
                run_data.get("started_at_utc"),
                run_data.get("ended_at"),
                run_data.get("ended_at_utc"),
                run_data.get("hostname"),
                run_data.get("user"),
                run_data.get("app_version"),
                run_data.get("git_sha"),
                run_data.get("run_mode"),
                run_data.get("effective_run_mode"),
                run_data.get("event_replay_mode"),
                run_data.get("resolved_config_json"),
                run_data.get("config_fingerprint"),
                run_data.get("schema_version"),
                run_data.get("system_version"),
                run_data.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_cycle(self, cycle_data: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO cycles (
                cycle_id, run_id, tick, session, cycle_started_at, cycle_ended_at,
                scanner_n, patterns_n, intents_n, risk_n, exec_n, closed_n, created_at,
                market_session, scanner_candidates_count, patterns_count, signals_count,
                intents_count, risk_decisions_count, execution_results_count,
                trade_outcomes_count, warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cycle_data["cycle_id"],
                cycle_data["run_id"],
                cycle_data.get("tick"),
                cycle_data.get("session"),
                cycle_data.get("cycle_started_at"),
                cycle_data.get("cycle_ended_at"),
                cycle_data.get("scanner_n"),
                cycle_data.get("patterns_n"),
                cycle_data.get("intents_n"),
                cycle_data.get("risk_n"),
                cycle_data.get("exec_n"),
                cycle_data.get("closed_n"),
                cycle_data.get("created_at"),
                cycle_data.get("market_session"),
                cycle_data.get("scanner_candidates_count"),
                cycle_data.get("patterns_count"),
                cycle_data.get("signals_count"),
                cycle_data.get("intents_count"),
                cycle_data.get("risk_decisions_count"),
                cycle_data.get("execution_results_count"),
                cycle_data.get("trade_outcomes_count"),
                cycle_data.get("warnings_json"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_events(self, events: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO events (
                event_id, run_id, cycle_id, tick, event_type, source, timestamp,
                payload_json, schema_version, payload_hash, seq, prev_hash, event_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event["event_id"],
                    event["run_id"],
                    event.get("cycle_id"),
                    event.get("tick"),
                    event["event_type"],
                    event["source"],
                    event["timestamp"],
                    event.get("payload_json"),
                    event.get("schema_version"),
                    event.get("payload_hash"),
                    event.get("seq"),
                    event.get("prev_hash"),
                    event.get("event_hash"),
                    event.get("created_at"),
                )
                for event in events
            ],
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_lifecycle_transitions(self, transitions: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT OR REPLACE INTO position_lifecycle_transitions (
                transition_id, run_id, symbol, trader_type, strategy_owner,
                entry_source, entry_intent_id, entry_order_id, stop_loss_price,
                active_stop_order_id, pending_stop_order_intent, emergency_stop_exception,
                trailing_stop_price, from_state, to_state, intent,
                reason_code, reason, mode, requested_quantity, filled_quantity, quantity_before,
                quantity_after, remaining_quantity, fill_status, execution_blocked, fill_latency_ms, transition_seq,
                timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    transition["transition_id"],
                    transition["run_id"],
                    transition.get("symbol"),
                    transition.get("trader_type"),
                    transition.get("strategy_owner"),
                    transition.get("entry_source"),
                    transition.get("entry_intent_id"),
                    transition.get("entry_order_id"),
                    transition.get("stop_loss_price"),
                    transition.get("active_stop_order_id"),
                    transition.get("pending_stop_order_intent"),
                    transition.get("emergency_stop_exception"),
                    transition.get("trailing_stop_price"),
                    transition.get("from_state"),
                    transition.get("to_state"),
                    transition.get("intent"),
                    transition.get("reason_code"),
                    transition.get("reason"),
                    transition.get("mode"),
                    transition.get("requested_quantity"),
                    transition.get("filled_quantity"),
                    transition.get("quantity_before"),
                    transition.get("quantity_after"),
                    transition.get("remaining_quantity"),
                    transition.get("fill_status"),
                    transition.get("execution_blocked"),
                    transition.get("fill_latency_ms"),
                    transition.get("transition_seq"),
                    transition.get("timestamp"),
                    transition.get("created_at"),
                )
                for transition in transitions
            ],
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trade_record(self, trade_record: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO trade_records (
                trade_record_id, run_id, cycle_id, tick,
                scanner_output_json, pattern_output_json, strategy_output_json,
                decision_output_json, risk_output_json, execution_output_json, trade_outcomes_json,
                performance_snapshot_json, regime_snapshot_json, regime_policy_decision_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_record["trade_record_id"],
                trade_record["run_id"],
                trade_record.get("cycle_id"),
                trade_record.get("tick"),
                trade_record.get("scanner_output_json"),
                trade_record.get("pattern_output_json"),
                trade_record.get("strategy_output_json"),
                trade_record.get("decision_output_json"),
                trade_record.get("risk_output_json"),
                trade_record.get("execution_output_json"),
                trade_record.get("trade_outcomes_json"),
                trade_record.get("performance_snapshot_json"),
                trade_record.get("regime_snapshot_json"),
                trade_record.get("regime_policy_decision_json"),
                trade_record.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def upsert_trade_lifecycle_trade(self, trade: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO trade_lifecycle_trades (
                lifecycle_trade_id, run_id, symbol, side, strategy_name, status, opened_at, closed_at,
                quantity_open, quantity_closed, entry_avg_price, exit_avg_price, stop_price,
                target_price, target_quantity, target_type, gross_realized_pnl,
                realized_pnl_by_exit_reason_json, unrealized_pnl, last_mark_price,
                source_order_ids_json, source_execution_ids_json, reconciliation_flags_json,
                drift_flags_json, notes_json, take_profit_events_json, updated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lifecycle_trade_id) DO UPDATE SET
                run_id=excluded.run_id,
                symbol=excluded.symbol,
                side=excluded.side,
                strategy_name=excluded.strategy_name,
                status=excluded.status,
                opened_at=excluded.opened_at,
                closed_at=excluded.closed_at,
                quantity_open=excluded.quantity_open,
                quantity_closed=excluded.quantity_closed,
                entry_avg_price=excluded.entry_avg_price,
                exit_avg_price=excluded.exit_avg_price,
                stop_price=excluded.stop_price,
                target_price=excluded.target_price,
                target_quantity=excluded.target_quantity,
                target_type=excluded.target_type,
                gross_realized_pnl=excluded.gross_realized_pnl,
                realized_pnl_by_exit_reason_json=excluded.realized_pnl_by_exit_reason_json,
                unrealized_pnl=excluded.unrealized_pnl,
                last_mark_price=excluded.last_mark_price,
                source_order_ids_json=excluded.source_order_ids_json,
                source_execution_ids_json=excluded.source_execution_ids_json,
                reconciliation_flags_json=excluded.reconciliation_flags_json,
                drift_flags_json=excluded.drift_flags_json,
                notes_json=excluded.notes_json,
                take_profit_events_json=excluded.take_profit_events_json,
                updated_at=excluded.updated_at
            """,
            (
                trade["lifecycle_trade_id"],
                trade["run_id"],
                trade.get("symbol"),
                trade.get("side"),
                trade.get("strategy_name"),
                trade.get("status"),
                trade.get("opened_at"),
                trade.get("closed_at"),
                trade.get("quantity_open"),
                trade.get("quantity_closed"),
                trade.get("entry_avg_price"),
                trade.get("exit_avg_price"),
                trade.get("stop_price"),
                trade.get("target_price"),
                trade.get("target_quantity"),
                trade.get("target_type"),
                trade.get("gross_realized_pnl"),
                trade.get("realized_pnl_by_exit_reason_json"),
                trade.get("unrealized_pnl"),
                trade.get("last_mark_price"),
                trade.get("source_order_ids_json"),
                trade.get("source_execution_ids_json"),
                trade.get("reconciliation_flags_json"),
                trade.get("drift_flags_json"),
                trade.get("notes_json"),
                trade.get("take_profit_events_json"),
                trade.get("updated_at"),
                trade.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trade_lifecycle_events(self, events: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO trade_lifecycle_events (
                event_id, run_id, lifecycle_trade_id, symbol, side, event_type, quantity,
                price, timestamp, order_id, execution_id, source, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event["event_id"],
                    event["run_id"],
                    event.get("lifecycle_trade_id"),
                    event.get("symbol"),
                    event.get("side"),
                    event.get("event_type"),
                    event.get("quantity"),
                    event.get("price"),
                    event.get("timestamp"),
                    event.get("order_id"),
                    event.get("execution_id"),
                    event.get("source"),
                    event.get("payload_json"),
                    event.get("created_at"),
                )
                for event in events
            ],
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trade_lifecycle_reconciliation_event(self, event: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO trade_lifecycle_reconciliation_events (
                reconciliation_id, run_id, lifecycle_trade_id, symbol, status, finding_type,
                classification, severity, source, details_json, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["reconciliation_id"],
                event["run_id"],
                event.get("lifecycle_trade_id"),
                event.get("symbol"),
                event.get("status"),
                event.get("finding_type"),
                event.get("classification"),
                event.get("severity"),
                event.get("source"),
                event.get("details_json"),
                event.get("timestamp"),
                event.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trade_lifecycle_summary(self, summary: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO trade_lifecycle_summaries (
                summary_id, run_id, payload_json, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                summary["summary_id"],
                summary["run_id"],
                summary.get("payload_json"),
                summary.get("timestamp"),
                summary.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_stop_authority_event(self, event: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO stop_authority_events (
                event_id, run_id, timestamp, event_type, symbol, lifecycle_trade_id,
                position_id, strategy_owner, entry_order_id, entry_intent_id,
                active_stop_order_id, pending_stop_order_intent, stop_price,
                previous_stop_price, quantity, status, reason, recovery_classification,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event.get("run_id"),
                event.get("timestamp"),
                event.get("event_type"),
                event.get("symbol"),
                event.get("lifecycle_trade_id"),
                event.get("position_id"),
                event.get("strategy_owner"),
                event.get("entry_order_id"),
                event.get("entry_intent_id"),
                event.get("active_stop_order_id"),
                event.get("pending_stop_order_intent"),
                event.get("stop_price"),
                event.get("previous_stop_price"),
                event.get("quantity"),
                event.get("status"),
                event.get("reason"),
                event.get("recovery_classification"),
                event.get("payload_json"),
                event.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_capital_audit_event(self, event: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO capital_audit_events (
                event_id, timestamp, event_type, decision_id, reservation_id,
                trade_id, intent_id, order_id, symbol, strategy_id, run_mode,
                status, requested_quantity, approved_quantity, requested_notional,
                approved_notional, reserved_capital, exposure_before, exposure_after,
                reason, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event.get("timestamp"),
                event.get("event_type"),
                event.get("decision_id"),
                event.get("reservation_id"),
                event.get("trade_id"),
                event.get("intent_id"),
                event.get("order_id"),
                event.get("symbol"),
                event.get("strategy_id"),
                event.get("run_mode"),
                event.get("status"),
                event.get("requested_quantity"),
                event.get("approved_quantity"),
                event.get("requested_notional"),
                event.get("approved_notional"),
                event.get("reserved_capital"),
                event.get("exposure_before"),
                event.get("exposure_after"),
                event.get("reason"),
                event.get("payload_json"),
                event.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_strategy_allocation_audit_event(self, event: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO strategy_allocation_audit_events (
                event_id, timestamp, event_type, decision_id, reservation_id,
                trade_id, intent_id, order_id, strategy_id, symbol, run_mode,
                status, requested_quantity, approved_quantity, requested_notional,
                approved_notional, strategy_capital_limit, reserved_capital,
                used_exposure, reason, global_capital_decision_id,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event.get("timestamp"),
                event.get("event_type"),
                event.get("decision_id"),
                event.get("reservation_id"),
                event.get("trade_id"),
                event.get("intent_id"),
                event.get("order_id"),
                event.get("strategy_id"),
                event.get("symbol"),
                event.get("run_mode"),
                event.get("status"),
                event.get("requested_quantity"),
                event.get("approved_quantity"),
                event.get("requested_notional"),
                event.get("approved_notional"),
                event.get("strategy_capital_limit"),
                event.get("reserved_capital"),
                event.get("used_exposure"),
                event.get("reason"),
                event.get("global_capital_decision_id"),
                event.get("payload_json"),
                event.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trade_admission_rows(self, rows: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO trade_admission_rows (
                admission_row_id, run_id, symbol, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    row["admission_row_id"],
                    row["run_id"],
                    row.get("symbol"),
                    row.get("payload_json"),
                    row.get("created_at"),
                )
                for row in rows
            ],
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trade_blocker_rows(self, rows: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO trade_blocker_rows (
                blocker_row_id, run_id, symbol, blocker_category, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["blocker_row_id"],
                    row["run_id"],
                    row.get("symbol"),
                    row.get("blocker_category"),
                    row.get("payload_json"),
                    row.get("created_at"),
                )
                for row in rows
            ],
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trade_analytics_rows(self, rows: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO trade_analytics_rows (
                analytics_row_id, run_id, trade_id, symbol, realized_pnl, exit_reason, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["analytics_row_id"],
                    row["run_id"],
                    row.get("trade_id"),
                    row.get("symbol"),
                    row.get("realized_pnl"),
                    row.get("exit_reason"),
                    row.get("payload_json"),
                    row.get("created_at"),
                )
                for row in rows
            ],
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_cycle_summary_row(self, row: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO cycle_summary_rows (
                cycle_summary_row_id, run_id, payload_json, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                row["cycle_summary_row_id"],
                row["run_id"],
                row.get("payload_json"),
                row.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trades(self, trades: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO trades (
                trade_id, run_id, symbol, trader_type, strategy_name, direction,
                entry_tick, entry_price, exit_tick, exit_price, quantity,
                gross_pnl, commission, net_pnl, status, pattern_name,
                opened_at, closed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    trade["trade_id"],
                    trade["run_id"],
                    trade.get("symbol"),
                    trade.get("trader_type"),
                    trade.get("strategy_name"),
                    trade.get("direction"),
                    trade.get("entry_tick"),
                    trade.get("entry_price"),
                    trade.get("exit_tick"),
                    trade.get("exit_price"),
                    trade.get("quantity"),
                    trade.get("gross_pnl"),
                    trade.get("commission"),
                    trade.get("net_pnl"),
                    trade.get("status"),
                    trade.get("pattern_name"),
                    trade.get("opened_at"),
                    trade.get("closed_at"),
                    trade.get("created_at"),
                )
                for trade in trades
            ],
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_execution_results(self, results: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO execution_results (
                execution_result_id, run_id, cycle_id, symbol, trader_type, status,
                attempted, direction, requested_quantity, filled_quantity, remaining_quantity,
                fill_status, entry_price, exit_price, gross_realised_pnl, commission,
                net_realised_pnl, slippage_applied, rejection_reason, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    result["execution_result_id"],
                    result["run_id"],
                    result.get("cycle_id"),
                    result.get("symbol"),
                    result.get("trader_type"),
                    result.get("status"),
                    result.get("attempted"),
                    result.get("direction"),
                    result.get("requested_quantity"),
                    result.get("filled_quantity"),
                    result.get("remaining_quantity"),
                    result.get("fill_status"),
                    result.get("entry_price"),
                    result.get("exit_price"),
                    result.get("gross_realised_pnl"),
                    result.get("commission"),
                    result.get("net_realised_pnl"),
                    result.get("slippage_applied"),
                    result.get("rejection_reason"),
                    result.get("payload_json"),
                    result.get("created_at"),
                )
                for result in results
            ],
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trade_outcomes(self, outcomes: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO trade_outcomes (
                trade_outcome_id, run_id, cycle_id, symbol, trader_type, strategy_name,
                direction, entry_price, exit_price, quantity, gross_realised_pnl,
                commission, net_realised_pnl, duration_ticks, outcome, closed_at,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    outcome["trade_outcome_id"],
                    outcome["run_id"],
                    outcome.get("cycle_id"),
                    outcome.get("symbol"),
                    outcome.get("trader_type"),
                    outcome.get("strategy_name"),
                    outcome.get("direction"),
                    outcome.get("entry_price"),
                    outcome.get("exit_price"),
                    outcome.get("quantity"),
                    outcome.get("gross_realised_pnl"),
                    outcome.get("commission"),
                    outcome.get("net_realised_pnl"),
                    outcome.get("duration_ticks"),
                    outcome.get("outcome"),
                    outcome.get("closed_at"),
                    outcome.get("payload_json"),
                    outcome.get("created_at"),
                )
                for outcome in outcomes
            ],
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_performance_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO performance_snapshots (
                performance_snapshot_id, run_id, cycle_id, tick, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot["performance_snapshot_id"],
                snapshot["run_id"],
                snapshot.get("cycle_id"),
                snapshot.get("tick"),
                snapshot.get("payload_json"),
                snapshot.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_watchlist(self, watchlist: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO watchlists (
                watchlist_id, strategy_name, asof_date, session_phase,
                created_at_utc, symbols_json, focus_json, watchlist_hash, metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                watchlist.get("watchlist_id"),
                watchlist.get("strategy_name"),
                watchlist.get("asof_date"),
                watchlist.get("session_phase"),
                watchlist.get("created_at_utc"),
                watchlist.get("symbols_json"),
                watchlist.get("focus_json"),
                watchlist.get("watchlist_hash"),
                watchlist.get("metrics_json"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def fetch_latest_watchlist(self, strategy_name: str, asof_date: str) -> dict[str, Any] | None:
        cursor = self.connection.execute(
            """
            SELECT * FROM watchlists
            WHERE strategy_name = ? AND asof_date = ?
            ORDER BY created_at_utc DESC
            LIMIT 1
            """,
            (strategy_name, asof_date),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_runs(self) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            "SELECT run_id, started_at, started_at_utc, ended_at, ended_at_utc, "
            "run_mode, effective_run_mode, event_replay_mode FROM runs"
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_runs_with_cycle_counts(self) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            """
            SELECT runs.run_id,
                   runs.started_at_utc,
                   runs.run_mode,
                   runs.effective_run_mode,
                   runs.event_replay_mode,
                   COUNT(cycles.cycle_id) as cycles
            FROM runs
            LEFT JOIN cycles ON cycles.run_id = runs.run_id
            GROUP BY runs.run_id
            ORDER BY runs.started_at_utc
            """
        )
        return [dict(row) for row in cursor.fetchall()]

    def commit(self) -> None:
        self.connection.commit()

    def fetch_run(self, run_id: str) -> dict[str, Any] | None:
        cursor = self.connection.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetch_table(self, table: str, run_id: str) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            f"SELECT * FROM {table} WHERE run_id = ?",
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def fetch_cycles(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            "SELECT * FROM cycles WHERE run_id = ? ORDER BY tick ASC",
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def fetch_lifecycle_transitions(
        self,
        run_id: str,
        *,
        symbol: str | None = None,
        trader_type: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM position_lifecycle_transitions WHERE run_id = ?"
        params: list[Any] = [run_id]
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if trader_type:
            query += " AND trader_type = ?"
            params.append(trader_type)
        query += " ORDER BY transition_seq ASC"
        cursor = self.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_events(
        self,
        run_id: str,
        *,
        cycle_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if cycle_id:
            cursor = self.connection.execute(
                """
                SELECT * FROM events
                WHERE run_id = ? AND cycle_id = ?
                ORDER BY tick ASC, timestamp ASC, event_type ASC, source ASC, seq ASC
                """,
                (run_id, cycle_id),
            )
        else:
            cursor = self.connection.execute(
                """
                SELECT * FROM events
                WHERE run_id = ?
                ORDER BY tick ASC, timestamp ASC, event_type ASC, source ASC, seq ASC
                """,
                (run_id,),
            )
        return [dict(row) for row in cursor.fetchall()]

    def fetch_trade_records(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            "SELECT * FROM trade_records WHERE run_id = ? ORDER BY tick ASC",
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def fetch_trade_lifecycle_trades(
        self,
        run_id: str,
        *,
        status: str | None = None,
        symbol: str | None = None,
        open_only: bool = False,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM trade_lifecycle_trades WHERE run_id = ?"
        params: list[Any] = [run_id]
        if open_only:
            query += (
                " AND status IN ("
                "'OPEN', 'PARTIALLY_CLOSED', 'DRIFTED', 'PARTIALLY_FILLED', "
                "'PROTECTION_PENDING', 'PROTECTED', 'TARGET_ACTIVE'"
                ") AND COALESCE(quantity_open, 0) > 0"
            )
        if status:
            query += " AND status = ?"
            params.append(status)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY opened_at ASC, lifecycle_trade_id ASC"
        cursor = self.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_open_trade_lifecycle_trades(self, *, symbol: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM trade_lifecycle_trades
            WHERE status IN (
                'OPEN', 'PARTIALLY_CLOSED', 'DRIFTED', 'PARTIALLY_FILLED',
                'PROTECTION_PENDING', 'PROTECTED', 'TARGET_ACTIVE'
            )
            AND COALESCE(quantity_open, 0) > 0
        """
        params: list[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY opened_at ASC, lifecycle_trade_id ASC"
        cursor = self.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_trade_lifecycle_events(
        self,
        run_id: str,
        *,
        lifecycle_trade_id: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM trade_lifecycle_events WHERE run_id = ?"
        params: list[Any] = [run_id]
        if lifecycle_trade_id:
            query += " AND lifecycle_trade_id = ?"
            params.append(lifecycle_trade_id)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY timestamp ASC, created_at ASC"
        cursor = self.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_trade_lifecycle_reconciliation_events(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            """
            SELECT * FROM trade_lifecycle_reconciliation_events
            WHERE run_id = ?
            ORDER BY timestamp ASC, created_at ASC
            """,
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def fetch_stop_authority_events(
        self,
        run_id: str,
        *,
        lifecycle_trade_id: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM stop_authority_events WHERE run_id = ?"
        params: list[Any] = [run_id]
        if lifecycle_trade_id:
            query += " AND lifecycle_trade_id = ?"
            params.append(lifecycle_trade_id)
        if symbol:
            query += " AND symbol = ?"
            params.append(str(symbol).upper())
        query += " ORDER BY timestamp ASC, event_id ASC"
        cursor = self.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_trade_outcomes(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            "SELECT * FROM trade_outcomes WHERE run_id = ? ORDER BY closed_at ASC",
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def fetch_performance_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            "SELECT * FROM performance_snapshots WHERE run_id = ? ORDER BY created_at ASC",
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_cycle_warnings(self, cycle_id: str, warnings_json: str) -> None:
        self.connection.execute(
            "UPDATE cycles SET warnings_json = ? WHERE cycle_id = ?",
            (warnings_json, cycle_id),
        )
        if self.commit_each_write:
            self.connection.commit()

    def export_run(self, run_id: str, fmt: str, out_path: str) -> list[str]:
        tables = [
            "runs",
            "cycles",
            "events",
            "trade_records",
            "trades",
            "execution_results",
            "trade_outcomes",
            "performance_snapshots",
            "stop_authority_events",
        ]
        fmt = fmt.lower()
        created_files: list[str] = []
        if fmt == "jsonl":
            rows: list[dict[str, Any]] = []
            for table in tables:
                for row in self.fetch_table(table, run_id):
                    rows.append({"table": table, "row": row})
            with open(out_path, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            created_files.append(out_path)
            return created_files
        if fmt != "csv":
            raise ValueError(f"Unsupported export format: {fmt}")
        os.makedirs(out_path, exist_ok=True)
        for table in tables:
            table_path = os.path.join(out_path, f"{table}.csv")
            rows = self.fetch_table(table, run_id)
            if not rows:
                continue
            fieldnames = list(rows[0].keys())
            with open(table_path, "w", encoding="utf-8") as handle:
                handle.write(",".join(fieldnames) + "\n")
                for row in rows:
                    handle.write(",".join(_csv_escape(row.get(field) for field in fieldnames)) + "\n")
            created_files.append(table_path)
        return created_files

    def export_events(self, run_id: str, fmt: str, out_path: str) -> list[str]:
        fmt = fmt.lower()
        events = self.fetch_events(run_id)
        if fmt == "jsonl":
            _write_jsonl(out_path, events)
            return [out_path]
        if fmt != "csv":
            raise ValueError(f"Unsupported export format: {fmt}")
        _write_csv(out_path, events)
        return [out_path]

    def export_trade_records(self, run_id: str, fmt: str, out_path: str) -> list[str]:
        fmt = fmt.lower()
        records = self.fetch_trade_records(run_id)
        if fmt == "json":
            with open(out_path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(records, ensure_ascii=False, sort_keys=True))
            return [out_path]
        if fmt != "csv":
            raise ValueError(f"Unsupported export format: {fmt}")
        _write_csv(out_path, records)
        return [out_path]

    def verify_audit_chain(self, run_id: str) -> AuditVerificationResult:
        cursor = self.connection.execute(
            "SELECT seq, event_type, source, timestamp, payload_json, prev_hash, event_hash, cycle_id "
            "FROM events WHERE run_id = ? ORDER BY seq ASC",
            (run_id,),
        )
        prev_hash = "GENESIS"
        for row in cursor.fetchall():
            payload = json.loads(row["payload_json"]) if row["payload_json"] else None
            event_payload = {
                "run_id": run_id,
                "cycle_id": row["cycle_id"],
                "seq": row["seq"],
                "event_type": row["event_type"],
                "source": row["source"],
                "timestamp": row["timestamp"],
                "payload": payload,
            }
            expected_hash = compute_audit_hash(prev_hash, event_payload)
            if row["prev_hash"] != prev_hash:
                return AuditVerificationResult(
                    ok=False,
                    first_bad_seq=row["seq"],
                    reason="prev_hash mismatch",
                )
            if row["event_hash"] != expected_hash:
                return AuditVerificationResult(
                    ok=False,
                    first_bad_seq=row["seq"],
                    reason="event_hash mismatch",
                )
            prev_hash = row["event_hash"]
        return AuditVerificationResult(ok=True, first_bad_seq=None, reason="ok")

    def _record_schema_version(self) -> None:
        self.connection.execute(
            """
            INSERT INTO schema_meta (version, applied_at_utc)
            SELECT ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM schema_meta WHERE version = ?)
            """,
            (SCHEMA_VERSION, now_iso(), SCHEMA_VERSION),
        )

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        existing = self._column_names(table)
        for column, col_type in columns.items():
            if column in existing:
                continue
            self.connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            )

    def _column_names(self, table: str) -> set[str]:
        cursor = self.connection.execute(f"PRAGMA table_info({table})")
        return {row["name"] for row in cursor.fetchall()}

    def initialize_synthetic_capital_scope(self, scope: str, mode: str):
        """Explicit test enrollment only. Never initialize an operational database."""
        if (os.environ.get("EXECUTION_ENV") != "TEST" or (not isinstance(scope,str) or not 1 <= len(scope) <= 256 or not scope.startswith("synthetic:"))
                or mode not in {"SIM", "PAPER"} or self.connection.in_transaction
                or self.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]):
            raise RuntimeError("CAPITAL_OPERATIONAL_ENROLLMENT_FORBIDDEN")
        self._capital_schema_check(base_only=True)
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            marker=self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='capital_synthetic_database'").fetchone()
            if marker is None:
                tables=[r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='schema_meta'")]
                if any(self.connection.execute('SELECT 1 FROM "'+name.replace('"','""')+'" LIMIT 1').fetchone() for name in tables):
                    raise RuntimeError('CAPITAL_NONFRESH_DATABASE_QUARANTINED')
                self.connection.execute("CREATE TABLE capital_synthetic_database (version INTEGER PRIMARY KEY CHECK(version=2))")
                self.connection.execute("INSERT INTO capital_synthetic_database VALUES (2)")
            elif [r[0] for r in self.connection.execute("SELECT version FROM capital_synthetic_database")] != [2]:
                raise RuntimeError('CAPITAL_SYNTHETIC_SCHEMA_UNSUPPORTED')
            self.connection.execute("CREATE TABLE IF NOT EXISTS capital_owner_state (scope TEXT PRIMARY KEY, mode TEXT NOT NULL, schema_version INTEGER NOT NULL, version INTEGER NOT NULL, fence TEXT NOT NULL, pending TEXT, last_operation TEXT, writer_id TEXT NOT NULL)")
            self.connection.execute("CREATE TABLE IF NOT EXISTS capital_owner_reservations (scope TEXT NOT NULL, reservation_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(scope,reservation_id))")
            self.connection.execute("CREATE TABLE IF NOT EXISTS capital_owner_exposure (scope TEXT NOT NULL, dimension TEXT NOT NULL, name TEXT NOT NULL, amount REAL NOT NULL, PRIMARY KEY(scope,dimension,name))")
            self.connection.execute("CREATE TABLE IF NOT EXISTS capital_owner_execution (scope TEXT NOT NULL, identity TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(scope,identity))")
            writer_id = uuid4().hex
            self.connection.execute("INSERT INTO capital_owner_state VALUES (?,?,2,0,'SYNTHETIC_ONLY_V2',NULL,NULL,?)", (scope,mode,writer_id))
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

        writer = _CapitalWriter()
        path = os.path.normcase(os.path.realpath(self.path))
        stat = os.stat(path)
        self._capital_writers[scope] = (writer, {
            'issuer': weakref.ref(self), 'pid': os.getpid(), 'path': path,
            'file_id': (stat.st_dev,stat.st_ino), 'scope':scope,'mode':mode,
            'writer_id':writer_id, 'owner':None, 'claimed':False, 'revoked':False})
        return writer

    def _validate_capital_writer(self, writer, owner, scope, mode, *, claiming=False):
        entry = self._capital_writers.get(scope)
        if type(writer) is not _CapitalWriter or entry is None or entry[0] is not writer:
            raise _CapitalWriterRejected('CAPITAL_WRITER_SESSION_REQUIRED')
        record = entry[1]  # Authority stays issuer-private; token has no fields.
        if (record['issuer']() is not self or record['pid'] != os.getpid()
                or record['scope'] != scope or record['mode'] != mode):
            raise _CapitalWriterRejected('CAPITAL_WRITER_SESSION_REQUIRED')
        if record['revoked']:
            raise _CapitalWriterRejected('CAPITAL_WRITER_REVOKED')
        path = os.path.normcase(os.path.realpath(self.path))
        stat = os.stat(path)
        files = self.connection.execute('PRAGMA database_list').fetchall()
        actual = next((r['file'] for r in files if r['name']=='main'), None)
        if (path != record['path'] or (stat.st_dev,stat.st_ino) != record['file_id']
                or not actual or os.path.normcase(os.path.realpath(actual)) != record['path']
                or (not claiming and (not record['claimed'] or record['owner']() is not owner))
                or (claiming and record['claimed'] and record['owner']() is not owner)):
            raise _CapitalWriterRejected('CAPITAL_WRITER_IDENTITY_CONFLICT')
        return record['writer_id']

    def revoke_capital_writer(self, writer, owner, scope):
        """Only revoke this exact live claimant; no SQL, reset or transfer."""
        entry = self._capital_writers.get(scope)
        if (entry is not None and entry[0] is writer and entry[1]['pid']==os.getpid()
                and entry[1]['claimed'] and entry[1]['owner']() is owner):
            entry[1]['revoked'] = True

    def claim_capital_writer(self, writer, owner, scope, mode):
        writer_id = self._validate_capital_writer(writer, owner, scope, mode, claiming=True)
        self._capital_schema_check()
        state = self.read_capital_state(scope,mode)
        if state['schema_version'] != 2 or state['writer_id'] != writer_id:
            raise _CapitalWriterRejected('CAPITAL_WRITER_SCOPE_CONFLICT')
        record = self._capital_writers[scope][1]
        if not record['claimed']:
            record['owner'], record['claimed'] = weakref.ref(owner), True
        return writer

    def _capital_schema_check(self, *, base_only: bool = False) -> None:
        if (self.connection.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0] != SCHEMA_VERSION
                or self.connection.in_transaction or self.connection.execute("PRAGMA query_only").fetchone()[0]):
            raise RuntimeError("CAPITAL_STORAGE_UNSUPPORTED_OR_BUSY")
        if not base_only and os.environ.get("EXECUTION_ENV") != "TEST":
            raise RuntimeError("CAPITAL_OPERATIONAL_ACCESS_UNFENCED")
        # Receipt durability must not depend on cycle-flush configuration.
        self.connection.execute("PRAGMA synchronous=FULL")
        if self.connection.execute("PRAGMA synchronous").fetchone()[0] < 2:
            raise RuntimeError("CAPITAL_DURABILITY_UNAVAILABLE")

    def _capital_load(self, scope: str, mode: str) -> dict:
        row = self.connection.execute("SELECT * FROM capital_owner_state WHERE scope=?", (scope,)).fetchone()
        if (row is None or row['schema_version'] not in (1,2) or row['mode'] != mode
                or row['fence'] != ('SYNTHETIC_ONLY_V1' if row['schema_version']==1 else 'SYNTHETIC_ONLY_V2') or not scope.startswith('synthetic:')):
            raise RuntimeError("CAPITAL_SCOPE_UNENROLLED_OR_UNFENCED")
        if row['schema_version']==2 and (not isinstance(row['writer_id'],str) or not 1 <= len(row['writer_id']) <= 256):
            raise RuntimeError('CAPITAL_WRITER_IDENTITY_INVALID')
        if not self.connection.execute("SELECT 1 FROM capital_synthetic_database WHERE version IN (1,2)").fetchone():
            raise RuntimeError('CAPITAL_UNFENCED_DATABASE')
        reservations = {r['reservation_id']: json.loads(r['payload']) for r in self.connection.execute(
            "SELECT * FROM capital_owner_reservations WHERE scope=?", (scope,))}
        exposure = {'symbol': {}, 'strategy': {}}
        for r in self.connection.execute("SELECT * FROM capital_owner_exposure WHERE scope=?", (scope,)):
            exposure[r['dimension']][r['name']] = r['amount']
        if type(row['version']) is not int or row['version'] < 0:
            raise RuntimeError('CAPITAL_CORRUPT_VERSION')
        decisions=set()
        for key, r in reservations.items():
            if (r.get('decision_id') in decisions or r.get('remaining_quantity',0) > r.get('quantity',0)
                    or r.get('filled_quantity',0) > r.get('quantity',0) or r.get('filled_quantity',0)+r.get('remaining_quantity',0) > r.get('quantity',0)
                    or r.get('reservation_id') != key or r.get('run_mode') != mode
                    or any(type(r.get(k)) is not int or r[k] < 0 for k in ('quantity','remaining_quantity','filled_quantity'))
                    or any(isinstance(r.get(k), bool) or not isinstance(r.get(k),(int,float)) or not math.isfinite(r[k]) or r[k] < 0
                           for k in ('notional','remaining_notional','exposure_notional'))
                    or r.get('status') not in {'ACTIVE','CONVERTED','RELEASED'}):
                raise RuntimeError('CAPITAL_CORRUPT_RESERVATION')
            decisions.add(r['decision_id'])
            from src.core.capital_management_authority import CapitalReservation
            CapitalReservation(**{k:v for k,v in r.items() if k!='effect_identity'})  # Exact supported owner fields.
        if any(not math.isfinite(v) or v < 0 for values in exposure.values() for v in values.values()):
            raise RuntimeError('CAPITAL_CORRUPT_EXPOSURE')
        progress={r['identity']:json.loads(r['payload']) for r in self.connection.execute('SELECT * FROM capital_owner_execution WHERE scope=?',(scope,))}
        from src.storage.storage_engine import StorageEngine
        for key,b in progress.items():
            StorageEngine._owner_effect_record(b,phase='PREPARED')
            if key != json.dumps([b['relationship_id'],b['order_id'],b['effect']]):
                raise RuntimeError('CAPITAL_CORRUPT_PROGRESS_IDENTITY')
        for r in reservations.values():
            b=r.get('effect_identity')
            if b is not None:
                StorageEngine._owner_effect_record(b,phase='PREPARED')
                if (b['decision_id']!=r['decision_id'] or b['order_id']!=r['order_id'] or b['symbol']!=r['symbol']
                        or b['effect']!='CONVERT' or b['owner']!='capital' or b['mode']!=mode
                        or progress.get(json.dumps([b['relationship_id'],b['order_id'],b['effect']]))!=b):
                    raise RuntimeError('CAPITAL_CORRUPT_RESERVATION_BINDING')
        state={'schema_version':row['schema_version'],'writer_id':row['writer_id'] if row['schema_version']==2 else None,'version':row['version'],'pending':row['pending'],'reservations':reservations,'progress':progress,**exposure}
        if row['version']==0:
            if row['last_operation'] is not None or reservations or progress or any(exposure.values()):
                raise RuntimeError('CAPITAL_ZERO_VERSION_NOT_EMPTY')
        else:
            receipt=self.connection.execute('SELECT reason FROM position_lifecycle_transitions WHERE transition_id=?',
                ('capital-atomic-v'+str(row['schema_version'])+':'+scope+':'+str(row['last_operation']),)).fetchone()
            saved=json.loads(receipt[0]) if receipt else {}
            if (saved.get('atomic_capital_only') is not True or saved.get('scope')!=scope
                    or type(saved.get('schema')) is not int or saved['schema']!=row['schema_version']
                    or (row['schema_version']==2 and (not isinstance(state['writer_id'],str) or not state['writer_id'] or saved.get('writer_id')!=state['writer_id']))
                    or saved.get('after_version')!=row['version']
                    or saved.get('state_hash')!=self._capital_state_hash(scope,mode,row['version'],state)):
                raise RuntimeError('CAPITAL_STATE_RECEIPT_INTEGRITY_FAILURE')
        return state

    @staticmethod
    def _capital_state_hash(scope: str, mode: str, version: int, state: dict) -> str:
        # Private integrity binding, not independent publisher/execution authority.
        content={'scope':scope,'mode':mode,'version':version,
            **{k:state[k] for k in ('reservations','symbol','strategy','progress')}}
        if state.get('schema_version')==2:
            content['writer_id']=state['writer_id']
        return hashlib.sha256(json.dumps(content,sort_keys=True,allow_nan=False).encode()).hexdigest()

    def read_capital_state(self, scope: str, mode: str) -> dict:
        self._capital_schema_check()
        try:
            self.connection.execute("BEGIN")
            state = self._capital_load(scope,mode)
            self.connection.rollback()
            return state
        except BaseException:
            self.connection.rollback()
            raise

    def transact_capital(self, scope: str, mode: str, operation: str, binding: str, apply, *, writer=None, owner=None) -> tuple[dict, bool]:
        """One existing-owner state transition and receipt; callback is pure local policy."""
        writer_id = self._validate_capital_writer(writer,owner,scope,mode)
        self._capital_schema_check()
        receipt_id = 'capital-atomic-v2:' + scope + ':' + operation
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            before = self._capital_load(scope,mode)
            if before['schema_version']!=2 or before['writer_id']!=writer_id:
                raise _CapitalWriterRejected('CAPITAL_WRITER_SCOPE_CONFLICT')
            self._validate_capital_writer(writer,owner,scope,mode)
            if before['pending'] is not None:
                raise RuntimeError('CAPITAL_PENDING_AUTHORITATIVE_INSPECTION')
            previous = self.connection.execute("SELECT reason FROM position_lifecycle_transitions WHERE transition_id=?", (receipt_id,)).fetchone()
            if previous:
                saved=json.loads(previous[0])
                if (set(saved)!={'schema','scope','binding','before_version','after_version','post_state','result','atomic_capital_only','state_hash','writer_id'}
                        or saved['binding'] != binding or type(saved['schema']) is not int or saved['schema'] != 2 or saved['scope'] != scope or saved['writer_id'] != writer_id
                        or saved['atomic_capital_only'] is not True
                        or type(saved['before_version']) is not int or saved['before_version'] < 0
                        or type(saved['after_version']) is not int or saved['after_version']!=saved['before_version']+1
                        or saved['after_version']>before['version'] or not isinstance(saved['post_state'],dict)
                        or set(saved['result'])!={'type','value'} or saved['result']['type'] not in {'decision','reservation','scalar'}):
                    raise RuntimeError("CAPITAL_EFFECT_IDENTITY_CONFLICT")
                self.connection.rollback()
                return saved['result'], True
            # A separate durable processing marker survives lost acknowledgements,
            # known interruptions and restart. It is not a financial effect.
            self.connection.execute("UPDATE capital_owner_state SET pending=? WHERE scope=?", (operation,scope))
            self.connection.commit()
            self.connection.execute("BEGIN IMMEDIATE")
            current=self._capital_load(scope,mode)
            if current['pending']!=operation or current['version']!=before['version']:
                raise RuntimeError('CAPITAL_PENDING_IDENTITY_CONFLICT')
            after, result = apply(before)
            self.connection.execute("DELETE FROM capital_owner_reservations WHERE scope=?", (scope,))
            self.connection.executemany("INSERT INTO capital_owner_reservations VALUES (?,?,?)", [
                (scope,k,json.dumps(v,sort_keys=True,allow_nan=False)) for k,v in after['reservations'].items()])
            self.connection.execute("DELETE FROM capital_owner_exposure WHERE scope=?", (scope,))
            self.connection.executemany("INSERT INTO capital_owner_exposure VALUES (?,?,?,?)", [
                (scope,dimension,k,v) for dimension in ('symbol','strategy') for k,v in after[dimension].items()])
            self.connection.execute("DELETE FROM capital_owner_execution WHERE scope=?", (scope,))
            self.connection.executemany("INSERT INTO capital_owner_execution VALUES (?,?,?)", [
                (scope,k,json.dumps(v,sort_keys=True,allow_nan=False)) for k,v in after['progress'].items()])
            changed=self.connection.execute("UPDATE capital_owner_state SET version=version+1,last_operation=? WHERE scope=? AND version=?", (operation,scope,before['version'])).rowcount
            if changed != 1:
                raise RuntimeError("CAPITAL_STATE_VERSION_CONFLICT")
            after.update(schema_version=2,writer_id=writer_id)
            outcome={'schema':2,'writer_id':writer_id,'scope':scope,'binding':binding,'before_version':before['version'],
                'after_version':before['version']+1,'post_state':{'reservations':{k:v for k,v in after['reservations'].items() if before['reservations'].get(k)!=v},'symbol':{k:v for k,v in after['symbol'].items() if before['symbol'].get(k)!=v},'strategy':{k:v for k,v in after['strategy'].items() if before['strategy'].get(k)!=v}},'result':result,'atomic_capital_only':True,'state_hash':self._capital_state_hash(scope,mode,before['version']+1,after)}
            self.connection.execute("INSERT INTO position_lifecycle_transitions (transition_id,intent,reason_code,reason,transition_seq,timestamp,created_at) VALUES (?,?,?,?,?,?,?)",
                (receipt_id,'CAPITAL_OWNER_EFFECT','ATOMIC_CAPITAL_V2',json.dumps(outcome,sort_keys=True,allow_nan=False),before['version']+1,now_iso(),now_iso()))
            self.connection.commit()
            # Retire only this uninterrupted call's marker after confirmed commit.
            # Errors/crashes leave it quarantined; no replay/clear API exists.
            self.connection.execute("BEGIN IMMEDIATE")
            changed=self.connection.execute("UPDATE capital_owner_state SET pending=NULL WHERE scope=? AND pending=?", (scope,operation)).rowcount
            if changed!=1:
                raise RuntimeError('CAPITAL_PENDING_COMPLETION_CONFLICT')
            self.connection.commit()
            return result, False
        except _CapitalWriterRejected:
            self.connection.rollback()
            raise
        except BaseException:
            self.connection.rollback()
            # Persist an observed interrupted return even if normal completion
            # committed but its acknowledgement was lost. Never clear/replay.
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                self.connection.execute("UPDATE capital_owner_state SET pending=COALESCE(pending,?) WHERE scope=? AND schema_version=2 AND writer_id=? AND fence='SYNTHETIC_ONLY_V2'", (operation,scope,writer_id))
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                # Fail explicitly: never present the original error as proof
                # that the separate quarantine observation became durable.
                raise RuntimeError('CAPITAL_QUARANTINE_PERSISTENCE_UNKNOWN')
            raise

    def insert_owner_effect_record(self, transition_id: str, payload: str, *, run_id: str | None,
                                   prepared_id: str | None = None, prepared_payload: str | None = None) -> None:
        """Append-only evidence in the existing lifecycle audit table, not a balance ledger."""
        if self.connection.in_transaction:
            raise RuntimeError("OWNER_EFFECT_UNOWNED_TRANSACTION")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            if prepared_id is not None:
                row = self.connection.execute("SELECT reason FROM position_lifecycle_transitions WHERE transition_id=?", (prepared_id,)).fetchone()
                if row is None or row[0] != prepared_payload:
                    raise RuntimeError("OWNER_EFFECT_PREPARE_CONFLICT")
            self.connection.execute(
                "INSERT INTO position_lifecycle_transitions (transition_id,run_id,intent,reason_code,reason,transition_seq,timestamp,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (transition_id, run_id, "OWNER_EFFECT_EVIDENCE", "NON_ATOMIC_V1", payload, 0, now_iso(), now_iso()))
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def fetch_owner_effect_record(self, transition_id: str) -> str | None:
        row = self.connection.execute("SELECT reason FROM position_lifecycle_transitions WHERE transition_id=?", (transition_id,)).fetchone()
        return row[0] if row else None


def _csv_escape(values: Iterable[Any]) -> list[str]:
    escaped: list[str] = []
    for value in values:
        if value is None:
            escaped.append("")
            continue
        text = str(value)
        if "," in text or "\n" in text or "\"" in text:
            text = '"' + text.replace("\"", '""') + '"'
        escaped.append(text)
    return escaped


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: str, rows: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not rows:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(",".join(fieldnames) + "\n")
        for row in rows:
            handle.write(",".join(_csv_escape(row.get(field) for field in fieldnames)) + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
