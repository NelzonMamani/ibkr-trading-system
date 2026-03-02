from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "P02_STATISTICAL_INTRADAY_MOMENTUM_V2_MIGRATION"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_rg() -> str:
    cmd = [
        "rg",
        "-n",
        "SelectionEngineV2|strategy_policy_v2|resolve_policy_v2|STRATEGY_POLICY_V2_ENABLED|STRATEGY_POLICY_V2_STRATEGIES|statistical_intraday_momentum",
        "src/core/orchestrator.py",
        "src/strategy_policy_v2/registry.py",
        "src/config/config_registry.py",
        "src/strategies/statistical_intraday_momentum",
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return f"$ {' '.join(cmd)}\n\n{result.stdout}\n{result.stderr}".strip() + "\n"


def main() -> int:
    evidence_dir = EVIDENCE_ROOT / _ts()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    policy_v2 = REPO_ROOT / "src/strategies/statistical_intraday_momentum/strategy_policy_v2.py"
    registry_path = REPO_ROOT / "src/strategy_policy_v2/registry.py"
    config_path = REPO_ROOT / "src/config/config_registry.py"

    registry_text = registry_path.read_text(encoding="utf-8")
    config_text = config_path.read_text(encoding="utf-8")

    resolver_registered = '"statistical_intraday_momentum"' in registry_text
    disabled_by_default = '"default": {"ross_momentum": True, "statistical_intraday_momentum": False}' in config_text

    baseline_md = [
        "# BASELINE_RUNTIME_CONSUMPTION",
        "",
        f"- repo_root: `{REPO_ROOT}`",
        f"- policy_v2_exists: `{policy_v2.exists()}`",
        f"- resolver_registered_for_p02: `{resolver_registered}`",
        f"- disabled_by_default_in_config: `{disabled_by_default}`",
    ]

    (evidence_dir / "BASELINE_RUNTIME_CONSUMPTION.md").write_text("\n".join(baseline_md) + "\n", encoding="utf-8")
    (evidence_dir / "BASELINE_RIPGREP_LOG.txt").write_text(_run_rg(), encoding="utf-8")
    (evidence_dir / "BASELINE_POLICY_POINTERS.json").write_text(
        json.dumps(
            {
                "policy_v2": str(policy_v2.relative_to(REPO_ROOT)),
                "registry_file": str(registry_path.relative_to(REPO_ROOT)),
                "config_file": str(config_path.relative_to(REPO_ROOT)),
                "resolver_registered_for_p02": resolver_registered,
                "disabled_by_default_in_config": disabled_by_default,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "evidence_dir": str(evidence_dir),
                "resolver_registered_for_p02": resolver_registered,
                "disabled_by_default_in_config": disabled_by_default,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
