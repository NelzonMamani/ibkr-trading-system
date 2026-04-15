from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Iterable

from src.storage.serialization import compute_audit_hash


SCHEMA_VERSION = 6


@dataclass
class AuditVerificationResult:
    ok: bool
    first_bad_seq: int | None
    reason: str


class SQLiteStore:
    def __init__(self, path: str, *, commit_each_write: bool = True) -> None:
        self.path = path
        self.commit_each_write = commit_each_write
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.connection.close()

    def initialize_schema(self) -> None:
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
                gross_realized_pnl REAL,
                unrealized_pnl REAL,
                last_mark_price REAL,
                source_order_ids_json TEXT,
                source_execution_ids_json TEXT,
                reconciliation_flags_json TEXT,
                drift_flags_json TEXT,
                notes_json TEXT,
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
                transition_id, run_id, symbol, trader_type, from_state, to_state, intent,
                reason_code, reason, mode, requested_quantity, filled_quantity, quantity_before,
                quantity_after, fill_status, execution_blocked, fill_latency_ms, transition_seq,
                timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    transition["transition_id"],
                    transition["run_id"],
                    transition.get("symbol"),
                    transition.get("trader_type"),
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
                gross_realized_pnl, unrealized_pnl, last_mark_price, source_order_ids_json,
                source_execution_ids_json, reconciliation_flags_json, drift_flags_json, notes_json,
                updated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                gross_realized_pnl=excluded.gross_realized_pnl,
                unrealized_pnl=excluded.unrealized_pnl,
                last_mark_price=excluded.last_mark_price,
                source_order_ids_json=excluded.source_order_ids_json,
                source_execution_ids_json=excluded.source_execution_ids_json,
                reconciliation_flags_json=excluded.reconciliation_flags_json,
                drift_flags_json=excluded.drift_flags_json,
                notes_json=excluded.notes_json,
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
                trade.get("gross_realized_pnl"),
                trade.get("unrealized_pnl"),
                trade.get("last_mark_price"),
                trade.get("source_order_ids_json"),
                trade.get("source_execution_ids_json"),
                trade.get("reconciliation_flags_json"),
                trade.get("drift_flags_json"),
                trade.get("notes_json"),
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
                details_json, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["reconciliation_id"],
                event["run_id"],
                event.get("lifecycle_trade_id"),
                event.get("symbol"),
                event.get("status"),
                event.get("finding_type"),
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
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM trade_lifecycle_trades WHERE run_id = ?"
        params: list[Any] = [run_id]
        if status:
            query += " AND status = ?"
            params.append(status)
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
