"""Verify policy setup family coverage against canonical setup registry."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json

from src.setup_engine.registry import CANONICAL_SETUP_REGISTRY, SetupImplementationStatus
from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2


def main() -> int:
    policy_ids = [spec.setup_id for spec in POLICY_V2.setup_families.families]
    missing = [setup_id for setup_id in policy_ids if setup_id not in CANONICAL_SETUP_REGISTRY]
    spec_only = [
        setup_id
        for setup_id in policy_ids
        if CANONICAL_SETUP_REGISTRY[setup_id].status == SetupImplementationStatus.SPEC_ONLY
    ]

    evidence = {
        "policy_setup_ids": policy_ids,
        "registry_setup_ids": sorted(CANONICAL_SETUP_REGISTRY.keys()),
        "missing": missing,
        "spec_only": spec_only,
        "statuses": {
            setup_id: {
                "status": CANONICAL_SETUP_REGISTRY[setup_id].status.value,
                "pattern": CANONICAL_SETUP_REGISTRY[setup_id].pattern_cls.__name__,
                "reason": CANONICAL_SETUP_REGISTRY[setup_id].reason,
            }
            for setup_id in policy_ids
            if setup_id in CANONICAL_SETUP_REGISTRY
        },
        "pass": not missing and not spec_only,
    }

    out_dir = Path("AUDIT_EVIDENCE/p01_setup_family_sprint")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "setup_families_completeness.json"
    out_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    if missing:
        raise AssertionError(f"Missing setup families in canonical registry: {missing}")
    if spec_only:
        raise AssertionError(f"SPEC_ONLY setup families are not allowed: {spec_only}")

    print("PASS: setup_families_completeness_verifier")
    print(f"evidence={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
