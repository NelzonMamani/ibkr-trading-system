from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from storage.storage_engine import StorageEngine


@pytest.fixture(autouse=True)
def _reset_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


def test_storage_engine_recovers_missing_db(tmp_path):
    db_path = tmp_path / "recovered.db"
    assert not os.path.exists(db_path)
    set_config_overrides({"PERSISTENCE_SQLITE_PATH": str(db_path)})
    engine = StorageEngine()
    try:
        assert os.path.exists(db_path)
        assert engine._store is not None
        cursor = engine._store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        )
        assert cursor.fetchone() is not None
    finally:
        engine.shutdown()


def test_management_snapshot_distinguishes_absence_mapping_and_corruption(tmp_path):
    set_config_overrides({"PERSISTENCE_SQLITE_PATH": str(tmp_path / "management.db")})
    engine = StorageEngine()
    try:
        assert engine.fetch_management_state("absent") is None
        payload = {"orders": {"native-1": {"status": "UNKNOWN", "quantity": 2}}}
        engine.store_management_state("retained", payload)
        assert engine.fetch_management_state("retained") == payload
        connection = engine._store.connection
        for raw in ("null", "[]", "42", '"unavailable"'):
            connection.execute(
                "UPDATE position_lifecycle_transitions SET reason=? WHERE transition_id=?",
                (raw, "retained"),
            )
            connection.commit()
            with pytest.raises(ValueError, match="MANAGEMENT_STATE_NOT_OBJECT"):
                engine.fetch_management_state("retained")
        connection.execute(
            "UPDATE position_lifecycle_transitions SET reason='{}' WHERE transition_id='retained'"
        )
        connection.commit()
        assert engine.fetch_management_state("retained") == {}
    finally:
        engine.shutdown()
