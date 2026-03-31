"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import List

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.core_engine.events import ExecutionEvent, RiskDecisionRecord
from src.core_engine.state import RunMode


@dataclass(frozen=True)
class RouterAccountSnapshot:
    available_funds: float


def _is_test_environment() -> bool:
    return (
        "PYTEST_CURRENT_TEST" in os.environ
        or os.environ.get("CI") == "true"
        or os.environ.get("TEST_MODE") == "true"
    )


def _validate_ibkr_connection(mode: RunMode) -> None:
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


def _build_ibkr_contract(symbol: str):
    return SimpleNamespace(symbol=symbol)


def _build_ibkr_order(decision: RiskDecisionRecord):
    side = "BUY" if str(getattr(decision, "side", "LONG")).upper() in {"LONG", "BUY"} else "SELL"
    return SimpleNamespace(
        action=side,
        totalQuantity=int(decision.approved_quantity),
        orderType="MKT",
        tif="DAY",
        orderRef=decision.intent_id,
    )


def _submit_ibkr_order(mode: RunMode, decision: RiskDecisionRecord) -> ExecutionEvent:
    manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
    client = manager.get_client()
    contract = _build_ibkr_contract(decision.symbol)
    order = _build_ibkr_order(decision)

    # Canonical broker_order_id authority enters here from the live IBKR session (nextValidId -> placeOrder).
    broker_order_id = client.submit_order(contract, order)
    if broker_order_id is None:
        return ExecutionEvent(
            symbol=decision.symbol,
            intent_id=decision.intent_id,
            action="BLOCKED",
            detail="missing_broker_order_id",
            broker_status="REJECTED",
            submitted=False,
            broker_acknowledged=False,
            lifecycle_tracking_ready=False,
            dispatch_target="IBKR",
            reason_code="missing_broker_order_id",
        )

    working = client.get_working_order(broker_order_id) if hasattr(client, "get_working_order") else None
    status_payload = client.wait_for_order_status(broker_order_id, timeout_seconds=2)
    broker_status = str((status_payload or {}).get("status") or (working or {}).get("status") or "PendingSubmit")
    filled_quantity = int((status_payload or {}).get("filled") or 0)
    remaining_quantity = int((status_payload or {}).get("remaining") or int(decision.approved_quantity))
    broker_acknowledged = status_payload is not None
    return ExecutionEvent(
        symbol=decision.symbol,
        intent_id=decision.intent_id,
        action="SUBMITTED",
        detail="submitted_to_ibkr",
        broker_order_id=broker_order_id,
        filled_quantity=filled_quantity,
        remaining_quantity=remaining_quantity,
        broker_status=broker_status,
        submitted=True,
        broker_acknowledged=broker_acknowledged,
        lifecycle_tracking_ready=working is not None,
        dispatch_target="IBKR",
        reason_code="submitted_to_ibkr",
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
                        broker_status="REJECTED",
                        reason_code="invalid_entry_price",
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
                        reason_code="invalid_price_sanity_check",
                    )
                )
                continue

        dispatch = "SKIPPED"
        if mode in {RunMode.SIM, RunMode.READ_ONLY}:
            event = ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action="WOULD_PLACE",
                detail=f"mode={mode.value}; decision={decision.decision}; qty={quantity}",
                broker_status="SIMULATED",
                submitted=False,
                broker_acknowledged=False,
                lifecycle_tracking_ready=False,
                dispatch_target="SKIPPED",
                reason_code="execution_disabled",
            )
            dispatch = "SKIPPED"
        elif decision.decision == "ALLOW":
            if mode == RunMode.LIVE and decision.capital_source != "IBKR_CANONICAL":
                event = ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail="reason=CANONICAL_CAPITAL_UNAVAILABLE",
                    broker_status="REJECTED",
                    dispatch_target="SKIPPED",
                    reason_code="insufficient_capital",
                )
            elif quantity != int(decision.max_position_size):
                event = ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail=(
                        "reason=EXECUTION_QUANTITY_MISMATCH "
                        f"approved={decision.approved_quantity} max_size={decision.max_position_size}"
                    ),
                    broker_status="REJECTED",
                    dispatch_target="SKIPPED",
                    reason_code="broker_rejected",
                )
            else:
                dispatch = "IBKR"
                event = _submit_ibkr_order(mode, decision)
        elif decision.decision == "ALLOW_WITH_CONSTRAINTS":
            event = ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action="BLOCKED" if mode == RunMode.LIVE else "WOULD_PLACE",
                detail=f"constraints={decision.constraints}; qty={quantity}",
                dispatch_target="SKIPPED" if mode == RunMode.LIVE else "IBKR",
                reason_code="execution_disabled" if mode == RunMode.LIVE else "constraints_present",
            )
            dispatch = "SKIPPED" if mode == RunMode.LIVE else "IBKR"
        else:
            event = ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action="BLOCKED",
                detail=f"decision={decision.decision}; reason={decision.block_reason or 'RISK_BLOCK'}",
                broker_status="REJECTED",
                dispatch_target="SKIPPED",
                reason_code="broker_rejected",
            )
        print(f"[EXECUTION][DISPATCH] symbol={decision.symbol} dispatch={dispatch}")
        events.append(event)
    return events
