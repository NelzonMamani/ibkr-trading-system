"""Review helpers for stored trade artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import List


def list_cycle_files(base_path: str = "output/storage") -> List[Path]:
    base = Path(base_path)
    if not base.exists():
        return []
    return sorted(base.glob("cycle_*.json"))
