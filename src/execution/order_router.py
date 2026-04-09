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
from src.core_engine.state import RunMode
from src.runtime.async_runtime_bootstrap import safe_import_ib_insync

_EXECUTION_EVENT_BUFFER: dict[int, ExecutionEvent] = {}
_FILL_AUTHORITY_STATE = "UNKNOWN"
_RUNTIME_ORDERS: dict[int, "TrackedOrder"] = {}
_RUNTIME_POSITIONS: dict[str, "TrackedPosition"] = {}
_SEEN_EXEC_IDS: set[str] = set()
_UNMATCHED_CALLBACK_COUNT = 0
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
    "UNKNOWN",
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


@dataclass
class TrackedPosition:
    symbol: str
    qty: int = 0
    avg_price: float | None = None
    pending_entry_qty: int = 0
    pending_exit_qty: int = 0
    state: str = "NO_POSITION"


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
    normalized = failure_type if failure_type in FAILURE_TYPES else "UNKNOWN"
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
    open_positions = sum(1 for p in _RUNTIME_POSITIONS.values() if p.qty > 0)
    partial_positions = sum(1 for p in _RUNTIME_POSITIONS.values() if p.state == "PARTIAL_POSITION_OPEN")
    reducing_positions = sum(1 for p in _RUNTIME_POSITIONS.values() if p.state == "POSITION_REDUCING")
    closed_positions = sum(1 for p in _RUNTIME_POSITIONS.values() if p.state == "POSITION_CLOSED")
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


def fill_authority_state() -> str:
    return _FILL_AUTHORITY_STATE


def _execution_truth_threshold() -> int:
    raw = os.environ.get("EXECUTION_TRUTH_DEGRADED_THRESHOLD", "1")
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _is_diagnostics_mode() -> bool:
    return _env_truthy("EXECUTION_TRUTH_DIAGNOSTICS_MODE", default=False)


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


def _extract_position_qty(position_row: Any) -> int:
    for field in ("position", "qty", "quantity", "shares"):
        value = getattr(position_row, field, None)
        if value is None:
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return 0


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
        return str(symbol).upper()
    contract = _extract_callback_field(callback_payload, "contract")
    if contract is not None:
        from_contract = getattr(contract, "symbol", None)
        if from_contract:
            return str(from_contract).upper()
    return ""


def _extract_callback_order_id(callback_payload: Any) -> int | None:
    value = _extract_callback_field(callback_payload, "order_id", "orderId", "permId", "perm_id")
    if value is None:
        execution = _extract_callback_field(callback_payload, "execution")
        if execution is not None:
            value = getattr(execution, "orderId", None) or getattr(execution, "permId", None)
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
        return "BROKER_INACTIVE_UNKNOWN"
    if row.ack_seen:
        return "BROKER_ACK_SEEN"
    return "DISPATCH_SENT"


def _apply_position_fill(symbol: str, *, signed_delta_qty: int, fill_price: float | None, pending_entry_delta: int = 0, pending_exit_delta: int = 0) -> None:
    if not symbol:
        return
    row = _RUNTIME_POSITIONS.setdefault(symbol, TrackedPosition(symbol=symbol))
    row.qty = int(row.qty) + int(signed_delta_qty)
    row.pending_entry_qty = max(0, int(row.pending_entry_qty) + int(pending_entry_delta))
    row.pending_exit_qty = max(0, int(row.pending_exit_qty) + int(pending_exit_delta))
    if fill_price is not None and signed_delta_qty > 0:
        prev_qty = max(0, int(row.qty) - int(signed_delta_qty))
        prev_avg = float(row.avg_price or 0.0)
        total_qty = prev_qty + int(signed_delta_qty)
        row.avg_price = ((prev_qty * prev_avg) + (int(signed_delta_qty) * float(fill_price))) / total_qty if total_qty > 0 else row.avg_price
    if row.qty <= 0:
        row.qty = 0
        row.state = "POSITION_CLOSED"
    elif row.pending_exit_qty > 0:
        row.state = "POSITION_REDUCING"
    elif row.pending_entry_qty > 0:
        row.state = "PARTIAL_POSITION_OPEN"
    else:
        row.state = "POSITION_OPEN"
    print(f"[LIFECYCLE][POSITION] symbol={symbol} qty={row.qty} pending_entry={row.pending_entry_qty} pending_exit={row.pending_exit_qty} state={row.state}")
    print(
        "[EXECUTION][POSITION] "
        f"symbol={symbol} qty={row.qty} pending_entry={row.pending_entry_qty} "
        f"pending_exit={row.pending_exit_qty} state={row.state}"
    )
    if row.qty > 0 and row.avg_price is not None:
        print(f"[POSITION][OPEN] symbol={symbol} qty={row.qty} avg_price={row.avg_price}")
    print(f"[POSITION][OPENED_OR_UPDATED] symbol={symbol} qty={row.qty} avg_price={row.avg_price} state={row.state}")


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
    pos = _RUNTIME_POSITIONS.setdefault(symbol, TrackedPosition(symbol=symbol))
    normalized_side = str(side or "").upper()
    row.is_exit = normalized_side == "SELL" and pos.qty > 0
    row.is_entry = not row.is_exit
    if created:
        if row.is_exit:
            pos.pending_exit_qty = max(0, pos.pending_exit_qty + int(total_qty))
        else:
            pos.pending_entry_qty = max(0, pos.pending_entry_qty + int(total_qty))
    if pos.qty <= 0:
        pos.state = "PENDING_ENTRY"
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


def _apply_fill_to_tracked_order(*, order_id: int, symbol: str, fill_qty: int, fill_price: float | None, exec_id: str | None, timestamp: str, source: str) -> None:
    global _UNMATCHED_CALLBACK_COUNT, _UNRESOLVED_EXECUTION_RECONCILIATION_COUNT, _FILL_AUTHORITY_STATE
    row = _RUNTIME_ORDERS.get(order_id)
    if row is None:
        _UNMATCHED_CALLBACK_COUNT += 1
        print(f"[ORDER_EVENT][UNMATCHED] event=EXECUTION order_id={order_id} symbol={symbol} source={source}")
        print(f"[EXECUTION][RECONCILIATION_FAILED] event=EXECUTION order_id={order_id} order_ref=UNKNOWN source={source}")
        print(
            "[EXECUTION][TRUTH_GAP] "
            f"stage=FILL event=EXECUTION order_id={order_id} symbol={symbol or 'UNKNOWN'} source={source}"
        )
        _UNRESOLVED_EXECUTION_RECONCILIATION_COUNT += 1
        _FILL_AUTHORITY_STATE = "DEGRADED"
        return
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
    row.callback_pending = False
    row.callback_pending_since = None
    print(f"[EXECUTION][ORDER_MATCH] order_id={order_id} symbol={row.symbol} source={source}")
    print(
        "[EXECUTION][FILL] "
        f"order_id={order_id} symbol={row.symbol} authority=execDetails fill_qty={inc} "
        f"remaining_qty={row.remaining_qty} exec_id={exec_id or 'NA'}"
    )
    print(f"[PRICE_AUTHORITY][SOURCE=IBKR_EXECUTION] order_id={order_id} symbol={row.symbol} price={fill_price}")
    if row.remaining_qty == 0:
        print(f"[EXECUTION][FILL] order_id={order_id} symbol={row.symbol} fill_qty={inc} total_filled={row.filled_qty} exec_id={exec_id or 'NA'}")
    else:
        print(f"[EXECUTION][PARTIAL_FILL] order_id={order_id} symbol={row.symbol} fill_qty={inc} total_filled={row.filled_qty} remaining={row.remaining_qty} exec_id={exec_id or 'NA'}")
    if old_state != row.canonical_state:
        print(f"[ORDER_EVENT][STATE_TRANSITION] order_id={order_id} from={old_state} to={row.canonical_state}")
    signed = inc if row.is_entry else -inc
    _apply_position_fill(row.symbol, signed_delta_qty=signed, fill_price=fill_price, pending_entry_delta=(-inc if row.is_entry else 0), pending_exit_delta=(-inc if row.is_exit else 0))


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
        "[EXECUTION][CALLBACK_RECEIVED] "
        f"symbol={symbol or 'UNKNOWN'} order_id={order_id} filled_qty={filled_qty} fill_price={fill_price} timestamp={timestamp}"
    )
    if event_type == "positionend":
        print("[IBKR][CALLBACK_RAW] event=positionEnd")
        return
    if order_id is None:
        if event_type in {"position", "commissionreport"}:
            _NON_ORDER_UNMATCHED_CALLBACK_COUNT += 1
            return
        _UNMATCHED_CALLBACK_COUNT += 1
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
            _mark_execution_failure(None, "UNKNOWN", reason=f"missing_order_id callback={event_type or 'unknown'}")
        return
    tracked = _RUNTIME_ORDERS.get(int(order_id))
    trace = _EXECUTION_TRACE_BY_ORDER_ID.get(order_id)
    if tracked is None and trace is None and event_type in {"openorder", "orderstatus"}:
        tracked, trace = _recover_order_tracking_from_pending_submission(
            order_id=int(order_id),
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
            if mapped_id != int(order_id):
                print(f"[ORDER_EVENT][RECONCILED] source=orderRef order_ref={callback_order_ref} order_id={mapped_id}")
            order_id = int(mapped_id)
            tracked = _RUNTIME_ORDERS.get(int(order_id))
            trace = _EXECUTION_TRACE_BY_ORDER_ID.get(int(order_id))
            if tracked is None:
                tracked, trace = _recover_order_tracking_from_pending_submission(
                    order_id=int(order_id),
                    callback_symbol=str(symbol or ""),
                    timestamp=timestamp,
                )
    if event_type == "execdetails" and tracked is None:
        _UNMATCHED_CALLBACK_COUNT += 1
        print(
            "[ORDER_EVENT][UNMATCHED] "
            f"event=EXECUTION order_id={order_id} order_ref={callback_order_ref or 'UNKNOWN'} symbol={symbol or 'UNKNOWN'}"
        )
        print(
            "[EXECUTION][RECONCILIATION_FAILED] "
            f"event=EXECUTION order_id={order_id} order_ref={callback_order_ref or 'UNKNOWN'} source=CALLBACK_EXECDETAILS"
        )
        print(
            "[EXECUTION][TRUTH_GAP] "
            f"stage=FILL event=EXECUTION order_id={order_id} symbol={symbol or 'UNKNOWN'} source=CALLBACK_EXECDETAILS"
        )
        _UNRESOLVED_EXECUTION_RECONCILIATION_COUNT += 1
        _FILL_AUTHORITY_STATE = "DEGRADED"
        return
    if (not symbol) and tracked is not None and tracked.symbol:
        symbol = tracked.symbol
        print(f"[EXECUTION][CALLBACK_ENRICHED] order_id={order_id} symbol={symbol} source=order_id_mapping")
    if not symbol and tracked is None:
        print(f"[EXECUTION][CALLBACK_UNRESOLVED] order_id={order_id} event_type={event_type or 'unknown'}")
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
    _LAST_CALLBACK_FINGERPRINT_BY_ORDER_ID[int(order_id)] = fingerprint
    if trace is not None:
        _trace_log("ACK", trace, extra=f"callback={event_type or 'unknown'}")
    event_status = str(_extract_callback_field(callback_payload, "status") or "").upper()
    remaining_qty = _extract_callback_field(callback_payload, "remaining")
    try:
        remaining_int = int(float(remaining_qty)) if remaining_qty is not None else 0
    except (TypeError, ValueError):
        remaining_int = 0
    if event_type == "execdetails":
        fill_event_type = "ORDER_FILLED"
    else:
        fill_event_type = "ORDER_WORKING"
    broker_status = "Filled" if fill_event_type == "ORDER_FILLED" else (
        "Submitted" if event_status in {"SUBMITTED", "PRESUBMITTED"} else (event_status or "Submitted")
    )
    event = ExecutionEvent(
        symbol=symbol or "UNKNOWN",
        intent_id="",
        action="WORKING" if fill_event_type == "ORDER_WORKING" else "SUBMITTED",
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
        _VISIBILITY_BY_ORDER_ID.setdefault(order_id, {}).update({"execDetails_seen": True})
        exec_id = _extract_callback_field(callback_payload, "execId")
        print(
            "[EXECUTION][TRACE] "
            f"stage=FILL event_type=execDetails order_id={order_id} authority=execDetails exec_id={exec_id or 'NA'}"
        )
        _apply_fill_to_tracked_order(
            order_id=order_id,
            symbol=symbol,
            fill_qty=filled_qty,
            fill_price=fill_price,
            exec_id=str(exec_id) if exec_id else None,
            timestamp=timestamp,
            source="CALLBACK_EXECDETAILS",
        )
        if tracked is not None:
            print(
                "[EXECUTION][RECONCILED] "
                f"order_id={order_id} symbol={tracked.symbol or symbol or 'UNKNOWN'} "
                f"intent_id={tracked.intent_id or _INTENT_ID_BY_ORDER_ID.get(int(order_id), '')} "
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
            pos = _RUNTIME_POSITIONS.get(trace.symbol)
            if pos is not None and pos.qty > 0:
                trace.position_opened = True
                _trace_log("POSITION_OPENED", trace, extra=f"position_qty={pos.qty}")
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
        _VISIBILITY_BY_ORDER_ID.setdefault(order_id, {}).update({"orderStatus_seen": True})
        row = _RUNTIME_ORDERS.get(order_id)
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
            row.last_update_at = timestamp
            row.ack_seen = True
            if str(row.broker_status or "").upper() in {"SUBMITTED", "PRESUBMITTED"}:
                row.working_seen = True
            if str(row.broker_status or "").upper() == "PRESUBMITTED":
                row.queued_for_rth_seen = bool(row.queued_for_rth_seen)
            if str(row.broker_status or "").upper() in {"INACTIVE", "REJECTED"}:
                if row.normalized_reject_reason in {"OUTSIDE_RTH_IGNORED_WARNING", "QUEUED_UNTIL_RTH_WARNING"}:
                    row.queued_for_rth_seen = True
                else:
                    row.inactive_seen = True
                    row.reject_seen = bool(row.reject_seen or row.normalized_reject_reason)
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
        _VISIBILITY_BY_ORDER_ID.setdefault(order_id, {}).update({"openOrder_seen": True})
        if callback_order_ref:
            _ORDER_ID_BY_ORDER_REF[callback_order_ref] = int(order_id)
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
            tracked.final_execution_state = _resolve_authoritative_execution_state(tracked)
    elif event_type == "error":
        code_raw = _extract_callback_field(callback_payload, "errorCode", "code")
        message = str(_extract_callback_field(callback_payload, "errorString", "message") or "")
        try:
            code = int(code_raw) if code_raw is not None else None
        except (TypeError, ValueError):
            code = None
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
        if trace is not None:
            qty_raw = _extract_callback_field(callback_payload, "position", "qty", "shares")
            try:
                qty = int(float(qty_raw or 0))
            except (TypeError, ValueError):
                qty = 0
            if qty > 0:
                _VISIBILITY_BY_ORDER_ID.setdefault(order_id, {}).update({"position_seen": True})
                trace.position_opened = True
                trace.lifecycle_state = "POSITION_OPENED"
                _trace_log("POSITION_OPENED", trace, extra=f"position_qty={qty}")
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


def _run_passive_position_reconciliation(*, positions: list[Any]) -> None:
    global _RECON_RESYNC_NEEDED
    broker_position_by_symbol: dict[str, int] = {}
    for row in positions:
        symbol = _extract_symbol_from_order(row)
        if not symbol:
            continue
        broker_position_by_symbol[symbol] = broker_position_by_symbol.get(symbol, 0) + _extract_position_qty(row)
    symbols = set(_RUNTIME_POSITIONS.keys()) | set(broker_position_by_symbol.keys())
    for symbol in sorted(symbols):
        local = _RUNTIME_POSITIONS.get(symbol)
        local_qty = int(local.qty) if local is not None else 0
        broker_qty = int(broker_position_by_symbol.get(symbol, 0))
        if local_qty == broker_qty:
            continue
        print(f"[POSITION][RECON_MISMATCH] symbol={symbol} local_qty={local_qty} ibkr_qty={broker_qty}")
        print(
            "[EXECUTION][RECONCILE] "
            f"symbol={symbol} local_qty={local_qty} broker_qty={broker_qty} action=passive_detect_only"
        )
        if broker_qty > local_qty:
            print(f"[FILL][GAP_DETECTED] symbol={symbol} expected_qty={broker_qty} actual_qty={local_qty}")
            _RECON_RESYNC_NEEDED = True


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
    position_symbols = {symbol for symbol, row in _RUNTIME_POSITIONS.items() if row.qty > 0}
    for symbol in sorted(filled_symbols - position_symbols):
        print(f"[POSITION][INCONSISTENT_STATE] symbol={symbol} reason=filled_without_position")
    for symbol in sorted(position_symbols - filled_symbols):
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
                visibility["position_seen"] = bool(_RUNTIME_POSITIONS.get(tracked.symbol) and _RUNTIME_POSITIONS[tracked.symbol].qty > 0)
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
    print("[IBKR][CALLBACK_SUMMARY]")
    print(f"openOrder={open_order_callback_count}")
    print(f"orderStatus={order_status_callback_count}")
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
    return str(os.environ.get("EXECUTION_ENV", "")).strip().upper() == "TEST"


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


def _wait_for_ibkr_snapshot_for_symbol(symbol: str, *, wait_up_to: float = 1.0, poll_interval: float = 0.1) -> dict[str, float | None]:
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
    try:
        for _ in range(poll_count):
            try:
                ib.waitOnUpdate(timeout=poll_interval)
            except Exception:
                time.sleep(poll_interval)
            last = _safe_price_value(getattr(ticker, "last", None))
            bid = _safe_price_value(getattr(ticker, "bid", None))
            ask = _safe_price_value(getattr(ticker, "ask", None))
            snapshot = {"last": last, "bid": bid, "ask": ask}
            if last is not None or (bid is not None and ask is not None):
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
    order = Order()
    order.eTradeOnly = False
    order.firmQuoteOnly = False
    order.action = side.upper()
    order.orderType = "MKT"
    order.totalQuantity = int(quantity)
    order.tif = "DAY"
    order.outsideRth = True
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
    if "|" in order_ref:
        parts = [p for p in str(order_ref).split("|") if p]
        if len(parts) >= 2:
            strategy_name = parts[1]
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
    try:
        order_id = int(client.submit_order(resolved_contract, order))
    except Exception as exc:
        print(f"[IBKR][PLACE_ORDER][ERROR] symbol={symbol} order_id=PENDING error={exc}")
        raise
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
    orders_submitted = 0
    acks_received = 0
    fills_received = 0
    positions_opened = 0

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
    has_working_order_recon = hasattr(open_orders, "__iter__")
    if mode in {RunMode.PAPER, RunMode.LIVE} and not has_working_order_recon:
        _FILL_AUTHORITY_STATE = "DEGRADED"
        print("[EXECUTION][FILL_AUTHORITY_DEGRADED] reason=broker_fill_reconciliation_unavailable")
    existing_position_symbols = {str(getattr(row, "symbol", "") or "").upper() for row in positions}
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
        family = order_ref.split("|")[-1] if "|" in order_ref else order_ref
        working_order_candidates.append(
            {
                "symbol": symbol,
                "side": side,
                "family": str(family or ""),
                "order_id": int(order_id) if order_id is not None else None,
                "status": status or "UNKNOWN",
                "is_live_status": status in {"SUBMITTED", "PRESUBMITTED", "PENDING_SUBMIT", "PENDINGCANCEL", "UNKNOWN"},
            }
        )
    print(f"[EXECUTION][WORKING_ORDER_RECON] known_working_orders={len(working_order_candidates)}")

    submitted_order_ids: list[int] = []
    for index, decision in enumerate(decisions, start=1):
        intents_received += 1
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
        _trace_log("INTENT_RECEIVED", trace, extra=f"cycle_id={cycle_id}")
        duplicate_symbol = str(decision.symbol or "").upper()
        order_side = "BUY" if str(getattr(decision, "side", "LONG") or "LONG").upper() == "LONG" else "SELL"
        order_family = str(decision.intent_id or "")
        print(
            f"[EXECUTION][DUPLICATE_CHECK] symbol={duplicate_symbol} side={order_side} intent_id={order_family} "
            f"candidate_count={len(working_order_candidates)}"
        )
        working_duplicate = False
        duplicate_reason = ""
        duplicate_order_id = None
        duplicate_status = ""
        for candidate in working_order_candidates:
            if candidate["symbol"] != duplicate_symbol or candidate["side"] != order_side:
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
        if order_side == "BUY" and duplicate_symbol in existing_position_symbols:
            print(f"[EXECUTION][BLOCK] symbol={duplicate_symbol} reason=DUPLICATE_POSITION")
            _mark_execution_failure(trace, "ORDER_REJECTED", reason="duplicate_position")
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail="reason=DUPLICATE_POSITION",
                    broker_status="REJECTED",
                    last_update_time=_now_utc_iso(),
                )
            )
            continue
        if working_duplicate:
            print(
                f"[EXECUTION][DUPLICATE_BLOCK] symbol={duplicate_symbol} reason=DUPLICATE_WORKING_ORDER "
                f"existing_order_id={duplicate_order_id} existing_broker_state={duplicate_status} conflict_reason={duplicate_reason}"
            )
            _mark_execution_failure(trace, "ORDER_REJECTED", reason="duplicate_working_order")
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail="reason=DUPLICATE_WORKING_ORDER",
                    broker_status="REJECTED",
                    last_update_time=_now_utc_iso(),
                )
            )
            continue
        if not str(decision.intent_id or "").strip():
            print(f"[EXECUTION][BLOCK] symbol={decision.symbol} reason=MISSING_ORDER_REF_COMPONENT")
            _mark_execution_failure(trace, "ORDER_REJECTED", reason="missing_order_ref_component")
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail="reason=MISSING_ORDER_REF_COMPONENT",
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
                    entry_price, entry_price_source = resolve_entry_price(
                        str(decision.symbol or ""),
                        {
                            "ibkr_snapshot_by_symbol": {str(decision.symbol or "").upper(): snapshot} if snapshot else {},
                            "ibkr_stream_by_symbol": {str(decision.symbol or "").upper(): snapshot} if snapshot else {},
                        },
                    )
                    decision.entry_price = entry_price
                    trace.resolved_price = float(entry_price)
                    trace.price_state = "PARTIAL_OK"
                    print(f"[PRICE][RESOLVED] symbol={decision.symbol} source=IBKR_SNAPSHOT price={entry_price}")
                except PriceResolutionError:
                    print(f"[PRICE][BLOCK] symbol={decision.symbol} reason=NO_IBKR_PRICE_AVAILABLE")
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
            if quantity != int(decision.max_position_size):
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
            if not _ensure_submission_allowed(mode, symbol=str(decision.symbol or "").upper()):
                events.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail="reason=EXECUTION_TRUTH_DEGRADED",
                        broker_status="REJECTED",
                        last_update_time=_now_utc_iso(),
                    )
                )
                continue
            submit_attempts += 1
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
                _mark_execution_failure(trace, "UNKNOWN", reason=str(exc))
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
            submitted_order_ids.append(int(broker_order_id))
            print(f"[EXECUTION][SUBMITTED] symbol={decision.symbol} broker_order_id={broker_order_id} local_dispatch_attempted=true place_order_issued=true")
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
            _register_order_intent_mapping(
                order_id=int(broker_order_id),
                intent_id=str(decision.intent_id or ""),
                order_ref=order_ref,
            )
            _PENDING_SUBMISSIONS_BY_ORDER_ID.pop(int(broker_order_id), None)
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
        pos = _RUNTIME_POSITIONS.get(trace.symbol)
        if pos is not None and int(pos.qty) > 0:
            trace.position_opened = True
            trace.lifecycle_state = "POSITION_OPENED"
            positions_opened += 1
        if trace.order_submitted and not trace.ack_received:
            _mark_execution_failure(trace, "NO_ACK", reason="order_submitted_without_ack")
        if trace.ack_received and not trace.fill_received:
            tracked = _RUNTIME_ORDERS.get(int(trace.order_id)) if trace.order_id is not None else None
            authoritative_state = _resolve_authoritative_execution_state(tracked)
            if authoritative_state in {"BROKER_REJECTED", "BROKER_CANCELLED", "BROKER_EXPIRED", "BROKER_INACTIVE_UNKNOWN"}:
                _mark_execution_failure(trace, "NO_FILL", reason=f"terminal_no_fill state={authoritative_state}")
        if trace.fill_received and not trace.position_opened:
            _mark_execution_failure(trace, "PARTIAL_FILL_STALLED", reason="fill_without_position")
        if trace.lifecycle_state not in {"FAIL", "POSITION_OPENED"}:
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
            f"normalized_reject_reason={(tracked.normalized_reject_reason if tracked is not None else '') or 'NONE'}"
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
        f"orders_submitted={orders_submitted} acks_received={acks_received} fills_received={fills_received} "
        f"positions_opened={positions_opened} failures_by_type={dict(sorted(_EXECUTION_FAILURES_BY_TYPE.items()))}"
    )
    if _FILL_AUTHORITY_STATE == "UNKNOWN":
        _FILL_AUTHORITY_STATE = "ACTIVE" if mode in {RunMode.PAPER, RunMode.LIVE} else "N/A"
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
