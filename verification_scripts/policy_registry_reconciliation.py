from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2


def main() -> int:
    registry = RossPatternRegistry()
    implemented = set(registry.pattern_ids)
    catalog = list(POLICY_V2.pattern_catalog.patterns)
    execution_ids = {p.pattern_id for p in catalog if p.pattern_type == "EXECUTION"}

    missing = sorted(execution_ids - implemented)
    spec_only_patterns = sorted({p.pattern_id for p in catalog} - implemented)

    setup_families = list(POLICY_V2.setup_families.families)
    implemented_family_ids = {"MICRO_PULLBACK", "BULL_FLAG", "CONSOLIDATION_BREAKOUT", "RANGE_BREAK", "OPENING_DRIVE", "EMA_PULLBACK", "VWAP_PULLBACK", "THREE_BAR_PULLBACK", "TREND_CONTINUATION_STAIR_STEP", "SECOND_PULLBACK", "FLAT_TOP_BREAKOUT", "ASCENDING_TRIANGLE", "PENNANT", "HOD_BREAK"}
    spec_only_families = sorted({f.setup_id for f in setup_families} - implemented_family_ids)

    print("implemented_patterns=", sorted(implemented))
    print("spec_only_patterns=", spec_only_patterns)
    print("implemented_setup_families=", sorted(implemented_family_ids))
    print("spec_only_setup_families=", spec_only_families)

    if missing:
        print("missing_execution_patterns=", missing)
        return 1
    print("policy_registry_reconciliation=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
