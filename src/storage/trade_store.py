"""Trade storage for Epoch 5 artifacts."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict

from src.storage.schema_map import to_serializable


class TradeStore:
    def __init__(self, base_path: str = "output/storage") -> None:
        self.base = Path(base_path)
        self.base.mkdir(parents=True, exist_ok=True)

    def persist_cycle(self, cycle_id: int, payload: Dict[str, Any]) -> Path:
        serializable = to_serializable(payload)
        file_path = self.base / f"cycle_{cycle_id}.json"
        file_path.write_text(json.dumps(serializable, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[STORAGE] Persisted cycle {cycle_id} -> {file_path}")
        return file_path
