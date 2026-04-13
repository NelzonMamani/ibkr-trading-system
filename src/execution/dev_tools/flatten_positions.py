from __future__ import annotations

import time
from uuid import uuid4

from src.adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from src.domain.models.internal_order import InternalOrder


def _snapshot_positions(ibkr_client) -> list[dict[str, float | int | str]]:
    snapshot: list[dict[str, float | int | str]] = []
    for row in ibkr_client.positions():
        symbol = str(getattr(row, "symbol", "") or "").upper().strip()
        qty = int(getattr(row, "position", 0) or 0)
        if not symbol or qty == 0:
            continue
        avg_cost = float(getattr(row, "avgCost", 0.0) or 0.0)
        snapshot.append({"symbol": symbol, "quantity": qty, "avg_cost": avg_cost})
    return snapshot


def force_flatten_all_positions(ibkr_client, timeout_seconds: int = 30) -> dict:
    """
    Force closes all IBKR positions using market orders.

    Returns:
        {
            "positions_detected": int,
            "close_orders_submitted": int,
            "positions_remaining": int,
            "status": "SUCCESS" | "PARTIAL" | "FAILED"
        }
    """
    print("[DEV][FLATTEN][START]")
    positions = _snapshot_positions(ibkr_client)
    positions_detected = len(positions)

    if positions_detected == 0:
        print("[DEV][FLATTEN][RESULT] positions_remaining=0 status=SUCCESS")
        return {
            "positions_detected": 0,
            "close_orders_submitted": 0,
            "positions_remaining": 0,
            "status": "SUCCESS",
        }

    translator = IbkrOrderTranslator(order_translation_enabled=True)
    submitted = 0
    symbols_targeted = {str(p["symbol"]) for p in positions}

    for position in positions:
        symbol = str(position["symbol"])
        qty = int(position["quantity"])
        side = "SELL" if qty > 0 else "BUY"
        quantity_to_close = abs(qty)
        print(f"[DEV][FLATTEN][POSITION] symbol={symbol} qty={qty} action={side}")

        internal_order = InternalOrder(
            client_order_id=f"DEV_FLATTEN_{symbol}_{uuid4().hex[:10]}",
            symbol=symbol,
            direction=side,
            quantity=quantity_to_close,
            order_type="MKT",
            time_in_force="DAY",
            strategy_name="DEV_FLATTEN",
            trader_type="SYSTEM",
        )
        contract, order = translator.translate(internal_order)
        order.outsideRth = True

        try:
            ibkr_client.submit_order(contract, order)
            submitted += 1
            print(f"[DEV][FLATTEN][SUBMIT] symbol={symbol} qty={quantity_to_close}")
        except Exception as exc:
            print(f"[DEV][FLATTEN][SUBMIT][ERROR] symbol={symbol} qty={quantity_to_close} error={exc}")

    deadline = time.time() + max(1, int(timeout_seconds))
    latest_positions = positions
    print("[DEV][FLATTEN][WAIT]")
    while time.time() < deadline:
        latest_positions = _snapshot_positions(ibkr_client)
        remaining_symbols = {
            str(p["symbol"]) for p in latest_positions if str(p["symbol"]) in symbols_targeted and int(p["quantity"]) != 0
        }
        if not remaining_symbols:
            break
        time.sleep(1)

    remaining_positions = [
        p
        for p in latest_positions
        if str(p["symbol"]) in symbols_targeted and int(p["quantity"]) != 0
    ]
    positions_remaining = len(remaining_positions)

    if positions_remaining == 0:
        status = "SUCCESS"
    elif positions_remaining < positions_detected:
        status = "PARTIAL"
    else:
        status = "FAILED"

    print(f"[DEV][FLATTEN][RESULT] positions_remaining={positions_remaining} status={status}")
    return {
        "positions_detected": positions_detected,
        "close_orders_submitted": submitted,
        "positions_remaining": positions_remaining,
        "status": status,
    }
