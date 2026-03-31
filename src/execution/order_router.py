"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, List

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
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
        source="IBKR",
        broker_order_id=order_id,
        filled_quantity=max(0, filled_qty),
        remaining_quantity=0,
        broker_status="Filled",
        avg_fill_price=fill_price,
        last_update_time=timestamp,
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
        event.event_type = "ORDER_FILLED"
        event.source = callback_fill.source
        event.broker_status = "Filled"
        event.filled_quantity = int(callback_fill.filled_quantity or 0)
        base_remaining = int(event.remaining_quantity or 0)
        event.remaining_quantity = max(0, base_remaining - event.filled_quantity)
        event.avg_fill_price = callback_fill.avg_fill_price
        event.last_update_time = callback_fill.last_update_time or _now_utc_iso()
        fills_applied += 1
    return events, fills_applied


def _is_explicit_test_mode() -> bool:
    return os.getenv("EXECUTION_ENV", "").upper() == "TEST"


def _is_valid_fill_price(price: float | None) -> bool:
    try:
        return price is not None and float(price) > 0.0
    except (TypeError, ValueError):
        return False


def _emit_test_fill_fallback(mode: RunMode, events: List[ExecutionEvent], timeout_seconds: float) -> List[ExecutionEvent]:
    if mode != RunMode.PAPER:
        return events
    if os.getenv("IBKR_ENABLE_TEST_ONLY_FILL", "").lower() != "true":
        return events
    explicit_test_mode_flag = _is_explicit_test_mode()
    if not explicit_test_mode_flag:
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
        event.source = "TEST_FILL"
        event.broker_status = "Filled"
        event.filled_quantity = synthetic_qty
        event.remaining_quantity = 0
        event.last_update_time = _now_utc_iso()
        print(
            "[EXECUTION][EVENT_CREATED] "
            f"event_type={event.event_type} source={event.source} symbol={event.symbol} "
            f"order_id={event.broker_order_id} filled_qty={event.filled_quantity} fill_price={event.avg_fill_price}"
        )
    return events


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
    if not events:
        return events
    open_orders, executions, positions = _fetch_ibkr_truth(mode)
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
        event.event_type = "ORDER_FILLED"
        event.source = "IBKR"
        event.broker_status = "Filled"
        event.filled_quantity = _extract_exec_qty(match)
        event.remaining_quantity = max(0, int(event.remaining_quantity or 0))
        event.avg_fill_price = _extract_exec_price(match)
        if not _is_valid_fill_price(event.avg_fill_price):
            raise RuntimeError("INVALID_POSITION_OPEN_NON_AUTHORITATIVE")
        print(
            f"[EXECUTION][FILL] symbol={event.symbol} qty={event.filled_quantity} "
            f"price={event.avg_fill_price if event.avg_fill_price is not None else 'UNKNOWN'}"
        )
        for position in positions:
            symbol = str(getattr(position, "symbol", "") or "").upper()
            if symbol != str(event.symbol or "").upper():
                continue
            qty = int(getattr(position, "position", 0) or 0)
            avg = getattr(position, "avgCost", None)
            if not _is_valid_fill_price(float(avg) if avg is not None else None):
                raise RuntimeError("INVALID_POSITION_OPEN_NON_AUTHORITATIVE")
            print(f"[POSITION][OPEN_AUTHORITY] symbol={symbol} qty={qty} avg_price={avg}")
            break
    return events


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
    events: List[ExecutionEvent] = []
    manager: Any | None = None

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
                else:
                    print("[EXECUTION][CALLBACK_UNAVAILABLE] register_execution_callback not supported by client")

    broker_state = "CONNECTED" if mode in {RunMode.PAPER, RunMode.LIVE} else "DISCONNECTED"
    print(f"[EXECUTION][MODE] mode={mode.value} broker_connection_state={broker_state}")
    open_orders, _executions, positions = _fetch_ibkr_truth(mode)
    existing_position_symbols = {str(getattr(row, "symbol", "") or "").upper() for row in positions}
    existing_open_order_symbols = {_extract_symbol_from_order(row) for row in open_orders}
    existing_open_order_symbols.discard("")

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
                source="IBKR" if action == "SUBMITTED" else "ENGINE",
                filled_quantity=0,
                remaining_quantity=quantity if action == "SUBMITTED" else 0,
                last_update_time=_now_utc_iso(),
            )
        )
    events, _ = _apply_callback_fills(events)
    events = _sync_submitted_events_from_ibkr(mode, events)
    if not _is_explicit_test_mode():
        for event in events:
            if str(getattr(event, "source", "")).upper() == "TEST_FILL":
                print("[FATAL] TEST_FILL DETECTED IN NON-TEST EXECUTION")
                raise RuntimeError("TEST_FILL_LEAK")
    fill_timeout_seconds = float(os.environ.get("IBKR_TEST_FILL_TIMEOUT_SECONDS", "0.5"))
    return _emit_test_fill_fallback(mode, events, timeout_seconds=fill_timeout_seconds)
