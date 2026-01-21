from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any
from uuid import uuid4

from src.config.runtime_config import get_persistence_sqlite_path
from src.storage.serialization import canonical_json
from src.storage.sqlite_store import SQLiteStore
from src.storage.storage_engine import StorageEngine


@dataclass(frozen=True)
class LearningRunRecord:
    run_id: str
    started_at_utc: str
    completed_at_utc: str | None
    ok: bool
    error: str | None
    strategy_name: str
    window_start_utc: str | None
    window_end_utc: str | None
    inputs_hash: str | None
    outputs_hash: str | None


class LearningStorage:
    def __init__(self, sqlite_path: str | None = None) -> None:
        raw_path = sqlite_path or get_persistence_sqlite_path()
        resolved = StorageEngine._resolve_repo_relative_path(raw_path)
        self.store = SQLiteStore(resolved, commit_each_write=True)
        self.store.initialize_schema()

    def close(self) -> None:
        self.store.close()

    def fetch_trade_outcomes(self, strategy_name: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM trade_outcomes"
        params: list[Any] = []
        if strategy_name:
            query += " WHERE strategy_name = ?"
            params.append(strategy_name)
        query += " ORDER BY closed_at ASC"
        cursor = self.store.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_watchlists(self, strategy_name: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM watchlists"
        params: list[Any] = []
        if strategy_name:
            query += " WHERE strategy_name = ?"
            params.append(strategy_name)
        query += " ORDER BY created_at_utc ASC"
        cursor = self.store.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def insert_learning_run(self, record: LearningRunRecord) -> None:
        self.store.connection.execute(
            """
            INSERT OR REPLACE INTO learning_runs (
                run_id, started_at_utc, completed_at_utc, ok, error,
                strategy_name, window_start_utc, window_end_utc,
                inputs_hash, outputs_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run_id,
                record.started_at_utc,
                record.completed_at_utc,
                1 if record.ok else 0,
                record.error,
                record.strategy_name,
                record.window_start_utc,
                record.window_end_utc,
                record.inputs_hash,
                record.outputs_hash,
            ),
        )
        self.store.connection.commit()

    def insert_learning_report(
        self,
        *,
        run_id: str,
        report_type: str,
        asof_date_ny: str,
        strategy_name: str,
        payload: dict[str, Any],
        summary_text: str,
    ) -> str:
        report_id = str(uuid4())
        self.store.connection.execute(
            """
            INSERT OR REPLACE INTO learning_reports (
                report_id, run_id, report_type, asof_date_ny, strategy_name,
                payload_json, summary_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                run_id,
                report_type,
                asof_date_ny,
                strategy_name,
                canonical_json(payload, allow_fallback=True),
                summary_text,
            ),
        )
        self.store.connection.commit()
        return report_id

    def list_reports(self, strategy_name: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM learning_reports"
        params: list[Any] = []
        if strategy_name:
            query += " WHERE strategy_name = ?"
            params.append(strategy_name)
        query += " ORDER BY asof_date_ny DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        cursor = self.store.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_report(self, report_id: str) -> dict[str, Any] | None:
        cursor = self.store.connection.execute(
            "SELECT * FROM learning_reports WHERE report_id = ?",
            (report_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def insert_policy_proposal(
        self,
        *,
        strategy_name: str,
        baseline_policy_version: str,
        min_trades_required: int,
        trades_used: int,
        proposal: dict[str, Any],
        diff: dict[str, Any],
        rationale: dict[str, Any],
    ) -> str:
        proposal_id = str(uuid4())
        self.store.connection.execute(
            """
            INSERT INTO policy_proposals (
                proposal_id, created_at_utc, strategy_name, baseline_policy_version,
                min_trades_required, trades_used, proposal_json, diff_json,
                rationale_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                datetime.utcnow().isoformat(),
                strategy_name,
                baseline_policy_version,
                min_trades_required,
                trades_used,
                canonical_json(proposal, allow_fallback=True),
                canonical_json(diff, allow_fallback=True),
                canonical_json(rationale, allow_fallback=True),
                "DRAFT",
            ),
        )
        self.store.connection.commit()
        return proposal_id

    def update_policy_proposal(
        self,
        proposal_id: str,
        *,
        status: str,
        approved_by: str | None = None,
        rejection_reason: str | None = None,
    ) -> None:
        self.store.connection.execute(
            """
            UPDATE policy_proposals
            SET status = ?, approved_by = ?, approved_at_utc = ?, rejection_reason = ?
            WHERE proposal_id = ?
            """,
            (
                status,
                approved_by,
                datetime.utcnow().isoformat() if approved_by else None,
                rejection_reason,
                proposal_id,
            ),
        )
        self.store.connection.commit()

    def list_policy_proposals(self, strategy_name: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM policy_proposals"
        params: list[Any] = []
        if strategy_name:
            query += " WHERE strategy_name = ?"
            params.append(strategy_name)
        query += " ORDER BY created_at_utc DESC"
        cursor = self.store.connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_policy_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        cursor = self.store.connection.execute(
            "SELECT * FROM policy_proposals WHERE proposal_id = ?",
            (proposal_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def compute_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload, allow_fallback=True).encode("utf-8")).hexdigest()


def parse_json_field(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}
