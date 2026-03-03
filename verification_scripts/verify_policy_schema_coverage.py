from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from verification_scripts.verify_all_strategy_policies_v2_schema import run_schema_coverage_verification


def main() -> int:
    outcome = run_schema_coverage_verification()
    summary = outcome["summary"]
    print(json.dumps(summary, indent=2))
    return 1 if outcome["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
