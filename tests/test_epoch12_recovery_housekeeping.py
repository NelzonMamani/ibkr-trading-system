from __future__ import annotations

import filecmp
import sqlite3
from pathlib import Path

import pytest

from config.config_resolver import set_config_overrides
from core.stop_controller import StopController, StopMode
from storage.db_admin import (
    CONFIRM_RESTORE,
    CONFIRM_SAFE_RESET,
    backup_database,
    restore_database,
    safe_reset_database,
)
from storage.storage_engine import StorageEngine


@pytest.fixture(autouse=True)
def _reset_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


def _write_seed_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO demo (id) VALUES (1)")
        connection.commit()


def test_epoch12_recovery_path_smoke(tmp_path):
    db_path = tmp_path / "recovered.db"
    assert not db_path.exists()
    set_config_overrides(
        {
            "PERSISTENCE_SQLITE_PATH": str(db_path),
            "RUN_MODE": "SIM",
            "RUN_MODE_EFFECTIVE": "SIM",
        }
    )
    engine = StorageEngine()
    try:
        assert db_path.exists()
        assert engine._store is not None
    finally:
        engine.shutdown()


def test_epoch12_db_backup_and_reset_determinism(tmp_path):
    db_path = tmp_path / "seed.db"
    _write_seed_db(db_path)
    set_config_overrides({"RUN_MODE": "SIM", "RUN_MODE_EFFECTIVE": "SIM"})

    backup_dir = tmp_path / "backups"
    backup_path = backup_database(
        str(db_path),
        backup_dir=str(backup_dir),
        stamp="2024_01_01_000000",
    )
    assert Path(backup_path).exists()
    assert Path(backup_path).name == "ibkr_system_2024_01_01_000000.db"
    assert filecmp.cmp(db_path, backup_path, shallow=False)

    safe_reset_database(str(db_path), confirm_token=CONFIRM_SAFE_RESET)
    with sqlite3.connect(db_path) as connection:
        remaining = connection.execute("SELECT COUNT(*) FROM demo").fetchone()[0]
    assert remaining == 0

    restore_database(
        backup_path,
        str(db_path),
        confirm_token=CONFIRM_RESTORE,
        create_backup=False,
    )
    with sqlite3.connect(db_path) as connection:
        restored = connection.execute("SELECT COUNT(*) FROM demo").fetchone()[0]
    assert restored == 1


def test_epoch12_stop_controller_enforcement():
    controller = StopController()
    controller.request_stop(StopMode.GRACEFUL, reason="scheduled", source="unit")
    controller.request_stop(StopMode.PANIC, reason="panic", source="unit")
    assert controller.stop_mode() == StopMode.PANIC

    controller.trip_breaker(
        breaker_id="RISK_LOCK",
        reason="risk",
        source="unit",
    )
    assert controller.reset_breakers(open_positions=2, reason="blocked", source="unit") is False
    assert controller.reset_breakers(open_positions=0, reason="clear", source="unit") is True
