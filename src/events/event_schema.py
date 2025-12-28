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
}


OPTIONAL_FIELDS: Dict[str, Set[str]] = {
    "TRADE_OPENED": {"opened_at_tick", "mode", "direction", "quantity"},
    "TRADE_CLOSED": {
        "opened_at_tick",
        "close_tick",
        "close_price",
        "closed_at_tick",
        "realised_pnl",
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
