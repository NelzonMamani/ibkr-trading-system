from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from storage.serialization import canonical_json
from storage.sqlite_store import SCHEMA_VERSION, SQLiteStore, now_iso
from tools.storage_cli import main as storage_main


def test_storage_cli_epoch4_list_and_export(tmp_path):
    db_path = tmp_path / "cli.db"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    cycle_id = str(uuid4())
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
            "run_mode": "SIM",
            "effective_run_mode": "SIM",
            "event_replay_mode": "RUN",
            "resolved_config_json": canonical_json({"sample": True}),
            "config_fingerprint": "fingerprint",
            "schema_version": SCHEMA_VERSION,
            "system_version": "TEST",
            "created_at": now_iso(),
        }
    )
    store.insert_cycle(
        {
            "cycle_id": cycle_id,
            "run_id": run_id,
            "tick": 1,
            "session": "REGULAR",
            "market_session": "REGULAR",
            "cycle_started_at": now_iso(),
            "cycle_ended_at": now_iso(),
            "scanner_n": 0,
            "scanner_candidates_count": 0,
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
    store.insert_events(
        [
            {
                "event_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": cycle_id,
                "tick": 1,
                "event_type": "CYCLE_START",
                "source": "Orchestrator",
                "timestamp": now_iso(),
                "payload_json": canonical_json({"run_mode": "SIM", "tick": 1}),
                "seq": 1,
                "prev_hash": "GENESIS",
                "event_hash": "hash1",
                "created_at": now_iso(),
            }
        ]
    )
    store.close()

    assert storage_main(["--sqlite-path", str(db_path), "runs:list"]) == 0

    export_path = tmp_path / "events.jsonl"
    assert (
        storage_main(
            [
                "--sqlite-path",
                str(db_path),
                "events:export",
                "--run-id",
                run_id,
                "--format",
                "jsonl",
                "--out",
                str(export_path),
            ]
        )
        == 0
    )
    assert export_path.exists()
