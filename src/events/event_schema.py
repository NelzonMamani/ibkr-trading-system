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
    "raw_price": (float, type(None)),
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
    "client_order_id": (str, type(None)),
    "attempt_number": int,
    "gateway_decision": str,
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
    "client_order_id": (str, type(None)),
    "attempt_number": int,
    "gateway_decision": str,
}

ORDER_SUBMITTED_SCHEMA = {
    "client_order_id": str,
    "symbol": str,
    "trader_type": (str, type(None)),
    "strategy_name": (str, type(None)),
    "direction": str,
    "requested_quantity": int,
    "created_tick": int,
    "attempt_number": int,
    "order_type": str,
    "quantity": int,
    "timestamp": str,
}

ORDER_GATEWAY_DECISION_SCHEMA = {
    "client_order_id": str,
    "symbol": str,
    "trader_type": (str, type(None)),
    "tick": int,
    "attempt_number": int,
    "decision": str,
    "deterministic_key": str,
    "mapping_r": int,
}

ORDER_REJECTED_HARD_SCHEMA = {
    "client_order_id": str,
    "symbol": str,
    "trader_type": (str, type(None)),
    "tick": int,
    "attempt_number": int,
    "reason": str,
}

ORDER_RETRY_SCHEDULED_SCHEMA = {
    "client_order_id": str,
    "symbol": str,
    "trader_type": (str, type(None)),
    "from_tick": int,
    "next_retry_tick": int,
    "next_attempt_number": int,
}

ORDER_EXPIRED_SCHEMA = {
    "client_order_id": str,
    "symbol": str,
    "trader_type": (str, type(None)),
    "tick": int,
    "attempt_number": int,
    "reason": str,
}

ORDER_ACCEPTED_SCHEMA = {
    "client_order_id": str,
    "symbol": str,
    "direction": str,
    "quantity": int,
    "order_type": str,
    "timestamp": str,
    "status": str,
}

ORDER_REJECTED_SCHEMA = {
    "client_order_id": str,
    "symbol": str,
    "direction": str,
    "quantity": int,
    "order_type": str,
    "timestamp": str,
    "status": str,
}

ORDER_FINAL_STATUS_SCHEMA = {
    "client_order_id": str,
    "symbol": str,
    "direction": str,
    "quantity": int,
    "order_type": str,
    "timestamp": str,
    "final_status": str,
}

SIGNAL_DETECTED_SCHEMA = {
    "symbol": str,
    "signal_type": str,
    "confidence": float,
    "tick": int,
}

SIGNAL_SUMMARY_SCHEMA = {
    "tick": int,
    "total_signals": int,
    "by_type": dict,
}

SIGNAL_INTENTS_CREATED_SCHEMA = {
    "count": int,
    "signals_in": int,
}

PERF_SNAPSHOT_SCHEMA = {
    "total_trades": int,
    "wins": int,
    "losses": int,
    "flats": int,
    "win_rate": (float, int),
    "gross_pnl": (float, int),
    "total_commissions": (float, int),
    "net_pnl": (float, int),
    "avg_pnl_per_trade": (float, int),
    "by_strategy": dict,
    "by_trader_type": dict,
}

EVENT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "TRADE_OPENED": TRADE_OPENED_SCHEMA,
    "TRADE_CLOSED": TRADE_CLOSED_SCHEMA,
    "TRADE_NOT_FILLED": TRADE_NOT_FILLED_SCHEMA,
    "TRADE_BLOCKED": {
        "symbol": str,
        "trader_type": str,
        "strategy_name": str,
        "reason_code": str,
        "human_readable_rationale": str,
        "reason": str,
    },
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
    "ORDER_SUBMITTED": ORDER_SUBMITTED_SCHEMA,
    "ORDER_GATEWAY_DECISION": ORDER_GATEWAY_DECISION_SCHEMA,
    "ORDER_REJECTED_HARD": ORDER_REJECTED_HARD_SCHEMA,
    "ORDER_RETRY_SCHEDULED": ORDER_RETRY_SCHEDULED_SCHEMA,
    "ORDER_EXPIRED": ORDER_EXPIRED_SCHEMA,
    "ORDER_ACCEPTED": ORDER_ACCEPTED_SCHEMA,
    "ORDER_REJECTED": ORDER_REJECTED_SCHEMA,
    "ORDER_FINAL_STATUS": ORDER_FINAL_STATUS_SCHEMA,
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
    "SIGNAL_DETECTED": SIGNAL_DETECTED_SCHEMA,
    "SIGNAL_SUMMARY": SIGNAL_SUMMARY_SCHEMA,
    "SIGNAL_INTENTS_CREATED": SIGNAL_INTENTS_CREATED_SCHEMA,
    "INTENTS_FROM_SIGNALS": {
        "tick": int,
        "total_intents": int,
        "by_trader_type": dict,
        "by_strategy": dict,
    },
    "STRATEGY_PERF_SNAPSHOT": {
        "strategies": list,
    },
    "PERF_SNAPSHOT": PERF_SNAPSHOT_SCHEMA,
}


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
        "entry_tick",
        "opened_at_tick",
        "entry_price",
        "raw_price",
        "slippage_applied",
        "execution_price",
        "mode",
        "direction",
        "quantity",
        "stop_loss_price",
        "take_profit_price",
        "requested_quantity",
        "filled_quantity",
        "remaining_quantity",
        "fill_status",
    },
    "TRADE_NOT_FILLED": {
        "symbol",
        "trader_type",
        "tick",
        "requested_quantity",
        "available_liquidity",
        "filled_quantity",
        "remaining_quantity",
        "reason",
        "fill_status",
    },
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
    "TRADE_BLOCKED": {
        "symbol",
        "trader_type",
        "strategy_name",
        "reason_code",
        "human_readable_rationale",
    },
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
    "ORDER_SUBMITTED": {"client_order_id", "symbol", "direction"},
    "ORDER_GATEWAY_DECISION": {
        "client_order_id",
        "symbol",
        "trader_type",
        "tick",
        "attempt_number",
        "decision",
        "deterministic_key",
        "mapping_r",
    },
    "ORDER_REJECTED_HARD": {
        "client_order_id",
        "symbol",
        "trader_type",
        "tick",
        "attempt_number",
        "reason",
    },
    "ORDER_RETRY_SCHEDULED": {
        "client_order_id",
        "symbol",
        "trader_type",
        "from_tick",
        "next_retry_tick",
        "next_attempt_number",
    },
    "ORDER_EXPIRED": {
        "client_order_id",
        "symbol",
        "trader_type",
        "tick",
        "attempt_number",
        "reason",
    },
    "ORDER_ACCEPTED": {
        "client_order_id",
        "symbol",
        "direction",
        "quantity",
        "order_type",
        "timestamp",
        "status",
    },
    "ORDER_REJECTED": {
        "client_order_id",
        "symbol",
        "direction",
        "quantity",
        "order_type",
        "timestamp",
        "status",
    },
    "ORDER_FINAL_STATUS": {
        "client_order_id",
        "symbol",
        "direction",
        "quantity",
        "order_type",
        "timestamp",
        "final_status",
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
    "SIGNAL_DETECTED": {"symbol", "signal_type", "confidence", "tick"},
    "SIGNAL_SUMMARY": {"tick", "total_signals", "by_type"},
    "SIGNAL_INTENTS_CREATED": {"count", "signals_in"},
    "INTENTS_FROM_SIGNALS": {
        "tick",
        "total_intents",
        "by_trader_type",
        "by_strategy",
    },
    "STRATEGY_PERF_SNAPSHOT": {"strategies"},
    "PERF_SNAPSHOT": {"total_trades"},
}


OPTIONAL_FIELDS: Dict[str, Set[str]] = {
    "TRADE_OPENED": {"gateway_decision"},
    "TRADE_NOT_FILLED": {"client_order_id", "attempt_number", "gateway_decision"},
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
        "total_commissions",
        "net_pnl",
        "avg_pnl_per_trade",
        "by_strategy",
        "by_trader_type",
    },
    "TRADE_BLOCKED": {"reason"},
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
    "ORDER_SUBMITTED": {
        "trader_type",
        "strategy_name",
        "requested_quantity",
        "created_tick",
        "attempt_number",
        "order_type",
        "quantity",
        "timestamp",
    },
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
