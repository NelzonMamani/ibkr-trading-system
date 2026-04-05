from src.core.pipeline_audit import PipelineAudit, TerminalOutcome, normalize_execution_reason


def test_missing_pattern_inputs_not_no_pattern_detected() -> None:
    audit = PipelineAudit("cycle-a")
    audit.mark_kept(["ABCD"])
    audit.record("ABCD", TerminalOutcome.MISSING_PATTERN_INPUTS, "failed_to_build_inputs", "pattern")
    summary = audit.summary_payload()
    assert summary["symbols"]["ABCD"]["outcome"] == "MISSING_PATTERN_INPUTS"


def test_execution_ready_path_requires_submission_or_explicit_failure() -> None:
    audit = PipelineAudit("cycle-b")
    audit.mark_kept(["RSPT"])
    audit.mark_stage("RSPT", "PATTERN", pattern_inputs_ready=True, pattern_detected=True)
    audit.mark_stage("RSPT", "TRIGGER", trigger_fired=True)
    audit.mark_stage("RSPT", "INTENT", intent_emitted=True)
    audit.mark_stage("RSPT", "RISK", risk_approved=True)
    audit.mark_stage("RSPT", "EXECUTION", execution_attempted=True, execution_submitted=False)
    audit.record("RSPT", TerminalOutcome.EXECUTION_SUBMISSION_FAILED, "SUBMISSION_EXCEPTION", "execution")
    summary = audit.summary_payload()
    assert summary["symbols"]["RSPT"]["outcome"] in {"EXECUTION_SUBMITTED", "EXECUTION_SUBMISSION_FAILED"}


def test_session_policy_block_explicitly_labeled() -> None:
    audit = PipelineAudit("cycle-c")
    audit.mark_kept(["TSLA"])
    audit.record("TSLA", TerminalOutcome.SKIPPED_MODE_OR_SESSION_POLICY, "SESSION_BLOCK", "execution")
    assert audit.summary_payload()["symbols"]["TSLA"]["outcome"] == "SKIPPED_MODE_OR_SESSION_POLICY"


def test_risk_block_explicitly_labeled() -> None:
    audit = PipelineAudit("cycle-d")
    audit.mark_kept(["AAPL"])
    audit.record("AAPL", TerminalOutcome.RISK_BLOCKED, "MAX_RISK_EXCEEDED", "risk")
    assert audit.summary_payload()["symbols"]["AAPL"]["outcome"] == "RISK_BLOCKED"


def test_execution_disabled_reason_normalized() -> None:
    assert normalize_execution_reason("execution_disabled") == "EXECUTION_DISABLED"


def test_submitted_without_callback_is_callback_pending() -> None:
    audit = PipelineAudit("cycle-e")
    audit.mark_kept(["NVDA"])
    audit.mark_stage("NVDA", "EXECUTION", execution_attempted=True, execution_submitted=True)
    audit.record("NVDA", TerminalOutcome.CALLBACK_PENDING, "CALLBACK_PENDING", "execution")
    assert audit.summary_payload()["symbols"]["NVDA"]["outcome"] == "CALLBACK_PENDING"


def test_cycle_summary_readiness_counts_deterministic() -> None:
    audit = PipelineAudit("cycle-f")
    audit.mark_kept(["X", "Y"])
    audit.mark_stage("X", "PATTERN", pattern_detected=True)
    audit.mark_stage("X", "TRIGGER", trigger_fired=True)
    audit.mark_stage("X", "INTENT", intent_emitted=True)
    audit.mark_stage("X", "RISK", risk_approved=True)
    audit.mark_stage("X", "EXECUTION", execution_attempted=True, execution_submitted=True)
    audit.record("X", TerminalOutcome.EXECUTION_SUBMITTED, "ORDER_SUBMITTED", "execution")
    audit.record("Y", TerminalOutcome.NO_PATTERN_DETECTED, "NO_SETUP", "strategy")
    readiness = audit.summary_payload()["readiness"]
    assert readiness == {
        "symbols_pattern_ready": 1,
        "symbols_trigger_ready": 1,
        "symbols_intent_ready": 1,
        "symbols_risk_ready": 1,
        "symbols_execution_ready": 1,
        "symbols_submitted": 1,
    }


def test_no_terminal_verdict_ambiguity_for_symbol_cycle() -> None:
    audit = PipelineAudit("cycle-g")
    audit.mark_kept(["META"])
    audit.record("META", TerminalOutcome.NO_PATTERN_DETECTED, "NO_SETUP", "pattern")
    audit.record("META", TerminalOutcome.RISK_BLOCKED, "MAX_RISK_EXCEEDED", "risk")
    summary = audit.summary_payload()
    assert summary["symbols"]["META"]["outcome"] == "RISK_BLOCKED"
    assert len(summary["symbols"]) == 1


def test_duplicate_position_block_labeled_execution_stage() -> None:
    audit = PipelineAudit("cycle-h")
    audit.mark_kept(["PLTR"])
    audit.record("PLTR", TerminalOutcome.EXECUTION_PRECHECK_BLOCKED, "DUPLICATE_POSITION_CONFLICT", "execution")
    symbol = audit.summary_payload()["symbols"]["PLTR"]
    assert symbol["stage"] == "execution"
    assert symbol["reason"] == "DUPLICATE_POSITION_BLOCKED"


def test_price_authority_block_labeled_execution_stage() -> None:
    audit = PipelineAudit("cycle-i")
    audit.mark_kept(["SMCI"])
    audit.record("SMCI", TerminalOutcome.EXECUTION_PRECHECK_BLOCKED, "PRICE_AUTHORITY_BLOCKED:stale_quote", "execution")
    symbol = audit.summary_payload()["symbols"]["SMCI"]
    assert symbol["stage"] == "execution"
    assert symbol["reason"] == "PRICE_AUTHORITY_BLOCKED"
