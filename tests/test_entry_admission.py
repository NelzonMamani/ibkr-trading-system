from __future__ import annotations

from dataclasses import asdict

from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator
from src.execution.entry_admission import EntryAdmissionVerdict, evaluate_entry_admission
from src.models.data_models import TradeIntent


def _intent(symbol: str = "AAPL") -> TradeIntent:
    return TradeIntent(
        symbol=symbol,
        direction="LONG",
        strategy_name="ross_momentum",
        confidence=0.9,
        rationale="unit-test",
    )


def test_healthy_paper_cycle_allows_entries() -> None:
    verdict = evaluate_entry_admission(
        run_mode=RunMode.PAPER,
        position_truth_verdict={"block_new_entries": False},
        fill_authority_verdict={"execution_stalled": False},
        lifecycle_authority_verdict={"block_new_entries": False},
    )
    assert verdict.entries_allowed is True
    assert verdict.hard_blocked is False
    assert verdict.reasons == []
    assert verdict.rationale == "entries_allowed"


def test_position_truth_blocks_entries() -> None:
    verdict = evaluate_entry_admission(
        run_mode=RunMode.PAPER,
        position_truth_verdict={"block_new_entries": True},
        fill_authority_verdict={"execution_stalled": False},
        lifecycle_authority_verdict={"block_new_entries": False},
    )
    assert verdict.entries_allowed is False
    assert any(reason.source == "POSITION_TRUTH" for reason in verdict.reasons)


def test_fill_authority_blocks_entries() -> None:
    verdict = evaluate_entry_admission(
        run_mode=RunMode.PAPER,
        position_truth_verdict={"block_new_entries": False},
        fill_authority_verdict={"execution_stalled": True},
        lifecycle_authority_verdict={"block_new_entries": False},
    )
    assert verdict.entries_allowed is False
    assert any(reason.source == "FILL_AUTHORITY" for reason in verdict.reasons)


def test_lifecycle_authority_blocks_entries() -> None:
    verdict = evaluate_entry_admission(
        run_mode=RunMode.PAPER,
        position_truth_verdict={"block_new_entries": False},
        fill_authority_verdict={"execution_stalled": False},
        lifecycle_authority_verdict={"block_new_entries": True},
    )
    assert verdict.entries_allowed is False
    assert any(reason.source == "LIFECYCLE_AUTHORITY" for reason in verdict.reasons)


def test_multiple_authorities_set_multiple_rationale() -> None:
    verdict = evaluate_entry_admission(
        run_mode=RunMode.PAPER,
        position_truth_verdict={"block_new_entries": True},
        fill_authority_verdict={"execution_stalled": True},
        lifecycle_authority_verdict={"block_new_entries": True},
    )
    assert verdict.entries_allowed is False
    assert verdict.rationale == "blocked_by_multiple_authorities"
    assert {reason.source for reason in verdict.reasons} == {
        "POSITION_TRUTH",
        "FILL_AUTHORITY",
        "LIFECYCLE_AUTHORITY",
    }


def test_read_only_always_blocks_entries() -> None:
    verdict = evaluate_entry_admission(
        run_mode=RunMode.READ_ONLY,
        position_truth_verdict={"block_new_entries": False},
        fill_authority_verdict={"execution_stalled": False},
        lifecycle_authority_verdict={"block_new_entries": False},
    )
    assert verdict.entries_allowed is False
    assert any(
        reason.source == "RUN_MODE" and reason.reason_code == "READ_ONLY_MODE"
        for reason in verdict.reasons
    )


def test_orchestrator_gate_blocks_entries_in_strict_mode() -> None:
    verdict = EntryAdmissionVerdict(
        entries_allowed=False,
        hard_blocked=True,
        reasons=[],
        rationale="blocked_by_position_truth",
    )
    gated = CoreOrchestrator._apply_entry_admission_gate(
        [_intent("AAPL"), _intent("MSFT")],
        verdict=verdict,
        strict_enforcement=True,
    )
    assert gated == []


def test_orchestrator_diagnostic_mode_does_not_top_level_drop() -> None:
    verdict = EntryAdmissionVerdict(
        entries_allowed=False,
        hard_blocked=True,
        reasons=[],
        rationale="blocked_by_fill_authority",
    )
    intents = [_intent("AAPL")]
    gated = CoreOrchestrator._apply_entry_admission_gate(
        intents,
        verdict=verdict,
        strict_enforcement=False,
    )
    assert gated == intents


def test_verdict_is_serializable() -> None:
    verdict = evaluate_entry_admission(
        run_mode=RunMode.SIM,
        position_truth_verdict={"block_new_entries": True},
        fill_authority_verdict={"execution_stalled": True},
        lifecycle_authority_verdict={"block_new_entries": True},
    )
    payload = asdict(verdict)
    assert payload["entries_allowed"] is True
    assert payload["reasons"] == []
