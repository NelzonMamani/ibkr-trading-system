from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.strategy_policy_v2.registry import list_registered_policies_v2, resolve_policy_v2

EVIDENCE_ROOT = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "POLICY_V2_RESOLVER"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    evidence_dir = EVIDENCE_ROOT / _ts()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    registry = list_registered_policies_v2()
    (evidence_dir / "RESOLVER_REGISTRY.json").write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rg_cmd = [
        "rg",
        "-n",
        "resolve_policy_v2|ROSS_POLICY_V2",
        "src/core/orchestrator.py",
    ]
    rg_result = subprocess.run(rg_cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    markers = [f"$ {' '.join(rg_cmd)}", "", rg_result.stdout, rg_result.stderr]
    (evidence_dir / "ORCHESTRATOR_MARKERS.txt").write_text("\n".join(markers).strip() + "\n", encoding="utf-8")

    ross = resolve_policy_v2("ross_momentum")
    unknown = resolve_policy_v2("unknown")
    smoke = {
        "ross_momentum": {
            "resolved": ross is not None,
            "strategy_id": ross.identity.strategy_id if ross is not None else None,
        },
        "unknown": {"resolved": unknown is not None},
    }
    (evidence_dir / "RESOLVER_SMOKE.json").write_text(json.dumps(smoke, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"evidence_dir": str(evidence_dir), "smoke": smoke}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
