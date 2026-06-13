from __future__ import annotations

import pytest

from src.strategies.ross_momentum.certification.e2e_harness import (
    RossE2ECase,
    build_pr6_negative_cases,
    build_pr6_positive_cases,
    run_ross_e2e_case,
    run_ross_e2e_suite,
)
from src.strategies.ross_momentum.policy import IndicatorProvenance


_REQUIRED_TRACE_TAGS = (
    "[ROSS][E2E][START]",
    "[ROSS][E2E][SELECTION]",
    "[ROSS][E2E][WATCHLIST]",
    "[ROSS][E2E][FOCUS]",
    "[ROSS][E2E][INPUTS]",
    "[ROSS][E2E][SETUP]",
    "[ROSS][E2E][DECISION]",
    "[ROSS][E2E][RISK]",
    "[ROSS][E2E][EXECUTION_SIM]",
    "[ROSS][E2E][EXIT]",
    "[ROSS][E2E][RESULT]",
)


@pytest.mark.parametrize("case", build_pr6_positive_cases(), ids=lambda case: case.name)
def test_positive_pr6_cases_prove_full_safe_non_live_chain(case: RossE2ECase, capsys) -> None:
    result = run_ross_e2e_case(case)
    output = capsys.readouterr().out

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
    assert result.exit_evidence["status"] == "SIMULATED_MANAGEMENT_READY"
    assert result.analytics_record["storage_capturable"] is True
    assert result.analytics_record["intent_count"] == 1
    assert result.no_trade_reason is None
    for tag in _REQUIRED_TRACE_TAGS:
        assert tag in output


@pytest.mark.parametrize(
    "case",
    [
        case
        for case in build_pr6_negative_cases()
        if case.name
        in {
            "negative_no_catalyst",
            "negative_unknown_float",
            "negative_float_above_limit",
            "negative_low_session_rvol",
            "negative_weak_pct_gap",
        }
    ],
    ids=lambda case: case.name,
)
def test_negative_selection_cases_stop_before_inputs_and_fake_trade(case: RossE2ECase, capsys) -> None:
    result = run_ross_e2e_case(case)
    output = capsys.readouterr().out

    assert result.expected_trade is False
    assert result.execution_safe_non_live is False
    assert result.trade_intent_created is False
    assert result.risk_gate_called is False
    assert result.execution_path == "SKIPPED"
    assert result.inputs_built is False
    assert result.no_trade_reason is not None
    assert case.expected_no_trade_reason in result.no_trade_reason
    assert result.analytics_record["storage_capturable"] is True
    assert "SIMULATED_SAFE_NON_LIVE" not in result.execution_path
    assert "outcome=CREATED" not in output
    for tag in _REQUIRED_TRACE_TAGS:
        assert tag in output


def test_no_catalyst_reaches_watchlist_but_not_focus() -> None:
    case = next(case for case in build_pr6_negative_cases() if case.name == "negative_no_catalyst")
    result = run_ross_e2e_case(case)

    assert result.watchlist_accepted is True
    assert result.focus_accepted is False
    assert result.no_trade_reason == "DROP_NO_CATALYST"


@pytest.mark.parametrize(
    "case_name, reason_fragment",
    [
        ("negative_stale_opening_10s", "pr4_input_block"),
        ("negative_missing_stop", "missing_stop"),
        ("negative_indicator_only_signal", "missing_trigger"),
        ("negative_exhaustion_risk_off", "risk_off_non_entry"),
        ("negative_no_valid_setup", "no_valid_setup"),
    ],
)
def test_negative_runtime_cases_produce_no_intent_and_diagnostics(case_name: str, reason_fragment: str) -> None:
    case = next(case for case in build_pr6_negative_cases() if case.name == case_name)
    result = run_ross_e2e_case(case)

    assert result.watchlist_accepted is True
    assert result.focus_accepted is True
    assert result.inputs_built is True
    assert result.trade_intent_created is False
    assert result.risk_gate_called is False
    assert result.execution_safe_non_live is False
    assert result.no_trade_reason is not None
    assert reason_fragment in result.no_trade_reason
    assert result.analytics_record["storage_capturable"] is True
    assert result.analytics_record["no_trade_reason"] == result.no_trade_reason


def test_stale_opening_10s_is_explicitly_stale_and_blocking() -> None:
    case = next(case for case in build_pr6_negative_cases() if case.name == "negative_stale_opening_10s")
    result = run_ross_e2e_case(case)

    assert result.diagnostics["timeframe_provenance"]["10s"] == IndicatorProvenance.STALE.value
    assert "PATTERN_INPUT_BLOCK_MICRO_PULLBACK" in result.diagnostics["input_flags"]
    assert "pr4_input_block:MICRO_PULLBACK:timeframe:10s=STALE" in result.no_trade_reason


def test_malformed_setup_proofs_preserve_trigger_stop_distinctions() -> None:
    missing_stop = next(case for case in build_pr6_negative_cases() if case.name == "negative_missing_stop")
    indicator_only = next(case for case in build_pr6_negative_cases() if case.name == "negative_indicator_only_signal")

    missing_stop_result = run_ross_e2e_case(missing_stop)
    indicator_only_result = run_ross_e2e_case(indicator_only)

    assert missing_stop_result.setup_detected is True
    assert missing_stop_result.trigger_exists is True
    assert missing_stop_result.stop_exists is False
    assert missing_stop_result.rationale_exists is True
    assert indicator_only_result.setup_detected is True
    assert indicator_only_result.trigger_exists is False
    assert indicator_only_result.stop_exists is False
    assert indicator_only_result.rationale_exists is True


def test_pr6_suite_contains_required_positive_and_negative_coverage() -> None:
    results = run_ross_e2e_suite()

    positives = [result for result in results if result.expected_trade]
    negatives = [result for result in results if not result.expected_trade]
    assert {result.case_name for result in positives} == {
        "positive_micro_pullback_a_quality",
        "positive_flat_top_volume_expansion",
        "positive_pmh_break_valid_level_volume_stop_catalyst",
    }
    assert len(negatives) == 10
    assert all(result.execution_safe_non_live for result in positives)
    assert all(not result.execution_safe_non_live for result in negatives)
    assert all(result.analytics_record["storage_capturable"] for result in results)
