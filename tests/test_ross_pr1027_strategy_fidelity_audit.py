from __future__ import annotations

from src.strategies.ross_momentum.certification.e2e_harness import (
    build_pr6_negative_cases,
    build_pr6_positive_cases,
    run_ross_e2e_case,
    run_ross_e2e_suite,
)


_SCANNER_AND_CATALYST_REJECTION_CASES = {
    "negative_no_catalyst",
    "negative_unknown_float",
    "negative_float_above_limit",
    "negative_low_session_rvol",
    "negative_weak_pct_gap",
}

_SETUP_AND_DECISION_REJECTION_CASES = {
    "negative_stale_opening_10s",
    "negative_missing_stop",
    "negative_indicator_only_signal",
    "negative_exhaustion_risk_off",
    "negative_no_valid_setup",
}


def test_pr1027_positive_cases_preserve_scanner_to_decision_chain() -> None:
    for case in build_pr6_positive_cases():
        result = run_ross_e2e_case(case)

        assert result.expected_trade is True
        assert result.selection_passed is True
        assert result.watchlist_accepted is True
        assert result.focus_accepted is True
        assert result.watchlist_k_symbols == (case.candidate.symbol,)
        assert result.focus_m_symbols == (case.candidate.symbol,)
        assert result.inputs_built is True
        assert result.setup_detected is True
        assert result.entry_setup_detected is True
        assert result.selected_setup
        assert result.trigger_exists is True
        assert result.stop_exists is True
        assert result.rationale_exists is True
        assert result.trade_intent_created is True
        assert result.risk_gate_called is True
        assert result.risk_approved is True
        assert result.execution_path == "SIMULATED_SAFE_NON_LIVE"
        assert result.execution_safe_non_live is True
        assert result.no_trade_reason is None
        assert result.analytics_record["scanner_context"]["catalyst_status"] == "PRESENT"


def test_pr1027_scanner_and_catalyst_rejections_stop_before_setup_or_decision() -> None:
    cases = {case.name: case for case in build_pr6_negative_cases()}

    for case_name in _SCANNER_AND_CATALYST_REJECTION_CASES:
        case = cases[case_name]
        result = run_ross_e2e_case(case)

        assert result.expected_trade is False
        assert result.inputs_built is False
        assert result.setup_detected is False
        assert result.entry_setup_detected is False
        assert result.trade_intent_created is False
        assert result.risk_gate_called is False
        assert result.risk_approved is False
        assert result.execution_path == "SKIPPED"
        assert result.execution_safe_non_live is False
        assert result.no_trade_reason is not None
        assert case.expected_no_trade_reason in result.no_trade_reason


def test_pr1027_no_catalyst_is_not_silently_ignored() -> None:
    case = next(case for case in build_pr6_negative_cases() if case.name == "negative_no_catalyst")
    result = run_ross_e2e_case(case)

    assert result.watchlist_accepted is True
    assert result.focus_accepted is False
    assert result.inputs_built is False
    assert result.trade_intent_created is False
    assert result.no_trade_reason == "DROP_NO_CATALYST"
    assert result.diagnostics["selection_context"]["catalyst_present"] is False
    assert result.diagnostics["selection_context"]["catalyst_status"] == "DATA_UNAVAILABLE"


def test_pr1027_setup_and_decision_rejections_never_escape_to_risk_or_execution() -> None:
    cases = {case.name: case for case in build_pr6_negative_cases()}

    for case_name in _SETUP_AND_DECISION_REJECTION_CASES:
        case = cases[case_name]
        result = run_ross_e2e_case(case)

        assert result.expected_trade is False
        assert result.watchlist_accepted is True
        assert result.focus_accepted is True
        assert result.inputs_built is True
        assert result.trade_intent_created is False
        assert result.risk_gate_called is False
        assert result.risk_approved is False
        assert result.execution_path == "SKIPPED_NO_INTENT"
        assert result.execution_safe_non_live is False
        assert result.no_trade_reason is not None
        assert case.expected_no_trade_reason in result.no_trade_reason


def test_pr1027_suite_matrix_contains_only_certified_safe_non_live_successes() -> None:
    results = run_ross_e2e_suite()

    positive_results = [result for result in results if result.expected_trade]
    negative_results = [result for result in results if not result.expected_trade]

    assert {result.case_name for result in positive_results} == {
        "positive_micro_pullback_a_quality",
        "positive_flat_top_volume_expansion",
        "positive_pmh_break_valid_level_volume_stop_catalyst",
    }
    assert {result.case_name for result in negative_results} == (
        _SCANNER_AND_CATALYST_REJECTION_CASES | _SETUP_AND_DECISION_REJECTION_CASES
    )
    assert all(result.execution_safe_non_live for result in positive_results)
    assert all(result.trade_intent_created for result in positive_results)
    assert all(result.risk_gate_called for result in positive_results)
    assert all(not result.execution_safe_non_live for result in negative_results)
    assert all(not result.trade_intent_created for result in negative_results)
    assert all(not result.risk_gate_called for result in negative_results)
    assert all(result.analytics_record["storage_capturable"] for result in results)
