"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, List

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.core_engine.events import ExecutionEvent, RiskDecisionRecord
from src.execution.execution_authority import ExecutionAuthority
from src.storage.storage_engine import StorageEngine
from src.core_engine.state import RunMode




_AUTHORITY: ExecutionAuthority | None = None
_CALLBACK_EVENTS: list[tuple[str, dict[str, Any]]] = []


def _on_ibkr_callback(event_type: str, payload: dict[str, Any]) -> None:
    _CALLBACK_EVENTS.append((event_type, payload))


def _drain_callbacks(events: List[ExecutionEvent]) -> None:
    authority = _get_authority()
    by_local = {e.local_submission_id: e for e in events if e.local_submission_id}
    while _CALLBACK_EVENTS:
        event_type, payload = _CALLBACK_EVENTS.pop(0)
        if event_type == "order_status":
            ev = authority.apply_order_status(payload, source="ibkr_order_status_callback")
            if ev and ev.local_submission_id in by_local:
                current = by_local[ev.local_submission_id]
                current.broker_order_id = ev.broker_order_id
                current.broker_status = "Filled" if ev.broker_status == "FILLED" else ev.broker_status
                current.filled_quantity = ev.filled_quantity
                current.remaining_quantity = ev.remaining_quantity
                current.last_update_time = ev.last_update_time
                print(f"[EXECUTION][BROKER_ACK] symbol={current.symbol} broker_order_id={current.broker_order_id} state={current.broker_status}")
        elif event_type == "execution":
            ev, _ = authority.apply_fill(payload, source="ibkr_execution_callback")
            if ev and ev.local_submission_id in by_local:
                current = by_local[ev.local_submission_id]
                current.broker_order_id = ev.broker_order_id
                current.broker_status = "Filled" if ev.broker_status == "FILLED" else ev.broker_status
                current.filled_quantity = ev.filled_quantity
                current.remaining_quantity = ev.remaining_quantity
                current.avg_fill_price = ev.avg_fill_price
                current.exec_id = ev.exec_id


def _get_authority() -> ExecutionAuthority:
    global _AUTHORITY
    if _AUTHORITY is None:
        try:
            _AUTHORITY = ExecutionAuthority(persistence_adapter=StorageEngine())
        except Exception:
            _AUTHORITY = ExecutionAuthority(persistence_adapter=None)
    return _AUTHORITY
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
    _open_orders, executions, positions = _fetch_ibkr_truth(mode)
    authority = _get_authority()
    by_local_id: dict[str, ExecutionEvent] = {
        e.local_submission_id: e for e in events if e.local_submission_id
    }
    unmatched_local_ids = [e.local_submission_id for e in events if e.action == "SUBMITTED" and e.local_submission_id]
    for row in executions:
        order_id = _extract_exec_order_id(row)
        if order_id is None:
            continue
        local_submission_id = unmatched_local_ids[0] if unmatched_local_ids else None
        status_event = authority.apply_order_status(
            {
                "local_submission_id": local_submission_id,
                "order_id": order_id,
                "status": "Submitted",
                "filled": _extract_exec_qty(row),
                "remaining": 0,
                "avg_fill_price": _extract_exec_price(row),
            },
            source="reconciliation",
        )
        if status_event and status_event.local_submission_id in by_local_id:
            current = by_local_id[status_event.local_submission_id]
            current.broker_order_id = status_event.broker_order_id
            current.broker_status = status_event.broker_status
        fill_event, _position_event = authority.apply_fill(
            {
                "local_submission_id": local_submission_id,
                "order_id": order_id,
                "exec_id": getattr(row, "execId", None),
                "fill_qty": _extract_exec_qty(row),
                "cumulative_qty": _extract_exec_qty(row),
                "fill_price": _extract_exec_price(row),
                "avg_fill_price": _extract_exec_price(row),
            },
            source="reconciliation",
        )
        if fill_event and fill_event.local_submission_id in by_local_id:
            current = by_local_id[fill_event.local_submission_id]
            current.filled_quantity = fill_event.filled_quantity
            current.avg_fill_price = fill_event.avg_fill_price
            current.remaining_quantity = fill_event.remaining_quantity
            current.broker_status = "Filled" if fill_event.broker_status == "FILLED" else fill_event.broker_status
            current.broker_order_id = fill_event.broker_order_id
            print(
                f"[EXECUTION][FILL] symbol={current.symbol} qty={fill_event.filled_quantity} "
                f"price={fill_event.avg_fill_price if fill_event.avg_fill_price is not None else 'UNKNOWN'}"
            )
            print(
                f"[EXECUTION][FILL_CALLBACK] symbol={current.symbol} fill_qty={fill_event.filled_quantity} "
                f"avg_fill_price={fill_event.avg_fill_price} lifecycle_source=reconciliation"
            )
    for position in positions:
        symbol = str(getattr(position, "symbol", "") or "").upper()
        qty = int(getattr(position, "position", 0) or 0)
        avg = getattr(position, "avgCost", None)
        if qty != 0:
            print(f"[EXECUTION][RECONCILE] symbol={symbol} broker_qty={qty} broker_avg={avg}")
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


def execute_intents(
    mode: RunMode,
    decisions: List[RiskDecisionRecord],
) -> List[ExecutionEvent]:
    events: List[ExecutionEvent] = []

    if mode in {RunMode.PAPER, RunMode.LIVE}:
        if _is_test_environment():
            print("[EXECUTION][TEST_MODE] Skipping IBKR connection validation")
        else:
            _validate_ibkr_connection(mode)
            manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
            manager.get_client().register_execution_callback(_on_ibkr_callback)

    broker_state = "CONNECTED" if mode in {RunMode.PAPER, RunMode.LIVE} else "DISCONNECTED"
    print(f"[EXECUTION][MODE] mode={mode.value} broker_connection_state={broker_state}")
    open_orders, _executions, positions = _fetch_ibkr_truth(mode)
    existing_position_symbols = {str(getattr(row, "symbol", "") or "").upper() for row in positions}
    existing_open_order_symbols = {_extract_symbol_from_order(row) for row in open_orders}
    existing_open_order_symbols.discard("")


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
        if action == "SUBMITTED":
            authority = _get_authority()
            local_submission_id = f"{decision.intent_id}:{index}:{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            submit_event = authority.register_submit_request(
                decision,
                local_submission_id=local_submission_id,
                source="local_submit",
            )
            submit_event.action = "SUBMITTED"
            submit_event.detail = detail
            submit_event.broker_status = "SUBMITTING"
            submit_event.last_update_time = _now_utc_iso()
            print(
                f"[EXECUTION][SUBMIT_REQUEST] symbol={decision.symbol} intent_id={decision.intent_id} "
                f"local_submission_id={local_submission_id} broker_order_id=PENDING"
            )
            events.append(submit_event)
        else:
            events.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action=action,
                    detail=detail,
                    broker_status="REJECTED" if action == "BLOCKED" else "SIMULATED",
                    last_update_time=_now_utc_iso(),
                )
            )
    _drain_callbacks(events)
    return _sync_submitted_events_from_ibkr(mode, events)
