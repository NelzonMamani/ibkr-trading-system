from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.strategy_policy_v2.policy_v2 import StrategyPolicyV2


STRATEGIES_ROOT = REPO_ROOT / "src" / "strategies"
EVIDENCE_ROOT = (
    REPO_ROOT
    / "TRADING_OS_MASTER_CATALOGUE"
    / "AUDIT_EVIDENCE"
    / "POLICY_V2_SCHEMA_COVERAGE"
)


def _import_module_from_path(module_path: Path) -> Any:
    module_name = f"policy_v2_schema_{module_path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec for {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_schema_coverage_verification() -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = EVIDENCE_ROOT / timestamp
    evidence_dir.mkdir(parents=True, exist_ok=True)

    schema_field_names = {f.name for f in fields(StrategyPolicyV2)}
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    logs: list[str] = []

    if not STRATEGIES_ROOT.exists():
        raise FileNotFoundError(f"Strategies root not found: {STRATEGIES_ROOT}")

    for strategy_dir in sorted(p for p in STRATEGIES_ROOT.iterdir() if p.is_dir()):
        strategy_name = strategy_dir.name
        policy_file = strategy_dir / "strategy_policy_v2.py"
        if not policy_file.exists():
            continue

        result = {
            "strategy": strategy_name,
            "policy_file": str(policy_file.relative_to(REPO_ROOT)),
            "status": "PASS",
            "reasons": [],
        }

        try:
            module = _import_module_from_path(policy_file)
            if not hasattr(module, "POLICY_V2"):
                result["status"] = "FAIL"
                result["reasons"].append("POLICY_V2 not defined")
            else:
                policy = module.POLICY_V2
                if not isinstance(policy, StrategyPolicyV2):
                    result["status"] = "FAIL"
                    result["reasons"].append(
                        f"POLICY_V2 type mismatch: expected StrategyPolicyV2, got {type(policy).__name__}"
                    )
                else:
                    policy_fields = set(vars(policy).keys())
                    missing_fields = sorted(schema_field_names - policy_fields)
                    extra_fields = sorted(policy_fields - schema_field_names)

                    if missing_fields:
                        result["status"] = "FAIL"
                        result["reasons"].append(f"Missing schema fields: {missing_fields}")

                    if extra_fields:
                        result["status"] = "FAIL"
                        result["reasons"].append(f"Unknown extra fields: {extra_fields}")

        except Exception as exc:  # noqa: BLE001 - verifier should report all import/validation errors.
            result["status"] = "FAIL"
            result["reasons"].append(f"Import/validation error: {exc.__class__.__name__}: {exc}")

        logs.append(f"[{result['status']}] {result['strategy']} -> {', '.join(result['reasons']) or 'OK'}")
        results.append(result)
        if result["status"] == "FAIL":
            failures.append(result)

    summary = {
        "timestamp": timestamp,
        "strategies_checked": len(results),
        "passes": len([r for r in results if r["status"] == "PASS"]),
        "failures": len(failures),
        "evidence_dir": str(evidence_dir.relative_to(REPO_ROOT)),
        "results": results,
    }

    (evidence_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (evidence_dir / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    (evidence_dir / "console_log.txt").write_text("\n".join(logs) + "\n", encoding="utf-8")

    return {
        "summary": summary,
        "failures": failures,
        "evidence_dir": evidence_dir,
    }


def main() -> int:
    outcome = run_schema_coverage_verification()
    summary = outcome["summary"]
    print(
        "Policy V2 schema coverage complete: "
        f"checked={summary['strategies_checked']} pass={summary['passes']} fail={summary['failures']}"
    )
    print(f"Evidence: {summary['evidence_dir']}")
    return 1 if outcome["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
