from __future__ import annotations

import argparse
import logging
from datetime import datetime

from adapters.brokers.ibkr.ibkr_client import IbkrClient
from adapters.brokers.ibkr.ibkr_order_submitter import (
    IbkrOrderSubmitter,
    OrderSubmissionSettings,
)
from adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from adapters.brokers.ibkr.submission_guard import SubmissionGuard
from config.runtime_config import (
    get_ibkr_ack_timeout_seconds,
    get_ibkr_client_id_order_submit,
    get_ibkr_default_currency,
    get_ibkr_default_exchange,
    get_ibkr_guard_persist_path,
    get_ibkr_kill_switch,
    get_ibkr_live_port,
    get_ibkr_market_data_type,
    get_ibkr_order_submission_enabled,
    get_ibkr_order_translation_enabled,
    get_ibkr_paper_host,
    get_ibkr_paper_only_enforced,
    get_ibkr_paper_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
    get_ibkr_submit_only_symbol,
    get_ibkr_max_orders_per_run,
    get_run_mode,
)
from core.event_collector import EventCollector
from domain.models.internal_order import InternalOrder


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit exactly one IBKR paper order in SIM mode (kill-switch enforced)."
    )
    parser.add_argument("--symbol", required=True, help="Ticker symbol to submit.")
    parser.add_argument(
        "--direction",
        default="LONG",
        choices=["LONG", "SHORT"],
        help="Order direction (SHORT is blocked by default).",
    )
    parser.add_argument(
        "--quantity",
        type=int,
        default=1,
        help="Order quantity (positive integer).",
    )
    parser.add_argument(
        "--order-type",
        default="MKT",
        choices=["MKT", "LMT"],
        help="Order type (MKT enforced for Step 12.4).",
    )
    parser.add_argument(
        "--limit-price",
        type=float,
        default=None,
        help="Limit price (required if order-type=LMT).",
    )
    parser.add_argument(
        "--client-order-id",
        default=None,
        help="Client order id (auto-generated if omitted).",
    )
    parser.add_argument(
        "--time-in-force",
        default="DAY",
        choices=["DAY", "IOC"],
        help="Time in force.",
    )
    parser.add_argument(
        "--strategy-name",
        default="SUBMIT_ONE",
        help="Strategy name tag for audit.",
    )
    parser.add_argument(
        "--trader-type",
        default="MANUAL",
        help="Trader type tag for audit.",
    )
    return parser.parse_args()


def build_settings():
    run_mode = get_run_mode()
    return OrderSubmissionSettings(
        run_mode=run_mode,
        order_submission_enabled=get_ibkr_order_submission_enabled(),
        kill_switch=get_ibkr_kill_switch(),
        max_orders_per_run=get_ibkr_max_orders_per_run(),
        paper_only_enforced=get_ibkr_paper_only_enforced(),
        paper_host=get_ibkr_paper_host(),
        paper_port=get_ibkr_paper_port(),
        live_port=get_ibkr_live_port(),
        submit_only_symbol=get_ibkr_submit_only_symbol(),
        ack_timeout_seconds=get_ibkr_ack_timeout_seconds(),
        client_id=get_ibkr_client_id_order_submit(),
        submit_only_order_type="MKT",
        allow_shorting=False,
    )


def build_internal_order(args: argparse.Namespace) -> InternalOrder:
    client_order_id = args.client_order_id or f"submit-one-{args.symbol}-{int(datetime.now().timestamp())}"
    return InternalOrder(
        client_order_id=client_order_id,
        symbol=args.symbol.upper(),
        direction=args.direction.upper(),
        quantity=args.quantity,
        order_type=args.order_type.upper(),
        limit_price=args.limit_price,
        time_in_force=args.time_in_force.upper(),
        strategy_name=args.strategy_name,
        trader_type=args.trader_type,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_args()
    settings = build_settings()

    print("IBKR SUBMISSION MODE — SIM ONLY — SINGLE ORDER — KILL SWITCH AVAILABLE")
    print("[INIT] Loading components for single-order submission path")

    translator = IbkrOrderTranslator(
        order_translation_enabled=get_ibkr_order_translation_enabled(),
        default_exchange=get_ibkr_default_exchange(),
        default_currency=get_ibkr_default_currency(),
    )
    guard = SubmissionGuard(
        max_orders_per_run=settings.max_orders_per_run,
        persist_path=get_ibkr_guard_persist_path(),
    )
    event_bus = EventCollector()
    ibkr_client = IbkrClient(
        host=settings.paper_host,
        port=settings.paper_port,
        client_id=settings.client_id,
        snapshot_timeout_seconds=get_ibkr_snapshot_timeout_seconds(),
        market_data_type=get_ibkr_market_data_type(),
        readonly_enabled=get_ibkr_readonly_enabled(default=True),
    )
    submitter = IbkrOrderSubmitter(
        ibkr_client=ibkr_client,
        translator=translator,
        event_bus=event_bus,
        config=settings,
        guard=guard,
        logger=logging.getLogger("ibkr_submit_one"),
    )

    internal_order = build_internal_order(args)
    print(f"[SUBMIT] Preparing submission for {internal_order.symbol} qty={internal_order.quantity}")

    result = submitter.submit_once(internal_order)
    print(
        "[RESULT] status={status} ibkr_order_id={ibkr_order_id} error={error}".format(
            status=result.status,
            ibkr_order_id=result.ibkr_order_id,
            error=result.error,
        )
    )
    print("SIM SUBMISSION COMPLETE — NO LIVE TRADING")


if __name__ == "__main__":
    main()
