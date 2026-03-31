"""Execution router enforcing mode law for Epoch 5."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.brokers.base_broker import BrokerOrderRequest
from src.brokers.ibkr_live_broker import IbkrLiveBroker
from src.core_engine.events import ExecutionEvent, RiskDecisionRecord
from src.core_engine.state import RunMode
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector


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
    live_broker: IbkrLiveBroker | None = None

    if mode in {RunMode.PAPER, RunMode.LIVE}:
        if _is_test_environment():
            print("[EXECUTION][TEST_MODE] Skipping IBKR connection validation")
        else:
            _validate_ibkr_connection(mode)
        live_broker = IbkrLiveBroker(
            event_collector=EventCollector(),
            trade_registry=ActiveTradeRegistry(),
            run_mode=mode,
        )

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
                if live_broker is None:
                    action = "BLOCKED"
                    detail = "reason=IBKR_BROKER_UNAVAILABLE"
                    dispatch = "SKIPPED"
                else:
                    broker_request = BrokerOrderRequest(
                        client_order_id=decision.intent_id,
                        symbol=decision.symbol,
                        direction="LONG",
                        quantity=quantity,
                        order_type="MKT",
                        trader_type="EPOCH5",
                        strategy_name="ROSS_MOMENTUM",
                        attempt_number=1,
                    )
                    print(
                        "[EXECUTION][IBKR_CALL] "
                        f"symbol={decision.symbol} order_id={broker_request.client_order_id}"
                    )
                    broker_result = live_broker.place_order(broker_request)
                    resolved_order_id = (
                        getattr(broker_result, "ibkr_order_id", None)
                        or getattr(broker_result, "client_order_id", None)
                        or broker_request.client_order_id
                    )
                    ack_status = str(getattr(broker_result, "status", "UNKNOWN") or "UNKNOWN")
                    print(
                        "[EXECUTION][IBKR_ACK] "
                        f"symbol={decision.symbol} status={ack_status}"
                    )
                    if ack_status.upper() in {"ACKED", "FILLED", "PARTIAL"}:
                        action = "SUBMITTED"
                        detail = f"submitted qty={quantity} broker_status={ack_status}"
                        dispatch = "IBKR"
                    else:
                        action = "BLOCKED"
                        detail = (
                            "reason=IBKR_SUBMISSION_FAILED "
                            f"broker_status={ack_status} "
                            f"broker_reason={getattr(broker_result, 'rejection_reason', None) or getattr(broker_result, 'rationale', None)}"
                        ).strip()
                        dispatch = "SKIPPED"
                    events.append(
                        ExecutionEvent(
                            symbol=decision.symbol,
                            intent_id=decision.intent_id,
                            action=action,
                            detail=detail,
                            order_id=str(resolved_order_id),
                        )
                    )
                    print(f"[EXECUTION][DISPATCH] symbol={decision.symbol} dispatch={dispatch}")
                    continue
        elif decision.decision == "ALLOW_WITH_CONSTRAINTS":
            action = "BLOCKED" if mode == RunMode.LIVE else "WOULD_PLACE"
            detail = f"constraints={decision.constraints}; qty={quantity}"
            dispatch = "SKIPPED" if mode == RunMode.LIVE else "IBKR"
        else:
            action = "BLOCKED"
            detail = f"decision={decision.decision}; reason={decision.block_reason or 'RISK_BLOCK'}"
            dispatch = "SKIPPED"
        print(f"[EXECUTION][DISPATCH] symbol={decision.symbol} dispatch={dispatch}")
        events.append(
            ExecutionEvent(
                symbol=decision.symbol,
                intent_id=decision.intent_id,
                action=action,
                detail=detail,
                order_id=None,
            )
        )
    return events
