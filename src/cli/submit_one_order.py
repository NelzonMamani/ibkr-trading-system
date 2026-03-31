from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from src.config.runtime_config import (
    RunMode,
    get_ibkr_ack_timeout_seconds,
    get_ibkr_client_id_order_submit,
    get_ibkr_default_currency,
    get_ibkr_default_exchange,
    get_ibkr_guard_persist_path,
    get_ibkr_kill_switch,
    get_ibkr_live_port,
    get_ibkr_market_data_type,
    get_ibkr_max_orders_per_run,
    get_ibkr_order_submission_enabled,
    get_ibkr_order_translation_enabled,
    get_ibkr_paper_host,
    get_ibkr_paper_only_enforced,
    get_ibkr_paper_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
    get_run_mode,
)
from src.core.event_collector import EventCollector
from src.domain.models.internal_order import InternalOrder

if TYPE_CHECKING:
    from src.adapters.brokers.ibkr.ibkr_order_submitter import OrderSubmissionSettings


SOURCE = "CLI.SUBMIT_ONE_ORDER"
VALID_IBKR_STATUSES = {
    "Submitted",
    "PreSubmitted",
    "Filled",
    "PendingSubmit",
    "PendingCancel",
}


def abort(message: str) -> None:
    print(f"[ABORT] {message}")
    sys.exit(1)


def validate_runtime() -> RunMode:
    run_mode = get_run_mode()
    if run_mode != RunMode.PAPER:
        abort(
            "RUN_MODE must be PAPER — live submission is forbidden for this CLI."
        )

    if not get_ibkr_order_translation_enabled():
        abort("IBKR order translation disabled — enable IBKR_ORDER_TRANSLATION_ENABLED.")

    if get_ibkr_readonly_enabled(default=False):
        abort("IBKR read-only mode enabled — disable IBKR_READONLY_ENABLED to submit.")

    if not get_ibkr_order_submission_enabled(default=False):
        abort("IBKR order submission disabled — enable IBKR_ORDER_SUBMISSION_ENABLED.")

    if get_ibkr_kill_switch():
        abort("Kill-switch engaged — clear IBKR_KILL_SWITCH to proceed.")

    max_orders = get_ibkr_max_orders_per_run()
    if max_orders != 1:
        abort(
            f"Single-order CLI enforces exactly one order; IBKR_MAX_ORDERS_PER_RUN={max_orders}."
        )

    return run_mode


def build_internal_order() -> InternalOrder:
    return InternalOrder(
        client_order_id=str(uuid4()),
        symbol="AAPL",
        direction="LONG",
        quantity=1,
        order_type="MKT",
        limit_price=None,
        time_in_force="DAY",
        strategy_name="CLI_TEST",
        trader_type="MANUAL",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit one guarded PAPER market order through the IBKR adapter.",
        epilog="Run as a module: python -m src.cli.submit_one_order",
    )
    return parser.parse_args()


def build_settings(run_mode: RunMode) -> "OrderSubmissionSettings":
    return OrderSubmissionSettings(
        run_mode=run_mode,
        order_submission_enabled=True,
        kill_switch=False,
        max_orders_per_run=1,
        paper_only_enforced=get_ibkr_paper_only_enforced(),
        paper_host=get_ibkr_paper_host(),
        paper_port=get_ibkr_paper_port(),
        live_port=get_ibkr_live_port(),
        submit_only_symbol=None,
        ack_timeout_seconds=get_ibkr_ack_timeout_seconds(),
        client_id=get_ibkr_client_id_order_submit(),
        submit_only_order_type="MKT",
        allow_shorting=False,
    )


def emit_single_order_events(event_bus: EventCollector, internal_order: InternalOrder, status: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    event_payload = {
        "client_order_id": internal_order.client_order_id,
        "symbol": internal_order.symbol,
        "direction": internal_order.direction,
        "quantity": internal_order.quantity,
        "order_type": internal_order.order_type,
        "timestamp": timestamp,
    }
    event_bus.emit(event_type="ORDER_SUBMITTED", source=SOURCE, payload=event_payload)

    if status in VALID_IBKR_STATUSES:
        event_bus.emit(
            event_type="ORDER_ACCEPTED",
            source=SOURCE,
            payload={**event_payload, "status": status},
        )
    else:
        event_bus.emit(
            event_type="ORDER_REJECTED",
            source=SOURCE,
            payload={**event_payload, "status": status},
        )

    event_bus.emit(
        event_type="ORDER_FINAL_STATUS",
        source=SOURCE,
        payload={**event_payload, "final_status": status},
    )


def main() -> None:
    parse_args()

    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    from src.adapters.brokers.ibkr.ibkr_order_submitter import (
        IbkrOrderSubmitter,
        OrderSubmissionSettings,
    )
    from src.adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
    from src.adapters.brokers.ibkr.submission_guard import SubmissionGuard

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_mode = validate_runtime()

    print("IBKR SINGLE-ORDER CLI — PAPER ONLY — NO ORCHESTRATOR INVOCATION")
    print("[INIT] Loading isolated submission components")

    translator = IbkrOrderTranslator(
        order_translation_enabled=True,
        default_exchange=get_ibkr_default_exchange(),
        default_currency=get_ibkr_default_currency(),
    )
    guard = SubmissionGuard(
        max_orders_per_run=1,
        persist_path=get_ibkr_guard_persist_path(),
    )
    event_bus = EventCollector()
    ibkr_client = IbkrClient(
        host=get_ibkr_paper_host(),
        port=get_ibkr_paper_port(),
        client_id=get_ibkr_client_id_order_submit(),
        snapshot_timeout_seconds=get_ibkr_snapshot_timeout_seconds(),
        market_data_type=get_ibkr_market_data_type(),
        # The client requires readonly_enabled for connectivity; runtime validation already enforces
        # IBKR_READONLY_ENABLED must be False before proceeding.
        readonly_enabled=True,
    )
    settings = build_settings(run_mode=run_mode)
    submitter = IbkrOrderSubmitter(
        ibkr_client=ibkr_client,
        translator=translator,
        event_bus=event_bus,
        config=settings,
        guard=guard,
        logger=logging.getLogger(SOURCE),
    )

    internal_order = build_internal_order()
    if not guard.can_submit():
        abort("Guard blocked submission — more than one order attempt detected.")

    print(
        "[SUBMIT] client_order_id={cid} symbol={symbol} direction={direction} qty={qty} type={otype}".format(
            cid=internal_order.client_order_id,
            symbol=internal_order.symbol,
            direction=internal_order.direction,
            qty=internal_order.quantity,
            otype=internal_order.order_type,
        )
    )

    try:
        result = submitter.submit_once(internal_order)
    except Exception as exc:
        emit_single_order_events(event_bus, internal_order, status="FAILED")
        print(f"[ABORT] Submission failed: {exc}")
        sys.exit(1)

    emit_single_order_events(event_bus, internal_order, status=result.status)
    timestamp = datetime.now(timezone.utc).isoformat()
    mode_label = getattr(run_mode, "value", str(run_mode)).upper()
    print(
        "[RESULT] order_id={cid} symbol={symbol} status={status} mode={mode} ibkr_order_id={ibkr_id} at={ts}".format(
            cid=internal_order.client_order_id,
            symbol=internal_order.symbol,
            status=result.status,
            mode=mode_label,
            ibkr_id=result.ibkr_order_id,
            ts=timestamp,
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
