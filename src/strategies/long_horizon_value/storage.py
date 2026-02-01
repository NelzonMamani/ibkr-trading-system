"""Storage helpers for Long Horizon Value artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def persist_artifact(*, run_id: str, name: str, payload: Mapping[str, Any]) -> Path:
    base_path = Path("output") / "long_horizon_value" / run_id
    base_path.mkdir(parents=True, exist_ok=True)
    path = base_path / f"{name}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return path
