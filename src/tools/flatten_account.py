from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from src.domain.models.internal_order import InternalOrder


@dataclass(frozen=True)
class FlattenPosition:
    symbol: str
    quantity: int


@dataclass(frozen=True)
class FlattenSummary:
    run_mode: str
    positions_detected: int
    orders_submitted: int
    order_status_received: int


def _resolve_run_mode() -> str:
    return str(os.getenv("RUN_MODE", "PAPER") or "PAPER").upper().strip()


def _ensure_safe_run_mode(force_live: bool) -> str:
    run_mode = _resolve_run_mode()
    if run_mode == "PAPER":
        return run_mode
    if force_live:
        print(f"[FLATTEN][SAFETY] force_live_override=true run_mode={run_mode}")
        return run_mode
    raise RuntimeError(
        "Flatten tool is PAPER-only by default. Set RUN_MODE=PAPER or pass --force-live "
        "to acknowledge a non-paper run mode."
    )


def _resolve_connection(run_mode: str, client_id: int | None) -> tuple[str, int, int]:
    host = str(os.getenv("IBKR_HOST", "127.0.0.1") or "127.0.0.1")
    if os.getenv("IBKR_PORT"):
        port = int(os.getenv("IBKR_PORT", "7497"))
    else:
        port = 7497 if run_mode in {"PAPER", "SIM", "READ_ONLY"} else 7496
    resolved_client_id = int(os.getenv("IBKR_CLIENT_ID", str(client_id or 79)))
    return host, port, resolved_client_id


def _connect_ibkr(run_mode: str, client_id: int | None = None) -> IbkrClient:
    host, port, resolved_client_id = _resolve_connection(run_mode, client_id)
    snapshot_timeout_seconds = int(os.getenv("IBKR_SNAPSHOT_TIMEOUT_SECONDS", "10"))
    market_data_type = str(os.getenv("IBKR_MARKET_DATA_TYPE", "LIVE") or "LIVE")

    client = IbkrClient(
        host=host,
        port=port,
        client_id=resolved_client_id,
        snapshot_timeout_seconds=snapshot_timeout_seconds,
        market_data_type=market_data_type,
        readonly_enabled=False,
    )
    client.connect()
    return client


def _fetch_positions(client: IbkrClient, timeout_seconds: int) -> list[FlattenPosition]:
    rows = client.positions(timeout_seconds=timeout_seconds)
    positions: list[FlattenPosition] = []
    for row in rows:
        symbol = str(getattr(row, "symbol", "") or "").upper().strip()
        qty = int(getattr(row, "position", 0) or 0)
        if not symbol or qty == 0:
            continue
        print(f"[FLATTEN][POSITION] symbol={symbol} qty={qty}")
        positions.append(FlattenPosition(symbol=symbol, quantity=qty))
    return positions


def _build_order(symbol: str, qty: int, outside_rth: bool) -> tuple[Any, Any, str, int]:
    action = "SELL" if qty > 0 else "BUY"
    quantity = abs(int(qty))
    translator = IbkrOrderTranslator(order_translation_enabled=True)
    internal_order = InternalOrder(
        client_order_id=f"FLATTEN_{symbol}_{uuid4().hex[:10]}",
        symbol=symbol,
        direction=action,
        quantity=quantity,
        order_type="MKT",
        time_in_force="DAY",
        strategy_name="ACCOUNT_FLATTENER",
        trader_type="DEV_TOOL",
    )
    contract, order = translator.translate(internal_order)
    order.tif = "DAY"
    order.orderType = "MKT"
    order.outsideRth = bool(outside_rth)
    if hasattr(order, "orderRef"):
        order.orderRef = "FLATTEN|DEV_TOOL"
    return contract, order, action, quantity


def _submit_orders(
    client: IbkrClient,
    positions: list[FlattenPosition],
    outside_rth: bool,
    wait_for_status_seconds: int,
) -> tuple[int, int]:
    submitted = 0
    status_received = 0
    for position in positions:
        contract, order, action, quantity = _build_order(
            symbol=position.symbol,
            qty=position.quantity,
            outside_rth=outside_rth,
        )
        print(f"[FLATTEN][ORDER_SUBMIT] symbol={position.symbol} action={action} qty={quantity}")
        order_id = client.reserve_order_id()
        client.placeOrder(order_id, contract, order)
        submitted += 1

        if wait_for_status_seconds > 0:
            status = client.wait_for_order_status(order_id, timeout_seconds=wait_for_status_seconds)
            if status:
                status_received += 1
                status_name = str(status.get("status") or "UNKNOWN")
                print(
                    f"[FLATTEN][ORDER_STATUS] symbol={position.symbol} order_id={order_id} status={status_name}"
                )
    return submitted, status_received


def flatten_account(
    *,
    force_live: bool,
    outside_rth: bool,
    positions_timeout_seconds: int,
    wait_for_status_seconds: int,
    client_id: int | None,
) -> FlattenSummary:
    run_mode = _ensure_safe_run_mode(force_live=force_live)
    print("[FLATTEN][START]")

    client = _connect_ibkr(run_mode=run_mode, client_id=client_id)
    try:
        print("[FLATTEN][GLOBAL_CANCEL] requesting reqGlobalCancel")
        client.reqGlobalCancel()
        time.sleep(0.5)

        positions = _fetch_positions(client, timeout_seconds=positions_timeout_seconds)
        if not positions:
            summary = FlattenSummary(
                run_mode=run_mode,
                positions_detected=0,
                orders_submitted=0,
                order_status_received=0,
            )
            print(
                "[FLATTEN][SUMMARY] "
                f"run_mode={summary.run_mode} positions_detected=0 orders_submitted=0 order_status_received=0"
            )
            return summary

        submitted, status_received = _submit_orders(
            client=client,
            positions=positions,
            outside_rth=outside_rth,
            wait_for_status_seconds=wait_for_status_seconds,
        )
        summary = FlattenSummary(
            run_mode=run_mode,
            positions_detected=len(positions),
            orders_submitted=submitted,
            order_status_received=status_received,
        )
        print(
            "[FLATTEN][SUMMARY] "
            f"run_mode={summary.run_mode} positions_detected={summary.positions_detected} "
            f"orders_submitted={summary.orders_submitted} order_status_received={summary.order_status_received}"
        )
        return summary
    finally:
        client.disconnect()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Flatten all IBKR positions in a development-safe way (cancel open orders + submit market closes)."
    )
    parser.add_argument(
        "--force-live",
        action="store_true",
        help="Allow execution when RUN_MODE is not PAPER.",
    )
    parser.add_argument(
        "--outside-rth",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Set outsideRth on generated flatten orders (default: true).",
    )
    parser.add_argument(
        "--positions-timeout-seconds",
        type=int,
        default=10,
        help="Timeout for waiting on reqPositions/positionEnd snapshots.",
    )
    parser.add_argument(
        "--wait-for-status-seconds",
        type=int,
        default=0,
        help="Optional wait time per order for orderStatus confirmation (0 disables waits).",
    )
    parser.add_argument(
        "--client-id",
        type=int,
        default=None,
        help="Optional IBKR client id override.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        flatten_account(
            force_live=bool(args.force_live),
            outside_rth=bool(args.outside_rth),
            positions_timeout_seconds=max(1, int(args.positions_timeout_seconds)),
            wait_for_status_seconds=max(0, int(args.wait_for_status_seconds)),
            client_id=args.client_id,
        )
    except Exception as exc:
        print(f"[FLATTEN][ERROR] {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
