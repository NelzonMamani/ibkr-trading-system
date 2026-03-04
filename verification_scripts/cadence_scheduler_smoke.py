"""Smoke check for Ross policy intrabar cadence declarations."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2


def main() -> int:
    rules = list(POLICY_V2.intrabar_execution.cadence_rules)
    assert isinstance(rules, list), "cadence_rules should be list-like"
    assert len(rules) > 0, "expected at least one cadence rule"
    print(f"PASS: cadence_scheduler_smoke cadence_rules={len(rules)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
