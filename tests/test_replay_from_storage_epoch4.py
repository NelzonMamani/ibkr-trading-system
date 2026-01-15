from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from core.replay_engine import ReplayEngine
from storage.serialization import canonical_json
from storage.sqlite_store import SCHEMA_VERSION, SQLiteStore, now_iso


def _insert_run(store: SQLiteStore, run_id: str) -> None:
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


def test_replay_from_storage_epoch4_orders_events(tmp_path):
    db_path = tmp_path / "replay.db"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    cycle_id = str(uuid4())
    _insert_run(store, run_id)
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

    events = [
        {
            "event_id": str(uuid4()),
            "run_id": run_id,
            "cycle_id": cycle_id,
            "tick": 2,
            "event_type": "EXECUTION_COMPLETE",
            "source": "ExecutionEngine",
            "timestamp": now_iso(),
            "payload_json": canonical_json({"results": 0, "tick": 999}),
            "seq": 2,
            "prev_hash": "GENESIS",
            "event_hash": "hash2",
            "created_at": now_iso(),
        },
        {
            "event_id": str(uuid4()),
            "run_id": run_id,
            "cycle_id": cycle_id,
            "tick": 1,
            "event_type": "CYCLE_START",
            "source": "Orchestrator",
            "timestamp": now_iso(),
            "payload_json": canonical_json({"run_mode": "SIM", "tick": 0}),
            "seq": 1,
            "prev_hash": "GENESIS",
            "event_hash": "hash1",
            "created_at": now_iso(),
        },
    ]
    store.insert_events(events)

    set_config_overrides({"RUN_MODE": "SIM"})
    try:
        engine = ReplayEngine()
        replayed = engine.replay_from_storage(store, run_id)
    finally:
        set_config_overrides(None)

    assert [(event.tick, event.seq) for event in replayed] == [(1, 1), (2, 2)]
    assert [event.event_type for event in replayed] == [
        "CYCLE_START",
        "EXECUTION_COMPLETE",
    ]
    store.close()


def test_replay_from_storage_epoch4_schema_validation(tmp_path):
    db_path = tmp_path / "replay_invalid.db"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    cycle_id = str(uuid4())
    _insert_run(store, run_id)
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
                "payload_json": canonical_json({}),
                "seq": 1,
                "prev_hash": "GENESIS",
                "event_hash": "hash1",
                "created_at": now_iso(),
            }
        ]
    )

    set_config_overrides({"RUN_MODE": "SIM"})
    try:
        engine = ReplayEngine()
        with pytest.raises(Exception):
            engine.replay_from_storage(store, run_id)
    finally:
        set_config_overrides(None)
        store.close()
