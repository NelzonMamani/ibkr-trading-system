"""Runtime path helpers for deterministic regenerability."""

from __future__ import annotations

import os
from pathlib import Path

DATA_ENV_KEY = "IBKR_OS_DATA_DIR"
LOG_ENV_KEY = "IBKR_OS_LOG_DIR"
OUTPUT_ENV_KEY = "IBKR_OS_OUTPUT_DIR"



def resolve_repo_root(start: Path | None = None) -> Path:
    """Locate repository root by discovering SYSTEM_STATE.md."""
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    while True:
        if (current / "SYSTEM_STATE.md").exists():
            return current
        if current.parent == current:
            return Path.cwd().resolve()
        current = current.parent



def _resolve_runtime_dir(env_key: str, default_relative: str) -> Path:
    value = os.environ.get(env_key, "").strip()
    raw = Path(value) if value else Path(default_relative)
    if raw.is_absolute():
        return raw
    return (resolve_repo_root() / raw).resolve()



def get_data_dir() -> Path:
    return _resolve_runtime_dir(DATA_ENV_KEY, "data")



def get_logs_dir() -> Path:
    return _resolve_runtime_dir(LOG_ENV_KEY, "logs")



def get_output_dir() -> Path:
    return _resolve_runtime_dir(OUTPUT_ENV_KEY, "output")



def is_within(path: Path, root: Path) -> bool:
    candidate = path.resolve()
    resolved_root = root.resolve()
    return candidate == resolved_root or resolved_root in candidate.parents
