from __future__ import annotations

import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from storage.serialization import canonical_json, compute_audit_hash
from storage.sqlite_store import SCHEMA_VERSION, SQLiteStore, now_iso


def _insert_sample_run(store: SQLiteStore, run_id: str) -> None:
    store.insert_run(
        {
            "run_id": run_id,
            "started_at": now_iso(),
            "started_at_utc": now_iso(),
            "ended_at": None,
            "hostname": "host",
            "user": "tester",
            "app_version": "TEST",
            "git_sha": "deadbeef",
            "run_mode": "PAPER",
            "effective_run_mode": "PAPER",
            "event_replay_mode": "CYCLE",
            "resolved_config_json": canonical_json({"sample": True}),
            "config_fingerprint": "fingerprint",
            "schema_version": SCHEMA_VERSION,
            "system_version": "TEST",
            "created_at": now_iso(),
        }
    )


def test_sqlite_persists_run_cycle_events_trade_record(tmp_path):
    db_path = tmp_path / "store.sqlite"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    _insert_sample_run(store, run_id)

    cycle_id = str(uuid4())
    store.insert_cycle(
        {
            "cycle_id": cycle_id,
            "run_id": run_id,
            "tick": 1,
            "session": "RTH",
            "cycle_started_at": now_iso(),
            "cycle_ended_at": now_iso(),
            "scanner_n": 0,
            "patterns_n": 0,
            "intents_n": 0,
            "risk_n": 0,
            "exec_n": 0,
            "closed_n": 0,
            "created_at": now_iso(),
        }
    )

    payload = {"message": "hello"}
    payload_json = canonical_json(payload)
    event_payload = {
        "run_id": run_id,
        "cycle_id": cycle_id,
        "seq": 1,
        "event_type": "TEST_EVENT",
        "source": "UnitTest",
        "timestamp": now_iso(),
        "payload": json.loads(payload_json),
    }
    event_hash = compute_audit_hash("GENESIS", event_payload)
    store.insert_events(
        [
            {
                "event_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": cycle_id,
                "event_type": "TEST_EVENT",
                "source": "UnitTest",
                "timestamp": event_payload["timestamp"],
                "payload_json": payload_json,
                "seq": 1,
                "prev_hash": "GENESIS",
                "event_hash": event_hash,
                "created_at": now_iso(),
            }
        ]
    )

    trade_record_id = str(uuid4())
    store.insert_trade_record(
        {
            "trade_record_id": trade_record_id,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "tick": 1,
            "scanner_output_json": "[]",
            "pattern_output_json": "[]",
            "strategy_output_json": "[]",
            "risk_output_json": "[]",
            "execution_output_json": "[]",
            "trade_outcomes_json": "[]",
            "performance_snapshot_json": "{}",
            "created_at": now_iso(),
        }
    )

    assert store.fetch_run(run_id) is not None
    assert len(store.fetch_table("cycles", run_id)) == 1
    assert len(store.fetch_table("events", run_id)) == 1
    assert len(store.fetch_table("trade_records", run_id)) == 1

    store.close()


def test_audit_hash_chain_verification_ok(tmp_path):
    db_path = tmp_path / "audit.sqlite"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    _insert_sample_run(store, run_id)

    cycle_id = str(uuid4())
    store.insert_cycle(
        {
            "cycle_id": cycle_id,
            "run_id": run_id,
            "tick": 1,
            "session": "RTH",
            "cycle_started_at": now_iso(),
            "cycle_ended_at": now_iso(),
            "scanner_n": 0,
            "patterns_n": 0,
            "intents_n": 0,
            "risk_n": 0,
            "exec_n": 0,
            "closed_n": 0,
            "created_at": now_iso(),
        }
    )

    payload = {"message": "audit"}
    payload_json = canonical_json(payload)
    event_payload = {
        "run_id": run_id,
        "cycle_id": cycle_id,
        "seq": 1,
        "event_type": "AUDIT_EVENT",
        "source": "UnitTest",
        "timestamp": now_iso(),
        "payload": json.loads(payload_json),
    }
    event_hash = compute_audit_hash("GENESIS", event_payload)
    store.insert_events(
        [
            {
                "event_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": cycle_id,
                "event_type": "AUDIT_EVENT",
                "source": "UnitTest",
                "timestamp": event_payload["timestamp"],
                "payload_json": payload_json,
                "seq": 1,
                "prev_hash": "GENESIS",
                "event_hash": event_hash,
                "created_at": now_iso(),
            }
        ]
    )

    result = store.verify_audit_chain(run_id)
    assert result.ok is True

    store.close()


def test_audit_hash_chain_detects_tamper(tmp_path):
    db_path = tmp_path / "tamper.sqlite"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    _insert_sample_run(store, run_id)

    cycle_id = str(uuid4())
    store.insert_cycle(
        {
            "cycle_id": cycle_id,
            "run_id": run_id,
            "tick": 1,
            "session": "RTH",
            "cycle_started_at": now_iso(),
            "cycle_ended_at": now_iso(),
            "scanner_n": 0,
            "patterns_n": 0,
            "intents_n": 0,
            "risk_n": 0,
            "exec_n": 0,
            "closed_n": 0,
            "created_at": now_iso(),
        }
    )

    payload = {"message": "tamper"}
    payload_json = canonical_json(payload)
    event_payload = {
        "run_id": run_id,
        "cycle_id": cycle_id,
        "seq": 1,
        "event_type": "TAMPER_EVENT",
        "source": "UnitTest",
        "timestamp": now_iso(),
        "payload": json.loads(payload_json),
    }
    event_hash = compute_audit_hash("GENESIS", event_payload)
    store.insert_events(
        [
            {
                "event_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": cycle_id,
                "event_type": "TAMPER_EVENT",
                "source": "UnitTest",
                "timestamp": event_payload["timestamp"],
                "payload_json": payload_json,
                "seq": 1,
                "prev_hash": "GENESIS",
                "event_hash": event_hash,
                "created_at": now_iso(),
            }
        ]
    )

    store.connection.execute(
        "UPDATE events SET payload_json = ? WHERE run_id = ?",
        (canonical_json({"message": "evil"}), run_id),
    )
    store.connection.commit()

    result = store.verify_audit_chain(run_id)
    assert result.ok is False
    assert result.first_bad_seq == 1

    store.close()
