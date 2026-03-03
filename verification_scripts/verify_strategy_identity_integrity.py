from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.strategy_policy_v2.policy_v2 import StrategyIdentityV2, StrategyPolicyV2

STRATEGIES_ROOT = REPO_ROOT / "src" / "strategies"
CATALOGUE_ROOT = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "03_STRATEGIES"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _load_policy_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"identity_verify_{path.parent.name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _catalogue_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in sorted(CATALOGUE_ROOT.iterdir()):
        if not entry.is_dir() or "_" not in entry.name:
            continue
        strategy_id, slug = entry.name.split("_", 1)
        if re.fullmatch(r"P\d{2}", strategy_id):
            out[_norm(slug)] = strategy_id
    return out


def run() -> int:
    failures: list[str] = []
    seen_ids: dict[str, str] = {}
    catalogue_by_slug = _catalogue_map()

    for strategy_dir in sorted(p for p in STRATEGIES_ROOT.iterdir() if p.is_dir()):
        policy_file = strategy_dir / "strategy_policy_v2.py"
        if not policy_file.exists():
            continue

        folder_slug = strategy_dir.name
        try:
            module = _load_policy_module(policy_file)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{folder_slug}: import failure: {exc.__class__.__name__}: {exc}")
            continue

        if not hasattr(module, "POLICY_V2"):
            failures.append(f"{folder_slug}: missing POLICY_V2")
            continue

        policy = module.POLICY_V2
        if not isinstance(policy, StrategyPolicyV2):
            failures.append(f"{folder_slug}: POLICY_V2 must be StrategyPolicyV2, got {type(policy).__name__}")
            continue

        if policy.identity is None:
            failures.append(f"{folder_slug}: POLICY_V2.identity is None")
            continue

        if not isinstance(policy.identity, StrategyIdentityV2):
            failures.append(f"{folder_slug}: identity must be StrategyIdentityV2")
            continue

        identity_name_norm = _norm(policy.identity.name)
        folder_norm = _norm(folder_slug)
        if identity_name_norm != folder_norm:
            failures.append(
                f"{folder_slug}: folder '{folder_slug}' != identity.name '{policy.identity.name}' (case-normalized mismatch)"
            )

        expected_id = catalogue_by_slug.get(folder_norm)
        if expected_id is None:
            failures.append(f"{folder_slug}: no catalogue declaration under {CATALOGUE_ROOT}")
        elif policy.identity.strategy_id != expected_id:
            failures.append(
                f"{folder_slug}: strategy_id '{policy.identity.strategy_id}' != catalogue '{expected_id}'"
            )

        seen_at = seen_ids.get(policy.identity.strategy_id)
        if seen_at is not None:
            failures.append(
                f"duplicate strategy_id '{policy.identity.strategy_id}' across '{seen_at}' and '{folder_slug}'"
            )
        else:
            seen_ids[policy.identity.strategy_id] = folder_slug

    if failures:
        print("FAIL: Strategy identity integrity violations detected")
        for item in failures:
            print(f" - {item}")
        return 1

    print("PASS: Strategy identity integrity checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
