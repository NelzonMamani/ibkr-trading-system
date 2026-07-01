from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import (
    RunMode,
    broker_orders_allowed,
    execution_allowed,
    get_execution_enabled,
    get_ibkr_api_write_allowed,
    get_ibkr_order_submission_enabled,
    get_ibkr_readonly_enabled,
)
from src.core.managers.runtime_mode_manager import RuntimeModeManager
from src.strategies.ross_momentum.certification.e2e_harness import (
    RossE2ECase,
    build_pr6_negative_cases,
    build_pr6_positive_cases,
    run_ross_e2e_case,
)


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

_FORBIDDEN_ORDER_MARKERS = (
    "BROKER_ORDER_SUBMITTED",
    "ORDER_SUBMITTED",
    "SUBMIT_ORDER",
    "PLACE_ORDER",
    "LIVE_ORDER",
)

_REPORT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "certification"
    / "PR1031_READ_ONLY_FULL_SESSION_DRY_RUN_AND_PAPER_READINESS_GATE.md"
)


@pytest.fixture(autouse=True)
def _force_readonly_config(monkeypatch: pytest.MonkeyPatch):
    for key in (
        "RUN_MODE",
        "RUN_MODE_EFFECTIVE",
        "EXECUTION_ENABLED",
        "EXECUTION_ENABLED_EFFECTIVE",
        "EVENT_REPLAY_MODE",
        "EVENT_REPLAY_MODE_EFFECTIVE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RUN_MODE", "READ_ONLY")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "RUN_MODE_EFFECTIVE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "EXECUTION_ENABLED_EFFECTIVE": False,
            "EVENT_REPLAY_MODE": "OFF",
            "EVENT_REPLAY_MODE_EFFECTIVE": "OFF",
        }
    )
    yield
    set_config_overrides({})


def _readonly_case(case: RossE2ECase) -> RossE2ECase:
    return replace(case, run_mode="READ_ONLY")


def _assert_readonly_order_authority_blocked() -> None:
    manager = RuntimeModeManager.resolve()

    assert manager.resolved_mode is RunMode.READ_ONLY
    assert manager.is_live_like is True
    assert manager.allow_orders is False
    assert manager.event_replay_mode.value == "OFF"
    assert execution_allowed("READ_ONLY") is False
    assert broker_orders_allowed("READ_ONLY") is False
    assert get_execution_enabled() is False
    assert get_ibkr_api_write_allowed() is False
    assert get_ibkr_order_submission_enabled() is False
    assert get_ibkr_readonly_enabled() is True


def test_pr1031_readonly_positive_session_reaches_decision_without_broker_order(capsys) -> None:
    case = _readonly_case(
        next(
            candidate
            for candidate in build_pr6_positive_cases()
            if candidate.name == "positive_micro_pullback_a_quality"
        )
    )

    result = run_ross_e2e_case(case)
    output = capsys.readouterr().out

    _assert_readonly_order_authority_blocked()
    assert result.selection_passed is True
    assert result.watchlist_accepted is True
    assert result.focus_accepted is True
    assert result.inputs_built is True
    assert result.setup_detected is True
    assert result.entry_setup_detected is True
    assert result.trigger_exists is True
    assert result.stop_exists is True
    assert result.rationale_exists is True
    assert result.trade_intent_created is True
    assert result.risk_gate_called is True
    assert result.risk_approved is True
    assert result.execution_path == "SIMULATED_SAFE_NON_LIVE"
    assert result.execution_safe_non_live is True
    assert result.exit_evidence["status"] == "SIMULATED_MANAGEMENT_READY"
    assert result.exit_evidence["stop_model"]
    assert result.exit_evidence["target_model"]
    assert result.analytics_record["run_mode"] == "READ_ONLY"
    assert result.analytics_record["storage_capturable"] is True
    assert result.analytics_record["intent_count"] == 1
    assert result.no_trade_reason is None
    assert "[ROSS][OVERRIDE][PAPER_MODE]" not in output
    assert all(marker not in output for marker in _FORBIDDEN_ORDER_MARKERS)
    for tag in _REQUIRED_TRACE_TAGS:
        assert tag in output


def test_pr1031_readonly_negative_session_persists_no_trade_without_fake_intent(capsys) -> None:
    case = _readonly_case(
        next(
            candidate
            for candidate in build_pr6_negative_cases()
            if candidate.name == "negative_no_catalyst"
        )
    )

    result = run_ross_e2e_case(case)
    output = capsys.readouterr().out

    _assert_readonly_order_authority_blocked()
    assert result.watchlist_accepted is True
    assert result.focus_accepted is False
    assert result.inputs_built is False
    assert result.setup_detected is False
    assert result.trade_intent_created is False
    assert result.risk_gate_called is False
    assert result.risk_approved is False
    assert result.execution_path == "SKIPPED"
    assert result.execution_safe_non_live is False
    assert result.no_trade_reason == "DROP_NO_CATALYST"
    assert result.analytics_record["storage_capturable"] is True
    assert result.analytics_record["no_trade_reason"] == "DROP_NO_CATALYST"
    assert "outcome=CREATED" not in output
    assert all(marker not in output for marker in _FORBIDDEN_ORDER_MARKERS)
    for tag in _REQUIRED_TRACE_TAGS:
        assert tag in output


def test_pr1031_readonly_mode_blocks_execution_even_if_execution_flag_is_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUN_MODE", "READ_ONLY")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "RUN_MODE_EFFECTIVE": "READ_ONLY",
            "EXECUTION_ENABLED": True,
            "EXECUTION_ENABLED_EFFECTIVE": True,
            "EVENT_REPLAY_MODE": "CYCLE",
            "EVENT_REPLAY_MODE_EFFECTIVE": "CYCLE",
        }
    )

    manager = RuntimeModeManager.resolve()

    assert manager.resolved_mode is RunMode.READ_ONLY
    assert manager.allow_orders is False
    assert manager.event_replay_mode.value == "OFF"
    assert execution_allowed(manager.resolved_mode) is False
    assert broker_orders_allowed(manager.resolved_mode) is False
    assert get_execution_enabled() is False
    assert get_ibkr_api_write_allowed() is False
    assert get_ibkr_order_submission_enabled() is False
    assert get_ibkr_readonly_enabled() is True


def test_pr1031_report_keeps_paper_readiness_blocked_and_scope_precise() -> None:
    report = _REPORT_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "PAPER_READY: NO",
        "READ_ONLY_FULL_SESSION_REPLAY: CERTIFIED_DETERMINISTIC",
        "BROKER_ORDER_SUBMISSION_CERTIFIED_BLOCKED: YES",
        "REAL_BROKER_RUNTIME_SESSION_CERTIFIED: NO",
        "PAPER_READINESS_GATE: FAIL",
        "DO_NOT_GO_PAPER_REASON:",
        "numeric R:R remains uncertified",
        "partial/trailing/breakeven lifecycle behavior remains uncertified",
        "No PAPER/LIVE enablement was added.",
    )
    forbidden_fragments = (
        "PAPER_READY: YES",
        "PAPER_READINESS_GATE: PASS",
        "REAL_BROKER_RUNTIME_SESSION_CERTIFIED: YES",
        "PARTIAL_EXIT_MAPPING_CERTIFIED: YES",
        "TRAILING_BREAKEVEN_MAPPING_CERTIFIED: YES",
    )

    for fragment in required_fragments:
        assert fragment in report
    for fragment in forbidden_fragments:
        assert fragment not in report
