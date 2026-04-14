from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable
from uuid import uuid4

from src.adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from src.domain.models.internal_order import InternalOrder


@dataclass(frozen=True)
class CleanStartResult:
    enabled: bool
    ready_for_trading: bool
    remaining_positions: int
    remaining_open_orders: int
    status: str
    reason: str | None = None


def _safe_open_orders(ibkr_client: Any) -> list[object]:
    return list(ibkr_client.openOrders() or [])


def _safe_positions(ibkr_client: Any) -> list[object]:
    return list(ibkr_client.positions() or [])


def _non_flat_positions(positions: list[object]) -> list[object]:
    return [row for row in positions if int(getattr(row, "position", 0) or 0) != 0]


def enforce_clean_start_session(
    *,
    enabled: bool,
    ibkr_client: Any | None,
    timeout_seconds: int = 120,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> CleanStartResult:
    if not enabled:
        return CleanStartResult(
            enabled=False,
            ready_for_trading=True,
            remaining_positions=0,
            remaining_open_orders=0,
            status="DISABLED",
        )
    print("[CLEAN_START][BEGIN]")
    if ibkr_client is None:
        print("[CLEAN_START][FAILED] remaining_positions=UNKNOWN remaining_open_orders=UNKNOWN reason=NO_IBKR_CLIENT")
        print("[CLEAN_START][BLOCK] reason=DIRTY_SESSION_AFTER_CLEAN_ATTEMPT")
        return CleanStartResult(
            enabled=True,
            ready_for_trading=False,
            remaining_positions=-1,
            remaining_open_orders=-1,
            status="FAILED",
            reason="NO_IBKR_CLIENT",
        )

    open_orders = _safe_open_orders(ibkr_client)
    positions = _safe_positions(ibkr_client)
    non_flat_positions = _non_flat_positions(positions)
    print(
        "[CLEAN_START][STATE] "
        f"broker_open_orders={len(open_orders)} broker_positions={len(non_flat_positions)}"
    )

    # PHASE B — cancel all broker open orders
    for row in open_orders:
        order_id = int(getattr(row, "orderId", 0) or 0)
        symbol = str(getattr(getattr(row, "contract", None), "symbol", "") or "").upper()
        print(f"[CLEAN_START][CANCEL_ORDER] order_id={order_id} symbol={symbol}")
        ibkr_client.cancelOrder(order_id)

    open_orders = _safe_open_orders(ibkr_client)
    print(f"[CLEAN_START][ORDERS_AFTER_CANCEL] remaining_open_orders={len(open_orders)}")

    # PHASE C — flatten all positions
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    for row in non_flat_positions:
        symbol = str(getattr(row, "symbol", "") or "").upper().strip()
        qty = int(getattr(row, "position", 0) or 0)
        if not symbol or qty == 0:
            continue
        side = "SELL" if qty > 0 else "BUY"
        quantity_to_close = abs(qty)
        print(
            "[CLEAN_START][FLATTEN_SUBMIT] "
            f"symbol={symbol} qty={quantity_to_close} side={side} order_type=MKT outsideRth=True"
        )
        internal_order = InternalOrder(
            client_order_id=f"CLEAN_START_{symbol}_{uuid4().hex[:10]}",
            symbol=symbol,
            direction=side,
            quantity=quantity_to_close,
            order_type="MKT",
            time_in_force="DAY",
            strategy_name="CLEAN_START",
            trader_type="BROKER_CLEANUP",
        )
        contract, order = translator.translate(internal_order)
        order.outsideRth = True
        if hasattr(order, "orderRef"):
            order.orderRef = "CLEAN_START|BROKER_CLEANUP"
        ibkr_client.submit_order(contract, order)

    # PHASE D — wait for flat confirmation
    deadline = monotonic_fn() + max(1, int(timeout_seconds))
    while monotonic_fn() < deadline:
        open_orders = _safe_open_orders(ibkr_client)
        positions = _safe_positions(ibkr_client)
        non_flat_positions = _non_flat_positions(positions)
        print(
            "[CLEAN_START][WAIT] "
            f"remaining_positions={len(non_flat_positions)} remaining_open_orders={len(open_orders)}"
        )
        if not non_flat_positions and not open_orders:
            print("[CLEAN_START][COMPLETE] broker_positions=0 broker_open_orders=0 status=READY_FOR_TRADING")
            return CleanStartResult(
                enabled=True,
                ready_for_trading=True,
                remaining_positions=0,
                remaining_open_orders=0,
                status="COMPLETE",
            )
        sleep_fn(1.0)

    open_orders = _safe_open_orders(ibkr_client)
    positions = _safe_positions(ibkr_client)
    non_flat_positions = _non_flat_positions(positions)
    print(
        "[CLEAN_START][FAILED] "
        f"remaining_positions={len(non_flat_positions)} remaining_open_orders={len(open_orders)} reason=TIMEOUT"
    )
    print("[CLEAN_START][BLOCK] reason=DIRTY_SESSION_AFTER_CLEAN_ATTEMPT")
    return CleanStartResult(
        enabled=True,
        ready_for_trading=False,
        remaining_positions=len(non_flat_positions),
        remaining_open_orders=len(open_orders),
        status="FAILED",
        reason="TIMEOUT",
    )
