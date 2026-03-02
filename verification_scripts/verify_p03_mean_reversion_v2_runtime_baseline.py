from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "P03_MEAN_REVERSION_V2_MIGRATION"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_rg() -> str:
    cmd = [
        "rg",
        "-n",
        "SelectionEngineV2|strategy_policy_v2|resolve_policy_v2|STRATEGY_POLICY_V2_ENABLED|mean_reversion",
        "src/core/orchestrator.py",
        "src/strategies/mean_reversion",
        "src/strategy_policy_v2/registry.py",
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return f"$ {' '.join(cmd)}\n\n{result.stdout}\n{result.stderr}".strip() + "\n"


def main() -> int:
    evidence_dir = EVIDENCE_ROOT / _ts()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    policy_v1 = REPO_ROOT / "src/strategies/mean_reversion/strategy_policy.py"
    policy_v2 = REPO_ROOT / "src/strategies/mean_reversion/strategy_policy_v2.py"
    registry = (REPO_ROOT / "src/strategy_policy_v2/registry.py").read_text(encoding="utf-8")
    orchestrator = (REPO_ROOT / "src/core/orchestrator.py").read_text(encoding="utf-8")
    consumed = "SelectionEngineV2" in orchestrator and "resolve_policy_v2" in orchestrator
    registered = "mean_reversion" in registry and "src.strategies.mean_reversion.strategy_policy_v2.POLICY_V2" in registry

    baseline_md = [
        "# BASELINE_RUNTIME_CONSUMPTION",
        "",
        f"- repo_root: `{REPO_ROOT}`",
        f"- policy_v1_exists: `{policy_v1.exists()}`",
        f"- policy_v2_exists: `{policy_v2.exists()}`",
        f"- registry_has_mean_reversion: `{registered}`",
        f"- runtime_consumes_v2_surfaces_for_p03: `{'YES' if consumed else 'NO'}`",
    ]

    (evidence_dir / "BASELINE_RUNTIME_CONSUMPTION.md").write_text("\n".join(baseline_md) + "\n", encoding="utf-8")
    (evidence_dir / "BASELINE_RIPGREP_LOG.txt").write_text(_run_rg(), encoding="utf-8")
    (evidence_dir / "BASELINE_POLICY_POINTERS.json").write_text(
        json.dumps(
            {
                "policy_v1": str(policy_v1.relative_to(REPO_ROOT)),
                "policy_v2": str(policy_v2.relative_to(REPO_ROOT)),
                "registry_file": "src/strategy_policy_v2/registry.py",
                "runtime_file": "src/core/orchestrator.py",
                "registry_has_mean_reversion": registered,
                "runtime_consumes_v2_surfaces_for_p03": consumed,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"evidence_dir": str(evidence_dir), "runtime_consumes_v2": consumed, "registered": registered}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
