from __future__ import annotations

from src.metadata.strategy_policy_v2_audit import run_audit


def test_p01_remains_certified_under_matrix_v2() -> None:
    results = run_audit()
    p01 = next(result for result in results if result.strategy_id == "P01")
    assert p01.verdict == "CERTIFIED"



def test_p01_configured_family_inventory_has_explicit_policy_metadata():
    from src.setup_engine.registry import CANONICAL_SETUP_REGISTRY,build_tradeable_patterns
    from src.strategies.ross_momentum.strategy_policy import POLICY_V2
    from src.strategies.ross_momentum.patterns.pattern_types import Direction
    declared={spec.setup_id for spec in POLICY_V2.setup_families.families}
    assert declared==set(CANONICAL_SETUP_REGISTRY) and len(declared)==28
    patterns=build_tradeable_patterns()
    assert len(patterns)==len({pattern.pattern_id for pattern in patterns})==27
    assert CANONICAL_SETUP_REGISTRY['FAILED_ORB_FAKEOUT'].pattern_cls.direction_bias==Direction.SHORT
