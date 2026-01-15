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


def test_replay_locked_in_live_modes_epoch4(tmp_path):
    db_path = tmp_path / "replay_live.db"
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
            "run_mode": "LIVE",
            "effective_run_mode": "LIVE",
            "event_replay_mode": "OFF",
            "resolved_config_json": canonical_json({"sample": True}),
            "config_fingerprint": "fingerprint",
            "schema_version": SCHEMA_VERSION,
            "system_version": "TEST",
            "created_at": now_iso(),
        }
    )

    set_config_overrides(
        {
            "RUN_MODE": "LIVE",
            "IBKR_MARKET_DATA_TYPE": "DELAYED",
            "IBKR_API_WRITE_ALLOWED": False,
            "EXECUTION_ENABLED": False,
        }
    )
    try:
        engine = ReplayEngine()
        with pytest.raises(RuntimeError):
            engine.replay_from_storage(store, run_id)
    finally:
        set_config_overrides(None)
        store.close()
