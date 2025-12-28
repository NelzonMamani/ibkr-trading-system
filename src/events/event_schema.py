"""Lightweight event schema definitions and validation."""

from typing import Any, Dict, Set


class EventSchemaError(Exception):
    """Raised when an event payload violates the minimal schema."""


# Conservative schemas focused on consistency for teaching purposes.
REQUIRED_FIELDS: Dict[str, Set[str]] = {
    "CYCLE_START": {"run_mode"},
    "SCAN_COMPLETE": {"candidates"},
    "STRATEGY_COMPLETE": {"trade_intents"},
    "EXECUTION_COMPLETE": {"results"},
    "TRADE_OPENED": {
        "symbol",
        "trader_type",
        "strategy_name",
        "entry_price",
        "entry_tick",
    },
    "TRADE_CLOSED": {
        "symbol",
        "trader_type",
        "strategy_name",
        "entry_price",
        "exit_price",
        "pnl",
        "entry_tick",
        "exit_tick",
    },
    "TRADE_EXIT_COMPLETE": {"closed"},
    "STRATEGY_PERF_SNAPSHOT": {"strategies"},
    "PERF_SNAPSHOT": {"total_trades"},
    "TRADE_BLOCKED": {"symbol", "trader_type", "reason"},
    "RUNTIME_SAFETY_VIOLATION": {"stage", "run_mode", "replay_mode", "violations"},
    "FAULT_DETECTED": {
        "category",
        "severity",
        "message",
        "exception_type",
        "run_mode",
        "timestamp",
    },
    "FAULT_ACTION_TAKEN": {
        "category",
        "severity",
        "message",
        "exception_type",
        "run_mode",
        "timestamp",
        "recommended_action",
    },
    "SHUTDOWN_REQUESTED": {"mode", "reason", "source", "run_mode", "tick"},
    "SHUTDOWN_STARTED": {"mode", "reason", "source", "run_mode", "tick"},
    "SHUTDOWN_HOOK_FAILED": {"mode", "reason", "source", "run_mode", "tick", "hook"},
    "SHUTDOWN_COMPLETE": {"mode", "reason", "source", "run_mode", "tick"},
    "PANIC_STOP_TRIGGERED": {"mode", "reason", "source", "run_mode", "tick"},
}


OPTIONAL_FIELDS: Dict[str, Set[str]] = {
    "TRADE_OPENED": {"opened_at_tick", "mode", "direction", "quantity"},
    "TRADE_CLOSED": {
        "opened_at_tick",
        "close_tick",
        "close_price",
        "closed_at_tick",
        "realised_pnl",
        "tick",
        "mode",
        "reason",
    },
    "TRADE_EXIT_COMPLETE": {"outcomes"},
    "PERF_SNAPSHOT": {
        "wins",
        "losses",
        "flats",
        "win_rate",
        "gross_pnl",
        "avg_pnl_per_trade",
        "by_strategy",
        "by_trader_type",
    },
    "TRADE_BLOCKED": {"symbol", "trader_type", "reason"},
    "RUNTIME_SAFETY_VIOLATION": {
        "exception_type",
        "exception_message",
        "duplicate_keys",
        "stage_exception",
    },
    "FAULT_DETECTED": {"stack_hint", "recommended_action"},
    "FAULT_ACTION_TAKEN": {"stack_hint"},
    "SHUTDOWN_HOOK_FAILED": {
        "exception_type",
        "exception_message",
        "fault_category",
        "fault_severity",
    },
}


def _log_unknown_keys(event_type: str, payload: Dict[str, Any], known_keys: Set[str]) -> None:
    extra_keys = set(payload.keys()) - known_keys
    if not extra_keys:
        return
    extras_display = ", ".join(sorted(extra_keys))
    print(f"[SCHEMA] event={event_type} has extra keys: {extras_display}")


def validate_event(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Validate event payload against minimal schema.

    Allows unknown event types and extra keys but provides instructional logs.
    """

    if not isinstance(payload, dict):
        raise EventSchemaError(f"Payload for event_type={event_type} must be a dict.")

    if event_type not in REQUIRED_FIELDS:
        print(f"[SCHEMA] Unknown event_type={event_type} (no schema registered)")
        return

    required_keys = REQUIRED_FIELDS[event_type]
    missing = sorted(key for key in required_keys if key not in payload)
    if missing:
        raise EventSchemaError(
            f"event_type={event_type} missing required keys: {', '.join(missing)}"
        )

    optional_keys = OPTIONAL_FIELDS.get(event_type, set())
    known_keys = required_keys | optional_keys
    _log_unknown_keys(event_type, payload, known_keys)
