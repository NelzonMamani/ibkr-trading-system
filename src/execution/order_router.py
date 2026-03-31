"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.config.runtime_config import resolve_ibkr_connection
from src.core_engine.events import ExecutionEvent, RiskDecisionRecord
from src.core_engine.state import RunMode


@dataclass(frozen=True)
class RouterAccountSnapshot:
    available_funds: float


def _validate_ibkr_connection(mode: RunMode) -> None:
    if mode not in {RunMode.PAPER, RunMode.LIVE}:
        return

    expected_host, expected_port, expected_client_id, _ = resolve_ibkr_connection()
    required_port = 7497 if mode == RunMode.PAPER else 7496
    manager = get_shared_ibkr_connection_manager(readonly_enabled=False)

    try:
        client = manager.ensure_connected()
        metadata = manager.connection_metadata()
    except Exception:
        print("[EXECUTION][BLOCK] reason=IBKR_NOT_CONNECTED")
        raise RuntimeError("IBKR connection is not active or misconfigured")

    connected = bool(metadata.get("connected")) and bool(client.is_connected())
    active_port = int(metadata.get("port") or 0)
    configured_client_id = int(metadata.get("base_client_id") or -1)
    connected_client_id = int(metadata.get("connected_client_id") or -1)

    print(
        "[TRACE][stage=broker_connection] "
        f"mode={mode.value} host={expected_host} port={active_port} "
        f"configured_port={expected_port} required_port={required_port} "
        f"client_id={configured_client_id} connected_client_id={connected_client_id} "
        f"connected={connected}"
    )

    misconfigured = (
        not connected
        or active_port != required_port
        or configured_client_id != expected_client_id
        or connected_client_id != expected_client_id
    )
    if misconfigured:
        print("[EXECUTION][BLOCK] reason=IBKR_NOT_CONNECTED")
        raise RuntimeError("IBKR connection is not active or misconfigured")


def execute_intents(
    mode: RunMode,
    decisions: List[RiskDecisionRecord],
) -> List[ExecutionEvent]:
    events: List[ExecutionEvent] = []
    _validate_ibkr_connection(mode)
    broker_state = "CONNECTED" if mode in {RunMode.PAPER, RunMode.LIVE} else "DISCONNECTED"
    print(f"[EXECUTION][MODE] mode={mode.value} broker_connection_state={broker_state}")
    for decision in decisions:
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
                detail = f"submitted qty={quantity}"
                dispatch = "IBKR" if mode in {RunMode.PAPER, RunMode.LIVE} else "SKIPPED"
        elif decision.decision == "ALLOW_WITH_CONSTRAINTS":
            action = "BLOCKED" if mode == RunMode.LIVE else "WOULD_PLACE"
            detail = f"constraints={decision.constraints}; qty={quantity}"
            dispatch = "SKIPPED" if mode == RunMode.LIVE else "IBKR"
        else:
            action = "BLOCKED"
            detail = f"decision={decision.decision}; reason={decision.block_reason or 'RISK_BLOCK'}"
            dispatch = "SKIPPED"
        print(f"[EXECUTION][DISPATCH] symbol={decision.symbol} dispatch={dispatch}")
        order_id = f"{decision.intent_id}-IBKR"
        if dispatch == "IBKR" and action == "SUBMITTED":
            print(f"[IBKR][ORDER_ACK] order_id={order_id} status=Submitted")
        elif dispatch == "IBKR" and action != "SUBMITTED":
            print(
                f"[IBKR][ORDER_REJECT] order_id={order_id} symbol={decision.symbol} "
                f"reason={decision.block_reason or decision.decision}"
            )
        events.append(
            ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action=action,
                detail=detail,
            )
        )
    return events
