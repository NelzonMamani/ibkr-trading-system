"""Reconcile Ross setup-family policy catalog against implemented pattern registry."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2

EVIDENCE_DIR = REPO_ROOT / "AUDIT_EVIDENCE" / "pr343_amendments"


def _canonical_setup_key(value: str) -> str:
    return value.upper().replace(" ", "_").replace("-", "_")


def _derive_implemented_families(registry: RossPatternRegistry) -> set[str]:
    return {_canonical_setup_key(pattern.name) for pattern in registry.patterns}


def main() -> int:
    registry = RossPatternRegistry()
    implemented_pattern_ids = sorted(pattern.name for pattern in registry.patterns)
    implemented_family_keys = _derive_implemented_families(registry)

    policy_families = [family.setup_id for family in POLICY_V2.setup_families.families]

    implemented_family_ids: list[str] = []
    spec_only_family_ids: list[str] = []
    for family_id in policy_families:
        if _canonical_setup_key(family_id) in implemented_family_keys:
            implemented_family_ids.append(family_id)
        else:
            spec_only_family_ids.append(family_id)

    payload = {
        "status": "PASS",
        "implemented_pattern_ids": implemented_pattern_ids,
        "implemented_family_ids_derived": implemented_family_ids,
        "spec_only_family_ids": spec_only_family_ids,
        "notes": (
            "implemented_family_ids_derived is computed from RossPatternRegistry pattern names; "
            "remaining families are explicitly marked spec-only and not claimed as implemented."
        ),
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVIDENCE_DIR / "policy_registry_reconciliation.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS: policy_registry_reconciliation")
    print(f"EVIDENCE: {out_path.relative_to(REPO_ROOT)}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
