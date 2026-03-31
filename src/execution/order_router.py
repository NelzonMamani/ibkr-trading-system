"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

import os
from dataclasses import dataclass
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
            order_id = None
            order_id_status = "NOT_APPLICABLE"
            certification_state = "MODE_NO_BROKER_SUBMIT"
        elif decision.decision == "ALLOW":
            if mode == RunMode.LIVE and decision.capital_source != "IBKR_CANONICAL":
                action = "BLOCKED"
                detail = "reason=CANONICAL_CAPITAL_UNAVAILABLE"
                dispatch = "SKIPPED"
                order_id = None
                order_id_status = "NOT_APPLICABLE"
                certification_state = "BLOCKED_CAPITAL_AUTHORITY"
            elif quantity != int(decision.max_position_size):
                action = "BLOCKED"
                detail = (
                    "reason=EXECUTION_QUANTITY_MISMATCH "
                    f"approved={decision.approved_quantity} max_size={decision.max_position_size}"
                )
                dispatch = "SKIPPED"
                order_id = None
                order_id_status = "NOT_APPLICABLE"
                certification_state = "BLOCKED_QUANTITY_MISMATCH"
            else:
                action = "SUBMITTED"
                detail = f"submitted qty={quantity}"
                dispatch = "IBKR"
                order_id = None
                order_id_status = "UNRESOLVED"
                certification_state = "FAILED_ORDER_TRACKING"
                print(
                    "[IBKR][ORDER][SUBMITTED] "
                    f"symbol={decision.symbol} order_id=UNRESOLVED qty={quantity}"
                )
                print(
                    "[IBKR][ORDER][STATUS] "
                    f"symbol={decision.symbol} status=SUBMITTED order_id_status={order_id_status}"
                )
        elif decision.decision == "ALLOW_WITH_CONSTRAINTS":
            action = "BLOCKED" if mode == RunMode.LIVE else "WOULD_PLACE"
            detail = f"constraints={decision.constraints}; qty={quantity}"
            dispatch = "SKIPPED" if mode == RunMode.LIVE else "IBKR"
            order_id = None
            order_id_status = "NOT_APPLICABLE"
            certification_state = "CONSTRAINT_BLOCKED" if mode == RunMode.LIVE else "MODE_NO_BROKER_SUBMIT"
        else:
            action = "BLOCKED"
            detail = f"decision={decision.decision}; reason={decision.block_reason or 'RISK_BLOCK'}"
            dispatch = "SKIPPED"
            order_id = None
            order_id_status = "NOT_APPLICABLE"
            certification_state = "RISK_BLOCKED"
        print(f"[EXECUTION][DISPATCH] symbol={decision.symbol} dispatch={dispatch}")
        events.append(
            ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action=action,
                detail=detail,
                order_id=order_id,
                order_id_status=order_id_status,
                certification_state=certification_state,
            )
        )
    return events
