from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.core_engine.events import ExecutionEvent, RiskDecisionRecord


TERMINAL_STATES = {"FILLED", "CANCELLED", "REJECTED", "INACTIVE", "EXPIRED", "ERROR"}


_ORDER_STATE_RANK = {
    "CREATED": 0,
    "SUBMITTING": 1,
    "SUBMITTED": 2,
    "PARTIALLY_FILLED": 3,
    "FILLED": 4,
    "CANCEL_PENDING": 5,
    "CANCELLED": 6,
    "REJECTED": 6,
    "INACTIVE": 6,
    "EXPIRED": 6,
    "ERROR": 7,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_ibkr_status(raw_status: str) -> str:
    status = (raw_status or "").upper()
    if status in {"PRESUBMITTED", "SUBMITTED", "APIPENDING", "PENDINGSUBMIT"}:
        return "SUBMITTED"
    if status in {"PARTIAL", "PARTIALLYFILLED"}:
        return "PARTIALLY_FILLED"
    if status == "FILLED":
        return "FILLED"
    if status in {"PENDINGCANCEL", "APICANCELLED"}:
        return "CANCEL_PENDING"
    if status == "CANCELLED":
        return "CANCELLED"
    if status in {"INACTIVE"}:
        return "INACTIVE"
    return "SUBMITTED"


@dataclass
class ExecutionOrderRecord:
    local_submission_id: str
    intent_id: str
    symbol: str
    side: str
    requested_qty: int
    order_ref: str
    strategy_name: str | None = None
    broker_order_id: int | None = None
    perm_id: int | None = None
    state: str = "CREATED"
    filled_quantity: int = 0
    remaining_quantity: int = 0
    avg_fill_price: float | None = None
    updated_at: str = field(default_factory=_now_iso)
    created_at: str = field(default_factory=_now_iso)


@dataclass
class PositionRecord:
    symbol: str
    strategy_name: str | None
    net_qty: int = 0
    avg_entry: float = 0.0
    realized_pnl: float = 0.0


class ExecutionAuthority:
    def __init__(self, persistence_adapter: Any | None = None) -> None:
        self._orders: dict[str, ExecutionOrderRecord] = {}
        self._orders_by_broker_id: dict[int, str] = {}
        self._positions: dict[tuple[str, str | None], PositionRecord] = {}
        self._seen_exec_ids: set[str] = set()
        self._seen_cum_qty: set[tuple[int, int]] = set()
        self._persistence = persistence_adapter

    def register_submit_request(self, decision: RiskDecisionRecord, *, local_submission_id: str, source: str = "local_submit") -> ExecutionEvent:
        order_ref = f"TRADING_OS|ROSS_MOMENTUM|{decision.intent_id}"
        record = ExecutionOrderRecord(
            local_submission_id=local_submission_id,
            intent_id=decision.intent_id,
            symbol=decision.symbol,
            side="BUY",
            requested_qty=int(decision.approved_quantity),
            order_ref=order_ref,
            strategy_name="ROSS_MOMENTUM",
            state="SUBMITTING",
            remaining_quantity=int(decision.approved_quantity),
        )
        self._orders[local_submission_id] = record
        self._persist_order(record, source=source)
        return self._to_event(record, action="SUBMITTING", source=source, detail=f"submit_request qty={record.requested_qty} orderRef={order_ref}")

    def apply_order_status(self, payload: dict[str, Any], *, source: str = "ibkr_order_status_callback") -> ExecutionEvent | None:
        broker_order_id = payload.get("order_id")
        raw_status = str(payload.get("status") or "")
        next_state = _map_ibkr_status(raw_status)
        record = self._resolve_order(payload)
        if record is None:
            return None
        if broker_order_id is not None:
            record.broker_order_id = int(broker_order_id)
            self._orders_by_broker_id[int(broker_order_id)] = record.local_submission_id
        if payload.get("perm_id") is not None:
            record.perm_id = int(payload["perm_id"])
        filled = int(payload.get("filled") or 0)
        remaining = int(payload.get("remaining") or max(0, record.requested_qty - filled))
        avg = payload.get("avg_fill_price")
        if avg is not None:
            record.avg_fill_price = float(avg)
        record.filled_quantity = max(record.filled_quantity, filled)
        record.remaining_quantity = remaining
        state_before = record.state
        if self._is_transition_valid(state_before, next_state):
            record.state = next_state
        else:
            print(f"[EXECUTION][ERROR] invalid_transition state_before={state_before} state_after={next_state} source={source}")
        record.updated_at = _now_iso()
        self._persist_order(record, source=source, raw_status=raw_status)
        print(f"[EXECUTION][ORDER_STATUS] symbol={record.symbol} state_before={state_before} state_after={record.state} broker_order_id={record.broker_order_id} lifecycle_source={source}")
        return self._to_event(record, action=record.state, source=source, detail=f"order_status={raw_status}")

    def apply_fill(self, payload: dict[str, Any], *, source: str = "ibkr_execution_callback") -> tuple[ExecutionEvent | None, dict[str, Any] | None]:
        record = self._resolve_order(payload)
        if record is None:
            return None, None
        exec_id = str(payload.get("exec_id") or "").strip() or None
        if exec_id and exec_id in self._seen_exec_ids:
            return None, None
        fill_qty = int(payload.get("fill_qty") or 0)
        if fill_qty <= 0:
            return None, None
        cumulative_qty = int(payload.get("cumulative_qty") or (record.filled_quantity + fill_qty))
        dedupe_key = None
        if record.broker_order_id is not None:
            dedupe_key = (record.broker_order_id, cumulative_qty)
            if dedupe_key in self._seen_cum_qty:
                return None, None
        if exec_id:
            self._seen_exec_ids.add(exec_id)
        if dedupe_key:
            self._seen_cum_qty.add(dedupe_key)
        fill_price = payload.get("fill_price")
        avg_fill_price = payload.get("avg_fill_price")
        if avg_fill_price is None and fill_price is not None:
            avg_fill_price = fill_price
        state_before = record.state
        record.filled_quantity = max(record.filled_quantity, cumulative_qty)
        record.remaining_quantity = max(0, record.requested_qty - record.filled_quantity)
        if avg_fill_price is not None:
            record.avg_fill_price = float(avg_fill_price)
        record.state = "FILLED" if record.remaining_quantity == 0 else "PARTIALLY_FILLED"
        record.updated_at = _now_iso()
        self._persist_order(record, source=source)
        self._persist_fill(record, payload, source=source)
        position_event = self._apply_position_fill(record=record, fill_qty=fill_qty, fill_price=float(fill_price or avg_fill_price or 0.0), exec_id=exec_id, source=source)
        print(f"[EXECUTION][FILL_APPLIED] symbol={record.symbol} broker_order_id={record.broker_order_id} fill_qty={fill_qty} cumulative_qty={record.filled_quantity} state_before={state_before} state_after={record.state} lifecycle_source={source}")
        return self._to_event(record, action=record.state, source=source, detail="fill_applied", exec_id=exec_id), position_event

    def _apply_position_fill(self, *, record: ExecutionOrderRecord, fill_qty: int, fill_price: float, exec_id: str | None, source: str) -> dict[str, Any] | None:
        if fill_qty <= 0:
            return None
        key = (record.symbol.upper(), record.strategy_name)
        pos = self._positions.get(key)
        action = "OPEN"
        if pos is None:
            pos = PositionRecord(symbol=record.symbol.upper(), strategy_name=record.strategy_name)
            self._positions[key] = pos
        qty_before = pos.net_qty
        avg_before = pos.avg_entry
        if record.side.upper() == "BUY":
            new_qty = qty_before + fill_qty
            pos.avg_entry = ((qty_before * avg_before) + (fill_qty * fill_price)) / new_qty if new_qty > 0 else 0.0
            pos.net_qty = new_qty
            action = "OPEN" if qty_before == 0 else "ADD"
        else:
            new_qty = max(0, qty_before - fill_qty)
            pos.realized_pnl += (fill_price - avg_before) * min(fill_qty, qty_before)
            pos.net_qty = new_qty
            action = "CLOSE" if new_qty == 0 else "REDUCE"
        self._persist_position(record, pos, action=action, exec_id=exec_id, source=source)
        log_action = {"OPEN": "POSITION_OPEN", "ADD": "POSITION_ADD", "REDUCE": "POSITION_REDUCE", "CLOSE": "POSITION_CLOSE"}[action]
        print(f"[EXECUTION][{log_action}] symbol={record.symbol} quantity_after={pos.net_qty} avg_entry_after={pos.avg_entry} lifecycle_source={source}")
        return {"action": action, "symbol": record.symbol, "quantity_after": pos.net_qty, "avg_entry_after": pos.avg_entry}

    def _is_transition_valid(self, state_before: str, state_after: str) -> bool:
        if state_before == state_after:
            return True
        if state_before in TERMINAL_STATES:
            return False
        return _ORDER_STATE_RANK.get(state_after, -1) >= _ORDER_STATE_RANK.get(state_before, -1)

    def _resolve_order(self, payload: dict[str, Any]) -> ExecutionOrderRecord | None:
        local_submission_id = payload.get("local_submission_id")
        if local_submission_id and local_submission_id in self._orders:
            return self._orders[local_submission_id]
        broker_order_id = payload.get("order_id")
        if broker_order_id is not None:
            local = self._orders_by_broker_id.get(int(broker_order_id))
            if local:
                return self._orders[local]
        order_ref = str(payload.get("order_ref") or "")
        if order_ref:
            for order in self._orders.values():
                if order.order_ref == order_ref:
                    return order
        return None

    def _to_event(self, record: ExecutionOrderRecord, *, action: str, source: str, detail: str, exec_id: str | None = None) -> ExecutionEvent:
        return ExecutionEvent(
            symbol=record.symbol,
            intent_id=record.intent_id,
            action=action,
            detail=detail,
            broker_order_id=record.broker_order_id,
            filled_quantity=record.filled_quantity,
            remaining_quantity=record.remaining_quantity,
            broker_status=record.state,
            avg_fill_price=record.avg_fill_price,
            last_update_time=record.updated_at,
            local_submission_id=record.local_submission_id,
            order_ref=record.order_ref,
            lifecycle_source=source,
            exec_id=exec_id,
            perm_id=record.perm_id,
        )

    def _persist_order(self, record: ExecutionOrderRecord, *, source: str, raw_status: str | None = None) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.upsert_execution_order(
                {
                    "local_submission_id": record.local_submission_id,
                    "broker_order_id": record.broker_order_id,
                    "order_ref": record.order_ref,
                    "intent_id": record.intent_id,
                    "strategy_name": record.strategy_name,
                    "symbol": record.symbol,
                    "side": record.side,
                    "requested_qty": record.requested_qty,
                    "lifecycle_state": record.state,
                    "raw_broker_status": raw_status,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    "lifecycle_source": source,
                    "perm_id": record.perm_id,
                }
            )
            print(f"[EXECUTION][PERSIST] type=order local_submission_id={record.local_submission_id} broker_order_id={record.broker_order_id}")
        except Exception as exc:
            print(f"[EXECUTION][ERROR] stage=persist_order error={exc}")

    def _persist_fill(self, record: ExecutionOrderRecord, payload: dict[str, Any], *, source: str) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.insert_execution_fill(
                {
                    "broker_order_id": record.broker_order_id,
                    "exec_id": payload.get("exec_id"),
                    "perm_id": payload.get("perm_id") or record.perm_id,
                    "symbol": record.symbol,
                    "side": record.side,
                    "fill_qty": int(payload.get("fill_qty") or 0),
                    "cumulative_qty": int(payload.get("cumulative_qty") or record.filled_quantity),
                    "fill_price": payload.get("fill_price"),
                    "avg_fill_price": payload.get("avg_fill_price") or record.avg_fill_price,
                    "timestamp": payload.get("timestamp") or _now_iso(),
                    "source": source,
                }
            )
            print(f"[EXECUTION][PERSIST] type=fill broker_order_id={record.broker_order_id} exec_id={payload.get('exec_id')}")
        except Exception as exc:
            print(f"[EXECUTION][ERROR] stage=persist_fill error={exc}")

    def _persist_position(self, record: ExecutionOrderRecord, position: PositionRecord, *, action: str, exec_id: str | None, source: str) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.insert_execution_position_lifecycle(
                {
                    "symbol": record.symbol,
                    "strategy_name": record.strategy_name,
                    "action": action,
                    "quantity_after": position.net_qty,
                    "avg_entry_after": position.avg_entry,
                    "realized_pnl_delta": position.realized_pnl,
                    "causal_exec_id": exec_id,
                    "timestamp": _now_iso(),
                    "source": source,
                }
            )
            print(f"[EXECUTION][PERSIST] type=position action={action} symbol={record.symbol}")
        except Exception as exc:
            print(f"[EXECUTION][ERROR] stage=persist_position error={exc}")
