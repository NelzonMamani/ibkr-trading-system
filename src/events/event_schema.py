"""Lightweight event schema definitions and validation."""

from typing import Any, Dict, Set


class EventSchemaError(Exception):
    """Raised when an event payload violates the minimal schema."""


TRADE_OPENED_SCHEMA = {
    "symbol": str,
    "trader_type": str,
    "strategy_name": str,
    "entry_tick": int,
    "opened_at_tick": int,
    "entry_price": float,
    "raw_price": float,
    "slippage_applied": float,
    "execution_price": float,
    "mode": str,
    "direction": str,
    "quantity": int,
    "stop_loss_price": (float, type(None)),
    "take_profit_price": (float, type(None)),
    "requested_quantity": int,
    "filled_quantity": int,
    "remaining_quantity": int,
    "fill_status": str,
}

TRADE_CLOSED_SCHEMA = {
    "symbol": str,
    "trader_type": str,
    "strategy_name": str,
    "entry_tick": int,
    "exit_tick": int,
    "entry_price": float,
    "exit_price": float,
    "raw_price": float,
    "slippage_applied": float,
    "execution_price": float,
    "direction": str,
    "quantity": int,
    "exit_category": str,
    "exit_reason": str,
    "pnl": float,
    "hold_duration_ticks": int,
    "min_hold_ticks": int,
    "max_hold_ticks": int,
    "stop_loss_price": (float, type(None)),
    "take_profit_price": (float, type(None)),
}

TRADE_NOT_FILLED_SCHEMA = {
    "symbol": str,
    "trader_type": str,
    "tick": int,
    "requested_quantity": int,
    "available_liquidity": int,
    "filled_quantity": int,
    "remaining_quantity": int,
    "reason": str,
    "fill_status": str,
}

EVENT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "TRADE_OPENED": TRADE_OPENED_SCHEMA,
    "TRADE_CLOSED": TRADE_CLOSED_SCHEMA,
    "TRADE_NOT_FILLED": TRADE_NOT_FILLED_SCHEMA,
    "ORDER_SUBMISSION_ATTEMPTED": {
        "client_order_id": str,
        "symbol": str,
        "direction": str,
        "quantity": int,
        "order_type": str,
        "timestamp": str,
    },
    "ORDER_SUBMITTED_ACK": {
        "client_order_id": str,
        "symbol": str,
        "direction": str,
        "quantity": int,
        "order_type": str,
        "timestamp": str,
        "ibkr_order_id": (int, type(None)),
        "ack_status": (str, type(None)),
    },
    "ORDER_SUBMISSION_FAILED": {
        "client_order_id": str,
        "symbol": str,
        "direction": str,
        "quantity": int,
        "order_type": str,
        "timestamp": str,
        "ibkr_order_id": (int, type(None)),
        "reason": (str, type(None)),
    },
    "ORDER_SUBMISSION_BLOCKED": {
        "client_order_id": str,
        "symbol": str,
        "direction": str,
        "quantity": int,
        "order_type": str,
        "timestamp": str,
        "reason": str,
    },
    "SIGNALS_GENERATED": {
        "signals": int,
    },
    "SIGNAL_EMITTED": {
        "symbol": str,
        "signal_type": str,
        "decision": str,
        "confidence": float,
    },
    "SIGNAL_INVALID": {
        "symbol": str,
        "signal_type": str,
        "decision": str,
        "confidence": float,
    },
    "INTENTS_FROM_SIGNALS": {
        "tick": int,
        "total_intents": int,
        "by_trader_type": dict,
        "by_strategy": dict,
    },
}


# Conservative schemas focused on consistency for teaching purposes.
REQUIRED_FIELDS: Dict[str, Set[str]] = {
    "CYCLE_START": {"run_mode"},
    "SCAN_COMPLETE": {"candidates"},
    "STRATEGY_COMPLETE": {"trade_intents"},
    "EXECUTION_COMPLETE": {"results"},
    "TRADE_OPENED": set(TRADE_OPENED_SCHEMA.keys()),
    "TRADE_NOT_FILLED": set(TRADE_NOT_FILLED_SCHEMA.keys()),
    "TRADE_CLOSED": {
        "symbol",
        "trader_type",
        "strategy_name",
        "entry_price",
        "exit_price",
        "raw_price",
        "slippage_applied",
        "execution_price",
        "pnl",
        "entry_tick",
        "exit_tick",
        "hold_duration_ticks",
        "min_hold_ticks",
        "max_hold_ticks",
        "stop_loss_price",
        "take_profit_price",
    },
    "EXIT_SIGNALS_GENERATED": {"exit_signals"},
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
    "ORDER_SUBMISSION_ATTEMPTED": {
        "client_order_id",
        "symbol",
        "direction",
        "quantity",
        "order_type",
        "timestamp",
    },
    "ORDER_SUBMITTED_ACK": {
        "client_order_id",
        "symbol",
        "direction",
        "quantity",
        "order_type",
        "timestamp",
    },
    "ORDER_SUBMISSION_FAILED": {
        "client_order_id",
        "symbol",
        "direction",
        "quantity",
        "order_type",
        "timestamp",
    },
    "ORDER_SUBMISSION_BLOCKED": {
        "client_order_id",
        "symbol",
        "direction",
        "quantity",
        "order_type",
        "timestamp",
        "reason",
    },
    "SIGNALS_GENERATED": {"signals"},
    "SIGNAL_EMITTED": {"symbol", "signal_type", "decision", "confidence"},
    "SIGNAL_INVALID": {"symbol", "signal_type", "decision", "confidence"},
    "INTENTS_FROM_SIGNALS": {
        "tick",
        "total_intents",
        "by_trader_type",
        "by_strategy",
    },
}


OPTIONAL_FIELDS: Dict[str, Set[str]] = {
    "TRADE_OPENED": set(),
    "TRADE_NOT_FILLED": set(),
    "TRADE_CLOSED": {
        "opened_at_tick",
        "close_tick",
        "close_price",
        "closed_at_tick",
        "realised_pnl",
        "gross_realised_pnl",
        "commission",
        "net_realised_pnl",
        "tick",
        "mode",
        "reason",
    },
    "TRADE_EXIT_COMPLETE": {"outcomes"},
    "EXIT_SIGNALS_GENERATED": set(),
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
    "ORDER_SUBMISSION_ATTEMPTED": {"ibkr_order_id", "reason"},
    "ORDER_SUBMITTED_ACK": {"ibkr_order_id", "ack_status", "reason"},
    "ORDER_SUBMISSION_FAILED": {"ibkr_order_id", "reason"},
    "ORDER_SUBMISSION_BLOCKED": {"ibkr_order_id"},
}


def _log_unknown_keys(event_type: str, payload: Dict[str, Any], known_keys: Set[str]) -> None:
    extra_keys = set(payload.keys()) - known_keys
    if not extra_keys:
        return
    extras_display = ", ".join(sorted(extra_keys))
    print(f"[SCHEMA] event={event_type} has extra keys: {extras_display}")


def _validate_field_types(event_type: str, payload: Dict[str, Any], schema: Dict[str, Any]) -> None:
    for key, expected_type in schema.items():
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, expected_type):
            continue
        raise EventSchemaError(
            f"event_type={event_type} invalid type for key='{key}': "
            f"expected {expected_type}, got {type(value)}"
        )


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

    schema = EVENT_SCHEMAS.get(event_type, {})
    optional_keys = OPTIONAL_FIELDS.get(event_type, set())
    known_keys = required_keys | optional_keys | set(schema.keys())
    _log_unknown_keys(event_type, payload, known_keys)
    _validate_field_types(event_type, payload, schema)
