"""Generate M5 strategy certification authority artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m5_strategy_certification_authority import generate_strategy_certification_artifacts


if __name__ == "__main__":
    payload = generate_strategy_certification_artifacts()
    print(json.dumps(payload, indent=2))
