from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STRATEGIES_ROOT = REPO_ROOT / "src" / "strategies"


def _norm(value: str) -> str:
    return value.strip().lower()


def _load_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"strategy_policy_identity_{path.parent.name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_identity_check() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    seen_strategy_ids: dict[str, str] = {}

    for strategy_dir in sorted(p for p in STRATEGIES_ROOT.iterdir() if p.is_dir()):
        policy_file = strategy_dir / "strategy_policy_v2.py"
        if not policy_file.exists():
            continue

        result = {
            "strategy_folder": strategy_dir.name,
            "policy_file": str(policy_file.relative_to(REPO_ROOT)),
            "status": "PASS",
            "reasons": [],
        }

        try:
            module = _load_module(policy_file)
            policy = getattr(module, "POLICY_V2", None)
            if policy is None:
                result["status"] = "FAIL"
                result["reasons"].append("POLICY_V2 missing")
            else:
                identity = policy.identity
                identity_name = getattr(identity, "name", "")
                strategy_id = getattr(identity, "strategy_id", "")
                if _norm(identity_name) != _norm(strategy_dir.name):
                    result["status"] = "FAIL"
                    result["reasons"].append(
                        f"identity.name '{identity_name}' does not match folder '{strategy_dir.name}' (case-normalized)"
                    )
                if "_policy" in _norm(identity_name):
                    result["status"] = "FAIL"
                    result["reasons"].append("identity.name must not contain '_policy'")
                if strategy_id in seen_strategy_ids:
                    result["status"] = "FAIL"
                    result["reasons"].append(
                        f"duplicate strategy_id '{strategy_id}' also used by {seen_strategy_ids[strategy_id]}"
                    )
                else:
                    seen_strategy_ids[strategy_id] = strategy_dir.name
        except Exception as exc:  # noqa: BLE001
            result["status"] = "FAIL"
            result["reasons"].append(f"Import error: {exc.__class__.__name__}: {exc}")

        if result["status"] == "FAIL":
            failures.extend([f"{result['strategy_folder']}: {reason}" for reason in result["reasons"]])

        checks.append(result)

    return {
        "strategies_checked": len(checks),
        "failures": failures,
        "results": checks,
    }


def main() -> int:
    outcome = run_identity_check()
    print(json.dumps(outcome, indent=2))
    return 1 if outcome["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
