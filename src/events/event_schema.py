"""Lightweight event schema definitions and validation."""

from typing import Any, Dict, Set

from src.config.runtime_config import RunMode


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
    "pattern_name": (str, type(None)),
}

LIFECYCLE_INTENT_SCHEMA = {
    "symbol": str,
    "trader_type": str,
    "intent": str,
    "requested_quantity": int,
    "mode": str,
    "reason": str,
}

LIFECYCLE_TRANSITION_SCHEMA = {
    "symbol": str,
    "trader_type": str,
    "from_state": str,
    "to_state": str,
    "intent": str,
    "reason_code": str,
    "reason": str,
    "mode": str,
    "requested_quantity": int,
    "filled_quantity": int,
    "quantity_before": int,
    "quantity_after": int,
    "fill_status": str,
    "execution_blocked": bool,
    "fill_latency_ms": (int, type(None)),
    "transition_seq": int,
}

LIFECYCLE_TRANSITION_REJECTED_SCHEMA = {
    "symbol": str,
    "trader_type": str,
    "from_state": str,
    "intent": str,
    "reason_code": str,
    "reason": str,
    "mode": str,
}

CYCLE_START_SCHEMA = {
    "run_mode": (RunMode, str),
}

SCAN_COMPLETE_SCHEMA = {
    "candidates": int,
}

SCANNER_WATCHLIST_SCHEMA = {
    "scanner_version": (str, type(None)),
    "timestamp_utc": (str, type(None)),
    "symbols": list,
}

SCANNER_UNIVERSE_SNAPSHOT_SCHEMA = {
    "symbols": list,
    "requested_rows": int,
    "returned_rows": int,
    "session": str,
    "timestamp": str,
}

RAW_SCAN_SYMBOLS_SCHEMA = {
    "symbols": list,
    "requested_rows": int,
    "returned_rows": int,
    "session": str,
    "timestamp": str,
}

AFTER_GATES_SYMBOLS_SCHEMA = {
    "symbols": list,
    "count": int,
    "session": str,
    "timestamp": str,
}

SCANNER_SYMBOL_DROPPED_SCHEMA = {
    "symbol": str,
    "drop_reason": str,
    "metric_value": (int, float, str, dict, list, type(None)),
    "threshold": (int, float, str, dict, list, type(None)),
}

SCANNER_WATCHLIST_K_READY_SCHEMA = {
    "watchlist_k": list,
    "K": int,
    "policy_name": str,
}

WATCHLIST_K_SELECTED_SCHEMA = {
    "watchlist_k": list,
    "K": int,
    "policy_name": str,
}

PREP_UPDATED_SCHEMA = {
    "symbols": list,
    "count": int,
    "reason": str,
    "timestamp_utc": str,
}

PREP_CACHE_UPDATED_SCHEMA = {
    "symbols": list,
    "count": int,
    "reason": str,
    "timestamp_utc": str,
}

PREP_RESET_SCHEMA = {
    "reset_date": str,
    "reason": str,
}

STRATEGY_COMPLETE_SCHEMA = {
    "trade_intents": int,
}

STRATEGY_INTERFACE_INTENTS_SCHEMA = {
    "count": int,
}

EXECUTION_COMPLETE_SCHEMA = {
    "results": int,
}

EXIT_SIGNALS_GENERATED_SCHEMA = {
    "exit_signals": int,
}

TRADE_EXIT_COMPLETE_SCHEMA = {
    "closed": int,
    "outcomes": int,
}

PROTECTIVE_STOP_PLACED_SCHEMA = {
    "symbol": str,
    "trader_type": (str, type(None)),
    "strategy_name": (str, type(None)),
    "pattern_name": (str, type(None)),
    "stop_loss_price": float,
    "take_profit_price": float,
    "rationale": str,
    "tick": int,
}

TRADE_STATE_UPDATED_SCHEMA = {
    "symbol": str,
    "trader_type": str,
    "strategy_name": str,
    "from_state": (str, type(None)),
    "to_state": str,
    "tick": int,
    "reason": str,
}

EXIT_EVENT_SCHEMA = {
    "symbol": str,
    "trader_type": str,
    "strategy_name": str,
    "exit_tick": int,
    "exit_price": float,
    "exit_category": str,
    "exit_reason": str,
    "pnl": float,
    "hold_duration_ticks": int,
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
    "state_history": list,
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

INTENT_NORMALISED_SCHEMA = {
    "before_count": int,
    "after_count": int,
    "duplicates_dropped": int,
}

INTENT_DROPPED_DUPLICATE_SCHEMA = {
    "symbol": str,
    "trader_type": str,
    "direction": str,
    "kept_confidence": (float, int),
    "dropped_confidence": (float, int),
    "reason": str,
}

REGIME_SNAPSHOT_SCHEMA = {
    "label": str,
    "confidence": (float, int),
    "session": str,
    "features": dict,
    "evidence": list,
    "data_quality_flags": list,
    "baseline_stats": dict,
    "timestamp_utc": (str, type(None)),
}

REGIME_POLICY_DECISION_SCHEMA = {
    "label": str,
    "confidence": (float, int),
    "applied": bool,
    "eligible_strategies": list,
    "strategy_weights": dict,
    "risk_multiplier": (float, int),
    "notes": list,
    "data_quality_flags": list,
    "timestamp_utc": (str, type(None)),
}

PERF_SNAPSHOT_SCHEMA = {
    "total_trades": int,
    "closed_trades": int,
    "open_trades": int,
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

CIRCUIT_BREAKER_TRIGGERED_SCHEMA = {
    "run_mode": str,
    "breaches": list,
    "limits": dict,
    "metrics": dict,
    "timestamp": str,
}

DAILY_LOSS_WARNING_SCHEMA = {
    "run_mode": str,
    "daily_pnl": (float, int),
    "warning_limit": (float, int),
    "timestamp": str,
}

DAILY_RISK_DECISION_SCHEMA = {
    "decision_id": str,
    "status": str,
    "reason": str,
    "run_mode": str,
    "trading_day": str,
    "timezone_name": str,
    "realized_pnl": (float, int),
    "unrealized_pnl": (float, int),
    "include_unrealized": bool,
    "daily_trade_count": int,
    "losing_trade_count": int,
    "consecutive_losses": int,
    "lock_status": str,
    "existing_position_policy": str,
    "recommended_existing_position_action": str,
    "blocks_new_entries": bool,
    "allows_existing_position_management": bool,
    "reasons": list,
    "limit_snapshot": dict,
    "source_counts": dict,
    "audit_payload": dict,
    "timestamp": str,
}

AUTONOMOUS_RECOVERY_DECISION_SCHEMA = {
    "decision_id": str,
    "run_mode": str,
    "recovery_status": str,
    "failure_type": str,
    "severity": str,
    "action": str,
    "blocks_new_entries": bool,
    "allows_existing_position_management": bool,
    "requires_broker_resync": bool,
    "requires_storage_replay": bool,
    "requires_lifecycle_rebuild": bool,
    "requires_order_reconciliation": bool,
    "requires_stop_repair": bool,
    "requires_target_repair": bool,
    "requires_daily_risk_recheck": bool,
    "rationale": str,
    "evidence": dict,
    "timestamp": str,
}

AUTONOMOUS_RECOVERY_ACTION_SCHEMA = {
    **AUTONOMOUS_RECOVERY_DECISION_SCHEMA,
    "action_recommendations": list,
}

ANALYTICS_SNAPSHOT_SCHEMA = {
    "run_id": str,
    "trading_day": str,
    "run_mode": str,
    "strategy_key": str,
    "symbol": str,
    "setup_family": str,
    "trade_count": int,
    "attempted_trade_count": int,
    "blocked_trade_count": int,
    "filled_trade_count": int,
    "win_count": int,
    "loss_count": int,
    "breakeven_count": int,
    "realized_pnl": (float, int),
    "unrealized_pnl": (float, int),
    "gross_profit": (float, int),
    "gross_loss": (float, int),
    "average_win": (float, int),
    "average_loss": (float, int),
    "profit_factor": (float, int, type(None)),
    "win_rate": (float, int),
    "expectancy": (float, int),
    "max_single_trade_loss": (float, int),
    "max_single_trade_win": (float, int),
    "max_drawdown": (float, int),
    "daily_risk_lock_count": int,
    "recovery_lock_count": int,
    "stop_loss_exit_count": int,
    "target_exit_count": int,
    "trailing_exit_count": int,
    "manual_exit_count": int,
    "unknown_exit_count": int,
    "data_quality_issue_count": int,
    "execution_failure_count": int,
    "timestamp": str,
    "incomplete_data": bool,
    "source_counts": dict,
    "block_reason_counts": dict,
    "recovery_status_counts": dict,
    "breakdowns": dict,
    "data_quality_issues": list,
}

ANALYTICS_DATA_QUALITY_ISSUE_SCHEMA = {
    "issue_id": str,
    "code": str,
    "severity": str,
    "source": str,
    "trade_identity": str,
    "field_name": str,
    "detail": str,
    "timestamp": str,
}

AUTONOMOUS_CERTIFICATION_STARTED_SCHEMA = {
    "certification_id": str,
    "run_mode": str,
    "timestamp": str,
    "evidence": dict,
}

AUTONOMOUS_CERTIFICATION_REPORT_SCHEMA = {
    "platform_state": str,
    "certified": bool,
    "certification_timestamp": str,
    "run_mode": str,
    "startup_status": str,
    "recovery_status": str,
    "trading_status": str,
    "protection_status": str,
    "audit_status": str,
    "determinism_status": str,
    "critical_failures": list,
    "warnings": list,
    "recommendations": list,
    "evidence": dict,
}

RUNTIME_SAFETY_VIOLATION_SCHEMA = {
    "stage": str,
    "run_mode": str,
    "replay_mode": str,
    "violations": list,
    "duplicate_keys": list,
    "exception_type": str,
    "exception_message": str,
}

FAULT_DETECTED_SCHEMA = {
    "category": str,
    "severity": str,
    "message": str,
    "exception_type": str,
    "run_mode": str,
    "timestamp": str,
    "stack_hint": str,
}

FAULT_ACTION_TAKEN_SCHEMA = {
    **FAULT_DETECTED_SCHEMA,
    "recommended_action": str,
}

SHUTDOWN_BASE_SCHEMA = {
    "mode": str,
    "reason": str,
    "source": str,
    "run_mode": str,
    "tick": int,
}

SHUTDOWN_HOOK_FAILED_SCHEMA = {
    **SHUTDOWN_BASE_SCHEMA,
    "hook": str,
    "exception_type": str,
    "exception_message": str,
    "fault_category": str,
    "fault_severity": str,
}

EVENT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "CYCLE_START": CYCLE_START_SCHEMA,
    "SCANNER_WATCHLIST": SCANNER_WATCHLIST_SCHEMA,
    "SCANNER_UNIVERSE_SNAPSHOT": SCANNER_UNIVERSE_SNAPSHOT_SCHEMA,
    "RAW_SCAN_SYMBOLS": RAW_SCAN_SYMBOLS_SCHEMA,
    "AFTER_GATES_SYMBOLS": AFTER_GATES_SYMBOLS_SCHEMA,
    "SCANNER_SYMBOL_DROPPED": SCANNER_SYMBOL_DROPPED_SCHEMA,
    "SCANNER_WATCHLIST_K_READY": SCANNER_WATCHLIST_K_READY_SCHEMA,
    "WATCHLIST_K_SELECTED": WATCHLIST_K_SELECTED_SCHEMA,
    "PREP_UPDATED": PREP_UPDATED_SCHEMA,
    "PREP_CACHE_UPDATED": PREP_CACHE_UPDATED_SCHEMA,
    "PREP_RESET": PREP_RESET_SCHEMA,
    "SCAN_COMPLETE": SCAN_COMPLETE_SCHEMA,
    "STRATEGY_COMPLETE": STRATEGY_COMPLETE_SCHEMA,
    "STRATEGY_INTERFACE_INTENTS": STRATEGY_INTERFACE_INTENTS_SCHEMA,
    "EXECUTION_COMPLETE": EXECUTION_COMPLETE_SCHEMA,
    "PROTECTIVE_STOP_PLACED": PROTECTIVE_STOP_PLACED_SCHEMA,
    "TRADE_OPENED": TRADE_OPENED_SCHEMA,
    "TRADE_CLOSED": TRADE_CLOSED_SCHEMA,
    "TRADE_STATE_UPDATED": TRADE_STATE_UPDATED_SCHEMA,
    "TRADE_NOT_FILLED": TRADE_NOT_FILLED_SCHEMA,
    "LIFECYCLE_INTENT": LIFECYCLE_INTENT_SCHEMA,
    "LIFECYCLE_TRANSITION": LIFECYCLE_TRANSITION_SCHEMA,
    "LIFECYCLE_TRANSITION_REJECTED": LIFECYCLE_TRANSITION_REJECTED_SCHEMA,
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
    "ORDER_BLOCKED_READONLY": {
        "symbol": str,
        "trader_type": str,
        "strategy_name": str,
        "direction": str,
        "requested_quantity": int,
        "run_mode": str,
        "readonly_enabled": bool,
        "reason": str,
    },
    "ORDER_FILL_RECORDED": {
        "client_order_id": str,
        "symbol": str,
        "direction": str,
        "quantity": int,
        "order_type": str,
        "timestamp": str,
        "ibkr_order_id": (int, type(None)),
        "filled_quantity": int,
        "remaining_quantity": int,
        "average_fill_price": (float, type(None)),
        "last_fill_price": (float, type(None)),
        "fill_status": str,
        "commission": (float, type(None)),
        "slippage": (float, type(None)),
    },
    "READ_ONLY_BLOCK": {
        "symbol": str,
        "trader_type": str,
        "strategy_name": str,
        "direction": str,
        "requested_quantity": int,
        "run_mode": str,
        "reason": str,
    },
    "MARKET_DATA_CONNECTED": {
        "connected": bool,
        "market_data_type": str,
        "data_mode": str,
        "readonly_enabled": bool,
    },
    "MARKET_DATA_SNAPSHOT": {
        "symbol": str,
        "bid": (float, type(None)),
        "ask": (float, type(None)),
        "last": (float, type(None)),
        "spread": (float, type(None)),
        "volume": (float, type(None)),
        "asof_utc": str,
        "market_data_type": str,
        "data_mode": str,
        "request_mode": str,
        "request_source": str,
        "source": str,
    },
    "MARKET_DATA_FALLBACK": {
        "reason": str,
        "fallback_source": str,
        "data_mode": str,
        "request_source": str,
        "symbols": list,
    },
    "MARKET_SESSION_STATE": {
        "session": str,
        "previous_session": (str, type(None)),
        "timestamp_utc": str,
        "ny_time": str,
    },
    "INTENT_NORMALISED": INTENT_NORMALISED_SCHEMA,
    "INTENT_DROPPED_DUPLICATE": INTENT_DROPPED_DUPLICATE_SCHEMA,
    "REGIME_SNAPSHOT": REGIME_SNAPSHOT_SCHEMA,
    "REGIME_POLICY_DECISION": REGIME_POLICY_DECISION_SCHEMA,
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
    "EXIT_SIGNALS_GENERATED": EXIT_SIGNALS_GENERATED_SCHEMA,
    "TRADE_EXIT_COMPLETE": TRADE_EXIT_COMPLETE_SCHEMA,
    "EXIT_STOP_LOSS": EXIT_EVENT_SCHEMA,
    "EXIT_TIME": EXIT_EVENT_SCHEMA,
    "EXIT_TARGET": EXIT_EVENT_SCHEMA,
    "EXIT_FAILED_SETUP": EXIT_EVENT_SCHEMA,
    "EXIT_STRATEGY": EXIT_EVENT_SCHEMA,
    "EXIT_RISK": EXIT_EVENT_SCHEMA,
    "EXIT_BREAKER": EXIT_EVENT_SCHEMA,
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
    "CIRCUIT_BREAKER_TRIGGERED": CIRCUIT_BREAKER_TRIGGERED_SCHEMA,
    "DAILY_LOSS_WARNING": DAILY_LOSS_WARNING_SCHEMA,
    "DAILY_RISK_DECISION": DAILY_RISK_DECISION_SCHEMA,
    "AUTONOMOUS_RECOVERY_DECISION": AUTONOMOUS_RECOVERY_DECISION_SCHEMA,
    "AUTONOMOUS_RECOVERY_ACTION": AUTONOMOUS_RECOVERY_ACTION_SCHEMA,
    "ANALYTICS_SNAPSHOT": ANALYTICS_SNAPSHOT_SCHEMA,
    "ANALYTICS_DATA_QUALITY_ISSUE": ANALYTICS_DATA_QUALITY_ISSUE_SCHEMA,
    "AUTONOMOUS_CERTIFICATION_STARTED": AUTONOMOUS_CERTIFICATION_STARTED_SCHEMA,
    "AUTONOMOUS_CERTIFICATION_COMPLETED": AUTONOMOUS_CERTIFICATION_REPORT_SCHEMA,
    "AUTONOMOUS_CERTIFICATION_FAILED": AUTONOMOUS_CERTIFICATION_REPORT_SCHEMA,
    "RUNTIME_SAFETY_VIOLATION": RUNTIME_SAFETY_VIOLATION_SCHEMA,
    "FAULT_DETECTED": FAULT_DETECTED_SCHEMA,
    "FAULT_ACTION_TAKEN": FAULT_ACTION_TAKEN_SCHEMA,
    "SHUTDOWN_REQUESTED": SHUTDOWN_BASE_SCHEMA,
    "SHUTDOWN_STARTED": SHUTDOWN_BASE_SCHEMA,
    "SHUTDOWN_HOOK_FAILED": SHUTDOWN_HOOK_FAILED_SCHEMA,
    "SHUTDOWN_COMPLETE": SHUTDOWN_BASE_SCHEMA,
    "PANIC_STOP_TRIGGERED": SHUTDOWN_BASE_SCHEMA,
    "CONFIG_RESOLVED": {
        "resolved_at": str,
        "total": int,
        "hard": int,
        "soft": int,
        "advisory": int,
        "values": dict,
        "sources": dict,
    },
}


# Conservative schemas focused on consistency for teaching purposes.
REQUIRED_FIELDS: Dict[str, Set[str]] = {
    "CYCLE_START": {"run_mode"},
    "SCANNER_WATCHLIST": {"symbols"},
    "SCANNER_UNIVERSE_SNAPSHOT": {"symbols", "requested_rows", "returned_rows", "session", "timestamp"},
    "RAW_SCAN_SYMBOLS": {"symbols", "requested_rows", "returned_rows", "session", "timestamp"},
    "AFTER_GATES_SYMBOLS": {"symbols", "count", "session", "timestamp"},
    "SCANNER_SYMBOL_DROPPED": {"symbol", "drop_reason"},
    "SCANNER_WATCHLIST_K_READY": {"watchlist_k", "K", "policy_name"},
    "WATCHLIST_K_SELECTED": {"watchlist_k", "K", "policy_name"},
    "PREP_UPDATED": {"symbols", "count", "reason", "timestamp_utc"},
    "PREP_CACHE_UPDATED": {"symbols", "count", "reason", "timestamp_utc"},
    "PREP_RESET": {"reset_date", "reason"},
    "SCAN_COMPLETE": {"candidates"},
    "STRATEGY_COMPLETE": {"trade_intents"},
    "STRATEGY_INTERFACE_INTENTS": {"count"},
    "EXECUTION_COMPLETE": {"results"},
    "PROTECTIVE_STOP_PLACED": {
        "symbol",
        "trader_type",
        "strategy_name",
        "stop_loss_price",
        "take_profit_price",
        "tick",
    },
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
        "exit_category",
        "exit_reason",
        "pnl",
        "entry_tick",
        "exit_tick",
        "hold_duration_ticks",
        "min_hold_ticks",
        "max_hold_ticks",
        "stop_loss_price",
        "take_profit_price",
    },
    "TRADE_STATE_UPDATED": {
        "symbol",
        "trader_type",
        "strategy_name",
        "from_state",
        "to_state",
        "tick",
        "reason",
    },
    "LIFECYCLE_INTENT": {
        "symbol",
        "trader_type",
        "intent",
        "requested_quantity",
        "mode",
        "reason",
    },
    "LIFECYCLE_TRANSITION": {
        "symbol",
        "trader_type",
        "from_state",
        "to_state",
        "intent",
        "reason_code",
        "reason",
        "mode",
        "requested_quantity",
        "filled_quantity",
        "quantity_before",
        "quantity_after",
        "fill_status",
        "execution_blocked",
        "transition_seq",
    },
    "LIFECYCLE_TRANSITION_REJECTED": {
        "symbol",
        "trader_type",
        "from_state",
        "intent",
        "reason_code",
        "reason",
        "mode",
    },
    "EXIT_STOP_LOSS": {
        "symbol",
        "trader_type",
        "strategy_name",
        "exit_tick",
        "exit_price",
        "exit_category",
        "exit_reason",
        "pnl",
        "hold_duration_ticks",
    },
    "EXIT_TIME": {
        "symbol",
        "trader_type",
        "strategy_name",
        "exit_tick",
        "exit_price",
        "exit_category",
        "exit_reason",
        "pnl",
        "hold_duration_ticks",
    },
    "EXIT_TARGET": {
        "symbol",
        "trader_type",
        "strategy_name",
        "exit_tick",
        "exit_price",
        "exit_category",
        "exit_reason",
        "pnl",
        "hold_duration_ticks",
    },
    "EXIT_FAILED_SETUP": {
        "symbol",
        "trader_type",
        "strategy_name",
        "exit_tick",
        "exit_price",
        "exit_category",
        "exit_reason",
        "pnl",
        "hold_duration_ticks",
    },
    "EXIT_STRATEGY": {
        "symbol",
        "trader_type",
        "strategy_name",
        "exit_tick",
        "exit_price",
        "exit_category",
        "exit_reason",
        "pnl",
        "hold_duration_ticks",
    },
    "EXIT_RISK": {
        "symbol",
        "trader_type",
        "strategy_name",
        "exit_tick",
        "exit_price",
        "exit_category",
        "exit_reason",
        "pnl",
        "hold_duration_ticks",
    },
    "EXIT_BREAKER": {
        "symbol",
        "trader_type",
        "strategy_name",
        "exit_tick",
        "exit_price",
        "exit_category",
        "exit_reason",
        "pnl",
        "hold_duration_ticks",
    },
    "EXIT_SIGNALS_GENERATED": {"exit_signals"},
    "TRADE_EXIT_COMPLETE": {"closed"},
    "STRATEGY_PERF_SNAPSHOT": {"strategies"},
    "PERF_SNAPSHOT": {"total_trades"},
    "CIRCUIT_BREAKER_TRIGGERED": {"run_mode", "breaches", "limits", "metrics", "timestamp"},
    "DAILY_LOSS_WARNING": {"run_mode", "daily_pnl", "warning_limit", "timestamp"},
    "DAILY_RISK_DECISION": {
        "decision_id",
        "status",
        "reason",
        "run_mode",
        "trading_day",
        "timezone_name",
        "realized_pnl",
        "unrealized_pnl",
        "include_unrealized",
        "daily_trade_count",
        "losing_trade_count",
        "consecutive_losses",
        "lock_status",
        "existing_position_policy",
        "recommended_existing_position_action",
        "blocks_new_entries",
        "allows_existing_position_management",
        "timestamp",
    },
    "AUTONOMOUS_RECOVERY_DECISION": {
        "decision_id",
        "run_mode",
        "recovery_status",
        "failure_type",
        "severity",
        "action",
        "blocks_new_entries",
        "allows_existing_position_management",
        "requires_broker_resync",
        "requires_storage_replay",
        "requires_lifecycle_rebuild",
        "requires_order_reconciliation",
        "requires_stop_repair",
        "requires_target_repair",
        "requires_daily_risk_recheck",
        "rationale",
        "evidence",
        "timestamp",
    },
    "AUTONOMOUS_RECOVERY_ACTION": {
        "decision_id",
        "run_mode",
        "recovery_status",
        "failure_type",
        "severity",
        "action",
        "blocks_new_entries",
        "allows_existing_position_management",
        "requires_broker_resync",
        "requires_storage_replay",
        "requires_lifecycle_rebuild",
        "requires_order_reconciliation",
        "requires_stop_repair",
        "requires_target_repair",
        "requires_daily_risk_recheck",
        "rationale",
        "evidence",
        "timestamp",
        "action_recommendations",
    },
    "ANALYTICS_SNAPSHOT": {
        "run_id",
        "trading_day",
        "run_mode",
        "strategy_key",
        "symbol",
        "setup_family",
        "trade_count",
        "attempted_trade_count",
        "blocked_trade_count",
        "filled_trade_count",
        "win_count",
        "loss_count",
        "breakeven_count",
        "realized_pnl",
        "unrealized_pnl",
        "gross_profit",
        "gross_loss",
        "average_win",
        "average_loss",
        "profit_factor",
        "win_rate",
        "expectancy",
        "max_single_trade_loss",
        "max_single_trade_win",
        "max_drawdown",
        "daily_risk_lock_count",
        "recovery_lock_count",
        "stop_loss_exit_count",
        "target_exit_count",
        "trailing_exit_count",
        "manual_exit_count",
        "unknown_exit_count",
        "data_quality_issue_count",
        "execution_failure_count",
        "timestamp",
        "incomplete_data",
    },
    "ANALYTICS_DATA_QUALITY_ISSUE": {
        "issue_id",
        "code",
        "severity",
        "source",
        "trade_identity",
        "field_name",
        "detail",
        "timestamp",
    },
    "AUTONOMOUS_CERTIFICATION_STARTED": {
        "certification_id",
        "run_mode",
        "timestamp",
        "evidence",
    },
    "AUTONOMOUS_CERTIFICATION_COMPLETED": {
        "platform_state",
        "certified",
        "certification_timestamp",
        "run_mode",
        "startup_status",
        "recovery_status",
        "trading_status",
        "protection_status",
        "audit_status",
        "determinism_status",
        "critical_failures",
        "warnings",
        "recommendations",
        "evidence",
    },
    "AUTONOMOUS_CERTIFICATION_FAILED": {
        "platform_state",
        "certified",
        "certification_timestamp",
        "run_mode",
        "startup_status",
        "recovery_status",
        "trading_status",
        "protection_status",
        "audit_status",
        "determinism_status",
        "critical_failures",
        "warnings",
        "recommendations",
        "evidence",
    },
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
    "CONFIG_RESOLVED": {
        "resolved_at",
        "total",
        "hard",
        "soft",
        "advisory",
        "values",
        "sources",
    },
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
    "ORDER_BLOCKED_READONLY": {
        "symbol",
        "trader_type",
        "strategy_name",
        "direction",
        "requested_quantity",
        "run_mode",
        "readonly_enabled",
        "reason",
    },
    "ORDER_FILL_RECORDED": {
        "client_order_id",
        "symbol",
        "direction",
        "quantity",
        "order_type",
        "timestamp",
        "filled_quantity",
        "remaining_quantity",
        "fill_status",
    },
    "READ_ONLY_BLOCK": {
        "symbol",
        "trader_type",
        "strategy_name",
        "direction",
        "requested_quantity",
        "run_mode",
        "reason",
    },
    "MARKET_DATA_CONNECTED": {
        "connected",
        "market_data_type",
        "data_mode",
        "readonly_enabled",
    },
    "MARKET_DATA_SNAPSHOT": {
        "symbol",
        "bid",
        "ask",
        "last",
        "spread",
        "volume",
        "asof_utc",
        "market_data_type",
        "data_mode",
        "request_mode",
        "request_source",
        "source",
    },
    "MARKET_DATA_FALLBACK": {
        "reason",
        "fallback_source",
        "data_mode",
        "request_source",
        "symbols",
    },
    "MARKET_SESSION_STATE": {
        "session",
        "previous_session",
        "timestamp_utc",
        "ny_time",
    },
    "INTENT_NORMALISED": {"before_count", "after_count", "duplicates_dropped"},
    "INTENT_DROPPED_DUPLICATE": {
        "symbol",
        "trader_type",
        "direction",
        "kept_confidence",
        "dropped_confidence",
        "reason",
    },
    "REGIME_SNAPSHOT": {"label", "confidence", "session", "features"},
    "REGIME_POLICY_DECISION": {"label", "confidence", "applied", "risk_multiplier"},
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
    "SCANNER_SYMBOL_DROPPED": {"metric_value", "threshold"},
    "TRADE_OPENED": {"gateway_decision", "pattern_name"},
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
        "pattern_name",
        "state_history",
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
        "closed_trades",
        "open_trades",
        "by_strategy",
        "by_trader_type",
        "by_pattern",
        "by_session",
        "by_volatility_regime",
        "by_market_direction",
        "trade_outcomes",
        "rule_adherence",
        "reports",
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
    "ORDER_FILL_RECORDED": {
        "ibkr_order_id",
        "average_fill_price",
        "last_fill_price",
        "commission",
        "slippage",
    },
    "MARKET_DATA_FALLBACK": {"asof_utc"},
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
