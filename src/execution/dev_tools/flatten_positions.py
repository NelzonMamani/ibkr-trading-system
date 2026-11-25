from __future__ import annotations

from decimal import Decimal
import time
from uuid import uuid4

from src.adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from src.domain.models.internal_order import InternalOrder


def _snapshot_positions(ibkr_client) -> list[tuple[str, Decimal]]:
    if ibkr_client is None or not hasattr(ibkr_client, "positions"):
        print("[DEV][FLATTEN][SKIP] client_missing_positions_method")
        return []
    snapshot: list[tuple[str, Decimal]] = []
    for row in ibkr_client.positions():
        symbol = str(getattr(row, "symbol", "") or "").upper().strip()
        raw_quantity = row.position
        if isinstance(raw_quantity, bool):
            raise ValueError("Broker position quantity is boolean")
        quantity = Decimal.from_float(raw_quantity) if isinstance(raw_quantity, float) else Decimal(raw_quantity)
        if not quantity.is_finite():
            raise ValueError("Broker position quantity is not finite")
        if quantity != 0:
            if not symbol:
                raise ValueError("Nonzero broker position has no symbol")
            snapshot.append((symbol, quantity))
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

    # The translator accepts only whole-share orders. Validate the entire
    # snapshot before submitting the first close.
    if any(quantity != quantity.to_integral_value() for _, quantity in positions):
        print(
            f"[DEV][FLATTEN][RESULT] positions_remaining={positions_detected} "
            "status=FAILED reason=UNSUPPORTED_FRACTIONAL_POSITION"
        )
        return {
            "positions_detected": positions_detected,
            "close_orders_submitted": 0,
            "positions_remaining": positions_detected,
            "status": "FAILED",
        }

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
    symbols_targeted = {symbol for symbol, _ in positions}

    for symbol, quantity in positions:
        qty = int(quantity)
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
    remaining_positions = positions
    print("[DEV][FLATTEN][WAIT]")
    while time.time() < deadline:
        remaining_positions = [
            (symbol, quantity)
            for symbol, quantity in _snapshot_positions(ibkr_client)
            if symbol in symbols_targeted
        ]
        if not remaining_positions:
            break
        time.sleep(1)

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
