from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "P01_ROSS_V2_MIGRATION"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_rg() -> str:
    cmd = ["rg", "-n", "SelectionEngineV2|strategy_policy_v2|resolve_policy_v2|STRATEGY_POLICY_V2_ENABLED", "src/core/orchestrator.py", "src/strategies/ross_momentum"]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return f"$ {' '.join(cmd)}\n\n{result.stdout}\n{result.stderr}".strip() + "\n"


def main() -> int:
    evidence_dir = EVIDENCE_ROOT / _ts()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    policy_v1 = REPO_ROOT / "src/strategies/ross_momentum/strategy_policy.py"
    policy_v2 = REPO_ROOT / "src/strategies/ross_momentum/strategy_policy_v2.py"
    orchestrator = (REPO_ROOT / "src/core/orchestrator.py").read_text(encoding="utf-8")
    consumed = "SelectionEngineV2" in orchestrator and "resolve_policy_v2" in orchestrator

    baseline_md = [
        "# BASELINE_RUNTIME_CONSUMPTION",
        "",
        f"- repo_root: `{REPO_ROOT}`",
        f"- policy_v1_exists: `{policy_v1.exists()}`",
        f"- policy_v2_exists: `{policy_v2.exists()}`",
        f"- runtime_consumes_v2_surfaces_for_p01: `{'YES' if consumed else 'NO'}`",
    ]

    (evidence_dir / "BASELINE_RUNTIME_CONSUMPTION.md").write_text("\n".join(baseline_md) + "\n", encoding="utf-8")
    (evidence_dir / "BASELINE_RIPGREP_LOG.txt").write_text(_run_rg(), encoding="utf-8")
    (evidence_dir / "BASELINE_POLICY_POINTERS.json").write_text(
        json.dumps(
            {
                "policy_v1": str(policy_v1.relative_to(REPO_ROOT)),
                "policy_v2": str(policy_v2.relative_to(REPO_ROOT)),
                "runtime_file": "src/core/orchestrator.py",
                "runtime_consumes_v2_surfaces_for_p01": consumed,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"evidence_dir": str(evidence_dir), "runtime_consumes_v2": consumed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
