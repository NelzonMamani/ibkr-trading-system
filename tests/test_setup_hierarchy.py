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


def test_first_pullback_suppression_accepts_actual_trace_schema_without_mutation():
    from copy import deepcopy
    from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternTrace
    def trace(family):
        return RossPatternTrace(symbol='SYNTH',cycle_id='synthetic',strategy_key='ross_momentum',
            session_label='REGULAR',session_phase='RTH_OPEN',runtime_mode='READ_ONLY',
            symbol_source='synthetic',pattern_id='P_'+family,pattern_name=family,
            setup_family_id=family,detected=True,invoked=True)
    originals=[trace('MICRO_PULLBACK'),trace('FIRST_PULLBACK')]
    before=deepcopy(originals)
    out=apply_setup_hierarchy(originals,symbol='SYNTH')
    assert originals==before and out[1] is originals[1] and out[1].detected
    assert not out[0].detected and out[0].rejection_reason=='suppressed_by_setup_exclusivity'
    assert not hasattr(out[0],'rationale_text')
    # Existing result and dictionary projections keep their own supported rationale.
    result=apply_setup_hierarchy([_result('P_FIRST_PULLBACK','FIRST_PULLBACK'),
        _result('P_MICRO_PULLBACK','MICRO_PULLBACK')],symbol='SYNTH')[1]
    assert not result.detected and 'dominant=FIRST_PULLBACK' in result.rationale_text
    rows=[dict(setup_family_id='FIRST_PULLBACK',detected=True),dict(setup_family_id='MICRO_PULLBACK',detected=True)]
    saved=deepcopy(rows); projected=apply_setup_hierarchy(rows,symbol='SYNTH')
    assert rows==saved and not projected[1]['detected'] and 'dominant=FIRST_PULLBACK' in projected[1]['rationale_text']



def test_only_qualified_ready_entry_families_can_exercise_exclusivity():
    gap=_result('P_GAP_GO','GAP_GO')
    micro=_result('P_MICRO_PULLBACK','MICRO_PULLBACK')
    # Legacy API retains its default; the strategy supplies qualification only
    # after actual complete-contract/own-trigger evaluation.
    assert not apply_setup_hierarchy([gap,micro])[1].detected
    qualified=apply_setup_hierarchy([gap,micro],dominant_families={'MICRO_PULLBACK'})
    assert qualified==[gap,micro] and all(r.detected for r in qualified)
    hod=_result('P_HOD_BREAK','HOD_BREAK')
    assert apply_setup_hierarchy([hod,micro],dominant_families={'MICRO_PULLBACK'})==[hod,micro]
    assert not apply_setup_hierarchy([hod,micro],dominant_families={'HOD_BREAK','MICRO_PULLBACK'})[1].detected


def test_qualified_exclusivity_keeps_risk_off_and_opposing_direction_authority():
    from dataclasses import replace
    from src.core.engines.decision_engine import DecisionEngine
    hod=_result('P_HOD_BREAK','HOD_BREAK')
    bull=_result('P_BULL_FLAG','BULL_FLAG')
    warning=replace(bull,signal_class='RISK_OFF',non_entry_signal=True)
    opposing=replace(bull,direction=Direction.SHORT)
    for guard in (warning,opposing):
        projected=apply_setup_hierarchy([hod,guard],dominant_families={'HOD_BREAK'})
        assert projected==[hod,guard] and projected[1].detected
        out=DecisionEngine().compute_decision(symbol='SYNTH',levels={},structure={},setups=[],
            pattern_results=projected,entry_contract_validator=lambda source:(True,'valid'),
            trigger_readiness_validator=lambda index,source:(index==0,'unready'))
        assert out['selected_pattern_id'] is None
