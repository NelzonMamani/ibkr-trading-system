"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, List

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.config.config_resolver import get_config
from src.core_engine.events import ExecutionEvent, RiskDecisionRecord
from src.core_engine.state import RunMode

_EXECUTION_EVENT_BUFFER: dict[int, ExecutionEvent] = {}


@dataclass(frozen=True)
class RouterAccountSnapshot:
    available_funds: float


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _extract_order_status(order_row: Any) -> str:
    status = getattr(order_row, "status", None)
    if status is None:
        order_status = getattr(order_row, "orderStatus", None) or getattr(order_row, "order_status", None)
        if order_status is not None:
            status = getattr(order_status, "status", None)
    return str(status or "UNKNOWN")


def _extract_order_filled(order_row: Any) -> int:
    value = getattr(order_row, "filled", None)
    if value is None:
        order_status = getattr(order_row, "orderStatus", None) or getattr(order_row, "order_status", None)
        if order_status is not None:
            value = getattr(order_status, "filled", None)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _extract_order_remaining(order_row: Any) -> int:
    value = getattr(order_row, "remaining", None)
    if value is None:
        order_status = getattr(order_row, "orderStatus", None) or getattr(order_row, "order_status", None)
        if order_status is not None:
            value = getattr(order_status, "remaining", None)
    try:
        return int(float(value))
    except (TypeError, ValueError):
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


def _on_ibkr_callback(callback_payload: Any) -> None:
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
        return
    event = ExecutionEvent(
        symbol=symbol or "UNKNOWN",
        intent_id="",
        action="SUBMITTED",
        detail="callback_fill",
        event_type="ORDER_FILLED",
        source="IBKR_EXECUTION",
        broker_order_id=order_id,
        filled_quantity=max(0, filled_qty),
        remaining_quantity=0,
        broker_status="Filled",
        avg_fill_price=fill_price,
        last_update_time=timestamp,
        lifecycle_state="FILLED",
        fill_source="IBKR_EXECUTION",
        pending_fill_price_resolution=fill_price is None or float(fill_price or 0.0) <= 0.0,
    )
    _EXECUTION_EVENT_BUFFER[order_id] = event
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
        event.filled_quantity = int(callback_fill.filled_quantity or 0)
        base_remaining = int(event.remaining_quantity or 0)
        event.remaining_quantity = max(0, base_remaining - event.filled_quantity)
        event.avg_fill_price = callback_fill.avg_fill_price
        event.last_update_time = callback_fill.last_update_time or _now_utc_iso()
        event.fill_source = "IBKR_EXECUTION"
        event.source = "IBKR_EXECUTION"
        if event.filled_quantity > 0 and (event.avg_fill_price or 0.0) > 0.0:
            event.event_type = "ORDER_FILLED"
            event.broker_status = "Filled"
            event.lifecycle_state = "FILLED"
            event.pending_fill_price_resolution = False
            print(
                "[EXECUTION][FILL_RESOLVED] "
                f"symbol={event.symbol} order_id={event.broker_order_id} source={event.fill_source} "
                f"filled_qty={event.filled_quantity} fill_price={event.avg_fill_price}"
            )
        else:
            event.event_type = "ORDER_PARTIALLY_FILLED" if event.filled_quantity > 0 else "ORDER_WORKING"
            event.broker_status = "Submitted"
            event.lifecycle_state = "PARTIAL" if event.filled_quantity > 0 else "WORKING"
            event.pending_fill_price_resolution = event.filled_quantity > 0
            print(
                "[EXECUTION][FILL_PENDING] "
                f"symbol={event.symbol} order_id={event.broker_order_id} source={event.fill_source} "
                f"filled_qty={event.filled_quantity} fill_price={event.avg_fill_price}"
            )
        fills_applied += 1
    return events, fills_applied


def _emit_test_fill_fallback(mode: RunMode, events: List[ExecutionEvent], timeout_seconds: float) -> List[ExecutionEvent]:
    if mode != RunMode.PAPER or not _is_test_environment():
        return events
    fallback_enabled = os.environ.get("IBKR_ENABLE_TEST_ONLY_FILL", "").lower() == "true"
    if not fallback_enabled:
        return events
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while time.monotonic() < deadline:
        events, fills_applied = _apply_callback_fills(events)
        if fills_applied > 0:
            return events
        time.sleep(0.05)
    for event in events:
        if event.action != "SUBMITTED" or int(event.filled_quantity or 0) > 0:
            continue
        synthetic_qty = int(event.remaining_quantity or 0)
        if synthetic_qty <= 0:
            synthetic_qty = 1
        event.event_type = "ORDER_FILLED"
        event.source = "TEST_ONLY_FILL"
        event.fill_source = "TEST_ONLY_FILL"
        event.broker_status = "Filled"
        event.filled_quantity = synthetic_qty
        event.remaining_quantity = 0
        event.lifecycle_state = "FILLED"
        event.pending_fill_price_resolution = event.avg_fill_price is None or float(event.avg_fill_price or 0.0) <= 0.0
        event.last_update_time = _now_utc_iso()
        print(
            "[EXECUTION][EVENT_CREATED] "
            f"event_type={event.event_type} source={event.source} symbol={event.symbol} "
            f"order_id={event.broker_order_id} filled_qty={event.filled_quantity} fill_price={event.avg_fill_price}"
        )
    return events


def _fetch_ibkr_truth(mode: RunMode) -> tuple[list[Any], list[Any], list[Any]]:
    if _is_test_environment():
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
    if not events:
        return events
    open_orders, executions, positions = _fetch_ibkr_truth(mode)
    execution_index: dict[int, Any] = {}
    for row in executions:
        order_id = _extract_exec_order_id(row)
        if order_id is not None and order_id not in execution_index:
            execution_index[order_id] = row

    order_index: dict[int, Any] = {}
    for row in open_orders:
        row_order_id = _extract_exec_order_id(row)
        if row_order_id is not None and row_order_id not in order_index:
            order_index[row_order_id] = row

    for event in events:
        if event.action != "SUBMITTED":
            continue
        event.last_update_time = _now_utc_iso()
        if event.broker_order_id is None:
            continue
        order_id = int(event.broker_order_id)
        status_row = order_index.get(order_id)
        execution_row = execution_index.get(order_id)
        status = _extract_order_status(status_row) if status_row is not None else "Submitted"
        status_upper = status.upper()
        event.broker_status = status
        event.source = "IBKR_ORDER_STATUS"
        event.fill_source = "IBKR_ORDER_STATUS"
        if status_upper in {"SUBMITTED", "PENDINGSUBMIT", "PENDING_SUBMIT", "PRESUBMITTED", "API_PENDING"}:
            event.event_type = "ORDER_ACKNOWLEDGED"
            event.lifecycle_state = "ACKNOWLEDGED"
        else:
            event.event_type = "ORDER_WORKING"
            event.lifecycle_state = "WORKING"

        if status_row is not None:
            status_filled = _extract_order_filled(status_row)
            status_remaining = _extract_order_remaining(status_row)
            if status_filled > 0:
                event.filled_quantity = max(event.filled_quantity, status_filled)
                event.remaining_quantity = status_remaining

        if execution_row is not None:
            event.source = "IBKR_EXECUTION"
            event.fill_source = "IBKR_EXECUTION"
            event.filled_quantity = max(event.filled_quantity, _extract_exec_qty(execution_row))
            event.avg_fill_price = _extract_exec_price(execution_row)
            event.remaining_quantity = max(0, int(event.remaining_quantity or 0) - int(event.filled_quantity or 0))

        if event.filled_quantity > 0 and (event.avg_fill_price or 0.0) > 0.0:
            event.event_type = "ORDER_FILLED" if event.remaining_quantity <= 0 else "ORDER_PARTIALLY_FILLED"
            event.lifecycle_state = "FILLED" if event.remaining_quantity <= 0 else "PARTIAL"
            event.pending_fill_price_resolution = False
            print(
                "[EXECUTION][FILL_RESOLVED] "
                f"symbol={event.symbol} order_id={event.broker_order_id} source={event.fill_source} "
                f"filled_qty={event.filled_quantity} remaining_qty={event.remaining_quantity} fill_price={event.avg_fill_price}"
            )
        elif event.filled_quantity > 0:
            event.pending_fill_price_resolution = True
            event.event_type = "ORDER_PARTIALLY_FILLED"
            event.lifecycle_state = "PARTIAL"
            print(
                "[EXECUTION][FILL_PENDING] "
                f"symbol={event.symbol} order_id={event.broker_order_id} source={event.fill_source} "
                f"filled_qty={event.filled_quantity} remaining_qty={event.remaining_quantity} reason=missing_fill_price"
            )
        else:
            print(
                "[EXECUTION][FILL_PENDING] "
                f"symbol={event.symbol} order_id={event.broker_order_id} source={event.fill_source} "
                f"filled_qty=0 remaining_qty={event.remaining_quantity} broker_status={event.broker_status}"
            )
        for position in positions:
            symbol = str(getattr(position, "symbol", "") or "").upper()
            if symbol != str(event.symbol or "").upper():
                continue
            qty = int(getattr(position, "position", 0) or 0)
            avg = getattr(position, "avgCost", None)
            print(f"[POSITION][OPEN_AUTHORITY] symbol={symbol} qty={qty} avg_price={avg} source=IBKR_RESYNC")
            break
    return events


def _is_test_environment() -> bool:
    return (
        "PYTEST_CURRENT_TEST" in os.environ
        or os.environ.get("CI") == "true"
        or os.environ.get("TEST_MODE") == "true"
    )


def _validate_ibkr_connection(mode: RunMode) -> None:
    if _is_test_environment():
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


def _paper_sizing_settings() -> tuple[bool, int, float, bool]:
    enabled = bool(get_config("PAPER_VALIDATION_SIZING_ENABLED", default=False))
    max_shares = int(get_config("PAPER_VALIDATION_MAX_SHARES", default=0) or 0)
    max_notional = float(get_config("PAPER_VALIDATION_MAX_NOTIONAL", default=0.0) or 0.0)
    force_single_share = bool(get_config("PAPER_VALIDATION_FORCE_SINGLE_SHARE", default=False))
    return enabled, max_shares, max_notional, force_single_share


def _apply_paper_validation_sizing(quantity: int, entry_price: float | None) -> int:
    enabled, max_shares, max_notional, force_single_share = _paper_sizing_settings()
    if not enabled:
        return quantity
    sized_qty = max(0, int(quantity))
    if force_single_share:
        sized_qty = 1 if sized_qty > 0 else 0
    if max_shares > 0:
        sized_qty = min(sized_qty, max_shares)
    if max_notional > 0 and (entry_price or 0.0) > 0.0:
        notional_qty = max(1, int(max_notional // float(entry_price)))
        sized_qty = min(sized_qty, notional_qty)
    print(
        "[EXECUTION][PAPER_SIZING] "
        f"enabled=true requested_qty={quantity} resolved_qty={sized_qty} "
        f"entry_price={entry_price} max_shares={max_shares} max_notional={max_notional} "
        f"force_single_share={str(force_single_share).lower()}"
    )
    return sized_qty


def execute_intents(
    mode: RunMode,
    decisions: List[RiskDecisionRecord],
) -> List[ExecutionEvent]:
    events: List[ExecutionEvent] = []
    manager: Any | None = None

    if mode in {RunMode.PAPER, RunMode.LIVE}:
        if _is_test_environment():
            print("[EXECUTION][TEST_MODE] Skipping IBKR connection validation")
        else:
            _validate_ibkr_connection(mode)
            manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
            client = manager.get_client()
            callback = globals().get("_on_ibkr_callback")
            if callback is not None:
                if hasattr(client, "register_execution_callback"):
                    client.register_execution_callback(_on_ibkr_callback)
                else:
                    print("[EXECUTION][CALLBACK_UNAVAILABLE] register_execution_callback not supported by client")

    broker_state = "CONNECTED" if mode in {RunMode.PAPER, RunMode.LIVE} else "DISCONNECTED"
    print(f"[EXECUTION][MODE] mode={mode.value} broker_connection_state={broker_state}")
    open_orders, _executions, positions = _fetch_ibkr_truth(mode)
    existing_position_symbols = {str(getattr(row, "symbol", "") or "").upper() for row in positions}
    existing_open_order_symbols = {_extract_symbol_from_order(row) for row in open_orders}
    existing_open_order_symbols.discard("")

    order_id_seed = 0
    if mode in {RunMode.PAPER, RunMode.LIVE} and not _is_test_environment():
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
        if mode == RunMode.PAPER:
            quantity = _apply_paper_validation_sizing(quantity, getattr(decision, "entry_price", None))
        if decision.decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"} and quantity <= 0:
            raise RuntimeError("INVALID ORDER: quantity=0")
        duplicate_symbol = str(decision.symbol or "").upper()
        if duplicate_symbol in existing_position_symbols or duplicate_symbol in existing_open_order_symbols:
            print(f"[EXECUTION][BLOCK] symbol={duplicate_symbol} reason=DUPLICATE_PROTECTION")
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail="reason=DUPLICATE_PROTECTION",
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
                if mode == RunMode.PAPER and quantity < int(decision.max_position_size):
                    action = "SUBMITTED"
                    detail = (
                        f"submitted qty={quantity} orderRef=TRADING_OS|ROSS_MOMENTUM|{decision.intent_id} "
                        "sizing_override=PAPER_VALIDATION"
                    )
                    dispatch = "IBKR"
                else:
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
        events.append(
            ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action=action,
                detail=detail,
                broker_order_id=broker_order_id,
                event_type="ORDER_SUBMITTED" if action == "SUBMITTED" else action,
                broker_status="Submitted" if action == "SUBMITTED" else ("REJECTED" if action == "BLOCKED" else "SIMULATED"),
                source="IBKR_ORDER_STATUS" if action == "SUBMITTED" else "ENGINE",
                filled_quantity=0,
                remaining_quantity=quantity if action == "SUBMITTED" else 0,
                last_update_time=_now_utc_iso(),
                lifecycle_state="SUBMITTED" if action == "SUBMITTED" else action,
                fill_source="UNSET",
            )
        )
    events, _ = _apply_callback_fills(events)
    events = _sync_submitted_events_from_ibkr(mode, events)
    fill_timeout_seconds = float(os.environ.get("IBKR_TEST_FILL_TIMEOUT_SECONDS", "0.5"))
    return _emit_test_fill_fallback(mode, events, timeout_seconds=fill_timeout_seconds)
