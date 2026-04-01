from __future__ import annotations

from src.core.engines.setup_hierarchy import apply_setup_hierarchy
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _result(setup_id: str, family: str, *, detected: bool = True) -> PatternResult:
    return PatternResult(
        setup_id=setup_id,
        pattern_name=setup_id,
        pattern_family=PatternFamily.BREAKOUT,
        detected=detected,
        direction=Direction.LONG,
        confidence=0.7,
        setup_quality_tags=[],
        setup_family_id=family,
        rationale_text="baseline",
    )


def test_setup_hierarchy_can_suppress_lower_precision_setups_under_hod_break() -> None:
    results = [
        _result("P_HOD_BREAK", "HOD_BREAK", detected=True),
        _result("P_MICRO_PULLBACK", "MICRO_PULLBACK", detected=True),
        _result("P_BULL_FLAG", "BULL_FLAG", detected=True),
        _result("P_THREE_BAR_PULLBACK", "THREE_BAR_PULLBACK", detected=True),
    ]

    out = apply_setup_hierarchy(results, symbol="HODX")
    by_family = {item.setup_family_id: item for item in out}

    assert by_family["HOD_BREAK"].detected is True
    assert by_family["MICRO_PULLBACK"].detected is False
    assert by_family["MICRO_PULLBACK"].rejection_reason == "suppressed_by_setup_exclusivity"
    assert by_family["BULL_FLAG"].detected is False
    assert by_family["THREE_BAR_PULLBACK"].detected is False
