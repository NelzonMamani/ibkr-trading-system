from config.runtime_config import RunMode
from core.faults import (
    FaultCategory,
    FaultEvent,
    FaultSeverity,
    classify_exception,
    decide_recovery_action,
    RecoveryAction,
)


def test_classify_file_not_found_is_io():
    fault = classify_exception(FileNotFoundError("missing"))
    assert fault.category == FaultCategory.IO


def test_classify_key_error_is_data():
    fault = classify_exception(KeyError("symbol"))
    assert fault.category == FaultCategory.DATA


def test_classify_runtime_safety_flagged_as_safety():
    fault = classify_exception(RuntimeError("[SAFETY] tripwire"))
    assert fault.category == FaultCategory.SAFETY


def test_live_policy_enforces_halt_and_skip_rules():
    safety_fault = FaultEvent(
        category=FaultCategory.SAFETY,
        severity=FaultSeverity.CRITICAL,
        message="halt me",
        exception_type="RuntimeError",
    )
    unknown_fault = FaultEvent(
        category=FaultCategory.UNKNOWN,
        severity=FaultSeverity.CRITICAL,
        message="unknown",
        exception_type="Exception",
    )
    data_fault = FaultEvent(
        category=FaultCategory.DATA,
        severity=FaultSeverity.WARNING,
        message="data issue",
        exception_type="ValueError",
    )

    assert decide_recovery_action(safety_fault, RunMode.LIVE) == RecoveryAction.HALT_SYSTEM
    assert decide_recovery_action(unknown_fault, RunMode.LIVE) == RecoveryAction.HALT_SYSTEM
    assert decide_recovery_action(data_fault, RunMode.LIVE) == RecoveryAction.SKIP_STAGE
