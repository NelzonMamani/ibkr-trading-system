"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

import os
import math
import time
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, List

from ibapi.order import Order

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.core.pricing.price_resolver import PriceResolutionError, resolve_entry_price
from src.core_engine.events import ExecutionEvent, RiskDecisionRecord
from src.core_engine.state import RunMode, SessionState, resolve_session_state
from src.runtime.async_runtime_bootstrap import safe_import_ib_insync

_EXECUTION_EVENT_BUFFER: dict[int, ExecutionEvent] = {}
_FILL_AUTHORITY_STATE = "UNKNOWN"
_RUNTIME_ORDERS: dict[int, "TrackedOrder"] = {}
_EXECUTION_TRUTH_BY_ORDER_ID: dict[int, "ExecutionTruthRecord"] = {}
_RUNTIME_POSITIONS: dict[str, "TrackedPosition"] = {}
_IBKR_POSITIONS_BY_SYMBOL: dict[str, "IbkrPositionTruth"] = {}
_SEEN_EXEC_IDS: set[str] = set()
_UNMATCHED_CALLBACK_COUNT = 0
_RECONCILIATION_SUCCESSES = 0
_RECONCILIATION_FAILURES = 0
_RECONCILED_ORDERS_COUNT = 0
_RECONCILED_POSITIONS_COUNT = 0
_RECON_RESYNC_NEEDED = False
_CALLBACK_DELAY_WARNINGS_COUNT = 0
_CALLBACK_DELAY_THRESHOLD_SECONDS = 5
_EXECUTION_TRACE_BY_INTENT: dict[str, "ExecutionTrace"] = {}
_EXECUTION_TRACE_BY_ORDER_ID: dict[int, "ExecutionTrace"] = {}
_INTENT_ID_BY_ORDER_ID: dict[int, str] = {}
_ORDER_ID_BY_ORDER_REF: dict[str, int] = {}
_EXECUTION_CYCLE_COUNTER = 0
_EXECUTION_FAILURES_BY_TYPE: dict[str, int] = {}
_UNRESOLVED_EXECUTION_RECONCILIATION_COUNT = 0
_BROKER_TRUTH_FATALS = 0
_BROKER_TRUTH_CONFIRMATIONS = 0
_CONTRACT_VALIDATION_FAILURES = 0
_NEXT_VALID_ID_REBASES = 0
_NON_ORDER_UNMATCHED_CALLBACK_COUNT = 0
_CIRCUIT_BREAKER_ACTIVE = False
_VISIBILITY_BY_ORDER_ID: dict[int, dict[str, bool]] = {}
_LAST_CALLBACK_FINGERPRINT_BY_ORDER_ID: dict[int, str] = {}
_BROKER_ERRORS_BY_ORDER_ID: dict[int, list[dict[str, Any]]] = {}
_PENDING_SUBMISSIONS_BY_ORDER_ID: dict[int, "PendingSubmission"] = {}
_SUBMIT_FILLABILITY_COUNTS: dict[str, int] = {}
_IBKR_HEALTH_STATE = {
    "broker_connected": False,
    "market_data_ok": True,
    "historical_data_ok": True,
    "order_channel_ok": True,
    "degraded": False,
    "recovered_at": None,
    "last_error_codes": [],
    "last_recovery_codes": [],
}
_RECONCILED_POSITIONS_OK = 0
_RECONCILED_POSITIONS_MISMATCH = 0
_BROKER_POSITION_WITHOUT_FILL_COUNT = 0
_LOCAL_FILL_WITHOUT_POSITION_COUNT = 0
_WATCHDOG_STALLS_TOTAL = 0
_WATCHDOG_SUBMITTED_NO_ACK_TIMEOUTS = 0
_WATCHDOG_WORKING_NO_FILL_TIMEOUTS = 0
_WATCHDOG_PARTIAL_FILL_STALLS = 0
_OPEN_POSITIONS_CONFIRMED = 0
_REDUCED_POSITIONS_CONFIRMED = 0
_CLOSED_POSITIONS_CONFIRMED = 0
_BROKER_POSITION_LAST_QTY_BY_SYMBOL: dict[str, int] = {}
_IBKR_POSITION_EVENTS_COUNT = 0
_TRADING_CONTROL_MODE = "LEGACY"
_TRADING_CONTROL_MODE_LOCKED = False
_POSITION_OWNERSHIP_BY_SYMBOL: dict[str, str] = {}
_OPEN_ORDER_OWNERSHIP_BY_ID: dict[int, str] = {}

AUTHORITATIVE_EXECUTION_STATES = {
    "DISPATCH_INTENDED",
    "DISPATCH_SENT",
    "BROKER_ACK_SEEN",
    "BROKER_WORKING",
    "BROKER_QUEUED_FOR_RTH",
    "BROKER_REJECTED",
    "BROKER_CANCELLED",
    "BROKER_FILLED_PARTIAL",
    "BROKER_FILLED_FULL",
    "BROKER_EXPIRED",
    "BROKER_INACTIVE_UNKNOWN",
    "BROKER_INACTIVE_NON_MARKETABLE",
    "BROKER_INACTIVE_SESSION_MISMATCH",
    "BROKER_INACTIVE_OUTSIDE_RTH",
    "BROKER_INACTIVE_ROUTING",
    "BROKER_INACTIVE_HELD",
    "BROKER_INACTIVE_NO_QUOTE",
    "NO_FILL_TIMEOUT_NON_TERMINAL",
    "NO_FILL_TIMEOUT_TERMINAL",
    "BROKER_VISIBILITY_FAILURE",
}

FAILURE_TYPES = {
    "PRICE_UNAVAILABLE",
    "ORDER_REJECTED",
    "NO_ACK",
    "NO_FILL",
    "PARTIAL_FILL_STALLED",
    "CONTRACT_NOT_QUALIFIED",
    "BROKER_DISCONNECTED",
    "NO_QUOTE_CONTEXT",
    "CONTRACT_RESOLUTION_FAIL",
    "IBKR_REJECT",
    "CALLBACK_TIMEOUT",
}

ORDER_STATES = {
    "PENDING_SUBMISSION",
    "SUBMITTED_PENDING_CONFIRMATION",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "WORKING",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
}

CANONICAL_EXECUTION_STATES = {
    "CREATED",
    "BLOCKED",
    "SUBMITTING",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "WORKING",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_PENDING",
    "CANCELLED",
    "REJECTED",
    "INACTIVE",
    "EXPIRED",
    "ERROR",
}

BROKER_ONLY_MUTATION_FIELDS = {
    "filled_qty",
    "remaining_qty",
    "avg_fill_price",
    "last_fill_price",
}

BROKER_ONLY_STATES = {
    "ACKNOWLEDGED",
    "WORKING",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
    "INACTIVE",
    "EXPIRED",
}

LOCAL_ALLOWED_STATES = {"CREATED", "BLOCKED", "SUBMITTING", "SUBMITTED"}

FULL_QUOTE_PATH = "FULL_QUOTE_PATH"
DEGRADED_QUOTE_PATH = "DEGRADED_QUOTE_PATH"
OWNERSHIP_SYSTEM = "SYSTEM"
OWNERSHIP_EXTERNAL = "EXTERNAL"
OWNERSHIP_UNKNOWN = "UNKNOWN"


class ExecutionInvariantViolation(RuntimeError):
    """Raised when execution intent invariants are violated."""

ALLOWED_EXECUTION_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"BLOCKED", "SUBMITTING", "SUBMITTED", "ERROR"},
    "BLOCKED": set(),
    "SUBMITTING": {"SUBMITTED", "BLOCKED", "ERROR"},
    "SUBMITTED": {"ACKNOWLEDGED", "WORKING", "PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "CANCELLED", "REJECTED", "INACTIVE", "EXPIRED", "ERROR"},
    "ACKNOWLEDGED": {"WORKING", "PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "CANCELLED", "REJECTED", "INACTIVE", "EXPIRED", "ERROR"},
    "WORKING": {"PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "CANCELLED", "REJECTED", "INACTIVE", "EXPIRED", "ERROR"},
    "PARTIALLY_FILLED": {"FILLED", "CANCEL_PENDING", "CANCELLED", "REJECTED", "INACTIVE", "EXPIRED", "ERROR"},
    "FILLED": set(),
    "CANCEL_PENDING": {"CANCELLED", "FILLED", "REJECTED", "ERROR"},
    "CANCELLED": set(),
    "REJECTED": set(),
    "INACTIVE": set(),
    "EXPIRED": set(),
    "ERROR": set(),
}

POSITION_STATES = {
    "NO_POSITION",
    "PENDING_ENTRY",
    "PARTIAL_POSITION_OPEN",
    "POSITION_OPEN",
    "POSITION_REDUCING",
    "POSITION_CLOSED",
}


@dataclass(frozen=True)
class RouterAccountSnapshot:
    available_funds: float


@dataclass
class TrackedOrder:
    broker_order_id: int
    order_ref: str
    symbol: str
    side: str
    total_qty: int
    filled_qty: int = 0
    remaining_qty: int = 0
    avg_fill_price: float | None = None
    broker_status: str = "UNKNOWN"
    canonical_state: str = "PENDING_SUBMISSION"
    first_seen_at: str = field(default_factory=lambda: _now_utc_iso())
    last_update_at: str = field(default_factory=lambda: _now_utc_iso())
    is_entry: bool = True
    is_exit: bool = False
    strategy_id: str = ""
    setup_family: str = ""
    seen_exec_ids: set[str] = field(default_factory=set)
    callback_pending: bool = False
    callback_pending_since: str | None = None
    ack_seen: bool = False
    working_seen: bool = False
    queued_for_rth_seen: bool = False
    reject_seen: bool = False
    fill_seen: bool = False
    cancelled_seen: bool = False
    expired_seen: bool = False
    inactive_seen: bool = False
    broker_error_codes: list[int] = field(default_factory=list)
    normalized_reject_reason: str = ""
    final_execution_state: str = "DISPATCH_INTENDED"
    terminal: bool = False
    last_callback_fingerprint: str = ""
    intent_id: str = ""
    order_wire_payload: dict[str, Any] = field(default_factory=dict)
    open_order_detail: dict[str, Any] = field(default_factory=dict)
    fillability_classification: str = "NON_MARKETABLE_UNKNOWN"
    fillability_rationale: str = ""
    inactive_normalized_reason: str = ""
    inactive_rationale: str = ""
    ack_seen_at: str | None = None
    working_seen_at: str | None = None
    first_fill_seen_at: str | None = None
    escalation_required: bool = False
    escalation_reason: str = ""
    market_session: str = "CLOSED"
    min_tick: float = 0.01
    initial_bid: float | None = None
    initial_ask: float | None = None
    initial_limit_price: float | None = None
    last_limit_price: float | None = None
    reprice_attempt_count: int = 0
    last_reprice_at: str | None = None
    max_reprice_attempts: int = 0


@dataclass
class TrackedPosition:
    symbol: str
    qty: int = 0
    avg_price: float | None = None
    pending_entry_qty: int = 0
    pending_exit_qty: int = 0
    state: str = "NO_POSITION"


@dataclass
class IbkrPositionTruth:
    symbol: str
    quantity: int = 0
    avg_price: float | None = None
    last_update_time: str = field(default_factory=lambda: _now_utc_iso())


@dataclass
class ExecutionTruthRecord:
    order_ref: str
    broker_order_id: int | None
    symbol: str
    strategy_id: str = ""
    intent_id: str = ""
    side: str = ""
    order_type: str = "MKT"
    tif: str = "DAY"
    submitted_qty: int = 0
    filled_qty: int = 0
    remaining_qty: int = 0
    avg_fill_price: float | None = None
    last_fill_price: float | None = None
    execution_state: str = "CREATED"
    last_broker_status: str = ""
    last_broker_message: str = ""
    created_at: str = field(default_factory=lambda: _now_utc_iso())
    submitted_at: str | None = None
    last_update_at: str = field(default_factory=lambda: _now_utc_iso())
    terminal_at: str | None = None
    rejection_reason: str = ""
    cancellation_reason: str = ""
    source_of_truth: str = "IBKR"


@dataclass
class ExecutionTrace:
    symbol: str
    cycle_id: str
    intent_id: str
    strategy_name: str = ""
    entry_price_requested: float | None = None
    resolved_price: float | None = None
    price_state: str = "WAITING_IBKR"
    order_submitted: bool = False
    order_id: int | None = None
    order_status: str = "PENDING_SUBMISSION"
    ack_received: bool = False
    fill_received: bool = False
    fill_price: float | None = None
    fill_qty: int = 0
    position_opened: bool = False
    lifecycle_state: str = "INTENT_RECEIVED"
    rejection_reason: str = ""
    intent_time: str = field(default_factory=lambda: _now_utc_iso())
    submit_time: str | None = None
    ack_time: str | None = None
    fill_time: str | None = None


@dataclass
class PendingSubmission:
    order_id: int
    symbol: str
    intent_id: str
    order_ref: str = ""
    created_at: str = field(default_factory=lambda: _now_utc_iso())


def _trace_log(stage: str, trace: ExecutionTrace, *, extra: str = "") -> None:
    base = (
        f"[EXECUTION][{stage}] "
        f"symbol={trace.symbol or 'UNKNOWN'} intent_id={trace.intent_id or 'UNKNOWN'} "
        f"order_id={trace.order_id} price_state={trace.price_state}"
    )
    print(f"{base} {extra}".rstrip())


def _mark_execution_failure(trace: ExecutionTrace | None, failure_type: str, *, reason: str = "") -> None:
    normalized = failure_type if failure_type in FAILURE_TYPES else "IBKR_REJECT"
    _EXECUTION_FAILURES_BY_TYPE[normalized] = int(_EXECUTION_FAILURES_BY_TYPE.get(normalized, 0)) + 1
    if trace is not None:
        trace.lifecycle_state = "FAIL"
        trace.rejection_reason = reason or normalized
        _trace_log("FAIL", trace, extra=f"type={normalized} reason={trace.rejection_reason}")
    else:
        print(f"[EXECUTION][FAIL][TYPE={normalized}] reason={reason or 'unknown'}")


def runtime_lifecycle_snapshot() -> dict[str, int | str]:
    working = 0
    partial = 0
    filled = 0
    pending_entries = 0
    for row in _RUNTIME_ORDERS.values():
        if row.canonical_state in {"SUBMITTED_PENDING_CONFIRMATION", "SUBMITTED", "ACKNOWLEDGED", "WORKING", "PARTIALLY_FILLED"} and row.remaining_qty > 0:
            working += 1
        if row.canonical_state == "PARTIALLY_FILLED":
            partial += 1
        if row.canonical_state == "FILLED":
            filled += 1
        if row.is_entry and row.remaining_qty > 0 and row.canonical_state in {"WORKING", "PARTIALLY_FILLED", "SUBMITTED_PENDING_CONFIRMATION", "SUBMITTED", "ACKNOWLEDGED"}:
            pending_entries += 1
    open_positions = sum(1 for p in _IBKR_POSITIONS_BY_SYMBOL.values() if int(p.quantity) > 0)
    partial_positions = 0
    reducing_positions = 0
    closed_positions = sum(1 for p in _IBKR_POSITIONS_BY_SYMBOL.values() if int(p.quantity) == 0)
    return {
        "working_order_count": working,
        "partially_filled_order_count": partial,
        "fully_filled_order_count": filled,
        "pending_entry_count": pending_entries,
        "partial_position_open_count": partial_positions,
        "open_position_count": open_positions,
        "reducing_position_count": reducing_positions,
        "closed_position_count": closed_positions,
        "unmatched_callbacks_count": _UNMATCHED_CALLBACK_COUNT,
        "reconciled_orders_count": _RECONCILED_ORDERS_COUNT,
        "reconciled_positions_count": _RECONCILED_POSITIONS_COUNT,
        "recon_resync_needed": "YES" if _RECON_RESYNC_NEEDED else "NO",
        "fill_authority_state": fill_authority_state(),
        "callback_delay_warnings_count": _CALLBACK_DELAY_WARNINGS_COUNT,
        "reconciled_positions_ok": _RECONCILED_POSITIONS_OK,
        "reconciled_positions_mismatch": _RECONCILED_POSITIONS_MISMATCH,
        "broker_position_without_fill_count": _BROKER_POSITION_WITHOUT_FILL_COUNT,
        "local_fill_without_position_count": _LOCAL_FILL_WITHOUT_POSITION_COUNT,
        "watchdog_stalls_total": _WATCHDOG_STALLS_TOTAL,
        "submitted_no_ack_timeouts": _WATCHDOG_SUBMITTED_NO_ACK_TIMEOUTS,
        "working_no_fill_timeouts": _WATCHDOG_WORKING_NO_FILL_TIMEOUTS,
        "partial_fill_stalls": _WATCHDOG_PARTIAL_FILL_STALLS,
    }


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sanitize_ibkr_order_attributes(order: Order) -> None:
    order.eTradeOnly = False
    order.firmQuoteOnly = False
    order.outsideRth = True
    print("[EXECUTION][ORDER_SANITIZED] eTradeOnly=False firmQuoteOnly=False outsideRth=True")


def fill_authority_state() -> str:
    return _FILL_AUTHORITY_STATE


def _is_terminal_execution_state(state: str) -> bool:
    return state in {"BLOCKED", "FILLED", "CANCELLED", "REJECTED", "INACTIVE", "EXPIRED", "ERROR"}


def _transition_execution_truth_state(*, truth: ExecutionTruthRecord, next_state: str, source: str, broker_message: str = "") -> bool:
    next_norm = str(next_state or "").upper().strip()
    current = str(truth.execution_state or "CREATED").upper().strip()
    if next_norm not in CANONICAL_EXECUTION_STATES:
        print(f"[EXECUTION][TRUTH_TRANSITION_INVALID] symbol={truth.symbol} broker_order_id={truth.broker_order_id} from={current} to={next_norm} reason=UNKNOWN_STATE")
        return False
    if _is_terminal_execution_state(current) and next_norm != current:
        print(f"[EXECUTION][TRUTH_TRANSITION_INVALID] symbol={truth.symbol} broker_order_id={truth.broker_order_id} from={current} to={next_norm} reason=TERMINAL_IMMUTABLE")
        return False
    if next_norm in BROKER_ONLY_STATES and source != "IBKR_CALLBACK":
        print(f"[EXECUTION][TRUTH_REJECTED] symbol={truth.symbol} attempted_field=execution_state reason=NON_BROKER_MUTATION_BLOCKED")
        return False
    if source != "IBKR_CALLBACK" and next_norm not in LOCAL_ALLOWED_STATES:
        print(f"[EXECUTION][TRUTH_REJECTED] symbol={truth.symbol} attempted_field=execution_state reason=LOCAL_STATE_NOT_ALLOWED")
        return False
    allowed = ALLOWED_EXECUTION_TRANSITIONS.get(current, set())
    if next_norm != current and next_norm not in allowed:
        print(f"[EXECUTION][TRUTH_TRANSITION_INVALID] symbol={truth.symbol} broker_order_id={truth.broker_order_id} from={current} to={next_norm} reason=INVALID_TRANSITION")
        return False
    if next_norm != current:
        print(f"[EXECUTION][TRUTH_TRANSITION] symbol={truth.symbol} broker_order_id={truth.broker_order_id} from={current} to={next_norm} source={source}")
    truth.execution_state = next_norm
    truth.last_update_at = _now_utc_iso()
    if broker_message:
        truth.last_broker_message = broker_message
    if next_norm == "SUBMITTED" and truth.submitted_at is None:
        truth.submitted_at = truth.last_update_at
    if _is_terminal_execution_state(next_norm) and truth.terminal_at is None:
        truth.terminal_at = truth.last_update_at
    return True


def _update_truth_field(*, truth: ExecutionTruthRecord, field_name: str, value: Any, source: str) -> bool:
    if field_name in BROKER_ONLY_MUTATION_FIELDS and source != "IBKR_CALLBACK":
        print(f"[EXECUTION][TRUTH_REJECTED] symbol={truth.symbol} attempted_field={field_name} reason=NON_BROKER_MUTATION_BLOCKED")
        return False
    old_value = getattr(truth, field_name)
    if old_value == value:
        return True
    setattr(truth, field_name, value)
    truth.last_update_at = _now_utc_iso()
    print(
        "[EXECUTION][TRUTH_UPDATE] "
        f"symbol={truth.symbol} broker_order_id={truth.broker_order_id} field={field_name} "
        f"old={old_value} new={value} source={source}"
    )
    return True


def _create_execution_truth(*, order_ref: str, broker_order_id: int | None, symbol: str, intent_id: str, side: str, submitted_qty: int) -> ExecutionTruthRecord:
    truth = ExecutionTruthRecord(
        order_ref=order_ref,
        broker_order_id=broker_order_id,
        symbol=str(symbol or "").upper(),
        intent_id=intent_id,
        side=side,
        submitted_qty=max(0, int(submitted_qty)),
        remaining_qty=max(0, int(submitted_qty)),
    )
    _transition_execution_truth_state(truth=truth, next_state="CREATED", source="LOCAL")
    if broker_order_id is not None:
        _EXECUTION_TRUTH_BY_ORDER_ID[int(broker_order_id)] = truth
    return truth


def _record_reconciliation_result(success: bool) -> None:
    global _RECONCILIATION_SUCCESSES, _RECONCILIATION_FAILURES
    if success:
        _RECONCILIATION_SUCCESSES += 1
        return
    _RECONCILIATION_FAILURES += 1


def _refresh_fill_authority_state() -> None:
    global _FILL_AUTHORITY_STATE
    _FILL_AUTHORITY_STATE = "RECONCILIATION_MISMATCH" if _UNRESOLVED_EXECUTION_RECONCILIATION_COUNT > 0 else "ACKNOWLEDGED_NO_FILL"


def _position_reconciliation_window_seconds() -> int:
    raw = os.environ.get("EXECUTION_POSITION_RECONCILIATION_WINDOW_SECONDS", "5")
    try:
        return max(1, int(raw))
    except ValueError:
        return 5


def _watchdog_threshold_seconds(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        return max(1, int(raw))
    except ValueError:
        return max(1, int(default))


def _extract_position_avg_cost(position_row: Any) -> float | None:
    for field in ("avgCost", "averageCost", "avg_price", "cost"):
        value = getattr(position_row, field, None)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _signed_local_fill_qty(row: TrackedOrder) -> int:
    side = str(row.side or "").upper()
    qty = int(row.filled_qty or 0)
    return -qty if side == "SELL" else qty


def _classify_watchdog_state(row: TrackedOrder, now: datetime) -> tuple[str, int]:
    if row.terminal or row.canonical_state in {"FILLED", "REJECTED", "CANCELLED", "EXPIRED"}:
        return "NORMAL_IN_FLIGHT", 0
    if bool(_IBKR_HEALTH_STATE.get("degraded")):
        return "HEALTH_BLOCKED_PENDING", 0
    submit_to_ack = _watchdog_threshold_seconds("EXECUTION_SUBMIT_TO_ACK_TIMEOUT_SECONDS", 8)
    ack_to_working = _watchdog_threshold_seconds("EXECUTION_ACK_TO_WORKING_TIMEOUT_SECONDS", 10)
    working_no_fill = _watchdog_threshold_seconds("EXECUTION_WORKING_NO_FILL_TIMEOUT_SECONDS", 20)
    partial_stall = _watchdog_threshold_seconds("EXECUTION_PARTIAL_FILL_STALL_TIMEOUT_SECONDS", 30)
    first_seen = _parse_iso_utc(row.first_seen_at) or now
    elapsed_submit = int(max(0, (now - first_seen).total_seconds()))
    if not row.ack_seen and elapsed_submit >= submit_to_ack:
        return "SUBMITTED_NO_ACK_TIMEOUT", elapsed_submit
    if row.ack_seen and not row.working_seen:
        ack_seen_at = _parse_iso_utc(row.ack_seen_at) or _parse_iso_utc(row.last_update_at) or now
        elapsed_ack = int(max(0, (now - ack_seen_at).total_seconds()))
        if elapsed_ack >= ack_to_working:
            return "ACKNOWLEDGED_NO_WORKING_TIMEOUT", elapsed_ack
    if row.working_seen and int(row.filled_qty) <= 0:
        working_seen_at = _parse_iso_utc(row.working_seen_at) or _parse_iso_utc(row.last_update_at) or now
        elapsed_working = int(max(0, (now - working_seen_at).total_seconds()))
        if elapsed_working >= working_no_fill:
            return "WORKING_NO_FILL_TIMEOUT", elapsed_working
    if row.working_seen and 0 < int(row.filled_qty) < int(row.total_qty):
        fill_seen_at = _parse_iso_utc(row.first_fill_seen_at) or _parse_iso_utc(row.last_update_at) or now
        elapsed_partial = int(max(0, (now - fill_seen_at).total_seconds()))
        if elapsed_partial >= partial_stall:
            return "PARTIAL_FILL_STALLED", elapsed_partial
    return "NORMAL_IN_FLIGHT", elapsed_submit


def _watchdog_reprice_schedule_seconds() -> list[int]:
    raw = str(os.environ.get("EXECUTION_REPRICE_SCHEDULE_SECONDS", "3,6,10") or "")
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(max(1, int(token)))
        except ValueError:
            continue
    return values or [3, 6, 10]


def _attempt_watchdog_reprice(row: TrackedOrder, *, elapsed_seconds: int) -> None:
    if row.market_session != "PREMARKET":
        print(f"[EXECUTION][REPRICE_ABORT] symbol={row.symbol} order_id={row.broker_order_id} reason=SESSION_NOT_PREMARKET")
        return
    max_attempts = row.max_reprice_attempts or _watchdog_threshold_seconds("EXECUTION_MAX_REPRICE_ATTEMPTS", 3)
    if row.reprice_attempt_count >= max_attempts:
        print(f"[EXECUTION][REPRICE_ABORT] symbol={row.symbol} order_id={row.broker_order_id} reason=MAX_REPRICE_ATTEMPTS_REACHED")
        return
    schedule = _watchdog_reprice_schedule_seconds()
    next_attempt = row.reprice_attempt_count + 1
    gate_seconds = schedule[min(next_attempt - 1, len(schedule) - 1)]
    if elapsed_seconds < gate_seconds:
        return
    quote = _wait_for_ibkr_snapshot_for_symbol(str(row.symbol or ""), wait_up_to=0.4, poll_interval=0.1)
    bid = _safe_price_value(quote.get("bid"))
    ask = _safe_price_value(quote.get("ask"))
    if bid is None or ask is None or ask <= bid:
        print(f"[EXECUTION][REPRICE_ABORT] symbol={row.symbol} order_id={row.broker_order_id} reason=NO_QUOTE_CONTEXT")
        return
    spread = float(ask) - float(bid)
    max_spread_pct = float(os.environ.get("EXECUTION_MAX_REPRICE_SPREAD_PCT", "5.0") or "5.0")
    if ask > 0 and (spread / ask) * 100.0 > max_spread_pct:
        print(f"[EXECUTION][REPRICE_ABORT] symbol={row.symbol} order_id={row.broker_order_id} reason=PATHOLOGICAL_SPREAD")
        return
    _, Stock, _ = safe_import_ib_insync()
    manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
    client = manager.get_client()
    contract = Stock(row.symbol, "SMART", "USD")
    qualified = list(client.qualifyContracts(contract) or []) if hasattr(client, "qualifyContracts") else []
    if not qualified:
        print(f"[EXECUTION][REPRICE_ABORT] symbol={row.symbol} order_id={row.broker_order_id} reason=CONTRACT_NOT_QUALIFIED")
        return
    level = next_attempt
    new_limit, cap_applied, _component = _compute_aggressive_limit_price(
        side=row.side,
        bid=float(bid),
        ask=float(ask),
        tick_size=float(row.min_tick or 0.01),
        aggression_level=level,
    )
    old_limit = row.last_limit_price if row.last_limit_price is not None else row.initial_limit_price
    if old_limit is not None and abs(float(new_limit) - float(old_limit)) < 1e-9:
        print(f"[EXECUTION][REPRICE_ABORT] symbol={row.symbol} order_id={row.broker_order_id} reason=UNCHANGED_LIMIT")
        return
    order = Order()
    _sanitize_ibkr_order_attributes(order)
    order.action = str(row.side or "").upper()
    order.orderType = "LMT"
    order.totalQuantity = int(row.total_qty)
    order.tif = "DAY"
    order.orderRef = row.order_ref
    order.lmtPrice = float(new_limit)
    print(
        "[EXECUTION][REPRICE] "
        f"symbol={row.symbol} order_id={row.broker_order_id} attempt={next_attempt} old_limit={_none_text(old_limit)} new_limit={new_limit} "
        f"bid={bid} ask={ask} spread={spread:.6f} cap_applied={str(cap_applied).lower()}"
    )
    try:
        client.placeOrder(int(row.broker_order_id), qualified[0], order)
    except Exception as exc:
        print(f"[EXECUTION][REPRICE_ABORT] symbol={row.symbol} order_id={row.broker_order_id} reason=MODIFY_FAILED error={exc}")
        return
    row.reprice_attempt_count = next_attempt
    row.last_reprice_at = _now_utc_iso()
    row.last_limit_price = float(new_limit)
    if isinstance(row.order_wire_payload, dict):
        row.order_wire_payload["lmt_price"] = float(new_limit)
        row.order_wire_payload["bid"] = bid
        row.order_wire_payload["ask"] = ask
    print(f"[EXECUTION][REPRICE_RESULT] symbol={row.symbol} order_id={row.broker_order_id} status=MODIFY_SUBMITTED")


def _update_ibkr_health(*, event_type: str, code: int | None = None) -> None:
    degraded_codes = {1100, 2103, 2105, 2110}
    recovery_codes = {1101, 1102, 2104, 2106}
    if event_type == "connect":
        _IBKR_HEALTH_STATE["broker_connected"] = True
        _IBKR_HEALTH_STATE["order_channel_ok"] = True
    if event_type == "disconnect":
        _IBKR_HEALTH_STATE["broker_connected"] = False
        _IBKR_HEALTH_STATE["order_channel_ok"] = False
        _IBKR_HEALTH_STATE["degraded"] = True
    if code is not None:
        history = list(_IBKR_HEALTH_STATE.get("last_error_codes", []))
        history.append(int(code))
        _IBKR_HEALTH_STATE["last_error_codes"] = history[-20:]
        if int(code) == 1100:
            _IBKR_HEALTH_STATE["broker_connected"] = False
            _IBKR_HEALTH_STATE["order_channel_ok"] = False
            _IBKR_HEALTH_STATE["degraded"] = True
        if int(code) == 2110:
            _IBKR_HEALTH_STATE["broker_connected"] = False
            _IBKR_HEALTH_STATE["order_channel_ok"] = False
            _IBKR_HEALTH_STATE["degraded"] = True
        if int(code) == 2103:
            _IBKR_HEALTH_STATE["market_data_ok"] = False
            _IBKR_HEALTH_STATE["degraded"] = True
        if int(code) == 2105:
            _IBKR_HEALTH_STATE["historical_data_ok"] = False
            _IBKR_HEALTH_STATE["degraded"] = True
        if int(code) in degraded_codes:
            _IBKR_HEALTH_STATE["degraded"] = True
            _IBKR_HEALTH_STATE["order_channel_ok"] = False
        if int(code) in recovery_codes:
            _IBKR_HEALTH_STATE["broker_connected"] = True
            _IBKR_HEALTH_STATE["order_channel_ok"] = True
            if int(code) == 2104:
                _IBKR_HEALTH_STATE["market_data_ok"] = True
            if int(code) == 2106:
                _IBKR_HEALTH_STATE["historical_data_ok"] = True
            recovery_history = list(_IBKR_HEALTH_STATE.get("last_recovery_codes", []))
            recovery_history.append(int(code))
            _IBKR_HEALTH_STATE["last_recovery_codes"] = recovery_history[-20:]
    all_healthy = bool(_IBKR_HEALTH_STATE.get("broker_connected")) and bool(_IBKR_HEALTH_STATE.get("market_data_ok")) and bool(_IBKR_HEALTH_STATE.get("historical_data_ok")) and bool(_IBKR_HEALTH_STATE.get("order_channel_ok"))
    if all_healthy and bool(_IBKR_HEALTH_STATE.get("degraded")):
        _IBKR_HEALTH_STATE["degraded"] = False
        _IBKR_HEALTH_STATE["recovered_at"] = _now_utc_iso()
        print(
            "[IBKR][HEALTH_RECOVERY] "
            f"broker_connected={str(bool(_IBKR_HEALTH_STATE.get('broker_connected'))).lower()} "
            f"market_data_ok={str(bool(_IBKR_HEALTH_STATE.get('market_data_ok'))).lower()} "
            f"historical_data_ok={str(bool(_IBKR_HEALTH_STATE.get('historical_data_ok'))).lower()} "
            f"order_channel_ok={str(bool(_IBKR_HEALTH_STATE.get('order_channel_ok'))).lower()} "
            "status=STABLE"
        )
    status = "DEGRADED" if _IBKR_HEALTH_STATE.get("degraded") else "STABLE"
    print(
        "[IBKR][HEALTH] "
        f"broker_connected={str(bool(_IBKR_HEALTH_STATE.get('broker_connected'))).lower()} "
        f"market_data_ok={str(bool(_IBKR_HEALTH_STATE.get('market_data_ok'))).lower()} "
        f"historical_data_ok={str(bool(_IBKR_HEALTH_STATE.get('historical_data_ok'))).lower()} "
        f"order_channel_ok={str(bool(_IBKR_HEALTH_STATE.get('order_channel_ok'))).lower()} "
        f"status={status}"
    )


def _execution_truth_threshold() -> int:
    raw = os.environ.get("EXECUTION_TRUTH_DEGRADED_THRESHOLD", "1")
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _classify_fill_authority_state(*, intents_received: int, submit_attempts: int, orders_submitted: int, acks_received: int, fills_received: int, blocked_pre_submit: int) -> str:
    if intents_received <= 0:
        return "NO_INTENTS"
    if blocked_pre_submit >= intents_received:
        return "EXECUTION_BLOCKED_PRE_SUBMIT"
    if submit_attempts <= 0:
        return "NO_SUBMISSIONS"
    if orders_submitted > 0 and acks_received <= 0:
        return "SUBMITTED_AWAITING_ACK"
    if acks_received > 0 and fills_received <= 0:
        return "ACKNOWLEDGED_NO_FILL"
    if fills_received > 0:
        has_partial = any(t.execution_state == "PARTIALLY_FILLED" for t in _EXECUTION_TRUTH_BY_ORDER_ID.values())
        return "PARTIAL_FILL_CONFIRMED" if has_partial else "FILL_CONFIRMED"
    if _UNRESOLVED_EXECUTION_RECONCILIATION_COUNT > 0:
        return "RECONCILIATION_MISMATCH"
    return "BROKER_TRUTH_UNAVAILABLE"


def _is_diagnostics_mode() -> bool:
    return _env_truthy("EXECUTION_TRUTH_DIAGNOSTICS_MODE", default=False)


def _single_order_validation_mode() -> bool:
    return _env_truthy("EXECUTION_SINGLE_ORDER_VALIDATION_MODE", default=False)


def _maybe_trip_circuit_breaker(mode: RunMode, *, reason: str) -> None:
    global _CIRCUIT_BREAKER_ACTIVE
    if mode == RunMode.PAPER and _is_diagnostics_mode():
        return
    _CIRCUIT_BREAKER_ACTIVE = True
    print(f"[SAFETY][CIRCUIT_BREAKER] reason=EXECUTION_TRUTH_DEGRADED mode={mode.value} detail={reason}")


def _ensure_submission_allowed(mode: RunMode, *, symbol: str) -> bool:
    degraded = _FILL_AUTHORITY_STATE == "DEGRADED"
    threshold = _execution_truth_threshold()
    if _CIRCUIT_BREAKER_ACTIVE:
        print(f"[SAFETY][SUBMISSION_BLOCKED] symbol={symbol} reason=CIRCUIT_BREAKER_ACTIVE")
        return False
    if degraded and (
        _UNRESOLVED_EXECUTION_RECONCILIATION_COUNT >= threshold
        or _BROKER_TRUTH_FATALS >= threshold
        or _CONTRACT_VALIDATION_FAILURES >= threshold
    ):
        _maybe_trip_circuit_breaker(
            mode,
            reason=(
                f"unresolved={_UNRESOLVED_EXECUTION_RECONCILIATION_COUNT} "
                f"fatals={_BROKER_TRUTH_FATALS} contract_failures={_CONTRACT_VALIDATION_FAILURES}"
            ),
        )
    if _CIRCUIT_BREAKER_ACTIVE:
        print(f"[SAFETY][SUBMISSION_BLOCKED] symbol={symbol} reason=EXECUTION_TRUTH_DEGRADED")
        return False
    return True


def _build_order_ref(intent_id: str) -> str:
    normalized = str(intent_id or "").strip()
    if not normalized:
        return ""
    return f"TRADING_OS|ROSS_MOMENTUM|{normalized}"


def set_trading_control_mode(mode: str, *, lock: bool = True) -> bool:
    global _TRADING_CONTROL_MODE, _TRADING_CONTROL_MODE_LOCKED
    normalized = str(mode or "LEGACY").strip().upper()
    if normalized not in {"CLEAN_START", "ISOLATED_TRADING", "LEGACY"}:
        normalized = "LEGACY"
    if _TRADING_CONTROL_MODE_LOCKED and normalized != _TRADING_CONTROL_MODE:
        print("[CONTROL_MODE][VIOLATION] attempted_runtime_mode_switch=true")
        return False
    _TRADING_CONTROL_MODE = normalized
    if lock:
        _TRADING_CONTROL_MODE_LOCKED = True
    print(f"[CONTROL_MODE][SELECTED] mode={_TRADING_CONTROL_MODE}")
    return True


def get_trading_control_mode() -> str:
    return str(_TRADING_CONTROL_MODE or "LEGACY")


def _is_isolated_trading_mode() -> bool:
    return get_trading_control_mode() == "ISOLATED_TRADING"


def _is_system_order_ref(order_ref: str) -> bool:
    namespace, _strategy, family = _parse_order_ref_components(order_ref)
    return bool(str(namespace).upper() == "TRADING_OS" and str(family or "").strip())


def _owned_symbol_quantities_from_runtime_orders() -> dict[str, int]:
    owned: dict[str, int] = {}
    for row in _RUNTIME_ORDERS.values():
        symbol = str(row.symbol or "").upper().strip()
        if not symbol:
            continue
        owned[symbol] = int(owned.get(symbol, 0)) + _signed_local_fill_qty(row)
    return owned


def classify_broker_inventory(*, open_orders: list[Any], positions: list[Any]) -> dict[str, int]:
    _POSITION_OWNERSHIP_BY_SYMBOL.clear()
    _OPEN_ORDER_OWNERSHIP_BY_ID.clear()
    owned_qty = _owned_symbol_quantities_from_runtime_orders()

    system_positions = 0
    external_positions = 0
    for row in positions:
        symbol = str(getattr(row, "symbol", "") or "").upper().strip()
        if not symbol:
            continue
        qty = int(_extract_position_qty(row) or 0)
        ownership = OWNERSHIP_SYSTEM
        if _is_isolated_trading_mode():
            ownership = OWNERSHIP_SYSTEM if int(owned_qty.get(symbol, 0)) != 0 else OWNERSHIP_EXTERNAL
        _POSITION_OWNERSHIP_BY_SYMBOL[symbol] = ownership
        if qty != 0:
            if ownership == OWNERSHIP_SYSTEM:
                system_positions += 1
                print(f"[POSITION][SYSTEM] symbol={symbol} qty={qty}")
            else:
                external_positions += 1
                print(f"[POSITION][EXTERNAL] symbol={symbol} qty={qty}")
                print(f"[OWNERSHIP][DETAIL] type=position ownership=EXTERNAL symbol={symbol}")

    system_open_orders = 0
    external_open_orders = 0
    for row in open_orders:
        symbol = _extract_symbol_from_order(row)
        order_id_raw = getattr(row, "orderId", None)
        order_id = int(order_id_raw) if order_id_raw is not None else -1
        order_ref = _extract_order_ref(row)
        ownership = OWNERSHIP_SYSTEM
        if _is_isolated_trading_mode():
            ownership = OWNERSHIP_SYSTEM if _is_system_order_ref(order_ref) else OWNERSHIP_EXTERNAL
        _OPEN_ORDER_OWNERSHIP_BY_ID[order_id] = ownership
        if ownership == OWNERSHIP_SYSTEM:
            system_open_orders += 1
            print(f"[ORDER][SYSTEM] order_id={order_id} symbol={symbol or 'UNKNOWN'}")
        else:
            external_open_orders += 1
            print(f"[ORDER][EXTERNAL] order_id={order_id} symbol={symbol or 'UNKNOWN'}")
            print(
                f"[OWNERSHIP][DETAIL] type=open_order ownership=EXTERNAL symbol={symbol or 'UNKNOWN'} order_id={order_id}"
            )
    print(
        "[OWNERSHIP][SUMMARY] "
        f"system_positions={system_positions} external_positions={external_positions} "
        f"system_open_orders={system_open_orders} external_open_orders={external_open_orders}"
    )
    return {
        "system_positions": system_positions,
        "external_positions": external_positions,
        "system_open_orders": system_open_orders,
        "external_open_orders": external_open_orders,
    }


def current_ownership_summary() -> dict[str, int]:
    system_positions = sum(
        1
        for symbol, row in _IBKR_POSITIONS_BY_SYMBOL.items()
        if int(row.quantity) != 0 and _POSITION_OWNERSHIP_BY_SYMBOL.get(symbol, OWNERSHIP_EXTERNAL) == OWNERSHIP_SYSTEM
    )
    external_positions = sum(
        1
        for symbol, row in _IBKR_POSITIONS_BY_SYMBOL.items()
        if int(row.quantity) != 0 and _POSITION_OWNERSHIP_BY_SYMBOL.get(symbol, OWNERSHIP_EXTERNAL) == OWNERSHIP_EXTERNAL
    )
    system_open_orders = sum(1 for ownership in _OPEN_ORDER_OWNERSHIP_BY_ID.values() if ownership == OWNERSHIP_SYSTEM)
    external_open_orders = sum(1 for ownership in _OPEN_ORDER_OWNERSHIP_BY_ID.values() if ownership == OWNERSHIP_EXTERNAL)
    return {
        "system_positions": int(system_positions),
        "external_positions": int(external_positions),
        "system_open_orders": int(system_open_orders),
        "external_open_orders": int(external_open_orders),
    }


def _build_trace_id(*, intent_id: str, broker_order_id: int | None, cycle_id: str) -> str:
    return f"{intent_id or 'UNKNOWN'}::{broker_order_id if broker_order_id is not None else 'PENDING'}::{cycle_id}"


def _initialize_visibility(order_id: int) -> None:
    _VISIBILITY_BY_ORDER_ID[int(order_id)] = {
        "openOrder_seen": False,
        "orderStatus_seen": False,
        "execDetails_seen": False,
        "openOrders_snapshot_seen": False,
        "executions_snapshot_seen": False,
        "position_seen": False,
        "confirmed": False,
    }


def _visibility_confirmed(order_id: int) -> bool:
    row = _VISIBILITY_BY_ORDER_ID.get(int(order_id), {})
    return any(
        bool(row.get(key))
        for key in (
            "openOrder_seen",
            "orderStatus_seen",
            "execDetails_seen",
            "openOrders_snapshot_seen",
            "executions_snapshot_seen",
            "position_seen",
        )
    )


def _log_visibility_matrix(order_id: int, symbol: str) -> None:
    row = _VISIBILITY_BY_ORDER_ID.setdefault(int(order_id), {})
    row["confirmed"] = _visibility_confirmed(order_id)
    print(
        "[BROKER_TRUTH][VISIBILITY_MATRIX] "
        f"order_id={order_id} symbol={symbol} "
        f"openOrder_seen={bool(row.get('openOrder_seen'))} "
        f"orderStatus_seen={bool(row.get('orderStatus_seen'))} "
        f"execDetails_seen={bool(row.get('execDetails_seen'))} "
        f"openOrders_snapshot_seen={bool(row.get('openOrders_snapshot_seen'))} "
        f"executions_snapshot_seen={bool(row.get('executions_snapshot_seen'))} "
        f"position_seen={bool(row.get('position_seen'))} "
        f"confirmed={bool(row.get('confirmed'))}"
    )


def _visibility_confirmation_source(order_id: int) -> str:
    row = _VISIBILITY_BY_ORDER_ID.get(int(order_id), {})
    if bool(row.get("openOrder_seen")):
        return "openOrder_callback"
    if bool(row.get("orderStatus_seen")):
        return "orderStatus_callback"
    if bool(row.get("openOrders_snapshot_seen")):
        return "openOrders_snapshot"
    if bool(row.get("executions_snapshot_seen")):
        return "executions_snapshot"
    if bool(row.get("execDetails_seen")):
        return "execDetails"
    return "none"

def _safe_list_call(obj: Any, method_name: str) -> list[Any]:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return []
    try:
        rows = method()
    except Exception:
        return []
    return list(rows or [])


def _extract_symbol_from_order(order_row: Any) -> str:
    symbol = getattr(order_row, "symbol", None)
    if symbol is None:
        contract = getattr(order_row, "contract", None)
        symbol = getattr(contract, "symbol", None)
    if symbol is None:
        order = getattr(order_row, "order", None)
        contract = getattr(order_row, "contract", None)
        symbol = getattr(contract, "symbol", None) or getattr(order, "symbol", None)
    return str(symbol or "").upper()


def _extract_order_ref(row: Any) -> str:
    direct = getattr(row, "orderRef", None) or getattr(row, "order_ref", None)
    if direct:
        return str(direct)
    order = getattr(row, "order", None)
    if order is None:
        return ""
    return str(getattr(order, "orderRef", "") or "")


def _normalize_order_ref(order_ref: Any) -> str:
    return str(order_ref or "").strip()


def _parse_order_ref_components(order_ref: Any) -> tuple[str, str, str]:
    normalized = _normalize_order_ref(order_ref)
    if not normalized:
        return "", "", ""
    if "::" in normalized:
        parts = [p for p in normalized.split("::") if p]
        if len(parts) >= 4:
            return parts[0], parts[1], parts[-1]
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        if len(parts) == 2:
            return parts[0], parts[1], parts[-1]
        return "", "", parts[-1]
    if "|" in normalized:
        parts = [p for p in normalized.split("|") if p]
        if len(parts) >= 3:
            return parts[0], parts[1], parts[-1]
        if len(parts) == 2:
            return parts[0], parts[1], parts[-1]
        return "", "", parts[-1]
    return "", "", normalized


def _order_id_key(order_id: Any) -> int:
    return int(order_id) if order_id is not None else -1


def _register_order_intent_mapping(*, order_id: int, intent_id: str, order_ref: str) -> None:
    normalized_intent = _normalize_order_ref(intent_id)
    normalized_order_ref = _normalize_order_ref(order_ref)
    _INTENT_ID_BY_ORDER_ID[int(order_id)] = normalized_intent
    tracked = _RUNTIME_ORDERS.get(int(order_id))
    if tracked is not None:
        tracked.intent_id = normalized_intent
    if normalized_order_ref:
        _ORDER_ID_BY_ORDER_REF[normalized_order_ref] = int(order_id)


def _extract_callback_order_ref(callback_payload: Any) -> str:
    direct = _extract_callback_field(callback_payload, "order_ref", "orderRef", "intent_id", "intentId")
    if direct:
        return _normalize_order_ref(direct)
    order = _extract_callback_field(callback_payload, "order")
    if order is not None:
        return _normalize_order_ref(getattr(order, "orderRef", None))
    return ""


def _resolve_callback_order_id(callback_payload: Any) -> int | None:
    explicit_order_id = _extract_callback_order_id(callback_payload)
    if explicit_order_id is not None:
        return explicit_order_id
    callback_order_ref = _extract_callback_order_ref(callback_payload)
    if callback_order_ref:
        mapped_id = _resolve_order_id_from_order_ref(callback_order_ref)
        if mapped_id is not None:
            print(f"[ORDER_EVENT][RECONCILED] source=orderRef order_ref={callback_order_ref} order_id={mapped_id}")
            return int(mapped_id)
    return None


def _extract_exec_order_id(exec_row: Any) -> int | None:
    for field in ("orderId", "order_id", "permId", "perm_id"):
        value = getattr(exec_row, field, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    execution = getattr(exec_row, "execution", None)
    if execution is not None:
        value = getattr(execution, "orderId", None) or getattr(execution, "permId", None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _extract_exec_qty(exec_row: Any) -> int:
    for field in ("shares", "cumQty", "filled", "qty"):
        value = getattr(exec_row, field, None)
        if value is not None:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                continue
    execution = getattr(exec_row, "execution", None)
    if execution is not None:
        value = getattr(execution, "shares", None) or getattr(execution, "cumQty", None)
        if value is not None:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0
    return 0


def _extract_exec_price(exec_row: Any) -> float | None:
    for field in ("price", "avgPrice", "avg_fill_price"):
        value = getattr(exec_row, field, None)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    execution = getattr(exec_row, "execution", None)
    if execution is not None:
        value = getattr(execution, "price", None) or getattr(execution, "avgPrice", None)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _extract_position_qty(position_row: Any) -> float:
    for field in ("position", "qty", "quantity", "shares"):
        value = getattr(position_row, field, None)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _upsert_ibkr_position_truth(*, symbol: str, quantity: int, avg_price: float | None, update_time: str | None = None) -> None:
    global _IBKR_POSITION_EVENTS_COUNT
    normalized_symbol = str(symbol or "").upper().strip()
    if not normalized_symbol:
        return
    _IBKR_POSITION_EVENTS_COUNT += 1
    row = _IBKR_POSITIONS_BY_SYMBOL.setdefault(normalized_symbol, IbkrPositionTruth(symbol=normalized_symbol))
    row.quantity = int(quantity)
    row.avg_price = float(avg_price) if avg_price is not None else None
    row.last_update_time = str(update_time or _now_utc_iso())
    print(
        "[POSITION][SYNC] "
        f"symbol={normalized_symbol} qty={row.quantity} avg_price={row.avg_price} source=IBKR"
    )


def _sync_ibkr_positions_from_snapshot(positions: list[Any]) -> None:
    seen_symbols: set[str] = set()
    for row in positions:
        symbol = _extract_symbol_from_order(row)
        if not symbol:
            continue
        normalized_symbol = str(symbol or "").upper().strip()
        if not normalized_symbol:
            continue
        seen_symbols.add(normalized_symbol)
        quantity = int(_extract_position_qty(row) or 0)
        avg_cost = _extract_position_avg_cost(row)
        _upsert_ibkr_position_truth(
            symbol=normalized_symbol,
            quantity=quantity,
            avg_price=avg_cost,
            update_time=_now_utc_iso(),
        )
    stale_symbols = [symbol for symbol in _IBKR_POSITIONS_BY_SYMBOL.keys() if symbol not in seen_symbols]
    for symbol in stale_symbols:
        _IBKR_POSITIONS_BY_SYMBOL.pop(symbol, None)


def _extract_callback_field(callback_payload: Any, *field_names: str) -> Any:
    for field in field_names:
        if isinstance(callback_payload, dict) and field in callback_payload:
            return callback_payload.get(field)
        value = getattr(callback_payload, field, None)
        if value is not None:
            return value
    return None


def _extract_callback_symbol(callback_payload: Any) -> str:
    symbol = _extract_callback_field(callback_payload, "symbol")
    if symbol:
        return str(symbol).upper().strip()
    contract = _extract_callback_field(callback_payload, "contract")
    if contract is not None:
        from_contract = getattr(contract, "symbol", None)
        if from_contract:
            return str(from_contract).upper().strip()
    return ""


def _extract_callback_order_id(callback_payload: Any) -> int | None:
    value = _extract_callback_field(callback_payload, "order_id", "orderId", "permId", "perm_id")
    if value is None:
        execution = _extract_callback_field(callback_payload, "execution")
        if execution is not None:
            value = getattr(execution, "orderId", None)
            if value is None:
                value = getattr(execution, "permId", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_callback_filled_qty(callback_payload: Any) -> int:
    value = _extract_callback_field(callback_payload, "filled_qty", "shares", "cumQty", "filled", "qty")
    if value is None:
        execution = _extract_callback_field(callback_payload, "execution")
        if execution is not None:
            value = getattr(execution, "shares", None) or getattr(execution, "cumQty", None)
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _extract_callback_fill_price(callback_payload: Any) -> float | None:
    value = _extract_callback_field(callback_payload, "fill_price", "price", "avgPrice", "avg_fill_price")
    if value is None:
        execution = _extract_callback_field(callback_payload, "execution")
        if execution is not None:
            value = getattr(execution, "price", None) or getattr(execution, "avgPrice", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_callback_timestamp(callback_payload: Any) -> str:
    value = _extract_callback_field(callback_payload, "timestamp", "time")
    if value:
        return str(value)
    execution = _extract_callback_field(callback_payload, "execution")
    if execution is not None:
        execution_time = getattr(execution, "time", None)
        if execution_time:
            return str(execution_time)
    return _now_utc_iso()


def _state_from_broker_status(status: str, filled_qty: int, remaining_qty: int) -> str:
    status_norm = str(status or "").upper()
    if status_norm in {"CANCELLED", "CANCELED", "API_CANCELLED"}:
        return "CANCELLED"
    if status_norm in {"INACTIVE", "REJECTED"}:
        return "REJECTED"
    if status_norm == "EXPIRED":
        return "EXPIRED"
    if filled_qty > 0 and remaining_qty > 0:
        return "PARTIALLY_FILLED"
    if filled_qty > 0 and remaining_qty <= 0:
        return "FILLED"
    if status_norm in {"SUBMITTED", "PRESUBMITTED"}:
        return "WORKING"
    if status_norm in {"ACKNOWLEDGED"}:
        return "ACKNOWLEDGED"
    return "SUBMITTED"


def _normalize_broker_reject_reason(*, code: int | None, message: str, status: str) -> str:
    text = f"{message} {status}".upper()
    if code == 201:
        if "CLOSING" in text:
            return "REGULATORY_CLOSING_ONLY"
        return "PERMISSION_SMALL_CAP_OPENING_RESTRICTED"
    if code == 2109:
        return "OUTSIDE_RTH_IGNORED_WARNING"
    if code == 399 or "09:30" in text or "WILL NOT BE PLACED" in text:
        return "QUEUED_UNTIL_RTH_WARNING"
    if "PERMISSION" in text or "RESTRICT" in text:
        return "PERMISSION_SMALL_CAP_OPENING_RESTRICTED"
    if "REJECT" in text or "INACTIVE" in text:
        return "UNKNOWN_BROKER_REJECT"
    return ""


def _resolve_authoritative_execution_state(row: TrackedOrder | None) -> str:
    if row is None:
        return "BROKER_VISIBILITY_FAILURE"
    if row.fill_seen and row.remaining_qty <= 0:
        return "BROKER_FILLED_FULL"
    if row.fill_seen and row.remaining_qty > 0:
        return "BROKER_FILLED_PARTIAL"
    if row.reject_seen:
        return "BROKER_REJECTED"
    if row.cancelled_seen:
        return "BROKER_CANCELLED"
    if row.expired_seen:
        return "BROKER_EXPIRED"
    if row.queued_for_rth_seen:
        return "BROKER_QUEUED_FOR_RTH"
    if row.working_seen:
        return "BROKER_WORKING"
    if row.inactive_seen:
        return _inactive_terminal_state_from_reason(row.inactive_normalized_reason)
    if row.ack_seen:
        return "BROKER_ACK_SEEN"
    return "DISPATCH_SENT"


def _apply_position_fill(symbol: str, *, signed_delta_qty: int, fill_price: float | None, pending_entry_delta: int = 0, pending_exit_delta: int = 0) -> None:
    _ = (symbol, signed_delta_qty, fill_price, pending_entry_delta, pending_exit_delta)
    print("[EXECUTION][POSITION_WRITE_SKIPPED] reason=IBKR_POSITION_AUTHORITY_ONLY")


def _simulate_position_from_fill(*, order_id: int, symbol: str, fill_qty: int, fill_price: float | None) -> None:
    _ = (order_id, symbol, fill_qty, fill_price)
    print("[EXECUTION][POSITION_SIMULATION_DISABLED] reason=IBKR_POSITION_AUTHORITY_ONLY")


def _upsert_order_from_submission(*, order_id: int, symbol: str, side: str, total_qty: int, order_ref: str, intent_id: str = "") -> TrackedOrder:
    row = _RUNTIME_ORDERS.get(order_id)
    created = row is None
    if row is None:
        row = TrackedOrder(
            broker_order_id=order_id,
            order_ref=order_ref,
            symbol=symbol,
            side=side,
            total_qty=max(0, int(total_qty)),
            remaining_qty=max(0, int(total_qty)),
            broker_status="Submitted",
            canonical_state="SUBMITTED_PENDING_CONFIRMATION",
            final_execution_state="DISPATCH_SENT",
            last_update_at=_now_utc_iso(),
        )
        _RUNTIME_ORDERS[order_id] = row
    else:
        row.order_ref = order_ref or row.order_ref
        row.symbol = symbol or row.symbol
        row.side = side or row.side
        row.total_qty = max(int(row.total_qty), max(0, int(total_qty)))
        row.remaining_qty = max(0, int(row.total_qty) - int(row.filled_qty))
        row.last_update_at = _now_utc_iso()
        row.broker_status = "Submitted"
        row.canonical_state = "SUBMITTED_PENDING_CONFIRMATION"
        row.final_execution_state = "DISPATCH_SENT"
    if intent_id:
        row.intent_id = str(intent_id or "")
    normalized_side = str(side or "").upper()
    ibkr_qty = int(_IBKR_POSITIONS_BY_SYMBOL.get(symbol, IbkrPositionTruth(symbol=symbol)).quantity or 0)
    row.is_exit = normalized_side == "SELL" and ibkr_qty > 0
    row.is_entry = not row.is_exit
    print(f"[LIFECYCLE][ORDER] order_id={order_id} symbol={symbol} state={row.canonical_state} filled={row.filled_qty} remaining={row.remaining_qty}")
    return row


def _register_pending_submission(*, order_id: int, symbol: str, intent_id: str, order_ref: str = "") -> None:
    _PENDING_SUBMISSIONS_BY_ORDER_ID[int(order_id)] = PendingSubmission(
        order_id=int(order_id),
        symbol=str(symbol or "").upper(),
        intent_id=str(intent_id or ""),
        order_ref=str(order_ref or ""),
    )


def _resolve_order_id_from_order_ref(order_ref: str) -> int | None:
    normalized_order_ref = _normalize_order_ref(order_ref)
    if not normalized_order_ref:
        return None
    mapped = _ORDER_ID_BY_ORDER_REF.get(normalized_order_ref)
    if mapped is not None:
        return int(mapped)
    for pending in _PENDING_SUBMISSIONS_BY_ORDER_ID.values():
        if _normalize_order_ref(pending.order_ref) != normalized_order_ref:
            continue
        _ORDER_ID_BY_ORDER_REF[normalized_order_ref] = int(pending.order_id)
        return int(pending.order_id)
    return None


def _recover_order_tracking_from_pending_submission(*, order_id: int, callback_symbol: str, timestamp: str) -> tuple[TrackedOrder | None, ExecutionTrace | None]:
    pending = _PENDING_SUBMISSIONS_BY_ORDER_ID.get(int(order_id))
    if pending is None:
        return None, None
    symbol = (callback_symbol or pending.symbol or "UNKNOWN").upper()
    trace = _EXECUTION_TRACE_BY_ORDER_ID.get(int(order_id))
    if trace is None:
        cycle_id = "RECOVERY"
        existing = _EXECUTION_TRACE_BY_INTENT.get(pending.intent_id)
        if existing is not None:
            cycle_id = existing.cycle_id
        trace = ExecutionTrace(symbol=symbol, cycle_id=cycle_id, intent_id=pending.intent_id or f"RECOVERED-{order_id}")
        trace.order_submitted = True
        trace.order_id = int(order_id)
        trace.submit_time = pending.created_at
        trace.lifecycle_state = "SUBMITTED"
        _EXECUTION_TRACE_BY_ORDER_ID[int(order_id)] = trace
        if pending.intent_id:
            _EXECUTION_TRACE_BY_INTENT.setdefault(pending.intent_id, trace)
    row = _upsert_order_from_submission(
        order_id=int(order_id),
        symbol=symbol,
        side="BUY",
        total_qty=0,
        order_ref=pending.order_ref or f"PENDING_RECOVERY|{pending.intent_id or order_id}",
    )
    row.intent_id = pending.intent_id
    row.last_update_at = timestamp
    _register_order_intent_mapping(
        order_id=int(order_id),
        intent_id=pending.intent_id,
        order_ref=pending.order_ref or f"PENDING_RECOVERY|{pending.intent_id or order_id}",
    )
    _initialize_visibility(int(order_id))
    _PENDING_SUBMISSIONS_BY_ORDER_ID.pop(int(order_id), None)
    print(f"[EXECUTION][CALLBACK_RECOVERED] order_id={order_id} source=pending_registry")
    return row, trace


def _recover_order_from_execdetails(order_id: int, symbol: str, filled_qty: int, fill_price: float | None) -> TrackedOrder:
    normalized_symbol = str(symbol or "").upper().strip()
    timestamp = _now_utc_iso()
    tracked = _RUNTIME_ORDERS.get(int(order_id))
    trace = _EXECUTION_TRACE_BY_ORDER_ID.get(int(order_id))
    if tracked is None:
        tracked, trace = _recover_order_tracking_from_pending_submission(
            order_id=int(order_id),
            callback_symbol=normalized_symbol,
            timestamp=timestamp,
        )
    if tracked is None:
        side = "BUY"
        total_qty = max(0, int(filled_qty or 0))
        tracked = _upsert_order_from_submission(
            order_id=int(order_id),
            symbol=normalized_symbol or "UNKNOWN",
            side=side,
            total_qty=total_qty,
            order_ref=f"EXECDETAILS_BACKFILL|{order_id}",
        )
        _initialize_visibility(int(order_id))
    else:
        tracked.symbol = normalized_symbol or tracked.symbol
        tracked.total_qty = max(int(tracked.total_qty), max(0, int(filled_qty or 0)))
        tracked.remaining_qty = max(0, int(tracked.total_qty) - int(tracked.filled_qty))
    if trace is None:
        trace = ExecutionTrace(
            symbol=normalized_symbol or tracked.symbol or "UNKNOWN",
            cycle_id="EXECDETAILS_BACKFILL",
            intent_id=tracked.intent_id or f"BACKFILL-{order_id}",
        )
        _EXECUTION_TRACE_BY_ORDER_ID[int(order_id)] = trace
        if trace.intent_id:
            _EXECUTION_TRACE_BY_INTENT.setdefault(trace.intent_id, trace)
    trace.order_id = int(order_id)
    trace.order_submitted = True
    trace.lifecycle_state = "FILL_RECEIVED"
    if trace.fill_time is None:
        trace.fill_time = timestamp
    if fill_price is not None:
        trace.fill_price = fill_price
    return tracked


def _classify_fill_origin(*, source: str, is_backfill: bool) -> str:
    if is_backfill:
        return "IBKR_EXECDETAILS_BACKFILL"
    if source == "IBKR_EXECUTION":
        return "IBKR_EXECDETAILS"
    return "LIVE_EXECUTION"


def _apply_fill_to_tracked_order(
    *,
    order_id: int,
    symbol: str,
    fill_qty: int,
    fill_price: float | None,
    exec_id: str | None,
    timestamp: str,
    source: str,
    fill_origin: str = "LIVE_EXECUTION",
) -> None:
    normalized_symbol = str(symbol or "").upper().strip()
    row = _RUNTIME_ORDERS.get(order_id)
    if row is None:
        raise AssertionError(f"EXECDETAILS_MISSING_TRACKED_ORDER:{order_id}")
    row.symbol = normalized_symbol or row.symbol
    if exec_id:
        dedupe_key = f"{order_id}:{exec_id}"
        if dedupe_key in _SEEN_EXEC_IDS or exec_id in row.seen_exec_ids:
            print(f"[EXECUTION][FILL_DEDUP] order_id={order_id} exec_id={exec_id} deduped=true")
            return
        _SEEN_EXEC_IDS.add(dedupe_key)
        row.seen_exec_ids.add(exec_id)
    inc = max(0, int(fill_qty))
    if inc <= 0:
        return
    prev_filled = row.filled_qty
    row.filled_qty += inc
    row.remaining_qty = max(0, row.total_qty - row.filled_qty)
    if fill_price is not None:
        prev_qty = prev_filled
        prev_avg = float(row.avg_fill_price or 0.0)
        row.avg_fill_price = ((prev_qty * prev_avg) + (inc * float(fill_price))) / max(1, prev_qty + inc)
    old_state = row.canonical_state
    row.canonical_state = "FILLED" if row.remaining_qty == 0 else "PARTIALLY_FILLED"
    row.broker_status = "Filled" if row.canonical_state == "FILLED" else "Submitted"
    row.last_update_at = timestamp
    if row.first_fill_seen_at is None:
        row.first_fill_seen_at = timestamp
    row.callback_pending = False
    row.callback_pending_since = None
    print(f"[EXECUTION][ORDER_MATCH] order_id={order_id} symbol={row.symbol} source={source}")
    print(
        "[EXECUTION][FILL] "
        f"order_id={order_id} symbol={row.symbol} authority=execDetails fill_qty={inc} "
        f"remaining_qty={row.remaining_qty} exec_id={exec_id or 'NA'} fill_origin={fill_origin}"
    )
    print(f"[PRICE_AUTHORITY][SOURCE=IBKR_EXECUTION] order_id={order_id} symbol={row.symbol} price={fill_price}")
    if row.remaining_qty == 0:
        print(f"[EXECUTION][FILL] order_id={order_id} symbol={row.symbol} fill_qty={inc} total_filled={row.filled_qty} exec_id={exec_id or 'NA'}")
    else:
        print(f"[EXECUTION][PARTIAL_FILL] order_id={order_id} symbol={row.symbol} fill_qty={inc} total_filled={row.filled_qty} remaining={row.remaining_qty} exec_id={exec_id or 'NA'}")
    if old_state != row.canonical_state:
        print(f"[ORDER_EVENT][STATE_TRANSITION] order_id={order_id} from={old_state} to={row.canonical_state}")
    print(
        "[EXECUTION][FILL_CONFIRMED] "
        f"symbol={row.symbol} broker_order_id={order_id} filled_qty={row.filled_qty} avg_fill_price={row.avg_fill_price}"
    )
    print(f"[EXECUTION][LIFECYCLE] symbol={row.symbol} marker=FILL_CONFIRMED_AWAITING_POSITION")
    if _is_explicit_test_mode() and source != "IBKR_EXECUTION_BACKFILL":
        _simulate_position_from_fill(order_id=order_id, symbol=row.symbol, fill_qty=inc, fill_price=fill_price)


def _on_ibkr_callback(callback_payload: Any) -> None:
    global _UNMATCHED_CALLBACK_COUNT, _UNRESOLVED_EXECUTION_RECONCILIATION_COUNT, _FILL_AUTHORITY_STATE, _NON_ORDER_UNMATCHED_CALLBACK_COUNT
    event_type = str(_extract_callback_field(callback_payload, "event_type") or "").lower()
    if event_type and event_type not in {"execdetails", "orderstatus", "commissionreport", "openorder", "position", "positionend", "error"}:
        return
    order_id = _resolve_callback_order_id(callback_payload)
    callback_order_ref = _extract_callback_order_ref(callback_payload)
    symbol = _extract_callback_symbol(callback_payload)
    filled_qty = _extract_callback_filled_qty(callback_payload)
    fill_price = _extract_callback_fill_price(callback_payload)
    timestamp = _extract_callback_timestamp(callback_payload)
    print(
        "[IBKR][CALLBACK_RAW] "
        f"event={event_type or 'unknown'} order_id={order_id} symbol={symbol or 'UNKNOWN'} payload={callback_payload}"
    )
    print(
        "[EXECUTION][CALLBACK_RECEIVED] "
        f"symbol={symbol or 'UNKNOWN'} order_id={order_id} filled_qty={filled_qty} fill_price={fill_price} timestamp={timestamp}"
    )
    if event_type == "positionend":
        print("[IBKR][CALLBACK_RAW] event=positionEnd")
        return
    if event_type == "position":
        qty_raw = _extract_callback_field(callback_payload, "position", "qty", "shares", "quantity")
        avg_raw = _extract_callback_field(callback_payload, "avgCost", "avg_cost", "averageCost", "avg_price")
        try:
            qty = int(float(qty_raw or 0))
        except (TypeError, ValueError):
            qty = 0
        try:
            avg_price = float(avg_raw) if avg_raw is not None else None
        except (TypeError, ValueError):
            avg_price = None
        _upsert_ibkr_position_truth(symbol=symbol, quantity=qty, avg_price=avg_price, update_time=timestamp)
    if order_id is None:
        if event_type == "execdetails":
            _UNMATCHED_CALLBACK_COUNT += 1
            _record_reconciliation_result(False)
            return
        if event_type in {"position", "commissionreport"}:
            _NON_ORDER_UNMATCHED_CALLBACK_COUNT += 1
            return
        _UNMATCHED_CALLBACK_COUNT += 1
        print(f"[EXECUTION][UNMATCHED_CALLBACK] event={event_type or 'unknown'} broker_order_id=UNKNOWN symbol={symbol or 'UNKNOWN'}")
        print(f"[RECON][UNMATCHED_CALLBACK] event={event_type or 'unknown'} broker_order_id=UNKNOWN symbol={symbol or 'UNKNOWN'}")
        print(
            "[ORDER_EVENT][UNMATCHED] "
            f"event=CALLBACK reason=missing_order_id_and_order_ref order_ref={callback_order_ref or 'UNKNOWN'}"
        )
        print(
            "[EXECUTION][RECONCILIATION_FAILED] "
            f"event=CALLBACK callback={event_type or 'unknown'} order_ref={callback_order_ref or 'UNKNOWN'}"
        )
        print(
            "[EXECUTION][TRUTH_GAP] "
            f"stage=ACK callback={event_type or 'unknown'} reason=missing_order_id order_ref={callback_order_ref or 'UNKNOWN'}"
        )
        _UNRESOLVED_EXECUTION_RECONCILIATION_COUNT += 1
        _FILL_AUTHORITY_STATE = "DEGRADED"
        if event_type in {"execdetails", "orderstatus", "openorder"}:
            _mark_execution_failure(None, "CALLBACK_TIMEOUT", reason=f"missing_order_id callback={event_type or 'unknown'}")
        return
    order_id_key = _order_id_key(order_id)
    tracked = _RUNTIME_ORDERS.get(order_id_key)
    trace = _EXECUTION_TRACE_BY_ORDER_ID.get(order_id_key)
    if tracked is None and trace is None and event_type in {"openorder", "orderstatus"}:
        tracked, trace = _recover_order_tracking_from_pending_submission(
            order_id=order_id_key,
            callback_symbol=str(symbol or ""),
            timestamp=timestamp,
        )
        if tracked is None and trace is None:
            print(
                "[EXECUTION][CALLBACK_IGNORED] "
                f"event_type={event_type} order_id={order_id} reason=untracked_external_order"
            )
            print(
                "[EXECUTION][TRACE] "
                f"stage=ACK event_type={event_type} order_id={order_id} tracked=false action=ignored"
            )
            return
    if event_type == "execdetails" and tracked is None and callback_order_ref:
        mapped_id = _resolve_order_id_from_order_ref(callback_order_ref)
        if mapped_id is not None:
            if mapped_id != order_id_key:
                print(f"[ORDER_EVENT][RECONCILED] source=orderRef order_ref={callback_order_ref} order_id={mapped_id}")
            order_id = int(mapped_id)
            order_id_key = _order_id_key(order_id)
            tracked = _RUNTIME_ORDERS.get(order_id_key)
            trace = _EXECUTION_TRACE_BY_ORDER_ID.get(order_id_key)
            if tracked is None:
                tracked, trace = _recover_order_tracking_from_pending_submission(
                    order_id=order_id_key,
                    callback_symbol=str(symbol or ""),
                    timestamp=timestamp,
                )
    if event_type == "execdetails":
        normalized_symbol = str(symbol or "").upper().strip()
        tracked_before = tracked
        tracked = _recover_order_from_execdetails(
            order_id_key,
            normalized_symbol,
            int(filled_qty or 0),
            fill_price,
        )
        trace = _EXECUTION_TRACE_BY_ORDER_ID.get(order_id_key)
        is_backfill = tracked_before is None
        if is_backfill:
            print(
                "[EXECUTION][FORCED_BACKFILL] "
                f"order_id={order_id} symbol={normalized_symbol} "
                f"fill_qty={int(filled_qty or 0)} fill_price={fill_price}"
            )
        _apply_fill_to_tracked_order(
            order_id=order_id_key,
            symbol=normalized_symbol,
            fill_qty=int(filled_qty or 0),
            fill_price=fill_price,
            exec_id=str(_extract_callback_field(callback_payload, "execId") or f"BACKFILL-{order_id}"),
            timestamp=_now_utc_iso(),
            source="IBKR_EXECUTION_BACKFILL" if is_backfill else "IBKR_EXECUTION",
            fill_origin=_classify_fill_origin(
                source="IBKR_EXECUTION_BACKFILL" if is_backfill else "IBKR_EXECUTION",
                is_backfill=is_backfill,
            ),
        )
        truth = _EXECUTION_TRUTH_BY_ORDER_ID.get(order_id_key)
        if truth is not None:
            _update_truth_field(truth=truth, field_name="filled_qty", value=int(tracked.filled_qty), source="IBKR_CALLBACK")
            _update_truth_field(truth=truth, field_name="remaining_qty", value=int(tracked.remaining_qty), source="IBKR_CALLBACK")
            _update_truth_field(truth=truth, field_name="avg_fill_price", value=tracked.avg_fill_price, source="IBKR_CALLBACK")
            _update_truth_field(truth=truth, field_name="last_fill_price", value=fill_price, source="IBKR_CALLBACK")
            next_state = "PARTIALLY_FILLED" if int(tracked.remaining_qty) > 0 else "FILLED"
            _transition_execution_truth_state(truth=truth, next_state=next_state, source="IBKR_CALLBACK")
        assert order_id_key in _RUNTIME_ORDERS, "EXECDETAILS_RECOVERY_FAILED"
        _record_reconciliation_result(True)
        _refresh_fill_authority_state()
    if (not symbol) and tracked is not None and tracked.symbol:
        symbol = tracked.symbol
        print(f"[EXECUTION][CALLBACK_ENRICHED] order_id={order_id} symbol={symbol} source=order_id_mapping")
    if not symbol and tracked is None:
        print(f"[EXECUTION][CALLBACK_UNRESOLVED] order_id={order_id} event_type={event_type or 'unknown'}")
    if tracked is None and order_id is not None:
        print(f"[RECON][UNMATCHED_CALLBACK] event={event_type or 'unknown'} broker_order_id={order_id} symbol={symbol or 'UNKNOWN'}")
    fingerprint = (
        f"{event_type}|{order_id}|{symbol}|"
        f"{_extract_callback_field(callback_payload, 'status') or ''}|"
        f"{_extract_callback_field(callback_payload, 'errorCode') or _extract_callback_field(callback_payload, 'code') or ''}|"
        f"{filled_qty}|{fill_price}"
    )
    if tracked is not None and tracked.last_callback_fingerprint == fingerprint:
        print(f"[EXECUTION][CALLBACK_DEDUP] order_id={order_id} fingerprint={fingerprint}")
        return
    if tracked is not None:
        tracked.last_callback_fingerprint = fingerprint
        if not str(tracked.intent_id or _INTENT_ID_BY_ORDER_ID.get(order_id_key, "")).strip():
            print(
                f"[RECON][UNMATCHED_CALLBACK] event={event_type or 'unknown'} broker_order_id={order_id} "
                f"symbol={tracked.symbol or symbol or 'UNKNOWN'} reason=missing_intent_correlation"
            )
    _LAST_CALLBACK_FINGERPRINT_BY_ORDER_ID[order_id_key] = fingerprint
    if trace is not None:
        _trace_log("ACK", trace, extra=f"callback={event_type or 'unknown'}")
    event_status = str(_extract_callback_field(callback_payload, "status") or "").upper()
    remaining_qty = _extract_callback_field(callback_payload, "remaining")
    try:
        if remaining_qty is not None:
            remaining_int = int(float(remaining_qty))
        elif tracked is not None:
            remaining_int = int(tracked.remaining_qty)
        else:
            remaining_int = 0
    except (TypeError, ValueError):
        remaining_int = 0
    if event_type == "execdetails":
        print(f"[EXECUTION][CALLBACK_NORMALIZED] event=execDetails symbol={symbol or 'UNKNOWN'} broker_order_id={order_id} state={_state_from_broker_status(event_status, filled_qty, remaining_int)}")
        fill_event_type = "ORDER_FILLED"
    else:
        fill_event_type = "ORDER_WORKING"
    broker_status = "Filled" if fill_event_type == "ORDER_FILLED" else (
        "Submitted" if event_status in {"SUBMITTED", "PRESUBMITTED"} else (event_status or "Submitted")
    )
    event = ExecutionEvent(
        symbol=symbol or "UNKNOWN",
        intent_id="",
        action="WORKING" if fill_event_type == "ORDER_WORKING" else "FILLED",
        detail="callback_fill",
        event_type=fill_event_type,
        source="IBKR",
        broker_order_id=order_id,
        filled_quantity=max(0, filled_qty),
        remaining_quantity=max(0, remaining_int),
        broker_status=broker_status,
        avg_fill_price=fill_price,
        last_update_time=timestamp,
    )
    _EXECUTION_EVENT_BUFFER[order_id] = event
    if event_type == "execdetails":
        _VISIBILITY_BY_ORDER_ID.setdefault(order_id_key, {}).update({"execDetails_seen": True})
        exec_id = _extract_callback_field(callback_payload, "execId")
        print(
            "[EXECUTION][TRACE] "
            f"stage=FILL event_type=execDetails order_id={order_id} authority=execDetails exec_id={exec_id or 'NA'}"
        )
        if tracked is not None:
            print(
                "[EXECUTION][RECONCILED] "
                f"order_id={order_id} symbol={tracked.symbol or symbol or 'UNKNOWN'} "
                f"intent_id={tracked.intent_id or _INTENT_ID_BY_ORDER_ID.get(order_id_key, '')} "
                f"order_ref={tracked.order_ref or callback_order_ref or 'UNKNOWN'} "
                f"fill_qty={max(0, int(filled_qty))} fill_price={fill_price}"
            )
        if trace is not None:
            trace.fill_received = True
            trace.fill_qty = int(trace.fill_qty) + max(0, int(filled_qty))
            trace.fill_price = fill_price
            trace.fill_time = timestamp
            trace.lifecycle_state = "FILL_RECEIVED"
            _trace_log("FILL", trace, extra=f"exec_id={exec_id} fill_qty={filled_qty} fill_price={fill_price}")
            _trace_log("FILL_CONFIRMED_AWAITING_POSITION", trace)
        if filled_qty > 0 and remaining_int > 0:
            print(
                f"[ORDER][PARTIAL_FILL] symbol={symbol or 'UNKNOWN'} order_id={order_id} "
                f"shares={filled_qty} avg_price={fill_price}"
            )
        elif filled_qty > 0:
            print(
                f"[ORDER][FILL] symbol={symbol or 'UNKNOWN'} order_id={order_id} "
                f"shares={filled_qty} avg_price={fill_price}"
            )
        if tracked is not None:
            tracked.fill_seen = tracked.filled_qty > 0
            tracked.working_seen = tracked.remaining_qty > 0
            tracked.final_execution_state = _resolve_authoritative_execution_state(tracked)
    elif event_type == "orderstatus":
        print(f"[EXECUTION][CALLBACK_NORMALIZED] event=orderStatus symbol={symbol or 'UNKNOWN'} broker_order_id={order_id} state={_state_from_broker_status(event_status, filled_qty, remaining_int)}")
        _VISIBILITY_BY_ORDER_ID.setdefault(order_id_key, {}).update({"orderStatus_seen": True})
        row = _RUNTIME_ORDERS.get(order_id_key)
        if row is None:
            _UNMATCHED_CALLBACK_COUNT += 1
            print(f"[ORDER_EVENT][UNMATCHED] event=STATUS order_id={order_id} symbol={symbol}")
            if trace is not None:
                _mark_execution_failure(trace, "NO_ACK", reason="status_callback_for_unknown_order")
        else:
            old_state = row.canonical_state
            row.broker_status = event_status or row.broker_status
            if filled_qty > row.filled_qty:
                print(
                    "[EXECUTION][TRUTH_GAP] "
                    f"stage=FILL callback=orderStatus order_id={order_id} observed_filled={filled_qty} "
                    "action=ignored_non_authoritative_fill_signal"
                )
            if remaining_int > 0:
                row.remaining_qty = remaining_int
            row.canonical_state = _state_from_broker_status(row.broker_status, row.filled_qty, row.remaining_qty)
            truth = _EXECUTION_TRUTH_BY_ORDER_ID.get(order_id_key)
            if truth is not None:
                state_map = {
                    "REJECTED": "REJECTED",
                    "EXPIRED": "EXPIRED",
                    "CANCELLED": "CANCELLED",
                }
                mapped_state = state_map.get(row.canonical_state, "ACKNOWLEDGED")
                _update_truth_field(truth=truth, field_name="last_broker_status", value=str(row.broker_status or ""), source="IBKR_CALLBACK")
                _transition_execution_truth_state(truth=truth, next_state=mapped_state, source="IBKR_CALLBACK")
            row.last_update_at = timestamp
            row.ack_seen = True
            row.ack_seen_at = row.ack_seen_at or timestamp
            if str(row.broker_status or "").upper() in {"SUBMITTED", "PRESUBMITTED"}:
                row.working_seen = True
                row.working_seen_at = row.working_seen_at or timestamp
            if str(row.broker_status or "").upper() == "PRESUBMITTED":
                row.queued_for_rth_seen = bool(row.queued_for_rth_seen)
            if str(row.broker_status or "").upper() in {"INACTIVE", "REJECTED"}:
                if row.normalized_reject_reason in {"OUTSIDE_RTH_IGNORED_WARNING", "QUEUED_UNTIL_RTH_WARNING"}:
                    row.queued_for_rth_seen = True
                else:
                    row.inactive_seen = True
                    row.reject_seen = bool(row.reject_seen or row.normalized_reject_reason)
                why_held = str(_extract_callback_field(callback_payload, "whyHeld", "why_held") or "")
                submit_payload = dict(row.order_wire_payload or {})
                open_order_echo = dict(row.open_order_detail or {})
                fillability = str(row.fillability_classification or "NON_MARKETABLE_UNKNOWN")
                quote_available = any(
                    submit_payload.get(key) is not None for key in ("bid", "ask", "last")
                )
                normalized_inactive_reason, inactive_rationale = normalize_inactive_reason(
                    submit_payload=submit_payload,
                    open_order_echo=open_order_echo,
                    broker_status=row.broker_status,
                    why_held=why_held,
                    session_label=str(submit_payload.get("session_label") or _session_label_now()),
                    fillability=fillability,
                    quote_available=quote_available,
                )
                row.inactive_normalized_reason = normalized_inactive_reason
                row.inactive_rationale = inactive_rationale
                print(
                    "[EXECUTION][INACTIVE_CLASSIFIED] "
                    f"symbol={row.symbol} order_id={order_id} reason={normalized_inactive_reason} "
                    f"broker_status={_none_text(row.broker_status)} fillability={fillability} "
                    f"outside_rth={_none_text(open_order_echo.get('outside_rth', submit_payload.get('outside_rth')))} "
                    f"tif={_none_text(open_order_echo.get('tif', submit_payload.get('tif')))} "
                    f"session_label={_none_text(submit_payload.get('session_label'))} why_held={_none_text(why_held)} "
                    f"rationale={inactive_rationale}"
                )
            if str(row.broker_status or "").upper() in {"CANCELLED", "CANCELED", "API_CANCELLED"}:
                row.cancelled_seen = True
            if str(row.broker_status or "").upper() == "EXPIRED":
                row.expired_seen = True
            row.fill_seen = row.filled_qty > 0
            row.final_execution_state = _resolve_authoritative_execution_state(row)
            print(f"[ORDER_EVENT][STATUS] order_id={order_id} symbol={row.symbol} status={row.broker_status} filled={row.filled_qty} remaining={row.remaining_qty}")
            if old_state != row.canonical_state:
                print(f"[ORDER_EVENT][STATE_TRANSITION] order_id={order_id} from={old_state} to={row.canonical_state}")
            if trace is not None:
                trace.ack_received = True
                trace.ack_time = timestamp
                trace.order_status = row.canonical_state
                trace.lifecycle_state = "ACK_RECEIVED"
                _trace_log("ORDER_STATUS", trace, extra=f"status={row.canonical_state} broker_status={row.broker_status}")
                print(f"[IBKR][ACK] order_id={order_id} outsideRth=True")
                print(
                    f"[EXECUTION][ACK_CONFIRMED] symbol={row.symbol} order_id={order_id} "
                    f"status={row.broker_status}"
                )
                print(
                    "[EXECUTION][ACK] "
                    f"symbol={row.symbol} order_id={order_id} status={row.broker_status} tracked=true"
                )
                if row.canonical_state == "REJECTED":
                    _mark_execution_failure(trace, "ORDER_REJECTED", reason="broker_status_rejected")
            if row.canonical_state in {"WORKING", "ACKNOWLEDGED", "SUBMITTED"}:
                print(
                    f"[ORDER][WORKING] symbol={row.symbol} order_id={order_id} "
                    f"status={row.broker_status}"
                )
    elif event_type == "openorder":
        print(f"[EXECUTION][CALLBACK_NORMALIZED] event=openOrder symbol={symbol or 'UNKNOWN'} broker_order_id={order_id} state=SUBMITTED")
        _VISIBILITY_BY_ORDER_ID.setdefault(order_id_key, {}).update({"openOrder_seen": True})
        if callback_order_ref:
            _ORDER_ID_BY_ORDER_REF[callback_order_ref] = order_id_key
        callback_order = _extract_callback_field(callback_payload, "order")
        callback_state = _extract_callback_field(callback_payload, "orderState")
        open_order_detail = {
            "symbol": symbol or (tracked.symbol if tracked is not None else None),
            "order_id": order_id_key,
            "action": getattr(callback_order, "action", None),
            "total_quantity": getattr(callback_order, "totalQuantity", None),
            "order_type": getattr(callback_order, "orderType", None),
            "lmt_price": _safe_price_value(getattr(callback_order, "lmtPrice", None)),
            "aux_price": _safe_price_value(getattr(callback_order, "auxPrice", None)),
            "tif": getattr(callback_order, "tif", None),
            "outside_rth": getattr(callback_order, "outsideRth", None),
            "good_after_time": getattr(callback_order, "goodAfterTime", None),
            "good_till_date": getattr(callback_order, "goodTillDate", None),
            "why_held": getattr(callback_state, "whyHeld", None),
            "parent_id": getattr(callback_order, "parentId", None),
            "transmit": getattr(callback_order, "transmit", None),
            "exchange": getattr(callback_order, "exchange", None),
            "broker_status": getattr(callback_state, "status", None),
        }
        print(
            "[IBKR][OPEN_ORDER_DETAIL] "
            + " ".join(f"{key}={_none_text(value)}" for key, value in open_order_detail.items())
        )
        if trace is not None:
            trace.ack_received = True
            trace.ack_time = timestamp
            trace.lifecycle_state = "ACK_RECEIVED"
            _trace_log("ACK", trace, extra="callback=openOrder")
            print(f"[IBKR][ACK] order_id={order_id} outsideRth=True")
            print(
                f"[EXECUTION][ACK_CONFIRMED] symbol={trace.symbol or symbol or 'UNKNOWN'} "
                f"order_id={order_id} status=openOrder"
            )
            print(
                "[EXECUTION][ACK] "
                f"symbol={trace.symbol or symbol or 'UNKNOWN'} order_id={order_id} status=openOrder tracked=true"
            )
        if tracked is not None:
            tracked.ack_seen = True
            tracked.ack_seen_at = tracked.ack_seen_at or timestamp
            tracked.open_order_detail = dict(open_order_detail)
            tracked.final_execution_state = _resolve_authoritative_execution_state(tracked)
        truth = _EXECUTION_TRUTH_BY_ORDER_ID.get(int(order_id))
        if truth is not None:
            _transition_execution_truth_state(truth=truth, next_state="SUBMITTED", source="IBKR_CALLBACK")
    elif event_type == "error":
        code_raw = _extract_callback_field(callback_payload, "errorCode", "code")
        message = str(_extract_callback_field(callback_payload, "errorString", "message") or "")
        try:
            code = int(code_raw) if code_raw is not None else None
        except (TypeError, ValueError):
            code = None
        _update_ibkr_health(event_type="error", code=code)
        normalized_reason = _normalize_broker_reject_reason(code=code, message=message, status=event_status)
        if tracked is not None:
            if code is not None and code not in tracked.broker_error_codes:
                tracked.broker_error_codes.append(code)
            tracked.normalized_reject_reason = normalized_reason or tracked.normalized_reject_reason
            if normalized_reason in {"PERMISSION_SMALL_CAP_OPENING_RESTRICTED", "REGULATORY_CLOSING_ONLY", "UNKNOWN_BROKER_REJECT"}:
                tracked.reject_seen = True
            if normalized_reason == "QUEUED_UNTIL_RTH_WARNING":
                tracked.queued_for_rth_seen = True
            tracked.final_execution_state = _resolve_authoritative_execution_state(tracked)
        _BROKER_ERRORS_BY_ORDER_ID.setdefault(int(order_id), []).append({"code": code, "message": message, "normalized": normalized_reason})
        if normalized_reason == "OUTSIDE_RTH_IGNORED_WARNING":
            if tracked is not None:
                tracked.queued_for_rth_seen = True
                tracked.final_execution_state = _resolve_authoritative_execution_state(tracked)
            print(f"[EXECUTION][SESSION_CLASSIFICATION] order_id={order_id} verdict=OUTSIDE_RTH_IGNORED_WARNING")
            print(f"[EXECUTION][PREMARKET_ROUTE_VERDICT] order_id={order_id} normalized_reject_reason={normalized_reason}")
        if normalized_reason == "QUEUED_UNTIL_RTH_WARNING":
            print(f"[EXECUTION][QUEUED_FOR_RTH] order_id={order_id} message={message}")
        if normalized_reason in {"PERMISSION_SMALL_CAP_OPENING_RESTRICTED", "REGULATORY_CLOSING_ONLY", "UNKNOWN_BROKER_REJECT"}:
            print(f"[EXECUTION][PERMISSION_REJECT] order_id={order_id} code={code} normalized_reject_reason={normalized_reason}")
    elif event_type == "position":
        print(f"[EXECUTION][CALLBACK_NORMALIZED] event=position symbol={symbol or 'UNKNOWN'} broker_order_id={order_id} state=POSITION")
        if trace is not None:
            if qty > 0:
                _VISIBILITY_BY_ORDER_ID.setdefault(order_id, {}).update({"position_seen": True})
                trace.position_opened = True
                trace.lifecycle_state = "POSITION_CONFIRMED"
                _trace_log("POSITION_CONFIRMED", trace, extra=f"position_qty={qty}")
                print(f"[EXECUTION][LIFECYCLE] symbol={trace.symbol} marker=POSITION_CONFIRMED_FROM_IBKR")
    print(
        "[EXECUTION][EVENT_CREATED] "
        f"event_type={event.event_type} source={event.source} symbol={event.symbol} "
        f"order_id={event.broker_order_id} filled_qty={event.filled_quantity} fill_price={event.avg_fill_price}"
    )


def _apply_callback_fills(events: List[ExecutionEvent]) -> tuple[List[ExecutionEvent], int]:
    fills_applied = 0
    for event in events:
        if event.action != "SUBMITTED" or event.broker_order_id is None:
            continue
        callback_fill = _EXECUTION_EVENT_BUFFER.pop(int(event.broker_order_id), None)
        if callback_fill is None:
            continue
        event.event_type = callback_fill.event_type
        event.source = callback_fill.source
        event.broker_status = callback_fill.broker_status
        event.filled_quantity = int(callback_fill.filled_quantity or 0)
        callback_remaining = int(callback_fill.remaining_quantity or 0)
        if callback_remaining > 0:
            event.remaining_quantity = callback_remaining
        else:
            base_remaining = int(event.remaining_quantity or 0)
            event.remaining_quantity = max(0, base_remaining - event.filled_quantity)
        event.avg_fill_price = callback_fill.avg_fill_price
        event.last_update_time = callback_fill.last_update_time or _now_utc_iso()
        fills_applied += 1
    return events, fills_applied


def _fetch_ibkr_truth(mode: RunMode, include_executions: bool = False) -> tuple[list[Any], list[Any], list[Any]]:
    if _is_explicit_test_mode():
        return [], [], []
    if mode not in {RunMode.PAPER, RunMode.LIVE}:
        return [], [], []
    manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
    client = manager.get_client()
    open_orders = _safe_list_call(client, "openOrders")
    executions = _safe_list_call(client, "executions") if include_executions else []
    positions = _safe_list_call(client, "positions")
    print(f"[POSITION][SYNC] source=IBKR positions={len(positions)}")
    return open_orders, executions, positions


def _normalize_ibkr_truth(raw: Any) -> tuple[list[Any], list[Any], list[Any]]:
    if isinstance(raw, tuple):
        if len(raw) == 3:
            return list(raw[0] or []), list(raw[1] or []), list(raw[2] or [])
        if len(raw) == 2:
            return list(raw[0] or []), [], list(raw[1] or [])
    return [], [], []


def _run_watchdog_checks(*, now: datetime | None = None) -> None:
    global _WATCHDOG_STALLS_TOTAL, _WATCHDOG_SUBMITTED_NO_ACK_TIMEOUTS, _WATCHDOG_WORKING_NO_FILL_TIMEOUTS, _WATCHDOG_PARTIAL_FILL_STALLS
    now_utc = now or datetime.now(timezone.utc)
    for row in _RUNTIME_ORDERS.values():
        if row.terminal:
            continue
        verdict, elapsed = _classify_watchdog_state(row, now_utc)
        row.escalation_required = verdict in {
            "SUBMITTED_NO_ACK_TIMEOUT",
            "ACKNOWLEDGED_NO_WORKING_TIMEOUT",
            "WORKING_NO_FILL_TIMEOUT",
            "PARTIAL_FILL_STALLED",
        }
        row.escalation_reason = verdict if row.escalation_required else ""
        print(
            "[EXECUTION][WATCHDOG] "
            f"symbol={row.symbol} broker_order_id={row.broker_order_id} state={row.canonical_state} verdict={verdict} elapsed={elapsed}"
        )
        if not row.escalation_required:
            continue
        _WATCHDOG_STALLS_TOTAL += 1
        if verdict == "SUBMITTED_NO_ACK_TIMEOUT":
            _WATCHDOG_SUBMITTED_NO_ACK_TIMEOUTS += 1
        if verdict == "WORKING_NO_FILL_TIMEOUT":
            _WATCHDOG_WORKING_NO_FILL_TIMEOUTS += 1
        if verdict == "PARTIAL_FILL_STALLED":
            _WATCHDOG_PARTIAL_FILL_STALLS += 1
        print(
            "[EXECUTION][WATCHDOG_STALL] "
            f"symbol={row.symbol} broker_order_id={row.broker_order_id} verdict={verdict} elapsed={elapsed}"
        )
        if verdict in {"WORKING_NO_FILL_TIMEOUT", "ACKNOWLEDGED_NO_WORKING_TIMEOUT"} and int(row.filled_qty) <= 0:
            print(
                "[EXECUTION][WATCHDOG] "
                f"symbol={row.symbol} state=STALE_NO_FILL action=REPRICE_TRIGGERED seconds_waited={elapsed}"
            )
            _attempt_watchdog_reprice(row, elapsed_seconds=elapsed)


def _run_passive_position_reconciliation(*, positions: list[Any]) -> None:
    global _RECON_RESYNC_NEEDED, _RECONCILED_POSITIONS_OK, _RECONCILED_POSITIONS_MISMATCH, _BROKER_POSITION_WITHOUT_FILL_COUNT, _LOCAL_FILL_WITHOUT_POSITION_COUNT, _OPEN_POSITIONS_CONFIRMED, _REDUCED_POSITIONS_CONFIRMED, _CLOSED_POSITIONS_CONFIRMED
    _sync_ibkr_positions_from_snapshot(positions)
    broker_position_by_symbol: dict[str, int] = {
        symbol: int(row.quantity) for symbol, row in _IBKR_POSITIONS_BY_SYMBOL.items()
    }
    broker_avg_cost_by_symbol: dict[str, float | None] = {
        symbol: row.avg_price for symbol, row in _IBKR_POSITIONS_BY_SYMBOL.items()
    }
    local_fill_qty_by_symbol: dict[str, int] = {}
    local_fill_avg_by_symbol: dict[str, float | None] = {}
    local_fill_ts_by_symbol: dict[str, datetime | None] = {}
    for order in _RUNTIME_ORDERS.values():
        symbol = str(order.symbol or "").upper()
        if not symbol:
            continue
        local_fill_qty_by_symbol[symbol] = int(local_fill_qty_by_symbol.get(symbol, 0)) + _signed_local_fill_qty(order)
        if order.avg_fill_price is not None:
            local_fill_avg_by_symbol[symbol] = float(order.avg_fill_price)
        local_fill_ts_by_symbol[symbol] = _parse_iso_utc(order.first_fill_seen_at or order.last_update_at)
    symbols = set(broker_position_by_symbol.keys()) | set(local_fill_qty_by_symbol.keys())
    window_seconds = _position_reconciliation_window_seconds()
    now_utc = datetime.now(timezone.utc)
    mismatch_count = 0
    for symbol in sorted(symbols):
        local_qty = int(broker_position_by_symbol.get(symbol, 0))
        ibkr_qty = int(broker_position_by_symbol.get(symbol, 0))
        expected_position = int(local_fill_qty_by_symbol.get(symbol, 0))
        broker_avg_cost = broker_avg_cost_by_symbol.get(symbol)
        local_avg_cost = local_fill_avg_by_symbol.get(symbol)
        verdict = "ALIGNED"
        reason = ""
        prev_broker_qty = int(_BROKER_POSITION_LAST_QTY_BY_SYMBOL.get(symbol, 0))
        if ibkr_qty == 0 and expected_position == 0 and prev_broker_qty > 0:
            verdict = "POSITION_CLOSED_ALIGNED"
        elif ibkr_qty == 0 and expected_position == 0:
            verdict = "ALIGNED"
        elif ibkr_qty != 0 and expected_position == 0:
            verdict = "BROKER_POSITION_WITHOUT_FILL"
            reason = "broker_has_open_position_without_execdetails_fill_trail"
        elif ibkr_qty == 0 and expected_position != 0:
            fill_ts = local_fill_ts_by_symbol.get(symbol)
            pending = fill_ts is not None and (now_utc - fill_ts).total_seconds() <= float(window_seconds)
            if pending:
                verdict = "UNKNOWN_PENDING_RECONCILIATION"
                reason = "fill_seen_waiting_for_position_callback"
            else:
                verdict = "LOCAL_FILL_WITHOUT_BROKER_POSITION"
                reason = "local_fill_recorded_without_broker_open_position"
        elif ibkr_qty != expected_position:
            verdict = "QTY_MISMATCH"
            reason = f"expected_position={expected_position} ibkr_position={ibkr_qty}"
        elif broker_avg_cost is not None and local_avg_cost is not None and abs(float(broker_avg_cost) - float(local_avg_cost)) > 0.01:
            verdict = "AVG_COST_MISMATCH"
            reason = f"broker_avg_cost={broker_avg_cost} local_avg_cost={local_avg_cost}"
        elif ibkr_qty == 0 and expected_position == 0 and int(_BROKER_POSITION_LAST_QTY_BY_SYMBOL.get(symbol, 0)) > 0:
            verdict = "POSITION_CLOSED_ALIGNED"
        if verdict == "ALIGNED":
            _RECONCILED_POSITIONS_OK += 1
            print(f"[EXECUTION][POSITION_RECONCILE_OK] symbol={symbol} verdict=ALIGNED")
        elif verdict == "POSITION_CLOSED_ALIGNED":
            _RECONCILED_POSITIONS_OK += 1
            print(f"[EXECUTION][POSITION_RECONCILE_OK] symbol={symbol} verdict=ALIGNED")
        elif verdict in {"UNKNOWN_PENDING_RECONCILIATION"}:
            print(
                "[EXECUTION][POSITION_RECONCILE] "
                f"symbol={symbol} local_qty={local_qty} expected_position={expected_position} broker_qty={ibkr_qty} verdict={verdict}"
            )
        else:
            ownership = _POSITION_OWNERSHIP_BY_SYMBOL.get(symbol, OWNERSHIP_EXTERNAL)
            is_external_inventory = (
                _is_isolated_trading_mode() and verdict == "BROKER_POSITION_WITHOUT_FILL" and ownership == OWNERSHIP_EXTERNAL
            )
            if is_external_inventory:
                print(
                    f"[RECON][EXTERNAL_INVENTORY] symbol={symbol} reason=unowned_broker_state"
                )
                print(
                    "[EXECUTION][POSITION_RECONCILE_MISMATCH] "
                    f"symbol={symbol} verdict={verdict} reason=external_inventory"
                )
            else:
                _RECONCILED_POSITIONS_MISMATCH += 1
                mismatch_count += 1
                if verdict == "BROKER_POSITION_WITHOUT_FILL":
                    _BROKER_POSITION_WITHOUT_FILL_COUNT += 1
                    print(
                        "[RECON][SYSTEM_MISMATCH] "
                        f"symbol={symbol} verdict={verdict} reason={reason or 'mismatch'}"
                    )
                if verdict == "LOCAL_FILL_WITHOUT_BROKER_POSITION":
                    _LOCAL_FILL_WITHOUT_POSITION_COUNT += 1
                print(
                    "[POSITION][MISMATCH] "
                    f"symbol={symbol} expected_position={expected_position} ibkr_position={ibkr_qty} reason={reason or verdict}"
                )
                print(
                    "[EXECUTION][POSITION_RECONCILE_MISMATCH] "
                    f"symbol={symbol} verdict={verdict} reason={reason or 'mismatch'}"
                )
                _RECON_RESYNC_NEEDED = True
        print(
            "[EXECUTION][POSITION_RECONCILE] "
            f"symbol={symbol} local_qty={local_qty} expected_position={expected_position} broker_qty={ibkr_qty} verdict={verdict}"
        )
        if ibkr_qty > 0 and prev_broker_qty <= 0:
            print(f"[EXECUTION][POSITION_OPEN_CONFIRMED] symbol={symbol} broker_qty={ibkr_qty} avg_cost={broker_avg_cost}")
            _OPEN_POSITIONS_CONFIRMED += 1
        elif ibkr_qty > 0 and prev_broker_qty > ibkr_qty:
            print(f"[EXECUTION][POSITION_REDUCED_CONFIRMED] symbol={symbol} broker_qty={ibkr_qty}")
            print(f"[EXECUTION][LIFECYCLE] symbol={symbol} marker=POSITION_REDUCED_CONFIRMED")
            _REDUCED_POSITIONS_CONFIRMED += 1
        elif ibkr_qty == 0 and prev_broker_qty > 0:
            print(f"[EXECUTION][POSITION_CLOSED_CONFIRMED] symbol={symbol}")
            print(f"[EXECUTION][LIFECYCLE] symbol={symbol} marker=POSITION_CLOSED_CONFIRMED")
            _CLOSED_POSITIONS_CONFIRMED += 1
        _BROKER_POSITION_LAST_QTY_BY_SYMBOL[symbol] = ibkr_qty
    print(
        "[POSITION][SUMMARY] "
        f"total_positions={len(_IBKR_POSITIONS_BY_SYMBOL)} mismatches={mismatch_count}"
    )


def _check_callback_delay(*, now: datetime | None = None) -> None:
    global _CALLBACK_DELAY_WARNINGS_COUNT
    now_utc = now or datetime.now(timezone.utc)
    threshold = timedelta(seconds=max(1, int(_CALLBACK_DELAY_THRESHOLD_SECONDS)))
    for row in _RUNTIME_ORDERS.values():
        if row.canonical_state not in {"SUBMITTED_PENDING_CONFIRMATION", "SUBMITTED", "ACKNOWLEDGED", "WORKING"}:
            continue
        if row.filled_qty > 0:
            row.callback_pending = False
            row.callback_pending_since = None
            continue
        seen_at = _parse_iso_utc(row.first_seen_at)
        if seen_at is None:
            continue
        if now_utc - seen_at < threshold:
            continue
        if not row.callback_pending:
            row.callback_pending = True
            row.callback_pending_since = _now_utc_iso()
            _CALLBACK_DELAY_WARNINGS_COUNT += 1
            print(
                f"[EXECUTION][CALLBACK_DELAY_WARNING] order_id={row.broker_order_id} "
                f"symbol={row.symbol} callback_pending=true wait_seconds={int((now_utc - seen_at).total_seconds())}"
            )


def _check_position_consistency() -> None:
    filled_symbols = {
        row.symbol
        for row in _RUNTIME_ORDERS.values()
        if row.filled_qty > 0 or row.canonical_state in {"PARTIALLY_FILLED", "FILLED"}
    }
    position_symbols = {symbol for symbol, row in _IBKR_POSITIONS_BY_SYMBOL.items() if int(row.quantity) > 0}
    for symbol in sorted(filled_symbols - position_symbols):
        print(f"[POSITION][INCONSISTENT_STATE] symbol={symbol} reason=PENDING_POSITION_CONFIRMATION")
    for symbol in sorted(position_symbols - filled_symbols):
        ownership = _POSITION_OWNERSHIP_BY_SYMBOL.get(symbol, OWNERSHIP_EXTERNAL)
        if _is_isolated_trading_mode() and ownership == OWNERSHIP_EXTERNAL:
            print(f"[RECON][EXTERNAL_INVENTORY] symbol={symbol} reason=unowned_broker_state")
            continue
        print(f"[POSITION][INCONSISTENT_STATE] symbol={symbol} reason=position_without_fill_history")


def _sync_submitted_events_from_ibkr(
    mode: RunMode,
    events: List[ExecutionEvent],
) -> List[ExecutionEvent]:
    global _RECONCILED_ORDERS_COUNT, _RECONCILED_POSITIONS_COUNT
    if not events:
        return events
    open_orders, _executions, positions = _normalize_ibkr_truth(_fetch_ibkr_truth(mode))
    print(
        "[EXECUTION][WORKING_ORDER_RECON] "
        f"open_orders={len(open_orders)} positions={len(positions)}"
    )

    for event in events:
        if event.action != "SUBMITTED":
            continue
        event.last_update_time = _now_utc_iso()
    _run_passive_position_reconciliation(positions=positions)
    if positions:
        print("[POSITION][SYNC] reconciliation_snapshot_observed=true fill_source=CALLBACK_ONLY repair_mode=PASSIVE")
    _check_callback_delay()
    _run_watchdog_checks()
    _check_position_consistency()
    print(f"[EXECUTION][RECON_VERDICT] reconciled_orders={_RECONCILED_ORDERS_COUNT} reconciled_positions={_RECONCILED_POSITIONS_COUNT}")
    return events


def _post_submission_ibkr_diagnostics(
    *,
    mode: RunMode,
    manager: Any | None,
    submitted_order_ids: list[int],
) -> None:
    global _BROKER_TRUTH_FATALS, _BROKER_TRUTH_CONFIRMATIONS
    if not submitted_order_ids:
        return
    if mode not in {RunMode.PAPER, RunMode.LIVE}:
        return
    if manager is None:
        if _is_explicit_test_mode():
            client = SimpleNamespace(
                client_id="TEST",
                host="TEST",
                port="TEST",
                openOrders=lambda: [],
                executions=lambda: [],
                positions=lambda: [],
            )
        else:
            manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
            client = manager.get_client()
    else:
        client = manager.get_client()
    print("[IBKR][CLIENT_SESSION]")
    print(f"client_id={getattr(client, 'client_id', 'UNKNOWN')}")
    print(f"host={getattr(client, 'host', 'UNKNOWN')}")
    print(f"port={getattr(client, 'port', 'UNKNOWN')}")
    if hasattr(manager, "connection_metadata"):
        try:
            metadata = manager.connection_metadata()
        except Exception:
            metadata = {}
        configured_client_id = metadata.get("base_client_id")
        connected_client_id = metadata.get("connected_client_id")
        if (
            isinstance(configured_client_id, int)
            and isinstance(connected_client_id, int)
            and connected_client_id != configured_client_id
        ):
            print("[WARNING][IBKR_CLIENT_ID_CONFLICT]")
            print(
                f"configured_client_id={configured_client_id} connected_client_id={connected_client_id}"
            )
    submitted_lookup = {int(order_id) for order_id in submitted_order_ids}

    def _snapshot_broker_visibility() -> tuple[list[Any], list[Any], bool]:
        current_open_orders = _safe_list_call(client, "openOrders")
        current_executions = _safe_list_call(client, "executions")
        visible_open_ids = {int(getattr(row, "orderId", -1)) for row in current_open_orders}
        visible_exec_ids = {int(_extract_exec_order_id(row)) for row in current_executions if _extract_exec_order_id(row) is not None}
        for order_id in submitted_lookup:
            visibility = _VISIBILITY_BY_ORDER_ID.setdefault(int(order_id), {})
            if int(order_id) in visible_open_ids:
                visibility["openOrders_snapshot_seen"] = True
            if int(order_id) in visible_exec_ids:
                visibility["executions_snapshot_seen"] = True
            tracked = _RUNTIME_ORDERS.get(int(order_id))
            if tracked is not None and tracked.filled_qty > 0:
                visibility["position_seen"] = bool(_IBKR_POSITIONS_BY_SYMBOL.get(tracked.symbol) and int(_IBKR_POSITIONS_BY_SYMBOL[tracked.symbol].quantity) > 0)
        broker_truth_confirmed = any(_visibility_confirmed(order_id) for order_id in submitted_lookup)
        return current_open_orders, current_executions, broker_truth_confirmed

    open_orders, executions, broker_truth_confirmed = _snapshot_broker_visibility()
    print(f"[IBKR][OPEN_ORDERS] count={len(open_orders)}")
    print(f"[IBKR][EXEC_HISTORY] count={len(executions)}")
    for execution_row in executions:
        symbol = _extract_symbol_from_order(execution_row)
        order_id = _extract_exec_order_id(execution_row)
        shares = _extract_exec_qty(execution_row)
        price = _extract_exec_price(execution_row)
        print(
            "[IBKR][EXEC_HISTORY] "
            f"symbol={symbol or 'UNKNOWN'} order_id={order_id} shares={shares} price={price}"
        )
    for order_id in submitted_order_ids:
        tracked = _RUNTIME_ORDERS.get(int(order_id))
        status = tracked.broker_status if tracked is not None else "UNKNOWN"
        filled_qty = int(tracked.filled_qty) if tracked is not None else 0
        remaining_qty = int(tracked.remaining_qty) if tracked is not None else 0
        symbol = tracked.symbol if tracked is not None else "UNKNOWN"
        print(
            "[IBKR][ORDER_STATUS] "
            f"symbol={symbol} order_id={int(order_id)} status={status} "
            f"filled={filled_qty} remaining={remaining_qty}"
        )

    polling_timeout_seconds = 3
    callback_timeout_seconds = 2
    no_fill_timeout_seconds = polling_timeout_seconds + callback_timeout_seconds
    polling_deadline = time.time() + float(polling_timeout_seconds)
    print(
        f"[BROKER_TRUTH][ESCALATION_LEVEL=2] phase=POLLING submitted_order_ids={sorted(submitted_lookup)} "
        f"timeout_seconds={polling_timeout_seconds}"
    )
    while time.time() < polling_deadline and not broker_truth_confirmed:
        open_orders, executions, broker_truth_confirmed = _snapshot_broker_visibility()
        if broker_truth_confirmed:
            break
        time.sleep(0.1)

    callback_deadline = time.time() + float(callback_timeout_seconds)
    if not broker_truth_confirmed:
        print(
            f"[BROKER_TRUTH][ESCALATION_LEVEL=3] phase=CALLBACK_WAIT submitted_order_ids={sorted(submitted_lookup)} "
            f"timeout_seconds={callback_timeout_seconds}"
        )
    while time.time() < callback_deadline and not broker_truth_confirmed:
        open_orders, executions, broker_truth_confirmed = _snapshot_broker_visibility()
        if broker_truth_confirmed:
            break
        time.sleep(0.1)
    exec_detail_rows = 0
    for order_id in submitted_order_ids:
        tracked = _RUNTIME_ORDERS.get(int(order_id))
        seen_exec_ids = sorted(tracked.seen_exec_ids) if tracked is not None else []
        exec_detail_rows += len(seen_exec_ids)
        print(
            "[IBKR][EXEC_DETAILS] "
            f"order_id={int(order_id)} seen_exec_details={len(seen_exec_ids)} "
            f"exec_ids={','.join(seen_exec_ids) or 'NONE'}"
        )
    observed_exec_details = exec_detail_rows > 0
    if not observed_exec_details:
        print("[CRITICAL] IBKR_NO_FILL_CONFIRMATION")
    for order_id in submitted_order_ids:
        tracked = _RUNTIME_ORDERS.get(int(order_id))
        if tracked is None:
            continue
        tracked.final_execution_state = _resolve_authoritative_execution_state(tracked)
        if int(tracked.filled_qty) <= 0:
            timeout_state = "NO_FILL_TIMEOUT_TERMINAL"
            if tracked.final_execution_state in {"BROKER_WORKING", "BROKER_QUEUED_FOR_RTH", "BROKER_ACK_SEEN", "DISPATCH_SENT"}:
                timeout_state = "NO_FILL_TIMEOUT_NON_TERMINAL"
            tracked.final_execution_state = timeout_state if tracked.final_execution_state not in {"BROKER_QUEUED_FOR_RTH", "BROKER_WORKING"} else tracked.final_execution_state
            tracked.terminal = timeout_state == "NO_FILL_TIMEOUT_TERMINAL"
            print(
                f"[EXECUTION][NO_FILL_TIMEOUT] symbol={tracked.symbol} order_id={int(order_id)} "
                f"seconds_waited={no_fill_timeout_seconds} classification={tracked.final_execution_state}"
            )
    open_order_callback_count = sum(
        1
        for order_id in submitted_lookup
        if bool(_VISIBILITY_BY_ORDER_ID.get(int(order_id), {}).get("openOrder_seen"))
    )
    order_status_callback_count = sum(
        1
        for order_id in submitted_lookup
        if bool(_VISIBILITY_BY_ORDER_ID.get(int(order_id), {}).get("orderStatus_seen"))
    )
    inactive_count = 0
    inactive_normalized_reason_counts: dict[str, int] = {}
    marketable_submit_count = 0
    passive_submit_count = 0
    no_quote_submit_count = 0
    for order_id in submitted_lookup:
        tracked = _RUNTIME_ORDERS.get(int(order_id))
        if tracked is None:
            continue
        if str(tracked.broker_status or "").upper() == "INACTIVE":
            inactive_count += 1
            reason_key = str(tracked.inactive_normalized_reason or "INACTIVE_UNKNOWN")
            inactive_normalized_reason_counts[reason_key] = int(inactive_normalized_reason_counts.get(reason_key, 0)) + 1
        bucket = _fillability_bucket(tracked.fillability_classification)
        if bucket == "marketable":
            marketable_submit_count += 1
        elif bucket == "no_quote":
            no_quote_submit_count += 1
        else:
            passive_submit_count += 1
    print("[IBKR][CALLBACK_SUMMARY]")
    print(f"openOrder={open_order_callback_count}")
    print(f"orderStatus={order_status_callback_count}")
    print(f"inactive_count={inactive_count}")
    print(f"inactive_normalized_reason_counts={dict(sorted(inactive_normalized_reason_counts.items()))}")
    print(f"marketable_submit_count={marketable_submit_count}")
    print(f"passive_submit_count={passive_submit_count}")
    print(f"no_quote_submit_count={no_quote_submit_count}")
    print(
        "[EXECUTION][CALLBACK_VERDICT] "
        f"mode={mode.value} open_order_seen={open_order_callback_count} "
        f"order_status_seen={order_status_callback_count} strict_required={_strict_broker_truth_required(mode)}"
    )
    if open_order_callback_count == 0 and order_status_callback_count == 0:
        print("[CRITICAL][NO_IBKR_ACK]")
        print("[CRITICAL][IBKR_NO_ORDER_ACKNOWLEDGEMENT]")
        print("reason=POSSIBLE_PLACEORDER_FAILURE_OR_SESSION_ISSUE")
        print("possible_causes:")
        print("- TWS not accepting orders")
        print("- API permissions disabled")
        print("- wrong account")
        print("- client_id conflict")
        print("- IB Gateway/TWS mismatch")
        if not _strict_broker_truth_required(mode):
            print("[EXECUTION][ACK_SKIPPED_NON_LIVE]")
            print(f"mode={mode.value}")
    if not broker_truth_confirmed:
        print(f"[BROKER_TRUTH][ESCALATION_LEVEL=4] phase=FORCED_RESYNC submitted_order_ids={sorted(submitted_lookup)}")
        req_open_orders = getattr(client, "reqOpenOrders", None)
        if callable(req_open_orders):
            req_open_orders()
        req_all_open_orders = getattr(client, "reqAllOpenOrders", None)
        if callable(req_all_open_orders):
            req_all_open_orders()
        req_executions = getattr(client, "reqExecutions", None)
        if callable(req_executions):
            try:
                from ibapi.execution import ExecutionFilter

                req_id = int(time.time() * 1000) % 1_000_000_000
                req_executions(req_id, ExecutionFilter())
            except Exception:
                print("[IBKR][SYNC_REQUEST][ERROR] executions_request_failed")
        _safe_list_call(client, "openOrders")
        _safe_list_call(client, "executions")
        _safe_list_call(client, "positions")
        open_orders, executions, broker_truth_confirmed = _snapshot_broker_visibility()
    for order_id in submitted_order_ids:
        tracked = _RUNTIME_ORDERS.get(int(order_id))
        _log_visibility_matrix(int(order_id), tracked.symbol if tracked is not None else "UNKNOWN")
        print(
            "[BROKER_TRUTH][CONFIRMATION_SOURCE] "
            f"order_id={int(order_id)} source={_visibility_confirmation_source(int(order_id))}"
        )
    if broker_truth_confirmed:
        _BROKER_TRUTH_CONFIRMATIONS += 1
        print(f"[BROKER_TRUTH][CONFIRMED] submitted_order_ids={sorted(submitted_lookup)}")
    print(
        "[EXECUTION][TRUTH_SUMMARY] "
        f"mode={mode.value} submitted_orders={len(submitted_order_ids)} "
        f"broker_truth_confirmed={broker_truth_confirmed}"
    )
    if len(submitted_order_ids) > 0 and not broker_truth_confirmed and _strict_broker_truth_required(mode):
        _BROKER_TRUTH_FATALS += 1
        print(f"[BROKER_TRUTH][FATAL] submitted_order_ids={sorted(submitted_lookup)}")
        raise RuntimeError("BROKER_TRUTH_NOT_CONFIRMED")
    if len(submitted_order_ids) > 0 and not broker_truth_confirmed:
        print("[EXECUTION][BROKER_TRUTH_SKIPPED]")
        print(f"mode={mode.value}")


def _is_explicit_test_mode() -> bool:
    if str(os.environ.get("EXECUTION_ENV", "")).strip().upper() == "TEST":
        return True
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _strict_broker_truth_required(mode: RunMode) -> bool:
    if _is_explicit_test_mode():
        return False
    return mode in {RunMode.PAPER, RunMode.LIVE}


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _validate_ibkr_connection(mode: RunMode) -> None:
    if _is_explicit_test_mode():
        return

    if mode not in {RunMode.PAPER, RunMode.LIVE}:
        return

    manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
    metadata = manager.connection_metadata()
    client = manager.get_client()
    print("[IBKR][SESSION_VALIDATION]")
    print(f"client_id={getattr(client, 'client_id', 'UNKNOWN')}")
    print(f"connected={bool(getattr(client, 'isConnected', lambda: False)())}")
    account = None
    if hasattr(client, "get_primary_account"):
        try:
            account = client.get_primary_account()
        except Exception:
            account = None
    print(f"account={account or 'UNKNOWN'}")

    connected = bool(metadata.get("connected", False))
    if not connected:
        raise RuntimeError(
            "IBKR connection is not active: connected=False "
            f"mode={mode.value} host={metadata.get('host')} port={metadata.get('port')}"
        )

    expected_port = 7496 if mode == RunMode.LIVE else 7497
    configured_port = metadata.get("port")
    if configured_port != expected_port:
        raise RuntimeError(
            "IBKR connection port validation failed "
            f"mode={mode.value} expected_port={expected_port} configured_port={configured_port}"
        )

    configured_client_id = metadata.get("base_client_id")
    connected_client_id = metadata.get("connected_client_id")
    if configured_client_id is None or connected_client_id is None:
        raise RuntimeError(
            "IBKR client id validation failed "
            f"mode={mode.value} base_client_id={configured_client_id} connected_client_id={connected_client_id}"
        )
    if not isinstance(configured_client_id, int) or not isinstance(connected_client_id, int):
        raise RuntimeError(
            "IBKR client id validation failed "
            f"mode={mode.value} base_client_id={configured_client_id} connected_client_id={connected_client_id}"
        )
    if connected_client_id < configured_client_id:
        raise RuntimeError(
            "IBKR connected client id is invalid "
            f"mode={mode.value} base_client_id={configured_client_id} connected_client_id={connected_client_id}"
        )
    if not bool(getattr(client, "isConnected", lambda: False)()):
        raise RuntimeError("IBKR_SESSION_INVALID")
    next_valid_id = getattr(client, "_next_valid_order_id", None)
    if next_valid_id is None:
        raise RuntimeError("IBKR_SESSION_INVALID")


def _safe_price_value(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _normalize_price_source(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"IBKR_LAST", "IBKR_BID_ASK", "SYNTHETIC"}:
        return normalized
    if normalized in {
        "IBKR_MARKET_DATA_SNAPSHOT",
        "IBKR_SNAPSHOT_LAST",
        "IBKR_LAST_PRICE",
        "IBKR_L1_LAST",
        "IBKR_STREAM",
    }:
        return "IBKR_LAST"
    if normalized in {
        "IBKR_SNAPSHOT",
        "IBKR_SNAPSHOT_MID",
        "IBKR_L1_MID",
        "IBKR_BID_ASK",
    }:
        return "IBKR_BID_ASK"
    if normalized in {"SYNTH", "SYNTHETIC_FALLBACK", "MOCK", "SIMULATED"}:
        return "SYNTHETIC"
    return normalized


def _none_text(value: Any) -> str:
    if value is None:
        return "NONE"
    text = str(value).strip()
    return text if text else "NONE"


def _session_label_now() -> str:
    session = resolve_session_state()
    if session == SessionState.REG:
        return "RTH"
    if session == SessionState.PRE:
        return "PRE"
    if session == SessionState.AFTER:
        return "AH"
    return "OVN"


def _canonical_execution_session(label: str) -> str:
    normalized = str(label or "").strip().upper()
    if normalized in {"PRE", "PREMARKET"}:
        return "PREMARKET"
    if normalized in {"REG", "RTH"}:
        return "RTH"
    if normalized in {"AFTER", "AH", "AFTER_HOURS"}:
        return "AFTER_HOURS"
    return "CLOSED"


def _resolved_tick_size(value: Any) -> float:
    tick = _safe_price_value(value)
    if tick is None:
        return 0.01
    return max(0.01, float(tick))


def _round_price_in_favor(*, side: str, price: float, tick_size: float) -> float:
    tick = _resolved_tick_size(tick_size)
    steps = float(price) / tick
    if str(side or "").upper() == "BUY":
        return round(math.ceil(steps) * tick, 6)
    return round(math.floor(steps) * tick, 6)


def _aggressive_cross_cap_ticks() -> int:
    return _watchdog_threshold_seconds("EXECUTION_AGGRESSIVE_MAX_CROSS_TICKS", 50)


def _compute_aggressive_limit_price(
    *,
    side: str,
    bid: float,
    ask: float,
    tick_size: float,
    aggression_level: int = 1,
) -> tuple[float, bool, float]:
    spread = max(0.0, float(ask) - float(bid))
    tick = _resolved_tick_size(tick_size)
    floor = max(tick, 0.01)
    component = max(floor, spread * 0.25)
    level = max(1, int(aggression_level))
    raw = (float(ask) + component * level) if str(side or "").upper() == "BUY" else (float(bid) - component * level)
    rounded = _round_price_in_favor(side=str(side or "").upper(), price=raw, tick_size=tick)
    max_cross_ticks = _aggressive_cross_cap_ticks()
    if str(side or "").upper() == "BUY":
        max_allowed = float(ask) + float(max_cross_ticks) * tick
        if rounded > max_allowed:
            return _round_price_in_favor(side="BUY", price=max_allowed, tick_size=tick), True, component
    else:
        min_allowed = max(0.0, float(bid) - float(max_cross_ticks) * tick)
        if rounded < min_allowed:
            return _round_price_in_favor(side="SELL", price=min_allowed, tick_size=tick), True, component
    return rounded, False, component


def _compute_quote_spread(*, bid: float | None, ask: float | None) -> tuple[float | None, float | None]:
    if bid is None or ask is None or ask <= 0:
        return None, None
    spread_abs = max(0.0, float(ask) - float(bid))
    spread_pct = (spread_abs / float(ask)) * 100 if ask > 0 else None
    return spread_abs, spread_pct


def classify_submit_fillability(
    *,
    order_type: str,
    action: str,
    lmt_price: float | None,
    bid: float | None,
    ask: float | None,
) -> tuple[str, str]:
    order_type_norm = str(order_type or "").upper()
    action_norm = str(action or "").upper()
    has_quote_context = bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0
    if order_type_norm == "MKT":
        if not has_quote_context:
            return "NO_QUOTE_CONTEXT", "market order but bid/ask unavailable"
        if action_norm == "BUY":
            return "CROSSING_ASK_AGGRESSIVE", "market buy crosses ask liquidity"
        if action_norm == "SELL":
            return "CROSSING_BID_AGGRESSIVE", "market sell crosses bid liquidity"
        return "NON_MARKETABLE_UNKNOWN", "market order with unsupported action"
    if not has_quote_context:
        return "NO_QUOTE_CONTEXT", "missing bid/ask quote context"
    if order_type_norm != "LMT" or lmt_price is None:
        return "NON_MARKETABLE_UNKNOWN", "unsupported order type or missing lmt_price"
    if action_norm == "BUY":
        if ask is not None and float(lmt_price) > float(ask):
            return "CROSSING_ASK_AGGRESSIVE", "buy limit above ask"
        if ask is not None and float(lmt_price) == float(ask):
            return "PASSIVE_AT_ASK", "buy limit joins ask"
        if bid is not None and ask is not None and float(lmt_price) > float(bid) and float(lmt_price) < float(ask):
            return "RESTING_INSIDE_SPREAD", "buy limit inside spread"
        if bid is not None and float(lmt_price) <= float(bid):
            return "PASSIVE_AWAY_FROM_MARKET", "buy limit at or below bid"
    if action_norm == "SELL":
        if bid is not None and float(lmt_price) < float(bid):
            return "CROSSING_BID_AGGRESSIVE", "sell limit below bid"
        if bid is not None and float(lmt_price) == float(bid):
            return "PASSIVE_AT_BID", "sell limit joins bid"
        if bid is not None and ask is not None and float(lmt_price) > float(bid) and float(lmt_price) < float(ask):
            return "RESTING_INSIDE_SPREAD", "sell limit inside spread"
        if ask is not None and float(lmt_price) >= float(ask):
            return "PASSIVE_AWAY_FROM_MARKET", "sell limit at or above ask"
    return "DEFERRED_OR_UNCLASSIFIABLE", "unable to classify from payload"


def normalize_inactive_reason(
    *,
    submit_payload: dict[str, Any],
    open_order_echo: dict[str, Any],
    broker_status: str,
    why_held: str,
    session_label: str,
    fillability: str,
    quote_available: bool,
) -> tuple[str, str]:
    if str(broker_status or "").upper() != "INACTIVE":
        return "INACTIVE_UNKNOWN", "broker status is not INACTIVE"
    why = str(why_held or "").strip()
    why_upper = why.upper()
    submit_outside_rth = submit_payload.get("outside_rth")
    echo_outside_rth = open_order_echo.get("outside_rth")
    tif = str(open_order_echo.get("tif") or submit_payload.get("tif") or "").upper()
    exchange = str(open_order_echo.get("exchange") or submit_payload.get("exchange") or "").upper()
    order_type = str(open_order_echo.get("order_type") or submit_payload.get("order_type") or "MKT").upper()
    last = _safe_price_value(submit_payload.get("last"))
    bid = _safe_price_value(submit_payload.get("bid"))
    ask = _safe_price_value(submit_payload.get("ask"))
    spread = (float(ask) - float(bid)) if bid is not None and ask is not None else None
    if why:
        if any(token in why_upper for token in ("ROUTE", "EXCHANGE", "DESTINATION")):
            return "ROUTING_REJECT", f"why_held indicates routing issue: {why}"
        if any(token in why_upper for token in ("RTH", "SESSION", "MARKET CLOSED", "CLOSED")):
            return "SESSION_MISMATCH", f"why_held indicates session mismatch: {why}"
        return "ROUTING_REJECT", f"why_held present: {why}"
    canonical_session = _canonical_execution_session(session_label)
    if (submit_outside_rth is False or echo_outside_rth is False) and canonical_session in {"PREMARKET", "AFTER_HOURS", "CLOSED"}:
        return "SESSION_MISMATCH", "outside_rth disabled outside regular session"
    if tif == "DAY" and canonical_session in {"AFTER_HOURS", "CLOSED"}:
        return "SESSION_MISMATCH", "DAY tif observed outside regular session"
    if not quote_available or fillability == "NO_QUOTE_CONTEXT" or bid is None or ask is None:
        return "NO_LIQUIDITY", "no quote context available at submit time"
    if spread is not None and spread <= 0:
        return "NO_LIQUIDITY", f"invalid spread={spread}"
    if order_type == "LMT" and fillability in {
        "PASSIVE_AWAY_FROM_MARKET",
        "RESTING_INSIDE_SPREAD",
        "PASSIVE_AT_ASK",
        "PASSIVE_AT_BID",
        "DEFERRED_OR_UNCLASSIFIABLE",
        "NON_MARKETABLE_UNKNOWN",
    }:
        return "NON_MARKETABLE", f"submit fillability={fillability}"
    if exchange and exchange not in {"SMART", "NONE"} and fillability.startswith("CROSSING_"):
        return "ROUTING_REJECT", f"non-SMART exchange for marketable order: {exchange}"
    if last is None and fillability in {"DEFERRED_OR_UNCLASSIFIABLE", "NON_MARKETABLE_UNKNOWN"}:
        return "NO_LIQUIDITY", "last price unavailable and fillability unclassifiable"
    return "UNKNOWN", "insufficient evidence for deterministic classification"


def _inactive_terminal_state_from_reason(reason: str) -> str:
    mapping = {
        "NON_MARKETABLE": "BROKER_INACTIVE_NON_MARKETABLE",
        "SESSION_MISMATCH": "BROKER_INACTIVE_SESSION_MISMATCH",
        "NO_LIQUIDITY": "BROKER_INACTIVE_NO_QUOTE",
        "ROUTING_REJECT": "BROKER_INACTIVE_ROUTING",
        "UNKNOWN": "BROKER_INACTIVE_UNKNOWN",
    }
    return mapping.get(str(reason or "").upper(), "BROKER_INACTIVE_UNKNOWN")


def _fillability_bucket(classification: str) -> str:
    normalized = str(classification or "").upper()
    if normalized in {"CROSSING_ASK_AGGRESSIVE", "CROSSING_BID_AGGRESSIVE"}:
        return "marketable"
    if normalized == "NO_QUOTE_CONTEXT":
        return "no_quote"
    if normalized in {"PASSIVE_AWAY_FROM_MARKET", "RESTING_INSIDE_SPREAD", "PASSIVE_AT_ASK", "PASSIVE_AT_BID", "DEFERRED_OR_UNCLASSIFIABLE", "NON_MARKETABLE_UNKNOWN"}:
        return "passive"
    return "passive"


def _evaluate_submission_restriction(
    *,
    symbol: str,
    entry_price: float | None,
    primary_exchange: str | None,
    float_millions: float | None,
    volume: float | None,
) -> tuple[bool, str]:
    if entry_price is not None and float(entry_price) < 2.0:
        return False, "price_below_2"
    if float_millions is not None and float(float_millions) < 20.0:
        return False, "float_below_20m"
    normalized_exchange = str(primary_exchange or "").strip().upper()
    if normalized_exchange in {"", "UNKNOWN", "NONE", "OTC", "PINK", "OTCBB"}:
        return False, "unsupported_primary_exchange"
    if volume is not None and float(volume) < 10_000:
        return False, "extremely_low_volume"
    return False, "ok"


def _config_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _config_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _wait_for_ibkr_snapshot_for_symbol(symbol: str, *, wait_up_to: float = 2.0, poll_interval: float = 0.2) -> dict[str, float | None]:
    normalized_symbol = str(symbol or "").upper().strip()
    if not normalized_symbol:
        return {}
    print(f"[IBKR][SNAPSHOT_REQUEST] symbol={normalized_symbol}")
    try:
        manager = get_shared_ibkr_connection_manager(readonly_enabled=True)
        ib = manager.get_client()
        _, Stock, _ = safe_import_ib_insync()
        contract = Stock(normalized_symbol, "SMART", "USD")
        ticker = ib.reqMktData(contract, genericTickList="", snapshot=True, regulatorySnapshot=False)
    except Exception as exc:
        print(f"[EXECUTION][WAIT] symbol={normalized_symbol} reason=WAITING_FOR_PRICE request_error={exc}")
        return {}

    snapshot: dict[str, float | None] = {}
    poll_count = max(1, int(wait_up_to / poll_interval))
    wait_started = time.monotonic()
    try:
        for attempt in range(1, poll_count + 1):
            elapsed = time.monotonic() - wait_started
            print(f"[PRICE][WAIT_LOOP] symbol={normalized_symbol} attempt={attempt} elapsed={elapsed:.3f}")
            try:
                ib.waitOnUpdate(timeout=poll_interval)
            except Exception:
                time.sleep(poll_interval)
            last = _safe_price_value(getattr(ticker, "last", None))
            bid = _safe_price_value(getattr(ticker, "bid", None))
            ask = _safe_price_value(getattr(ticker, "ask", None))
            volume = _safe_price_value(getattr(ticker, "volume", None))
            snapshot = {"last": last, "bid": bid, "ask": ask, "volume": volume}
            if last is not None or (bid is not None and ask is not None):
                wait_time = time.monotonic() - wait_started
                print(f"[PRICE][RESOLVED_AFTER_WAIT] symbol={normalized_symbol} wait_time={wait_time:.3f}")
                break
    finally:
        try:
            ib.cancelMktData(contract)
        except Exception:
            pass
    return snapshot


def _submit_ibkr_order(
    *,
    mode: RunMode,
    client: Any,
    symbol: str,
    side: str,
    quantity: int,
    order_ref: str,
    intent_id: str = "",
    entry_price: float | None = None,
    entry_price_source: str = "",
    float_millions: float | None = None,
    execution_context: dict[str, Any] | None = None,
    is_exit_order: bool = False,
) -> int:
    global _CONTRACT_VALIDATION_FAILURES
    assert isinstance(symbol, str)
    assert isinstance(side, str)
    assert isinstance(quantity, int)
    if symbol.__class__.__name__ == "ScannerSubscription" or side.__class__.__name__ == "ScannerSubscription":
        raise RuntimeError("SCANNER_SUBSCRIPTION_CONTAMINATION_DETECTED")
    _, Stock, _ = safe_import_ib_insync()
    print(f"[IBKR][CONTRACT_VALIDATION][START] symbol={symbol}")
    contract = Stock(symbol, "SMART", "USD")
    qualified = []
    if hasattr(client, "qualifyContracts"):
        qualified = list(client.qualifyContracts(contract) or [])
    if not qualified:
        _CONTRACT_VALIDATION_FAILURES += 1
        print(f"[IBKR][CONTRACT_VALIDATION][FAIL] symbol={symbol} reason=qualification_failed")
        raise RuntimeError(f"CONTRACT_NOT_QUALIFIED:{symbol}")
    resolved_contract = qualified[0]
    con_id = int(getattr(resolved_contract, "conId", 0) or 0)
    if con_id <= 0:
        _CONTRACT_VALIDATION_FAILURES += 1
        print(f"[IBKR][CONTRACT_VALIDATION][FAIL] symbol={symbol} reason=missing_conid")
        raise RuntimeError(f"CONTRACT_NOT_QUALIFIED:{symbol}")
    exchange = getattr(resolved_contract, "exchange", None)
    currency = getattr(resolved_contract, "currency", None)
    primary_exchange = getattr(resolved_contract, "primaryExchange", None)
    sec_type = getattr(resolved_contract, "secType", None)
    print("[IBKR][CONTRACT_VALIDATION]")
    print(f"symbol={symbol}")
    print(f"conId={con_id}")
    print(f"exchange={exchange}")
    print(f"primaryExchange={primary_exchange}")
    print(f"currency={currency}")
    print(f"secType={sec_type}")
    if not exchange or not currency:
        _CONTRACT_VALIDATION_FAILURES += 1
        raise RuntimeError("CONTRACT_NOT_QUALIFIED")
    print(f"[IBKR][CONTRACT_VALIDATION][OK] symbol={symbol} conId={con_id}")
    raw_entry_source = _none_text(entry_price_source)
    normalized_entry_source = _normalize_price_source(entry_price_source)
    authority_allowed = normalized_entry_source in {"IBKR_LAST", "IBKR_BID_ASK"}
    if mode == RunMode.LIVE:
        authority_allowed = normalized_entry_source == "IBKR_BID_ASK"
    print(
        "[EXECUTION][PRICE_AUTHORITY_CHECK] "
        f"symbol={symbol} raw_price_source={raw_entry_source} "
        f"normalized_price_source={_none_text(normalized_entry_source)} authority_allowed={str(authority_allowed).lower()}"
    )
    if not authority_allowed:
        print(f"[EXECUTION][BLOCK] symbol={symbol} reason=NO_IBKR_PRICE_AUTHORITY price_source={_none_text(entry_price_source)}")
        raise RuntimeError("NO_IBKR_PRICE_AUTHORITY")
    order = Order()
    _sanitize_ibkr_order_attributes(order)
    order.action = side.upper()
    order.orderType = "MKT"
    order.totalQuantity = int(quantity)
    order.tif = "DAY"
    order.orderRef = order_ref
    account = getattr(client, "get_primary_account", lambda: None)() if hasattr(client, "get_primary_account") else None
    if account:
        order.account = account
        print(f"[IBKR][ACCOUNT_BINDING] account={account}")
    print("[EXECUTION][FINAL_ORDER_CHECK]")
    print(f"type={type(order)}")
    print(f"action={getattr(order, 'action', None)}")
    print(f"qty={getattr(order, 'totalQuantity', None)}")
    print(f"orderType={getattr(order, 'orderType', None)}")
    if is_exit_order:
        order.orderType = "MKT"
        order.outsideRth = True
        print(f"[EXECUTION][EXIT_FORCE_ALLOW] symbol={symbol} action=FORCE_EXECUTABLE orderType={order.orderType} outsideRth={order.outsideRth}")
    if not isinstance(order, Order):
        raise RuntimeError("ORDER_OBJECT_CONTAMINATION_DETECTED")
    if order.action not in ("BUY", "SELL"):
        raise RuntimeError(f"INVALID_ORDER_OBJECT_TYPE: {type(order)}")
    assert order.action in ("BUY", "SELL")
    assert order.totalQuantity > 0
    assert order.orderType in ("MKT", "LMT")
    if str(getattr(resolved_contract, "secType", "STK") or "STK").upper() == "STK":
        outside_rth = getattr(order, "outsideRth", None)
        if outside_rth is not True:
            message = (
                f"EQUITY_ORDER_OUTSIDERTH_DISABLED symbol={symbol} "
                f"order_ref={order_ref} outsideRth={outside_rth}"
            )
            if _is_explicit_test_mode():
                raise RuntimeError(message)
            print(f"[EXECUTION][WARN] {message}")
    strategy_name = "UNKNOWN"
    _namespace, parsed_strategy, _parsed_intent = _parse_order_ref_components(order_ref)
    if parsed_strategy:
        strategy_name = parsed_strategy
    print(
        "[EXECUTION][SUBMIT] "
        f"symbol={symbol} side={order.action} qty={order.totalQuantity} "
        f"orderType={order.orderType} tif={order.tif} outsideRth={getattr(order, 'outsideRth', None)} "
        f"strategy={strategy_name}"
    )
    print(
        "[IBKR][PLACE_ORDER][START] "
        f"symbol={symbol} order_id=PENDING client_id={getattr(client, 'client_id', None)} account={account or 'UNKNOWN'} "
        f"order_type={getattr(order, 'orderType', 'MKT')} tif={getattr(order, 'tif', 'DAY')} qty={quantity} side={side}"
    )
    quote_snapshot = _wait_for_ibkr_snapshot_for_symbol(str(symbol or ""), wait_up_to=0.4, poll_interval=0.1)
    bid = _safe_price_value(quote_snapshot.get("bid"))
    ask = _safe_price_value(quote_snapshot.get("ask"))
    last = _safe_price_value(quote_snapshot.get("last"))
    volume = _safe_price_value(quote_snapshot.get("volume"))
    # Fallback to persisted resolved price if snapshot last is missing
    if last is None:
        persisted_last = (execution_context or {}).get("resolved_last_price")
        if persisted_last is not None and persisted_last > 0:
            last = persisted_last
            print(
                f"[EXECUTION][LAST_PRICE_FALLBACK] "
                f"symbol={symbol} using persisted_last_price={persisted_last}"
            )
    quote_context_ok = bid is not None and ask is not None and bid > 0 and ask > 0
    has_last_price = last is not None and last > 0
    execution_path = FULL_QUOTE_PATH if quote_context_ok else DEGRADED_QUOTE_PATH
    quote_context = "FULL_BID_ASK" if quote_context_ok else "DEGRADED_LAST_ONLY"
    price_source = "IBKR_BID_ASK" if quote_context_ok else ("IBKR_LAST" if has_last_price else "SYNTHETIC")
    degraded_paper_path_allowed = execution_path == DEGRADED_QUOTE_PATH and mode == RunMode.PAPER and has_last_price
    market_session = _canonical_execution_session(_session_label_now())
    is_premarket = market_session == "PREMARKET"
    print(f"[EXECUTION][PATH] symbol={symbol} path={execution_path}")
    print(f"[EXECUTION][QUOTE_CONTEXT] symbol={symbol} quote_context={quote_context} price_source={price_source}")
    if execution_path == DEGRADED_QUOTE_PATH:
        print(f"[EXECUTION][DEGRADED_MODE_OVERRIDE] symbol={symbol} action=FORCE_MKT")
        if degraded_paper_path_allowed:
            print(f"[EXECUTION][DEGRADED_MODE] symbol={symbol} using last_price_only no_bid_ask")
        print(
            "[EXECUTION][CONSISTENCY_CHECK] "
            f"symbol={symbol} execution_path={execution_path} quote_block_skipped=true"
        )
    min_tick = _resolved_tick_size(getattr(resolved_contract, "minTick", None))
    premarket_degraded_last_fallback_used = False
    if is_exit_order:
        order.orderType = "MKT"
        order.outsideRth = True
        print(
            "[EXECUTION][ORDER_MODE] "
            f"symbol={symbol} enforced=EXIT_FORCE_MKT orderType=MKT outsideRth=True"
        )
    elif is_premarket:
        if quote_context_ok:
            order.orderType = "LMT"
            buffered_limit, _cap_applied, _component = _compute_aggressive_limit_price(
                side=order.action,
                bid=float(bid),
                ask=float(ask),
                tick_size=min_tick,
                aggression_level=1,
            )
            if order.action == "BUY":
                order.lmtPrice = float(buffered_limit)
            else:
                order.lmtPrice = float(buffered_limit)
            print(
                "[EXECUTION][ORDER_MODE] "
                f"symbol={symbol} enforced=PREMARKET_LIMIT orderType=LMT "
                f"lmtPrice={order.lmtPrice} source=BID_ASK_BUFFERED"
            )
        else:
            order.orderType = "MKT"
            premarket_degraded_last_fallback_used = True
            print(
                "[EXECUTION][ORDER_MODE] "
                f"symbol={symbol} enforced=PREMARKET_DEGRADED_FORCE_MKT orderType=MKT source=NO_BID_ASK"
            )
    else:
        print(
            "[EXECUTION][ORDER_MODE] "
            f"symbol={symbol} enforced=SESSION_DEFAULT session={market_session} "
            f"orderType={getattr(order, 'orderType', 'UNKNOWN')} source={price_source}"
        )
    spread_abs, spread_pct = _compute_quote_spread(bid=bid, ask=ask)
    fillability, fillability_rationale = classify_submit_fillability(
        order_type=str(getattr(order, "orderType", "") or ""),
        action=str(getattr(order, "action", "") or ""),
        lmt_price=_safe_price_value(getattr(order, "lmtPrice", None)),
        bid=bid,
        ask=ask,
    )
    if fillability in {"PASSIVE_AWAY_FROM_MARKET", "RESTING_INSIDE_SPREAD", "PASSIVE_AT_ASK", "PASSIVE_AT_BID", "DEFERRED_OR_UNCLASSIFIABLE", "NON_MARKETABLE_UNKNOWN"}:
        if is_exit_order:
            print(
                "[EXECUTION][FILLABILITY_OVERRIDE] "
                f"symbol={symbol} reason=EXIT_FORCE_ALLOW classification={fillability}"
            )
        elif is_premarket and quote_context_ok:
            print(
                "[EXECUTION][FILLABILITY_OVERRIDE] "
                f"symbol={symbol} reason=PREMARKET_LIMIT_POLICY_BID_ASK classification={fillability}"
            )
        elif premarket_degraded_last_fallback_used:
            print(
                "[EXECUTION][FILLABILITY_OVERRIDE] "
                f"symbol={symbol} reason=PREMARKET_PAPER_LAST_FALLBACK_NO_BID_ASK classification={fillability}"
            )
        else:
            print(f"[EXECUTION][BLOCK] symbol={symbol} reason=NON_MARKETABLE_ORDER classification={fillability}")
            raise RuntimeError("NON_MARKETABLE_ORDER")
    _, restriction_detail = _evaluate_submission_restriction(
        symbol=str(symbol or "").upper(),
        entry_price=entry_price if entry_price is not None else (last if last is not None else ask),
        primary_exchange=str(primary_exchange or ""),
        float_millions=float_millions,
        volume=volume,
    )
    print(
        "[EXECUTION][RESTRICTION_CHECK_BYPASSED] "
        f"symbol={symbol} reason={restriction_detail} action=ALLOW"
    )
    print("[EXECUTION][FINAL_INTENT]")
    print(f"symbol={symbol}")
    print(f"orderType={getattr(order, 'orderType', None)}")
    print(f"price={_none_text(_safe_price_value(getattr(order, 'lmtPrice', None)))}")
    print(f"quote_mode={quote_context}")
    print(
        "reasoning="
        f"session={market_session};execution_path={execution_path};price_source={price_source};"
        f"fillability={fillability};restriction={restriction_detail};action=ALLOW_SUBMIT_TO_IBKR"
    )
    try:
        order_id = int(client.submit_order(resolved_contract, order))
    except Exception as exc:
        print(f"[IBKR][PLACE_ORDER][ERROR] symbol={symbol} order_id=PENDING error={exc}")
        raise
    wire_payload = {
        "symbol": str(symbol or "").upper(),
        "order_id": int(order_id),
        "action": getattr(order, "action", None),
        "quantity": getattr(order, "totalQuantity", None),
        "order_type": getattr(order, "orderType", None),
        "lmt_price": _safe_price_value(getattr(order, "lmtPrice", None)),
        "aux_price": _safe_price_value(getattr(order, "auxPrice", None)),
        "tif": getattr(order, "tif", None),
        "outside_rth": getattr(order, "outsideRth", None),
        "transmit": getattr(order, "transmit", None),
        "account": account,
        "exchange": getattr(resolved_contract, "exchange", None),
        "primary_exchange": getattr(resolved_contract, "primaryExchange", None),
        "routing_exchange": getattr(order, "exchange", None),
        "session_label": market_session,
        "runtime_mode": mode.value,
        "execution_path": execution_path,
        "quote_context": quote_context,
        "price_source": price_source,
        "bid": bid,
        "ask": ask,
        "last": last,
        "volume": volume,
        "spread_abs": spread_abs,
        "spread_pct": spread_pct,
        "timestamp": _now_utc_iso(),
        "market_session": market_session,
        "min_tick": min_tick,
    }
    print(
        "[EXECUTION][ORDER_WIRE_PAYLOAD] "
        + " ".join(
            f"{key}={_none_text(value)}"
            for key, value in wire_payload.items()
        )
    )
    print(
        "[EXECUTION][FILLABILITY] "
        f"symbol={wire_payload['symbol']} order_id={wire_payload['order_id']} "
        f"order_type={_none_text(wire_payload['order_type'])} action={_none_text(wire_payload['action'])} "
        f"lmt_price={_none_text(wire_payload['lmt_price'])} bid={_none_text(bid)} ask={_none_text(ask)} "
        f"classification={fillability} rationale={fillability_rationale}"
    )
    _SUBMIT_FILLABILITY_COUNTS[fillability] = int(_SUBMIT_FILLABILITY_COUNTS.get(fillability, 0)) + 1
    _upsert_order_from_submission(
        order_id=int(order_id),
        symbol=str(symbol or "").upper(),
        side=str(side or "").upper(),
        total_qty=int(quantity),
        order_ref=str(order_ref or ""),
        intent_id=str(intent_id or ""),
    )
    _register_order_intent_mapping(
        order_id=int(order_id),
        intent_id=str(intent_id or ""),
        order_ref=str(order_ref or ""),
    )
    print(
        f"[EXECUTION][ORDER_REGISTERED] order_id={int(order_id)} symbol={str(symbol or '').upper()} "
        f"intent_id={str(intent_id or '')} order_ref={str(order_ref or '')}"
    )
    tracked = _RUNTIME_ORDERS.get(int(order_id))
    if tracked is not None:
        tracked.order_wire_payload = dict(wire_payload)
        tracked.fillability_classification = str(fillability)
        tracked.fillability_rationale = str(fillability_rationale)
        tracked.market_session = str(market_session)
        tracked.min_tick = float(min_tick)
        tracked.initial_bid = bid
        tracked.initial_ask = ask
        tracked.initial_limit_price = _safe_price_value(getattr(order, "lmtPrice", None))
        tracked.last_limit_price = _safe_price_value(getattr(order, "lmtPrice", None))
        tracked.max_reprice_attempts = _watchdog_threshold_seconds("EXECUTION_MAX_REPRICE_ATTEMPTS", 3)
    _register_pending_submission(
        order_id=int(order_id),
        symbol=str(symbol or "").upper(),
        intent_id=str(intent_id or ""),
        order_ref=str(order_ref or ""),
    )
    print("[IBKR][ORDER_DISPATCH_VERIFICATION]")
    print(f"order_id={order_id} awaiting_acknowledgement")
    wait_for_order_status = getattr(client, "wait_for_order_status", None)
    if callable(wait_for_order_status):
        try:
            status = wait_for_order_status(order_id, timeout_seconds=5)
        except TypeError:
            status = wait_for_order_status(order_id, timeout=5)
        if status is None:
            print("[CRITICAL][NO_IBKR_ACK]")
            print("[CRITICAL][IBKR_NO_ACK]")
            print(f"order_id={order_id} no orderStatus within 5 seconds")
            if _strict_broker_truth_required(mode):
                raise RuntimeError("IBKR_ACKNOWLEDGEMENT_FAILED")
            print("[EXECUTION][ACK_SKIPPED_NON_LIVE]")
            print(f"mode={mode.value}")
    print(f"[IBKR][PLACE_ORDER][SENT] symbol={symbol} order_id={order_id}")
    return order_id


def execute_intents(
    mode: RunMode,
    decisions: List[RiskDecisionRecord],
) -> List[ExecutionEvent]:
    global _FILL_AUTHORITY_STATE, _EXECUTION_CYCLE_COUNTER, _CIRCUIT_BREAKER_ACTIVE
    _FILL_AUTHORITY_STATE = "UNKNOWN"
    if _is_explicit_test_mode():
        _CIRCUIT_BREAKER_ACTIVE = False
    events: List[ExecutionEvent] = []
    manager: Any | None = None
    _EXECUTION_CYCLE_COUNTER += 1
    cycle_id = f"CYCLE-{_EXECUTION_CYCLE_COUNTER}"
    intents_received = 0
    submit_attempts = 0
    submission_attempted_total = 0
    orders_submitted = 0
    acks_received = 0
    fills_received = 0
    positions_opened = 0
    blocked_no_quote = 0
    blocked_non_marketable = 0
    blocked_restricted = 0
    blocked_no_ibkr_price_authority = 0
    blocked_price_unavailable = 0
    blocked_pre_submit = 0

    for decision in decisions:
        raw_qty = float(getattr(decision, "approved_quantity", 0) or 0)
        if raw_qty <= 0:
            raise RuntimeError("INVALID ORDER: quantity=0")
        quantity = max(1, math.floor(raw_qty))
        if decision.decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"} and quantity <= 0:
            raise RuntimeError("INVALID ORDER: quantity=0")

    if mode in {RunMode.PAPER, RunMode.LIVE}:
        if _is_explicit_test_mode():
            print("[EXECUTION][TEST_MODE] Skipping IBKR connection validation")
        else:
            _validate_ibkr_connection(mode)
            manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
            client = manager.get_client()
            _update_ibkr_health(event_type="connect")
            callback = globals().get("_on_ibkr_callback")
            if callback is not None:
                if hasattr(client, "register_execution_callback"):
                    client.register_execution_callback(_on_ibkr_callback)
                    print("[EXECUTION][CALLBACK_REGISTERED] source=ibkr_client event_types=orderStatus,execDetails,commissionReport")
                else:
                    print("[EXECUTION][CALLBACK_UNAVAILABLE] register_execution_callback not supported by client")
                    _FILL_AUTHORITY_STATE = "DEGRADED"
                    print("[EXECUTION][FILL_AUTHORITY_DEGRADED] reason=execution_callback_unavailable")

    broker_state = "CONNECTED" if mode in {RunMode.PAPER, RunMode.LIVE} else "DISCONNECTED"
    print(f"[EXECUTION][MODE] mode={mode.value} broker_connection_state={broker_state}")
    open_orders, _executions, positions = _normalize_ibkr_truth(_fetch_ibkr_truth(mode))
    ownership_summary = classify_broker_inventory(open_orders=open_orders, positions=positions)
    has_working_order_recon = hasattr(open_orders, "__iter__")
    if mode in {RunMode.PAPER, RunMode.LIVE} and not has_working_order_recon:
        _FILL_AUTHORITY_STATE = "DEGRADED"
        print("[EXECUTION][FILL_AUTHORITY_DEGRADED] reason=broker_fill_reconciliation_unavailable")
    existing_position_qty_by_symbol: dict[str, float] = {}
    system_position_qty_by_symbol: dict[str, float] = {}
    external_position_qty_by_symbol: dict[str, float] = {}
    for row in positions:
        symbol = str(getattr(row, "symbol", "") or "").upper()
        if not symbol:
            continue
        qty = float(_extract_position_qty(row) or 0.0)
        existing_position_qty_by_symbol[symbol] = existing_position_qty_by_symbol.get(symbol, 0.0) + qty
        ownership = _POSITION_OWNERSHIP_BY_SYMBOL.get(symbol, OWNERSHIP_EXTERNAL)
        if ownership == OWNERSHIP_SYSTEM:
            system_position_qty_by_symbol[symbol] = system_position_qty_by_symbol.get(symbol, 0.0) + qty
        else:
            external_position_qty_by_symbol[symbol] = external_position_qty_by_symbol.get(symbol, 0.0) + qty
    working_order_candidates: list[dict[str, Any]] = []
    for row in open_orders:
        symbol = _extract_symbol_from_order(row)
        if not symbol:
            continue
        order = getattr(row, "order", None)
        side = str(getattr(order, "action", "") or "").upper()
        status = str(getattr(row, "status", "") or getattr(order, "status", "") or "").upper()
        order_id = getattr(row, "orderId", None)
        order_ref = _extract_order_ref(row)
        _namespace, _strategy, family = _parse_order_ref_components(order_ref)
        candidate = (
            {
                "symbol": symbol,
                "side": side,
                "family": str(family or ""),
                "order_id": int(order_id) if order_id is not None else None,
                "status": status or "UNKNOWN",
                "is_live_status": status in {"SUBMITTED", "ACKNOWLEDGED", "WORKING", "PRESUBMITTED"},
            }
        )
        if _is_isolated_trading_mode():
            candidate_order_id = int(order_id) if order_id is not None else -1
            if _OPEN_ORDER_OWNERSHIP_BY_ID.get(candidate_order_id, OWNERSHIP_EXTERNAL) != OWNERSHIP_SYSTEM:
                continue
        working_order_candidates.append(candidate)
    print(f"[EXECUTION][WORKING_ORDER_RECON] known_working_orders={len(working_order_candidates)}")
    print(
        "[RISK][SYSTEM_PORTFOLIO] "
        f"system_open_positions={ownership_summary.get('system_positions', 0)} "
        f"external_open_positions={ownership_summary.get('external_positions', 0)}"
    )

    submitted_order_ids: list[int] = []
    allow_pyramiding = _config_bool("ALLOW_PYRAMIDING", True)
    max_position_size = max(1, _config_int("MAX_POSITION_SIZE", 3))
    max_open_positions = max(1, _config_int("MAX_OPEN_POSITIONS", 5))
    for index, decision in enumerate(decisions, start=1):
        intents_received += 1
        execution_attempted = False
        execution_context: dict[str, Any] = {}
        blocked_reason: str | None = None
        account = RouterAccountSnapshot(available_funds=float(decision.available_funds))
        order_value = float(decision.order_value)
        risk_allowed = bool(decision.risk_allowed)
        print(
            f"[CAPITAL] available_funds={account.available_funds} "
            f"order_value={order_value} "
            f"risk_allowed={risk_allowed}"
        )
        raw_qty = float(getattr(decision, "approved_quantity", 0) or 0)
        if raw_qty <= 0:
            raise RuntimeError("INVALID ORDER: quantity=0")
        quantity = max(1, math.floor(raw_qty))
        initial_entry_price = getattr(decision, "entry_price", None)
        trace = ExecutionTrace(
            symbol=str(decision.symbol or "").upper(),
            cycle_id=cycle_id,
            intent_id=str(decision.intent_id or ""),
            strategy_name=str(getattr(decision, "strategy_name", "") or ""),
            entry_price_requested=float(initial_entry_price or 0.0),
            resolved_price=float(initial_entry_price or 0.0),
            price_state="FULL" if initial_entry_price else "WAITING_FOR_PRICE",
        )
        if trace.intent_id:
            _EXECUTION_TRACE_BY_INTENT[trace.intent_id] = trace
        order_side = "BUY" if str(getattr(decision, "side", "LONG") or "LONG").upper() == "LONG" else "SELL"
        is_exit_order = str(getattr(decision, "action", "") or "").upper() == "EXIT" or order_side == "SELL"
        truth = _create_execution_truth(
            order_ref=_build_order_ref(str(decision.intent_id or "")),
            broker_order_id=None,
            symbol=str(decision.symbol or "").upper(),
            intent_id=str(decision.intent_id or ""),
            side=order_side,
            submitted_qty=quantity,
        )
        _trace_log("INTENT_RECEIVED", trace, extra=f"cycle_id={cycle_id}")
        duplicate_symbol = str(decision.symbol or "").upper()
        order_family = str(decision.intent_id or "")
        print(
            f"[EXECUTION][DUPLICATE_CHECK] symbol={duplicate_symbol} side={order_side} intent_id={order_family} "
            f"candidate_count={len(working_order_candidates)}"
        )
        if is_exit_order:
            print(f"[EXECUTION][EXIT_FORCE_ALLOW] symbol={duplicate_symbol} reason=EXIT_BYPASS_ROUTER_GATES")
        working_duplicate = False
        duplicate_reason = ""
        duplicate_order_id = None
        duplicate_status = ""
        for candidate in working_order_candidates:
            if candidate["symbol"] != duplicate_symbol:
                continue
            if not bool(candidate["is_live_status"]):
                print(
                    f"[EXECUTION][DUPLICATE_IGNORE_STALE] symbol={duplicate_symbol} existing_order_id={candidate['order_id']} "
                    f"existing_status={candidate['status']} reason=non_live_status"
                )
                continue
            if candidate["family"] and candidate["family"] != order_family:
                print(
                    f"[EXECUTION][DUPLICATE_IGNORE_STALE] symbol={duplicate_symbol} existing_order_id={candidate['order_id']} "
                    f"existing_status={candidate['status']} reason=intent_mismatch existing_family={candidate['family']} intent_id={order_family}"
                )
                continue
            working_duplicate = True
            duplicate_order_id = candidate["order_id"]
            duplicate_status = candidate["status"]
            duplicate_reason = "live_symbol_side_intent_conflict"
            print(
                f"[EXECUTION][DUPLICATE_MATCH] symbol={duplicate_symbol} existing_order_id={duplicate_order_id} "
                f"existing_status={duplicate_status} reason={duplicate_reason}"
            )
            break
        if working_duplicate and not is_exit_order:
            blocked_reason = "DUPLICATE_WORKING_ORDER"
            blocked_pre_submit += 1
            print(
                f"[EXECUTION][DUPLICATE_WORKING_ORDER] symbol={duplicate_symbol} reason={blocked_reason} "
                f"existing_order_id={duplicate_order_id} existing_broker_state={duplicate_status} conflict_reason={duplicate_reason}"
            )
            print(
                f"[EXECUTION][DUPLICATE_BLOCK] symbol={duplicate_symbol} reason={blocked_reason} "
                f"existing_order_id={duplicate_order_id} existing_broker_state={duplicate_status} conflict_reason={duplicate_reason}"
            )
            print(f"[EXECUTION][HARD_BLOCK] symbol={duplicate_symbol} reason=DUPLICATE_WORKING_ORDER")
            print(f"[EXECUTION][BLOCK] symbol={duplicate_symbol} reason={blocked_reason}")
            _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
            truth.rejection_reason = blocked_reason
            _mark_execution_failure(trace, "EXECUTION_SKIPPED_DUPLICATE", reason="duplicate_working_order")
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail=f"reason={blocked_reason}; event=EXECUTION_SKIPPED_DUPLICATE",
                    event_type="EXECUTION_SKIPPED_DUPLICATE",
                    broker_status="REJECTED",
                    last_update_time=_now_utc_iso(),
                )
            )
            continue
        system_qty = float(system_position_qty_by_symbol.get(duplicate_symbol, 0.0) or 0.0)
        external_qty = float(external_position_qty_by_symbol.get(duplicate_symbol, 0.0) or 0.0)
        effective_position_qty = system_qty
        has_intent_mismatch_override = any(
            str(existing.symbol or "").upper() == duplicate_symbol
            and int(existing.filled_qty or 0) > 0
            and str(existing.intent_id or "").strip()
            and str(existing.intent_id or "").strip() != order_family
            for existing in _RUNTIME_ORDERS.values()
        )
        treated_as_flat = effective_position_qty <= 0
        position_source = "IBKR_EXTERNAL"
        print(
            f"[EXECUTION][POSITION_SCOPE] symbol={duplicate_symbol} system_qty={system_qty} external_qty={external_qty} "
            f"effective_system_qty={effective_position_qty}"
        )
        print(
            f"[EXECUTION][POSITION_CHECK] symbol={duplicate_symbol} local_qty={system_qty} broker_qty={external_qty} "
            f"effective_qty={effective_position_qty} source={position_source} treated_as_flat={str(treated_as_flat).lower()} "
            f"intent_mismatch_override={str(has_intent_mismatch_override).lower()}"
        )
        if (
            _is_isolated_trading_mode()
            and (not is_exit_order)
            and order_side == "BUY"
            and system_qty <= 0
            and external_qty > 0
        ):
            blocked_reason = "EXTERNAL_POSITION_PRESENT"
            blocked_pre_submit += 1
            print(f"[EXECUTION][SYMBOL_OWNERSHIP_BLOCK] symbol={duplicate_symbol} reason=EXTERNAL_POSITION_PRESENT")
            print(f"[EXECUTION][BLOCK] symbol={duplicate_symbol} reason={blocked_reason}")
            _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
            truth.rejection_reason = blocked_reason
            _mark_execution_failure(trace, "ORDER_REJECTED", reason="external_position_present")
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail=f"reason={blocked_reason}",
                    event_type="ORDER_REJECTED",
                    broker_status="REJECTED",
                    last_update_time=_now_utc_iso(),
                )
            )
            continue
        if (
            _is_isolated_trading_mode()
            and is_exit_order
            and system_qty <= 0
            and external_qty > 0
        ):
            blocked_reason = "EXTERNAL_POSITION_PRESENT"
            blocked_pre_submit += 1
            print(f"[EXECUTION][SYMBOL_OWNERSHIP_BLOCK] symbol={duplicate_symbol} reason=EXTERNAL_POSITION_PRESENT")
            print(f"[EXECUTION][BLOCK] symbol={duplicate_symbol} reason={blocked_reason}")
            _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
            truth.rejection_reason = blocked_reason
            _mark_execution_failure(trace, "ORDER_REJECTED", reason="external_only_exit_blocked")
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail=f"reason={blocked_reason}",
                    event_type="ORDER_REJECTED",
                    broker_status="REJECTED",
                    last_update_time=_now_utc_iso(),
                )
            )
            continue
        current_open_positions = sum(1 for qty in system_position_qty_by_symbol.values() if float(qty or 0.0) > 0.0)
        if (not is_exit_order) and order_side == "BUY" and treated_as_flat and current_open_positions >= max_open_positions:
            blocked_reason = "MAX_OPEN_POSITIONS"
            blocked_pre_submit += 1
            print(f"[RISK][POSITION_LIMIT] symbol={duplicate_symbol} open_positions={current_open_positions} max_open_positions={max_open_positions}")
            print(f"[EXECUTION][BLOCK] symbol={duplicate_symbol} reason={blocked_reason}")
            _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
            truth.rejection_reason = blocked_reason
            _mark_execution_failure(trace, "ORDER_REJECTED", reason="max_open_positions")
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail=f"reason={blocked_reason}",
                    event_type="ORDER_REJECTED",
                    broker_status="REJECTED",
                    last_update_time=_now_utc_iso(),
                )
            )
            continue
        if (not is_exit_order) and order_side == "BUY" and not treated_as_flat and not has_intent_mismatch_override:
            proposed_qty = effective_position_qty + float(quantity)
            if not allow_pyramiding:
                blocked_reason = "DUPLICATE_POSITION"
                blocked_pre_submit += 1
                print(f"[EXECUTION][PYRAMID] symbol={duplicate_symbol} existing_qty={effective_position_qty:.4f} new_qty={quantity} decision=BLOCK reason=DUPLICATE_POSITION")
                print(f"[EXECUTION][HARD_BLOCK] symbol={duplicate_symbol} reason=DUPLICATE_POSITION")
                print(f"[EXECUTION][BLOCK] symbol={duplicate_symbol} reason={blocked_reason}")
                _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
                truth.rejection_reason = blocked_reason
                _mark_execution_failure(trace, "ORDER_REJECTED", reason="duplicate_position")
                events.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail=f"reason={blocked_reason}",
                        event_type="ORDER_REJECTED",
                        broker_status="REJECTED",
                        last_update_time=_now_utc_iso(),
                    )
                )
                continue
            if proposed_qty > float(max_position_size):
                blocked_reason = "MAX_SIZE_REACHED"
                blocked_pre_submit += 1
                print(
                    f"[EXECUTION][PYRAMID] symbol={duplicate_symbol} existing_qty={effective_position_qty:.4f} "
                    f"new_qty={quantity} decision=BLOCK reason={blocked_reason} max_position_size={max_position_size}"
                )
                print(f"[EXECUTION][BLOCK] symbol={duplicate_symbol} reason={blocked_reason}")
                _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
                truth.rejection_reason = blocked_reason
                _mark_execution_failure(trace, "ORDER_REJECTED", reason="max_size_reached")
                events.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail=f"reason={blocked_reason}",
                        event_type="ORDER_REJECTED",
                        broker_status="REJECTED",
                        last_update_time=_now_utc_iso(),
                    )
                )
                continue
            print(
                f"[EXECUTION][PYRAMID] symbol={duplicate_symbol} existing_qty={effective_position_qty:.4f} "
                f"new_qty={quantity} decision=ALLOW reason=PYRAMID_ADD"
            )
        if not str(decision.intent_id or "").strip():
            blocked_reason = "INVALID_ORDER_CONFIG"
            blocked_pre_submit += 1
            print(f"[EXECUTION][BLOCK] symbol={decision.symbol} reason={blocked_reason}")
            _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
            _mark_execution_failure(trace, "ORDER_REJECTED", reason="missing_order_ref_component")
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail=f"reason={blocked_reason}",
                    broker_status="REJECTED",
                    last_update_time=_now_utc_iso(),
                )
            )
            continue
        entry_price = getattr(decision, "entry_price", None)
        if decision.decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}:
            _trace_log("PRECHECK", trace, extra=f"decision={decision.decision} qty={quantity}")
            if entry_price is None or float(entry_price) <= 0:
                trace.price_state = "WAITING_FOR_PRICE"
                print(f"[EXECUTION][WAIT] symbol={decision.symbol} reason=WAITING_FOR_PRICE")
                snapshot = _wait_for_ibkr_snapshot_for_symbol(str(decision.symbol or ""))
                try:
                    entry_price, _entry_price_source = resolve_entry_price(
                        str(decision.symbol or ""),
                        {
                            "ibkr_stream_by_symbol": {str(decision.symbol or "").upper(): snapshot} if snapshot else {},
                        },
                    )
                    decision.entry_price = entry_price
                    setattr(decision, "entry_price_source", "IBKR_STREAM")
                    trace.resolved_price = float(entry_price)
                    trace.price_state = "PARTIAL_OK"
                    print(f"[PRICE][RESOLVED] symbol={decision.symbol} source=IBKR_STREAM price={entry_price}")
                    # Persist resolved price for execution fallback
                    if entry_price is not None and entry_price > 0:
                        execution_context["resolved_last_price"] = entry_price
                except PriceResolutionError:
                    blocked_price_unavailable += 1
                    blocked_reason = "NO_IBKR_PRICE"
                    blocked_pre_submit += 1
                    print(f"[PRICE][BLOCK] symbol={decision.symbol} reason={blocked_reason}")
                    print(f"[EXECUTION][BLOCK] symbol={decision.symbol} reason=PRICE_AUTHORITY_INVALID")
                    _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
                    _mark_execution_failure(trace, "PRICE_UNAVAILABLE", reason="waiting_for_price")
                    events.append(
                        ExecutionEvent(
                            symbol=decision.symbol,
                            intent_id=decision.intent_id,
                            action="DEFERRED",
                            detail="reason=WAITING_FOR_PRICE",
                            broker_status="PENDING_PRICE",
                            event_type="ORDER_PENDING",
                            last_update_time=_now_utc_iso(),
                        )
                    )
                    continue
        dispatch = "SKIPPED"
        if mode in {RunMode.SIM, RunMode.READ_ONLY}:
            action = "WOULD_PLACE"
            detail = f"mode={mode.value}; decision={decision.decision}; qty={quantity}"
            dispatch = "SKIPPED"
        elif decision.decision == "ALLOW":
            if (not is_exit_order) and quantity != int(decision.max_position_size):
                action = "BLOCKED"
                detail = (
                    "reason=EXECUTION_QUANTITY_MISMATCH "
                    f"approved={decision.approved_quantity} max_size={decision.max_position_size}"
                )
                dispatch = "SKIPPED"
                print(f"[EXECUTION][BLOCK] symbol={decision.symbol} reason=EXECUTION_QUANTITY_MISMATCH")
                _mark_execution_failure(trace, "ORDER_REJECTED", reason="quantity_mismatch")
                events.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail=detail,
                        broker_status="REJECTED",
                    )
                )
                continue
            else:
                action = "SUBMITTED"
                detail = f"submitted qty={quantity} orderRef=TRADING_OS|ROSS_MOMENTUM|{decision.intent_id}"
                dispatch = "IBKR"
        elif decision.decision == "ALLOW_WITH_CONSTRAINTS":
            action = "BLOCKED" if mode == RunMode.LIVE else "WOULD_PLACE"
            detail = f"constraints={decision.constraints}; qty={quantity}"
            dispatch = "SKIPPED" if mode == RunMode.LIVE else "IBKR"
        else:
            action = "BLOCKED"
            detail = f"decision={decision.decision}; reason={decision.block_reason or 'RISK_BLOCK'}"
            dispatch = "SKIPPED"
        print(f"[EXECUTION][DISPATCH] symbol={decision.symbol} dispatch={dispatch}")
        broker_order_id = None
        if action == "SUBMITTED":
            if (not _is_explicit_test_mode()) and mode in {RunMode.PAPER, RunMode.LIVE} and (
                not bool(_IBKR_HEALTH_STATE.get("broker_connected")) or bool(_IBKR_HEALTH_STATE.get("degraded"))
            ):
                blocked_reason = "IBKR_HEALTH_UNSTABLE" if _IBKR_HEALTH_STATE.get("degraded") else "BROKER_NOT_CONNECTED"
                blocked_pre_submit += 1
                print(f"[EXECUTION][BLOCK] symbol={decision.symbol} reason={blocked_reason}")
                _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
                events.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail=f"reason={blocked_reason}",
                        broker_status="REJECTED",
                        last_update_time=_now_utc_iso(),
                    )
                )
                continue
            if not _ensure_submission_allowed(mode, symbol=str(decision.symbol or "").upper()):
                blocked_reason = "EXECUTION_DISABLED"
                blocked_pre_submit += 1
                _transition_execution_truth_state(truth=truth, next_state="BLOCKED", source="LOCAL")
                events.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail=f"reason={blocked_reason}",
                        broker_status="REJECTED",
                        last_update_time=_now_utc_iso(),
                    )
                )
                continue
            submit_attempts += 1
            execution_attempted = True
            submission_attempted_total += 1
            _transition_execution_truth_state(truth=truth, next_state="SUBMITTING", source="LOCAL")
            print(f"[EXECUTION][SUBMIT_ATTEMPT] symbol={decision.symbol} intent_id={decision.intent_id} mode={mode.value} qty={quantity}")
            try:
                order_ref = _build_order_ref(str(decision.intent_id or ""))
                if mode in {RunMode.PAPER, RunMode.LIVE} and not _is_explicit_test_mode():
                    if manager is None:
                        manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
                    payload = {
                        "symbol": str(decision.symbol or "").upper(),
                        "side": order_side,
                        "quantity": quantity,
                        "order_ref": order_ref,
                    }
                    print("[TRACE][CALLER_INPUT]")
                    print(f"type_of_payload={type(payload)}")
                    print(f"repr={repr(payload)}")
                    broker_order_id = _submit_ibkr_order(
                        mode=mode,
                        client=manager.get_client(),
                        symbol=payload["symbol"],
                        side=payload["side"],
                        quantity=payload["quantity"],
                        order_ref=payload["order_ref"],
                        intent_id=str(decision.intent_id or ""),
                        entry_price=_safe_price_value(getattr(decision, "entry_price", None)),
                        entry_price_source=str(getattr(decision, "entry_price_source", "") or ""),
                        float_millions=_safe_price_value(getattr(decision, "float_millions", None)),
                        execution_context=execution_context,
                        is_exit_order=is_exit_order,
                    )
                else:
                    broker_order_id = index
                    _register_pending_submission(
                        order_id=int(broker_order_id),
                        symbol=str(decision.symbol or "").upper(),
                        intent_id=str(decision.intent_id or ""),
                        order_ref=str(order_ref or ""),
                    )
            except Exception as exc:
                error_text = str(exc or "")
                if "NO_QUOTE_CONTEXT" in error_text:
                    blocked_no_quote += 1
                    failure_type = "NO_QUOTE_CONTEXT"
                elif "NON_MARKETABLE_ORDER" in error_text:
                    blocked_non_marketable += 1
                    failure_type = "IBKR_REJECT"
                elif "LIKELY_IBKR_RESTRICTED" in error_text:
                    blocked_restricted += 1
                    failure_type = "IBKR_REJECT"
                elif "NO_IBKR_PRICE_AUTHORITY" in error_text:
                    blocked_no_ibkr_price_authority += 1
                    failure_type = "IBKR_REJECT"
                elif "CONTRACT_NOT_QUALIFIED" in error_text:
                    failure_type = "CONTRACT_RESOLUTION_FAIL"
                elif "ACKNOWLEDGEMENT_FAILED" in error_text:
                    failure_type = "CALLBACK_TIMEOUT"
                else:
                    failure_type = "IBKR_REJECT"
                _mark_execution_failure(trace, failure_type, reason=str(exc))
                events.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail=f"reason=SUBMISSION_FAILED:{exc}",
                        broker_status="REJECTED",
                        last_update_time=_now_utc_iso(),
                    )
                )
                continue
            truth.broker_order_id = int(broker_order_id)
            _EXECUTION_TRUTH_BY_ORDER_ID[int(broker_order_id)] = truth
            _transition_execution_truth_state(truth=truth, next_state="SUBMITTED", source="LOCAL")
            submitted_order_ids.append(int(broker_order_id))
            print(f"[EXECUTION][SUBMITTED] symbol={decision.symbol} broker_order_id={broker_order_id} local_dispatch_attempted=true place_order_issued=true")
            if str(getattr(decision, "action", "") or "").upper() == "EXIT" or order_side == "SELL":
                print(
                    f"[EXECUTION][EXIT_ORDER_SUBMITTED] symbol={decision.symbol} broker_order_id={broker_order_id} "
                    f"qty={quantity} intent_id={decision.intent_id}"
                )
            print(
                "[EXECUTION][SUBMIT] "
                f"symbol={decision.symbol} intent_id={decision.intent_id} order_id={broker_order_id} "
                f"order_ref={order_ref} qty={quantity}"
            )
            orders_submitted += 1
            trace.order_submitted = True
            trace.order_id = int(broker_order_id)
            trace.submit_time = _now_utc_iso()
            trace.lifecycle_state = "SUBMITTED"
            _EXECUTION_TRACE_BY_ORDER_ID[int(broker_order_id)] = trace
            trace_id = _build_trace_id(intent_id=str(decision.intent_id or ""), broker_order_id=int(broker_order_id), cycle_id=cycle_id)
            print(f"[EXECUTION][TRACE_ID] symbol={decision.symbol} trace_id={trace_id} intent_id={decision.intent_id} broker_order_id={broker_order_id}")
            _trace_log("SUBMITTED", trace, extra=f"qty={quantity}")
            _initialize_visibility(int(broker_order_id))
            _upsert_order_from_submission(
                order_id=broker_order_id,
                symbol=str(decision.symbol or "").upper(),
                side=order_side,
                total_qty=quantity,
                order_ref=order_ref,
                intent_id=str(decision.intent_id or ""),
            )
            tracked = _RUNTIME_ORDERS.get(int(broker_order_id))
            if tracked is not None and not tracked.order_wire_payload:
                fallback_wire_payload = {
                    "symbol": str(decision.symbol or "").upper(),
                    "order_id": int(broker_order_id),
                    "action": order_side,
                    "quantity": quantity,
                    "order_type": "MKT",
                    "lmt_price": None,
                    "aux_price": None,
                    "tif": "DAY",
                    "outside_rth": True,
                    "transmit": None,
                    "account": None,
                    "exchange": None,
                    "primary_exchange": None,
                    "routing_exchange": None,
                    "session_label": _canonical_execution_session(_session_label_now()),
                    "runtime_mode": mode.value,
                    "bid": None,
                    "ask": None,
                    "last": None,
                    "spread_abs": None,
                    "spread_pct": None,
                    "timestamp": _now_utc_iso(),
                }
                tracked.order_wire_payload = fallback_wire_payload
                tracked.fillability_classification = "NO_QUOTE_CONTEXT"
                tracked.fillability_rationale = "submission path without quote snapshot context"
            _register_order_intent_mapping(
                order_id=int(broker_order_id),
                intent_id=str(decision.intent_id or ""),
                order_ref=order_ref,
            )
            _PENDING_SUBMISSIONS_BY_ORDER_ID.pop(int(broker_order_id), None)
        if mode in {RunMode.PAPER, RunMode.LIVE} and decision.decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"} and not execution_attempted and action != "BLOCKED":
            raise ExecutionInvariantViolation(
                f"intent_received_without_submission_attempt symbol={decision.symbol} intent_id={decision.intent_id}"
            )
        events.append(
            ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action=action,
                detail=detail,
                broker_order_id=broker_order_id,
                event_type="ORDER_WORKING" if action == "SUBMITTED" else action,
                broker_status="Submitted" if action == "SUBMITTED" else ("REJECTED" if action == "BLOCKED" else "SIMULATED"),
                source="IBKR" if action == "SUBMITTED" else "ENGINE",
                filled_quantity=0,
                remaining_quantity=quantity if action == "SUBMITTED" else 0,
                last_update_time=_now_utc_iso(),
            )
        )
    events, _ = _apply_callback_fills(events)
    for event in events:
        if event.broker_order_id is None:
            continue
        trace = _EXECUTION_TRACE_BY_ORDER_ID.get(int(event.broker_order_id))
        if trace is None:
            continue
        if event.filled_quantity > 0:
            trace.fill_received = True
            trace.fill_qty = int(event.filled_quantity)
            trace.fill_price = event.avg_fill_price
            trace.lifecycle_state = "FILL_RECEIVED"
            fills_received += 1
            _trace_log("FILL", trace, extra=f"fill_qty={event.filled_quantity} fill_price={event.avg_fill_price}")
        if trace.ack_received:
            acks_received += 1
            print(f"[EXECUTION][BROKER_ACK] symbol={trace.symbol} intent_id={trace.intent_id} order_id={trace.order_id}")
    events = _sync_submitted_events_from_ibkr(mode, events)
    _post_submission_ibkr_diagnostics(mode=mode, manager=manager, submitted_order_ids=submitted_order_ids)
    open_order_seen_total = sum(
        1
        for order_id in submitted_order_ids
        if bool(_VISIBILITY_BY_ORDER_ID.get(int(order_id), {}).get("openOrder_seen"))
    )
    order_status_seen_total = sum(
        1
        for order_id in submitted_order_ids
        if bool(_VISIBILITY_BY_ORDER_ID.get(int(order_id), {}).get("orderStatus_seen"))
    )
    print(
        "[EXECUTION][CALLBACK_VERDICT] "
        f"mode={mode.value} open_order_seen_total={open_order_seen_total} "
        f"order_status_seen_total={order_status_seen_total} orders_submitted={orders_submitted}"
    )
    print(
        "[EXECUTION][TRUTH_SUMMARY] "
        f"mode={mode.value} orders_submitted={orders_submitted} "
        f"open_order_seen_total={open_order_seen_total} order_status_seen_total={order_status_seen_total}"
    )
    if orders_submitted > 0 and open_order_seen_total == 0 and order_status_seen_total == 0:
        if _strict_broker_truth_required(mode):
            raise RuntimeError("BROKER_TRUTH_NOT_CONFIRMED")
        print("[EXECUTION][BROKER_TRUTH_SKIPPED]")
        print(f"mode={mode.value}")
    for trace in _EXECUTION_TRACE_BY_INTENT.values():
        if trace.cycle_id != cycle_id:
            continue
        ibkr_pos = _IBKR_POSITIONS_BY_SYMBOL.get(trace.symbol)
        if ibkr_pos is not None and int(ibkr_pos.quantity) > 0:
            trace.position_opened = True
            trace.lifecycle_state = "POSITION_CONFIRMED"
            positions_opened += 1
        if trace.order_submitted and not trace.ack_received:
            _mark_execution_failure(trace, "NO_ACK", reason="order_submitted_without_ack")
        if trace.ack_received and not trace.fill_received:
            tracked = _RUNTIME_ORDERS.get(int(trace.order_id)) if trace.order_id is not None else None
            authoritative_state = _resolve_authoritative_execution_state(tracked)
            if authoritative_state in {"BROKER_REJECTED", "BROKER_CANCELLED", "BROKER_EXPIRED", "BROKER_INACTIVE_UNKNOWN"}:
                _mark_execution_failure(trace, "NO_FILL", reason=f"terminal_no_fill state={authoritative_state}")
        if trace.fill_received and not trace.position_opened:
            timeout_seconds = int(os.environ.get("EXECUTION_POSITION_CONFIRMATION_TIMEOUT_SECONDS", "30") or "30")
            fill_seen_at = _parse_iso_utc(trace.fill_time)
            if fill_seen_at is not None and (datetime.now(timezone.utc) - fill_seen_at).total_seconds() > timeout_seconds:
                _mark_execution_failure(trace, "PARTIAL_FILL_STALLED", reason="position_confirmation_timeout")
            else:
                _trace_log("PENDING_POSITION_CONFIRMATION", trace, extra="awaiting_ibkr_position_callback=true")
        if trace.lifecycle_state not in {"FAIL", "POSITION_CONFIRMED"}:
            trace.lifecycle_state = "COMPLETE"
            _trace_log("COMPLETE", trace, extra=f"state={trace.lifecycle_state}")
    truth_terminal_counts: dict[str, int] = {}
    for order_id in submitted_order_ids:
        tracked = _RUNTIME_ORDERS.get(int(order_id))
        final_state = _resolve_authoritative_execution_state(tracked)
        if tracked is not None:
            tracked.final_execution_state = final_state
        truth_terminal_counts[final_state] = int(truth_terminal_counts.get(final_state, 0)) + 1
        print(
            "[EXECUTION][TRUTH_ROW] "
            f"symbol={(tracked.symbol if tracked is not None else 'UNKNOWN')} order_id={int(order_id)} "
            f"dispatch={'yes' if tracked is not None else 'no'} ack={'yes' if tracked and tracked.ack_seen else 'no'} "
            f"working={'yes' if tracked and tracked.working_seen else 'no'} queued_for_rth={'yes' if tracked and tracked.queued_for_rth_seen else 'no'} "
            f"rejected={'yes' if tracked and tracked.reject_seen else 'no'} filled={'yes' if tracked and tracked.fill_seen else 'no'} "
            f"terminal_state={final_state} broker_status={(tracked.broker_status if tracked is not None else 'UNKNOWN')} "
            f"broker_error_code={','.join(str(v) for v in (tracked.broker_error_codes if tracked is not None else [])) or 'NONE'} "
            f"normalized_reject_reason={(tracked.normalized_reject_reason if tracked is not None else '') or 'NONE'} "
            f"fillability={(tracked.fillability_classification if tracked is not None else 'NONE')} "
            f"inactive_normalized_reason={(tracked.inactive_normalized_reason if tracked is not None else '') or 'NONE'}"
        )
    print(f"[EXECUTION][TRUTH_SUMMARY] total={len(submitted_order_ids)} states={dict(sorted(truth_terminal_counts.items()))}")

    for event in events:
        if event.broker_order_id is None:
            continue
        tracked = _RUNTIME_ORDERS.get(int(event.broker_order_id))
        if tracked is None:
            continue
        final_state = _resolve_authoritative_execution_state(tracked)
        preserve_initial_submission = event.event_type == "ORDER_SUBMITTED"
        # Normalize ORDER_SUBMITTED → broker truth compliant state
        if event.event_type == "ORDER_SUBMITTED":
            if tracked is not None:
                broker_status = str(tracked.broker_status or "").lower()

                if broker_status in {"submitted", "presubmitted"}:
                    event.event_type = "ORDER_ACKNOWLEDGED"
                else:
                    event.event_type = "ORDER_WORKING"
            else:
                event.event_type = "ORDER_WORKING"
        tracked.final_execution_state = final_state
        if final_state == "BROKER_REJECTED":
            event.event_type = "ORDER_REJECTED"
            event.broker_status = "Rejected"
            event.action = "BLOCKED"
        elif final_state == "BROKER_FILLED_FULL":
            event.event_type = "ORDER_FILLED"
            event.broker_status = "Filled"
        elif final_state == "BROKER_FILLED_PARTIAL":
            event.event_type = "ORDER_PARTIALLY_FILLED"
            event.broker_status = "Submitted"
        elif final_state == "BROKER_QUEUED_FOR_RTH":
            event.event_type = "ORDER_WORKING"
            event.broker_status = "PreSubmitted"
        elif final_state == "BROKER_WORKING" and not preserve_initial_submission:
            event.event_type = "ORDER_WORKING"
        total_quantity = int(event.filled_quantity or 0) + int(event.remaining_quantity or 0)
        if int(event.filled_quantity or 0) >= total_quantity and total_quantity > 0:
            event.event_type = "ORDER_FILLED"
            event.broker_status = "Filled"
        elif int(event.filled_quantity or 0) > 0:
            event.event_type = "ORDER_PARTIALLY_FILLED"
            if str(event.broker_status or "").strip() == "":
                event.broker_status = "Submitted"
        event.detail = (
            f"{event.detail}; final_execution_state={final_state}; "
            f"normalized_reject_reason={(tracked.normalized_reject_reason or 'NONE')}; "
            f"broker_error_codes={','.join(str(v) for v in tracked.broker_error_codes) or 'NONE'}"
        )
    print(
        "[EXECUTION][CALLBACK_HEALTH] "
        f"open_order_callbacks_received={sum(1 for v in _VISIBILITY_BY_ORDER_ID.values() if v.get('openOrder_seen'))} "
        f"order_status_callbacks_received={sum(1 for v in _VISIBILITY_BY_ORDER_ID.values() if v.get('orderStatus_seen'))} "
        f"exec_details_callbacks_received={sum(1 for v in _VISIBILITY_BY_ORDER_ID.values() if v.get('execDetails_seen'))} "
        f"unresolved_order_callbacks={_UNRESOLVED_EXECUTION_RECONCILIATION_COUNT} "
        f"unresolved_non_order_callbacks={_NON_ORDER_UNMATCHED_CALLBACK_COUNT} "
        f"broker_truth_confirmations={_BROKER_TRUTH_CONFIRMATIONS} "
        f"broker_truth_fatals={_BROKER_TRUTH_FATALS} "
        f"contract_validation_failures={_CONTRACT_VALIDATION_FAILURES} "
        f"next_valid_id_resets_or_rebases={_NEXT_VALID_ID_REBASES}"
    )
    print(
        "[EXECUTION][SUMMARY] "
        f"cycle_id={cycle_id} intents_received={intents_received} submit_attempts={submit_attempts} "
        f"submission_attempted={submission_attempted_total} "
        f"orders_submitted={orders_submitted} acks_received={acks_received} fills_received={fills_received} "
        f"filled_orders={sum(1 for row in _RUNTIME_ORDERS.values() if int(row.filled_qty) > 0)} "
        f"open_positions={sum(1 for row in _IBKR_POSITIONS_BY_SYMBOL.values() if int(row.quantity) > 0)} "
        f"positions_opened={_IBKR_POSITION_EVENTS_COUNT} failures_by_type={dict(sorted(_EXECUTION_FAILURES_BY_TYPE.items()))}"
    )
    working_count = sum(1 for row in _RUNTIME_ORDERS.values() if row.canonical_state == "WORKING")
    partial_fill_count = sum(1 for row in _RUNTIME_ORDERS.values() if row.canonical_state == "PARTIALLY_FILLED")
    fill_count = sum(1 for row in _RUNTIME_ORDERS.values() if row.canonical_state == "FILLED")
    acknowledged_count = sum(1 for row in _RUNTIME_ORDERS.values() if row.ack_seen)
    orphan_intents = max(0, intents_received - blocked_pre_submit - submission_attempted_total)
    health_status = "DEGRADED" if bool(_IBKR_HEALTH_STATE.get("degraded")) else "STABLE"
    print(
        "[EXECUTION][RECONCILIATION_SUMMARY] "
        f"submitted_orders={orders_submitted} acknowledged_orders={acknowledged_count} "
        f"filled_orders={fill_count} unmatched_callbacks={_UNMATCHED_CALLBACK_COUNT} orphan_intents={orphan_intents} "
        f"intents_received={intents_received} execution_attempts={submit_attempts} submitted={orders_submitted} "
        f"acknowledged={acknowledged_count} working={working_count} partial_fills={partial_fill_count} fills={fill_count} "
        f"open_positions_confirmed={_OPEN_POSITIONS_CONFIRMED} reduced_positions_confirmed={_REDUCED_POSITIONS_CONFIRMED} "
        f"closed_positions_confirmed={_CLOSED_POSITIONS_CONFIRMED} "
        f"order_reconciliation_mismatches={_RECONCILIATION_FAILURES} position_reconciliation_mismatches={_RECONCILED_POSITIONS_MISMATCH} "
        f"watchdog_stalls_total={_WATCHDOG_STALLS_TOTAL} ibkr_health_status={health_status} fill_authority_state={fill_authority_state()}"
    )
    submitted_marketable = int(_SUBMIT_FILLABILITY_COUNTS.get("CROSSING_ASK_AGGRESSIVE", 0)) + int(
        _SUBMIT_FILLABILITY_COUNTS.get("CROSSING_BID_AGGRESSIVE", 0)
    )
    print(
        "[EXECUTION][EXECUTABILITY_SUMMARY] "
        f"total_intents={intents_received} blocked_no_quote={blocked_no_quote} "
        f"blocked_non_marketable={blocked_non_marketable} blocked_restricted={blocked_restricted} "
        f"blocked_no_ibkr_price_authority={blocked_no_ibkr_price_authority} "
        f"blocked_price_unavailable={blocked_price_unavailable} "
        f"submitted_marketable={submitted_marketable} submitted_total={orders_submitted}"
    )
    _FILL_AUTHORITY_STATE = _classify_fill_authority_state(
        intents_received=intents_received,
        submit_attempts=submit_attempts,
        orders_submitted=orders_submitted,
        acks_received=acks_received,
        fills_received=fills_received,
        blocked_pre_submit=blocked_pre_submit,
    )
    for e in events:
        if e.event_type == "ORDER_SUBMITTED":
            if str(e.action or "").upper() == "BLOCKED":
                e.event_type = "ORDER_REJECTED"
            elif int(e.filled_quantity or 0) > 0:
                total_quantity = int(e.filled_quantity or 0) + int(e.remaining_quantity or 0)
                e.event_type = "ORDER_FILLED" if total_quantity > 0 and int(e.filled_quantity or 0) >= total_quantity else "ORDER_PARTIALLY_FILLED"
            elif str(e.action or "").upper() == "SUBMITTED":
                e.event_type = "ORDER_ACKNOWLEDGED"
            else:
                e.event_type = "ORDER_WORKING"
        assert e.event_type != "ORDER_SUBMITTED", "INVALID_FINAL_EVENT_TYPE"
    return events
