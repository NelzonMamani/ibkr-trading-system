"""Deterministic runtime bootstrap for E26."""

from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from src.config.runtime_config import get_persistence_sqlite_path
from src.runtime.paths import get_data_dir, get_logs_dir, get_output_dir, resolve_repo_root
from src.storage.sqlite_store import SQLiteStore



def resolve_sqlite_path() -> Path:
    env_override = os.environ.get("PERSISTENCE_SQLITE_PATH", "").strip()
    configured = Path(env_override or get_persistence_sqlite_path(default="data/ibkr_system.db"))
    if configured.is_absolute():
        return configured
    return (resolve_repo_root() / configured).resolve()



def bootstrap_runtime() -> dict[str, Any]:
    data_dir = get_data_dir()
    logs_dir = get_logs_dir()
    output_dir = get_output_dir()
    for root in (data_dir, logs_dir, output_dir):
        root.mkdir(parents=True, exist_ok=True)

    trade_store_path = output_dir / "trade_store.jsonl"
    if not trade_store_path.exists():
        trade_store_path.touch()

    sqlite_path = resolve_sqlite_path()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(str(sqlite_path))
    try:
        store.initialize_schema()
    finally:
        store.close()

    return {
        "data_dir": str(data_dir),
        "logs_dir": str(logs_dir),
        "output_dir": str(output_dir),
        "sqlite_path": str(sqlite_path),
    }
