"""Fault classification and deterministic recovery policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from src.config.runtime_config import RunMode


class FaultCategory(str, Enum):
    CONFIG = "CONFIG"
    SAFETY = "SAFETY"
    IO = "IO"
    DATA = "DATA"
    EXTERNAL = "EXTERNAL"
    LOGIC = "LOGIC"
    STATE = "STATE"
    UNKNOWN = "UNKNOWN"


class FaultSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class RecoveryAction(str, Enum):
    IGNORE = "IGNORE"
    RETRY = "RETRY"
    SKIP_STAGE = "SKIP_STAGE"
    SKIP_CYCLE = "SKIP_CYCLE"
    DEGRADE_MODE = "DEGRADE_MODE"
    ABORT_CYCLE = "ABORT_CYCLE"
    HALT_SYSTEM = "HALT_SYSTEM"


@dataclass(frozen=True)
class FaultEvent:
    category: FaultCategory
    severity: FaultSeverity
    message: str
    exception_type: str
    stack_hint: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


_CATEGORY_SEVERITY: Dict[FaultCategory, FaultSeverity] = {
    FaultCategory.SAFETY: FaultSeverity.CRITICAL,
    FaultCategory.CONFIG: FaultSeverity.CRITICAL,
    FaultCategory.STATE: FaultSeverity.CRITICAL,
    FaultCategory.LOGIC: FaultSeverity.CRITICAL,
    FaultCategory.IO: FaultSeverity.ERROR,
    FaultCategory.DATA: FaultSeverity.WARNING,
    FaultCategory.EXTERNAL: FaultSeverity.ERROR,
    FaultCategory.UNKNOWN: FaultSeverity.CRITICAL,
}


def _default_severity(category: FaultCategory) -> FaultSeverity:
    return _CATEGORY_SEVERITY.get(category, FaultSeverity.ERROR)


def classify_exception(exc: Exception) -> FaultEvent:
    """Classify an exception into a structured FaultEvent."""

    from src.events.event_invariants import EventInvariantError

    if isinstance(exc, RuntimeError) and "[SAFETY]" in str(exc):
        category = FaultCategory.SAFETY
    elif isinstance(exc, RuntimeError) and "[REPLAY]" in str(exc):
        category = FaultCategory.SAFETY
    elif isinstance(exc, EventInvariantError):
        category = FaultCategory.STATE
    elif isinstance(exc, FileNotFoundError):
        category = FaultCategory.IO
    elif isinstance(exc, OSError):
        category = FaultCategory.IO
    elif isinstance(exc, KeyError):
        category = FaultCategory.DATA
    elif isinstance(exc, ValueError):
        category = FaultCategory.DATA
    elif isinstance(exc, TypeError):
        category = FaultCategory.LOGIC
    else:
        category = FaultCategory.UNKNOWN

    severity = _default_severity(category)
    stack_hint = None
    if hasattr(exc, "args") and exc.args:
        stack_hint = str(exc.args[0])

    return FaultEvent(
        category=category,
        severity=severity,
        message=str(exc),
        exception_type=type(exc).__name__,
        stack_hint=stack_hint,
    )


def decide_recovery_action(fault: FaultEvent, run_mode: RunMode) -> RecoveryAction:
    """Deterministically map fault categories to recovery actions by run mode."""

    if run_mode in {
        RunMode.LIVE,
        RunMode.LIVE_READ_ONLY,
        RunMode.LIVE_MICRO,
        RunMode.LIVE_ONE_SHARE,
    }:
        mapping = {
            FaultCategory.SAFETY: RecoveryAction.HALT_SYSTEM,
            FaultCategory.CONFIG: RecoveryAction.HALT_SYSTEM,
            FaultCategory.STATE: RecoveryAction.HALT_SYSTEM,
            FaultCategory.LOGIC: RecoveryAction.HALT_SYSTEM,
            FaultCategory.IO: RecoveryAction.ABORT_CYCLE,
            FaultCategory.DATA: RecoveryAction.SKIP_STAGE,
            FaultCategory.EXTERNAL: RecoveryAction.ABORT_CYCLE,
            FaultCategory.UNKNOWN: RecoveryAction.HALT_SYSTEM,
        }
    elif run_mode == RunMode.PAPER:
        mapping = {
            FaultCategory.SAFETY: RecoveryAction.HALT_SYSTEM,
            FaultCategory.CONFIG: RecoveryAction.HALT_SYSTEM,
            FaultCategory.STATE: RecoveryAction.HALT_SYSTEM,
            FaultCategory.LOGIC: RecoveryAction.HALT_SYSTEM,
            FaultCategory.IO: RecoveryAction.RETRY,
            FaultCategory.DATA: RecoveryAction.SKIP_STAGE,
            FaultCategory.EXTERNAL: RecoveryAction.RETRY,
            FaultCategory.UNKNOWN: RecoveryAction.ABORT_CYCLE,
        }
    else:
        mapping = {
            FaultCategory.SAFETY: RecoveryAction.HALT_SYSTEM,
            FaultCategory.CONFIG: RecoveryAction.ABORT_CYCLE,
            FaultCategory.STATE: RecoveryAction.ABORT_CYCLE,
            FaultCategory.LOGIC: RecoveryAction.ABORT_CYCLE,
            FaultCategory.IO: RecoveryAction.RETRY,
            FaultCategory.DATA: RecoveryAction.SKIP_STAGE,
            FaultCategory.EXTERNAL: RecoveryAction.RETRY,
            FaultCategory.UNKNOWN: RecoveryAction.ABORT_CYCLE,
        }

    return mapping.get(fault.category, RecoveryAction.ABORT_CYCLE)


def fault_to_payload(
    fault: FaultEvent,
    run_mode: RunMode,
    action: Optional[RecoveryAction] = None,
) -> Dict[str, Any]:
    """Convert fault metadata into an event payload."""

    payload: Dict[str, Any] = {
        "category": fault.category.value,
        "severity": fault.severity.value,
        "message": fault.message,
        "exception_type": fault.exception_type,
        "run_mode": run_mode.value,
        "timestamp": fault.timestamp.isoformat(),
    }
    if fault.stack_hint is not None:
        payload["stack_hint"] = fault.stack_hint
    if action is not None:
        payload["recommended_action"] = action.value
    return payload
