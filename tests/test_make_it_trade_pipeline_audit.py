from pathlib import Path

from src.core.pipeline_audit import PipelineAudit, TerminalOutcome


def test_kept_symbol_not_selected_for_focus_has_terminal_outcome(tmp_path: Path) -> None:
    audit = PipelineAudit("cycle-1")
    audit.mark_kept(["BOIL"])
    audit.record("BOIL", TerminalOutcome.NOT_IN_FOCUS, "NOT_SELECTED_FOR_FOCUS", "focus")
    assert not audit.contract_violations()


def test_focus_selected_with_no_pattern_has_terminal_outcome() -> None:
    audit = PipelineAudit("cycle-1")
    audit.mark_kept(["ABCD"])
    audit.record("ABCD", TerminalOutcome.FOCUS_SELECTED_NO_PATTERN, "NO_SETUP", "strategy")
    assert audit.summary_payload()["symbols"]["ABCD"]["outcome"] == "FOCUS_SELECTED_NO_PATTERN"


def test_detected_pattern_but_rejected_decision_terminal_outcome() -> None:
    audit = PipelineAudit("cycle-1")
    audit.mark_kept(["EFGH"])
    audit.record("EFGH", TerminalOutcome.DECISION_REJECTED, "DECISION_RULE_BLOCK", "decision")
    assert audit.summary_payload()["symbols"]["EFGH"]["outcome"] == "DECISION_REJECTED"


def test_decision_passes_trigger_fails_terminal_outcome() -> None:
    audit = PipelineAudit("cycle-1")
    audit.mark_kept(["IJKL"])
    audit.record("IJKL", TerminalOutcome.TRIGGER_NOT_FIRED, "TRIGGER_CONDITION_NOT_MET", "trigger")
    assert audit.summary_payload()["symbols"]["IJKL"]["outcome"] == "TRIGGER_NOT_FIRED"


def test_trigger_passes_creates_trade_intent_terminal_outcome() -> None:
    audit = PipelineAudit("cycle-1")
    audit.mark_kept(["MNOP"])
    audit.record("MNOP", TerminalOutcome.TRADE_INTENT_CREATED, "INTENT_CREATED", "intent")
    assert audit.summary_payload()["symbols"]["MNOP"]["outcome"] == "TRADE_INTENT_CREATED"


def test_trade_intent_created_but_execution_blocked_terminal_outcome() -> None:
    audit = PipelineAudit("cycle-1")
    audit.mark_kept(["QRST"])
    audit.record("QRST", TerminalOutcome.EXECUTION_BLOCKED, "EXECUTION_DISABLED", "execution")
    assert audit.summary_payload()["symbols"]["QRST"]["outcome"] == "EXECUTION_BLOCKED"


def test_all_kept_symbols_accounted_for_in_cycle_summary(tmp_path: Path) -> None:
    audit = PipelineAudit("cycle-1")
    audit.mark_kept(["UVWX", "YZAA"])
    audit.record("UVWX", TerminalOutcome.NOT_IN_FOCUS, "NOT_SELECTED_FOR_FOCUS", "focus")
    audit.record("YZAA", TerminalOutcome.EXECUTION_SUBMITTED, "ORDER_SUBMITTED", "execution")
    paths = audit.persist(base_dir=tmp_path)
    assert not audit.contract_violations()
    assert Path(paths["summary"]).exists()
    assert Path(paths["outcomes"]).exists()
