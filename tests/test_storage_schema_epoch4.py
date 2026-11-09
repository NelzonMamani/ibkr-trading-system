from __future__ import annotations

import json
from pathlib import Path
import sys
from uuid import uuid4

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from storage.serialization import canonical_json
from storage.sqlite_store import SCHEMA_VERSION, SQLiteStore, now_iso


def _column_names(store: SQLiteStore, table: str) -> set[str]:
    cursor = store.connection.execute(f"PRAGMA table_info({table})")
    return {row["name"] for row in cursor.fetchall()}


def test_runtime_schema_copies_are_empty_independent_and_rechecked(runtime_schema_template, tmp_path):
    import shutil
    from src.storage.sqlite_store import SQLiteStore as RuntimeStore
    stores = []
    try:
        fresh = RuntimeStore(str(tmp_path / "fresh.sqlite3")); stores.append(fresh)
        fresh_sql = []
        fresh.connection.set_trace_callback(fresh_sql.append)
        fresh.initialize_schema()
        copies = []
        for name in ("one", "two"):
            path = tmp_path / (name + ".sqlite3")
            shutil.copyfile(runtime_schema_template, path)
            store = RuntimeStore(str(path)); stores.append(store); copies.append(store)
            sql = []
            store.connection.set_trace_callback(sql.append)
            store.initialize_schema()  # Same actual idempotent owner as Core.
            assert any("CREATE TABLE IF NOT EXISTS" in s for s in sql)
            assert not any(s.lstrip().upper().startswith("ALTER TABLE") for s in sql)
            def schema(db):
                return [tuple(row) for row in db.connection.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
            assert schema(store) == schema(fresh)
            tables = [row[0] for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            assert "capital_owner_state" not in tables
            for table in tables:
                if table != "schema_meta":
                    assert store.connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0
        assert any(s.lstrip().upper().startswith("ALTER TABLE") for s in fresh_sql)
        copies[0].connection.execute("INSERT INTO runs (run_id) VALUES ('private-runtime')")
        copies[0].connection.commit()
        assert copies[0].connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        assert copies[1].connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        # The session template remains data-free after a scenario commits.
        template = RuntimeStore(str(runtime_schema_template)); stores.append(template)
        assert template.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    finally:
        for store in stores:
            store.close()


def test_storage_schema_epoch4_tables_and_columns(tmp_path):
    db_path = tmp_path / "schema.db"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    tables = {
        "schema_meta",
        "runs",
        "cycles",
        "events",
        "trade_records",
        "trades",
        "execution_results",
        "trade_outcomes",
        "performance_snapshots",
        "watchlists",
        "learning_runs",
        "learning_reports",
        "policy_proposals",
    }
    cursor = store.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    existing_tables = {row["name"] for row in cursor.fetchall()}
    assert tables.issubset(existing_tables)

    runs_cols = _column_names(store, "runs")
    assert {"run_id", "started_at_utc", "effective_run_mode", "config_fingerprint"}.issubset(
        runs_cols
    )

    cycles_cols = _column_names(store, "cycles")
    assert {
        "market_session",
        "scanner_candidates_count",
        "signals_count",
        "warnings_json",
    }.issubset(cycles_cols)

    events_cols = _column_names(store, "events")
    assert {"tick", "schema_version", "payload_hash"}.issubset(events_cols)

    trade_record_cols = _column_names(store, "trade_records")
    assert {"decision_output_json", "regime_snapshot_json", "regime_policy_decision_json"}.issubset(
        trade_record_cols
    )

    execution_cols = _column_names(store, "execution_results")
    assert {"execution_result_id", "fill_status", "payload_json"}.issubset(execution_cols)

    outcome_cols = _column_names(store, "trade_outcomes")
    assert {"trade_outcome_id", "net_realised_pnl", "closed_at"}.issubset(outcome_cols)

    snapshot_cols = _column_names(store, "performance_snapshots")
    assert {"performance_snapshot_id", "payload_json"}.issubset(snapshot_cols)

    watchlist_cols = _column_names(store, "watchlists")
    assert {"watchlist_id", "strategy_name", "symbols_json", "watchlist_hash"}.issubset(
        watchlist_cols
    )

    report_cols = _column_names(store, "learning_reports")
    assert {"report_id", "report_type", "payload_json"}.issubset(report_cols)

    proposal_cols = _column_names(store, "policy_proposals")
    assert {"proposal_id", "proposal_json", "status"}.issubset(proposal_cols)

    store.close()


def test_storage_schema_epoch4_round_trip(tmp_path):
    db_path = tmp_path / "roundtrip.db"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    store.insert_run(
        {
            "run_id": run_id,
            "started_at": now_iso(),
            "started_at_utc": now_iso(),
            "ended_at": None,
            "ended_at_utc": None,
            "hostname": "host",
            "user": "tester",
            "app_version": "TEST",
            "git_sha": "deadbeef",
            "run_mode": "PAPER",
            "effective_run_mode": "PAPER",
            "event_replay_mode": "RUN",
            "resolved_config_json": canonical_json({"sample": True}),
            "config_fingerprint": "fingerprint",
            "schema_version": SCHEMA_VERSION,
            "system_version": "TEST",
            "created_at": now_iso(),
        }
    )

    cycle_id = str(uuid4())
    store.insert_cycle(
        {
            "cycle_id": cycle_id,
            "run_id": run_id,
            "tick": 7,
            "session": "RTH",
            "market_session": "RTH",
            "cycle_started_at": now_iso(),
            "cycle_ended_at": now_iso(),
            "scanner_n": 1,
            "scanner_candidates_count": 1,
            "patterns_n": 0,
            "patterns_count": 0,
            "signals_count": 0,
            "intents_n": 0,
            "intents_count": 0,
            "risk_n": 0,
            "risk_decisions_count": 0,
            "exec_n": 0,
            "execution_results_count": 0,
            "closed_n": 0,
            "trade_outcomes_count": 0,
            "warnings_json": "[]",
            "created_at": now_iso(),
        }
    )

    record_payload = {"scanner_output": [{"symbol": "AAPL"}]}
    store.insert_trade_record(
        {
            "trade_record_id": str(uuid4()),
            "run_id": run_id,
            "cycle_id": cycle_id,
            "tick": 7,
            "scanner_output_json": canonical_json(record_payload["scanner_output"]),
            "pattern_output_json": "[]",
            "strategy_output_json": "[]",
            "decision_output_json": "[]",
            "risk_output_json": "[]",
            "execution_output_json": "[]",
            "trade_outcomes_json": "[]",
            "performance_snapshot_json": "{}",
            "created_at": now_iso(),
        }
    )

    snapshot_payload = {"total_trades": 0, "rule_adherence": {"stop_loss_violations": 0}}
    store.insert_performance_snapshot(
        {
            "performance_snapshot_id": str(uuid4()),
            "run_id": run_id,
            "cycle_id": cycle_id,
            "tick": 7,
            "payload_json": canonical_json(snapshot_payload),
            "created_at": now_iso(),
        }
    )

    records = store.fetch_trade_records(run_id)
    assert len(records) == 1
    loaded_payload = json.loads(records[0]["scanner_output_json"])
    assert loaded_payload == record_payload["scanner_output"]

    snapshots = store.fetch_performance_snapshots(run_id)
    assert len(snapshots) == 1
    assert json.loads(snapshots[0]["payload_json"]) == snapshot_payload

    store.close()
