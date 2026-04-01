from __future__ import annotations

from src.core.engines.setup_hierarchy import SUPPRESSION_REASON, apply_setup_hierarchy
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _detected(family: str, pattern_id: str) -> PatternResult:
    return PatternResult(
        setup_id=pattern_id,
        pattern_name=pattern_id,
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=0.7,
        setup_quality_tags=["test"],
        setup_family_id=family,
    )


def test_setup_hierarchy_suppresses_subordinate_setups_under_opening_drive() -> None:
    results = [
        _detected("OPENING_DRIVE", "P_OPENING_DRIVE"),
        _detected("FIRST_PULLBACK", "P_FIRST_PULLBACK"),
        _detected("MICRO_PULLBACK", "P_MICRO_PULLBACK"),
        _detected("BULL_FLAG", "P_BULL_FLAG"),
    ]
    out = apply_setup_hierarchy(results, symbol="TEST")
    by_family = {item.setup_family_id: item for item in out}
    assert by_family["OPENING_DRIVE"].detected is True
    assert by_family["FIRST_PULLBACK"].detected is False
    assert by_family["FIRST_PULLBACK"].rejection_reason == SUPPRESSION_REASON
    assert by_family["MICRO_PULLBACK"].detected is False
    assert by_family["BULL_FLAG"].detected is False


def test_ross_runtime_can_consume_opening_drive_result_without_bypass() -> None:
    strategy = RossMomentumStrategyV1()
    filtered = strategy._filter_trusted_pattern_results(
        [
            {
                "setup_family_id": "OPENING_DRIVE",
                "pattern_id": "P_OPENING_DRIVE",
                "detected": True,
                "confidence": 0.8,
            }
        ],
        symbol="TEST",
    )
    assert filtered[0].get("untrusted") is not True


def test_setup_hierarchy_can_suppress_lower_tier_setups_under_key_level_break() -> None:
    results = [
        _detected("KEY_LEVEL_BREAK", "P_KEY_LEVEL_BREAK"),
        _detected("MICRO_PULLBACK", "P_MICRO_PULLBACK"),
        _detected("BULL_FLAG", "P_BULL_FLAG"),
        _detected("VWAP_PULLBACK", "P_VWAP_PULLBACK"),
    ]
    out = apply_setup_hierarchy(results, symbol="TEST")
    by_family = {item.setup_family_id: item for item in out}
    assert by_family["KEY_LEVEL_BREAK"].detected is True
    assert by_family["MICRO_PULLBACK"].detected is False
    assert by_family["MICRO_PULLBACK"].rejection_reason == SUPPRESSION_REASON
    assert by_family["BULL_FLAG"].detected is False
    assert by_family["VWAP_PULLBACK"].detected is False
