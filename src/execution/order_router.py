"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, List

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.core_engine.events import ExecutionEvent, RiskDecisionRecord
from src.core_engine.state import RunMode

_EXECUTION_EVENT_BUFFER: dict[int, ExecutionEvent] = {}
_FILL_AUTHORITY_STATE = "UNKNOWN"
_RUNTIME_ORDERS: dict[int, "TrackedOrder"] = {}
_RUNTIME_POSITIONS: dict[str, "TrackedPosition"] = {}
_SEEN_EXEC_IDS: set[str] = set()
_UNMATCHED_CALLBACK_COUNT = 0
_RECONCILED_ORDERS_COUNT = 0
_RECONCILED_POSITIONS_COUNT = 0

ORDER_STATES = {
    "PENDING_SUBMISSION",
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


@dataclass
class TrackedPosition:
    symbol: str
    qty: int = 0
    avg_price: float | None = None
    pending_entry_qty: int = 0
    pending_exit_qty: int = 0
    state: str = "NO_POSITION"


def runtime_lifecycle_snapshot() -> dict[str, int | str]:
    working = 0
    partial = 0
    filled = 0
    pending_entries = 0
    for row in _RUNTIME_ORDERS.values():
        if row.canonical_state in {"SUBMITTED", "ACKNOWLEDGED", "WORKING", "PARTIALLY_FILLED"} and row.remaining_qty > 0:
            working += 1
        if row.canonical_state == "PARTIALLY_FILLED":
            partial += 1
        if row.canonical_state == "FILLED":
            filled += 1
        if row.is_entry and row.remaining_qty > 0 and row.canonical_state in {"WORKING", "PARTIALLY_FILLED", "SUBMITTED", "ACKNOWLEDGED"}:
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
        "fill_authority_state": fill_authority_state(),
    }


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fill_authority_state() -> str:
    return _FILL_AUTHORITY_STATE


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


def _upsert_order_from_submission(*, order_id: int, symbol: str, side: str, total_qty: int, order_ref: str) -> TrackedOrder:
    row = _RUNTIME_ORDERS.get(order_id)
    if row is None:
        row = TrackedOrder(
            broker_order_id=order_id,
            order_ref=order_ref,
            symbol=symbol,
            side=side,
            total_qty=max(0, int(total_qty)),
            remaining_qty=max(0, int(total_qty)),
            broker_status="Submitted",
            canonical_state="SUBMITTED",
            last_update_at=_now_utc_iso(),
        )
        _RUNTIME_ORDERS[order_id] = row
    else:
        row.last_update_at = _now_utc_iso()
        row.broker_status = "Submitted"
        row.canonical_state = "SUBMITTED"
    pos = _RUNTIME_POSITIONS.setdefault(symbol, TrackedPosition(symbol=symbol))
    normalized_side = str(side or "").upper()
    row.is_exit = normalized_side == "SELL" and pos.qty > 0
    row.is_entry = not row.is_exit
    if row.is_exit:
        pos.pending_exit_qty = max(0, pos.pending_exit_qty + int(total_qty))
    else:
        pos.pending_entry_qty = max(0, pos.pending_entry_qty + int(total_qty))
    if pos.qty <= 0:
        pos.state = "PENDING_ENTRY"
    print(f"[LIFECYCLE][ORDER] order_id={order_id} symbol={symbol} state={row.canonical_state} filled={row.filled_qty} remaining={row.remaining_qty}")
    return row


def _apply_fill_to_tracked_order(*, order_id: int, symbol: str, fill_qty: int, fill_price: float | None, exec_id: str | None, timestamp: str, source: str) -> None:
    global _UNMATCHED_CALLBACK_COUNT
    row = _RUNTIME_ORDERS.get(order_id)
    if row is None:
        _UNMATCHED_CALLBACK_COUNT += 1
        print(f"[ORDER_EVENT][UNMATCHED] event=EXECUTION order_id={order_id} symbol={symbol} source={source}")
        return
    if exec_id:
        dedupe_key = f"{order_id}:{exec_id}"
        if dedupe_key in _SEEN_EXEC_IDS or exec_id in row.seen_exec_ids:
            print(f"[ORDER_EVENT][EXECUTION] order_id={order_id} exec_id={exec_id} deduped=true")
            return
        _SEEN_EXEC_IDS.add(dedupe_key)
        row.seen_exec_ids.add(exec_id)
    inc = max(0, int(fill_qty))
    if inc <= 0:
        return
    prev_filled = row.filled_qty
    row.filled_qty = min(row.total_qty, row.filled_qty + inc)
    row.remaining_qty = max(0, row.total_qty - row.filled_qty)
    if fill_price is not None:
        prev_qty = prev_filled
        prev_avg = float(row.avg_fill_price or 0.0)
        row.avg_fill_price = ((prev_qty * prev_avg) + (inc * float(fill_price))) / max(1, prev_qty + inc)
    old_state = row.canonical_state
    row.canonical_state = "FILLED" if row.remaining_qty == 0 else "PARTIALLY_FILLED"
    row.broker_status = "Filled" if row.canonical_state == "FILLED" else "Submitted"
    row.last_update_at = timestamp
    print(f"[ORDER_EVENT][EXECUTION] order_id={order_id} symbol={row.symbol} fill_inc={inc} filled={row.filled_qty} remaining={row.remaining_qty} exec_id={exec_id or 'NA'}")
    if old_state != row.canonical_state:
        print(f"[ORDER_EVENT][STATE_TRANSITION] order_id={order_id} from={old_state} to={row.canonical_state}")
    signed = inc if row.is_entry else -inc
    _apply_position_fill(row.symbol, signed_delta_qty=signed, fill_price=fill_price, pending_entry_delta=(-inc if row.is_entry else 0), pending_exit_delta=(-inc if row.is_exit else 0))


def _on_ibkr_callback(callback_payload: Any) -> None:
    global _UNMATCHED_CALLBACK_COUNT
    event_type = str(_extract_callback_field(callback_payload, "event_type") or "").lower()
    if event_type and event_type not in {"execdetails", "orderstatus", "commissionreport"}:
        return
    order_id = _extract_callback_order_id(callback_payload)
    symbol = _extract_callback_symbol(callback_payload)
    filled_qty = _extract_callback_filled_qty(callback_payload)
    fill_price = _extract_callback_fill_price(callback_payload)
    timestamp = _extract_callback_timestamp(callback_payload)
    print(
        "[EXECUTION][CALLBACK_RECEIVED] "
        f"symbol={symbol or 'UNKNOWN'} order_id={order_id} filled_qty={filled_qty} fill_price={fill_price} timestamp={timestamp}"
    )
    if order_id is None:
        _UNMATCHED_CALLBACK_COUNT += 1
        print("[ORDER_EVENT][UNMATCHED] event=CALLBACK reason=missing_order_id")
        return
    event_status = str(_extract_callback_field(callback_payload, "status") or "").upper()
    remaining_qty = _extract_callback_field(callback_payload, "remaining")
    try:
        remaining_int = int(float(remaining_qty)) if remaining_qty is not None else 0
    except (TypeError, ValueError):
        remaining_int = 0
    if event_type == "orderstatus" and filled_qty > 0 and remaining_int > 0:
        fill_event_type = "ORDER_PARTIALLY_FILLED"
    else:
        fill_event_type = "ORDER_FILLED" if filled_qty > 0 else "ORDER_WORKING"
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
        exec_id = _extract_callback_field(callback_payload, "execId")
        _apply_fill_to_tracked_order(
            order_id=order_id,
            symbol=symbol,
            fill_qty=filled_qty,
            fill_price=fill_price,
            exec_id=str(exec_id) if exec_id else None,
            timestamp=timestamp,
            source="CALLBACK_EXECDETAILS",
        )
    elif event_type == "orderstatus":
        row = _RUNTIME_ORDERS.get(order_id)
        if row is None:
            _UNMATCHED_CALLBACK_COUNT += 1
            print(f"[ORDER_EVENT][UNMATCHED] event=STATUS order_id={order_id} symbol={symbol}")
        else:
            old_state = row.canonical_state
            row.broker_status = event_status or row.broker_status
            row.filled_qty = max(row.filled_qty, filled_qty)
            row.remaining_qty = remaining_int if remaining_int >= 0 else row.remaining_qty
            row.canonical_state = _state_from_broker_status(row.broker_status, row.filled_qty, row.remaining_qty)
            row.last_update_at = timestamp
            print(f"[ORDER_EVENT][STATUS] order_id={order_id} symbol={row.symbol} status={row.broker_status} filled={row.filled_qty} remaining={row.remaining_qty}")
            if old_state != row.canonical_state:
                print(f"[ORDER_EVENT][STATE_TRANSITION] order_id={order_id} from={old_state} to={row.canonical_state}")
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


def _fetch_ibkr_truth(mode: RunMode) -> tuple[list[Any], list[Any], list[Any]]:
    if _is_explicit_test_mode():
        return [], [], []
    if mode not in {RunMode.PAPER, RunMode.LIVE}:
        return [], [], []
    manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
    client = manager.get_client()
    open_orders = _safe_list_call(client, "openOrders")
    executions = _safe_list_call(client, "executions")
    positions = _safe_list_call(client, "positions")
    print(f"[POSITION][SYNC] source=IBKR positions={len(positions)}")
    return open_orders, executions, positions


def _sync_submitted_events_from_ibkr(
    mode: RunMode,
    events: List[ExecutionEvent],
) -> List[ExecutionEvent]:
    global _RECONCILED_ORDERS_COUNT, _RECONCILED_POSITIONS_COUNT
    if not events:
        return events
    open_orders, executions, positions = _fetch_ibkr_truth(mode)
    print(
        "[EXECUTION][WORKING_ORDER_RECON] "
        f"open_orders={len(open_orders)} executions={len(executions)} positions={len(positions)}"
    )
    execution_index: dict[int, Any] = {}
    for row in executions:
        order_id = _extract_exec_order_id(row)
        if order_id is not None and order_id not in execution_index:
            execution_index[order_id] = row

    for event in events:
        if event.action != "SUBMITTED":
            continue
        event.last_update_time = _now_utc_iso()
        if event.broker_order_id is None:
            continue
        match = execution_index.get(int(event.broker_order_id))
        if match is None:
            continue
        matched_qty = _extract_exec_qty(match)
        event.event_type = "ORDER_PARTIALLY_FILLED" if 0 < matched_qty < int(event.remaining_quantity or 0) else "ORDER_FILLED"
        event.source = "IBKR"
        event.broker_status = "Filled" if event.event_type == "ORDER_FILLED" else "Submitted"
        event.filled_quantity = matched_qty
        event.remaining_quantity = max(0, int(event.remaining_quantity or 0) - matched_qty)
        event.avg_fill_price = _extract_exec_price(match)
        print(
            f"[ORDER][{'PARTIAL_FILL' if event.event_type == 'ORDER_PARTIALLY_FILLED' else 'FILL'}] "
            f"symbol={event.symbol} order_id={event.broker_order_id} qty={event.filled_quantity} "
            f"price={event.avg_fill_price if event.avg_fill_price is not None else 'UNKNOWN'}"
        )
        _apply_fill_to_tracked_order(
            order_id=int(event.broker_order_id),
            symbol=str(event.symbol or "").upper(),
            fill_qty=max(0, matched_qty),
            fill_price=event.avg_fill_price,
            exec_id=None,
            timestamp=event.last_update_time or _now_utc_iso(),
            source="BROKER_RECON_EXECUTIONS",
        )
        _RECONCILED_ORDERS_COUNT += 1
        for position in positions:
            symbol = str(getattr(position, "symbol", "") or "").upper()
            if symbol != str(event.symbol or "").upper():
                continue
            qty = int(getattr(position, "position", 0) or 0)
            avg = getattr(position, "avgCost", None)
            print(f"[POSITION][OPEN] symbol={symbol} qty={qty} avg_price={avg}")
            tracked = _RUNTIME_POSITIONS.setdefault(symbol, TrackedPosition(symbol=symbol))
            if tracked.qty != qty:
                print(f"[POSITION][DRIFT] symbol={symbol} local_qty={tracked.qty} broker_qty={qty}")
                tracked.qty = qty
                tracked.state = "POSITION_CLOSED" if qty == 0 else "POSITION_OPEN"
                print(f"[POSITION][REPAIRED] symbol={symbol} qty={tracked.qty} state={tracked.state}")
            _RECONCILED_POSITIONS_COUNT += 1
            break
    print(f"[EXECUTION][RECON_VERDICT] reconciled_orders={_RECONCILED_ORDERS_COUNT} reconciled_positions={_RECONCILED_POSITIONS_COUNT}")
    return events


def _is_explicit_test_mode() -> bool:
    return str(os.environ.get("EXECUTION_ENV", "")).strip().upper() == "TEST"


def _validate_ibkr_connection(mode: RunMode) -> None:
    if _is_explicit_test_mode():
        return

    if mode not in {RunMode.PAPER, RunMode.LIVE}:
        return

    manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
    metadata = manager.connection_metadata()

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


def execute_intents(
    mode: RunMode,
    decisions: List[RiskDecisionRecord],
) -> List[ExecutionEvent]:
    global _FILL_AUTHORITY_STATE
    _FILL_AUTHORITY_STATE = "UNKNOWN"
    events: List[ExecutionEvent] = []
    manager: Any | None = None

    for decision in decisions:
        quantity = int(decision.approved_quantity)
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
    open_orders, _executions, positions = _fetch_ibkr_truth(mode)
    has_working_order_recon = hasattr(open_orders, "__iter__")
    if mode in {RunMode.PAPER, RunMode.LIVE} and not has_working_order_recon:
        _FILL_AUTHORITY_STATE = "DEGRADED"
        print("[EXECUTION][FILL_AUTHORITY_DEGRADED] reason=broker_fill_reconciliation_unavailable")
    existing_position_symbols = {str(getattr(row, "symbol", "") or "").upper() for row in positions}
    working_order_families: set[tuple[str, str, str]] = set()
    for row in open_orders:
        symbol = _extract_symbol_from_order(row)
        if not symbol:
            continue
        order = getattr(row, "order", None)
        side = str(getattr(order, "action", "") or "").upper()
        order_ref = _extract_order_ref(row)
        family = order_ref.split("|")[-1] if "|" in order_ref else order_ref
        working_order_families.add((symbol, side, family))
    print(f"[EXECUTION][WORKING_ORDER_RECON] known_working_orders={len(working_order_families)}")

    order_id_seed = 0
    if mode in {RunMode.PAPER, RunMode.LIVE} and not _is_explicit_test_mode():
        if manager is None:
            manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
        metadata = manager.connection_metadata()
        order_id_seed = int(metadata.get("connected_client_id") or 0) * 1_000_000

    for index, decision in enumerate(decisions, start=1):
        account = RouterAccountSnapshot(available_funds=float(decision.available_funds))
        order_value = float(decision.order_value)
        risk_allowed = bool(decision.risk_allowed)
        print(
            f"[CAPITAL] available_funds={account.available_funds} "
            f"order_value={order_value} "
            f"risk_allowed={risk_allowed}"
        )
        quantity = int(decision.approved_quantity)
        duplicate_symbol = str(decision.symbol or "").upper()
        order_side = "BUY" if str(getattr(decision, "side", "LONG") or "LONG").upper() == "LONG" else "SELL"
        order_family = str(decision.intent_id or "")
        working_duplicate = (duplicate_symbol, order_side, order_family) in working_order_families
        if duplicate_symbol in existing_position_symbols:
            print(f"[EXECUTION][BLOCK] symbol={duplicate_symbol} reason=DUPLICATE_POSITION")
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
            print(f"[EXECUTION][DUPLICATE_WORKING_ORDER_BLOCK] symbol={duplicate_symbol} reason=DUPLICATE_WORKING_ORDER")
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
            if entry_price is None or float(entry_price) <= 0:
                print(f"[EXECUTION][BLOCK] symbol={decision.symbol} reason=INVALID_ENTRY_PRICE")
                events.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail="reason=INVALID_ENTRY_PRICE",
                        broker_status="REJECTED",
                    )
                )
                continue
            if float(entry_price) <= 1.5:
                print(f"[EXECUTION][BLOCK] symbol={decision.symbol} reason=INVALID_PRICE_SANITY_CHECK")
                events.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail="reason=INVALID_PRICE_SANITY_CHECK",
                        broker_status="REJECTED",
                    )
                )
                continue
        dispatch = "SKIPPED"
        if mode in {RunMode.SIM, RunMode.READ_ONLY}:
            action = "WOULD_PLACE"
            detail = f"mode={mode.value}; decision={decision.decision}; qty={quantity}"
            dispatch = "SKIPPED"
        elif decision.decision == "ALLOW":
            if mode == RunMode.LIVE and decision.capital_source != "IBKR_CANONICAL":
                action = "BLOCKED"
                detail = "reason=CANONICAL_CAPITAL_UNAVAILABLE"
                dispatch = "SKIPPED"
            elif quantity != int(decision.max_position_size):
                action = "BLOCKED"
                detail = (
                    "reason=EXECUTION_QUANTITY_MISMATCH "
                    f"approved={decision.approved_quantity} max_size={decision.max_position_size}"
                )
                dispatch = "SKIPPED"
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
            broker_order_id = order_id_seed + index if order_id_seed > 0 else index
            print(f"[EXECUTION][SUBMITTED] symbol={decision.symbol} broker_order_id={broker_order_id}")
            _upsert_order_from_submission(
                order_id=broker_order_id,
                symbol=str(decision.symbol or "").upper(),
                side=order_side,
                total_qty=quantity,
                order_ref=str(decision.intent_id or ""),
            )
        events.append(
            ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action=action,
                detail=detail,
                broker_order_id=broker_order_id,
                event_type="ORDER_SUBMITTED" if action == "SUBMITTED" else action,
                broker_status="Submitted" if action == "SUBMITTED" else ("REJECTED" if action == "BLOCKED" else "SIMULATED"),
                source="IBKR" if action == "SUBMITTED" else "ENGINE",
                filled_quantity=0,
                remaining_quantity=quantity if action == "SUBMITTED" else 0,
                last_update_time=_now_utc_iso(),
            )
        )
    events, _ = _apply_callback_fills(events)
    events = _sync_submitted_events_from_ibkr(mode, events)
    if _FILL_AUTHORITY_STATE == "UNKNOWN":
        _FILL_AUTHORITY_STATE = "ACTIVE" if mode in {RunMode.PAPER, RunMode.LIVE} else "N/A"
    return events
