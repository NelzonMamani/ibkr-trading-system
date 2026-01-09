from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Iterable

from src.storage.serialization import compute_audit_hash


SCHEMA_VERSION = 1


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
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT,
                ended_at TEXT,
                hostname TEXT,
                user TEXT,
                app_version TEXT,
                git_sha TEXT,
                run_mode TEXT,
                event_replay_mode TEXT,
                resolved_config_json TEXT,
                schema_version INTEGER,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS cycles (
                cycle_id TEXT PRIMARY KEY,
                run_id TEXT,
                tick INTEGER,
                session TEXT,
                cycle_started_at TEXT,
                cycle_ended_at TEXT,
                scanner_n INTEGER,
                patterns_n INTEGER,
                intents_n INTEGER,
                risk_n INTEGER,
                exec_n INTEGER,
                closed_n INTEGER,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT,
                cycle_id TEXT,
                event_type TEXT,
                source TEXT,
                timestamp TEXT,
                payload_json TEXT,
                seq INTEGER,
                prev_hash TEXT,
                event_hash TEXT,
                created_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id),
                FOREIGN KEY(cycle_id) REFERENCES cycles(cycle_id)
            );
            CREATE TABLE IF NOT EXISTS trade_records (
                trade_record_id TEXT PRIMARY KEY,
                run_id TEXT,
                cycle_id TEXT,
                tick INTEGER,
                scanner_output_json TEXT,
                pattern_output_json TEXT,
                strategy_output_json TEXT,
                risk_output_json TEXT,
                execution_output_json TEXT,
                trade_outcomes_json TEXT,
                performance_snapshot_json TEXT,
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
            CREATE INDEX IF NOT EXISTS idx_cycles_run_id ON cycles(run_id);
            CREATE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq);
            CREATE INDEX IF NOT EXISTS idx_events_cycle_id ON events(cycle_id);
            CREATE INDEX IF NOT EXISTS idx_trade_records_run_id ON trade_records(run_id);
            CREATE INDEX IF NOT EXISTS idx_trades_run_id ON trades(run_id);
            """
        )
        self.connection.commit()

    def insert_run(self, run_data: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO runs (
                run_id, started_at, ended_at, hostname, user, app_version, git_sha,
                run_mode, event_replay_mode, resolved_config_json, schema_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_data["run_id"],
                run_data.get("started_at"),
                run_data.get("ended_at"),
                run_data.get("hostname"),
                run_data.get("user"),
                run_data.get("app_version"),
                run_data.get("git_sha"),
                run_data.get("run_mode"),
                run_data.get("event_replay_mode"),
                run_data.get("resolved_config_json"),
                run_data.get("schema_version"),
                run_data.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_cycle(self, cycle_data: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO cycles (
                cycle_id, run_id, tick, session, cycle_started_at, cycle_ended_at,
                scanner_n, patterns_n, intents_n, risk_n, exec_n, closed_n, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_events(self, events: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT INTO events (
                event_id, run_id, cycle_id, event_type, source, timestamp,
                payload_json, seq, prev_hash, event_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event["event_id"],
                    event["run_id"],
                    event.get("cycle_id"),
                    event["event_type"],
                    event["source"],
                    event["timestamp"],
                    event.get("payload_json"),
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

    def insert_trade_record(self, trade_record: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO trade_records (
                trade_record_id, run_id, cycle_id, tick,
                scanner_output_json, pattern_output_json, strategy_output_json,
                risk_output_json, execution_output_json, trade_outcomes_json,
                performance_snapshot_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_record["trade_record_id"],
                trade_record["run_id"],
                trade_record.get("cycle_id"),
                trade_record.get("tick"),
                trade_record.get("scanner_output_json"),
                trade_record.get("pattern_output_json"),
                trade_record.get("strategy_output_json"),
                trade_record.get("risk_output_json"),
                trade_record.get("execution_output_json"),
                trade_record.get("trade_outcomes_json"),
                trade_record.get("performance_snapshot_json"),
                trade_record.get("created_at"),
            ),
        )
        if self.commit_each_write:
            self.connection.commit()

    def insert_trades(self, trades: Iterable[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT INTO trades (
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

    def list_runs(self) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            "SELECT run_id, started_at, ended_at, run_mode, event_replay_mode FROM runs"
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

    def export_run(self, run_id: str, fmt: str, out_path: str) -> list[str]:
        tables = ["runs", "cycles", "events", "trade_records", "trades"]
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
