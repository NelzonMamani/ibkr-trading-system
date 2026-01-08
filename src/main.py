"""
Main entry point for PHASE 4 — Minimal Live-Capable System (Teaching-First).

This file provides a minimal, runnable starting point that prints clear,
teaching-style logs when executed via `python src/main.py`. It intentionally
avoids importing other project modules, performing any trading logic, loading
configuration, or connecting to brokers or data sources.
"""

import os

from config.runtime_config import (
    DEFAULT_EVENT_REPLAY_MODE,
    DEFAULT_RUN_MODE,
    RunMode,
    get_event_replay_mode,
    get_execution_enabled,
    get_ibkr_api_write_allowed,
    get_ibkr_client_id,
    get_ibkr_host,
    get_ibkr_market_data_type,
    get_ibkr_max_symbols_per_cycle,
    get_ibkr_default_currency,
    get_ibkr_default_exchange,
    get_ibkr_port,
    get_ibkr_order_translation_enabled,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
    get_intent_dedup_selftest_enabled,
    get_run_mode,
    get_scanner_mode,
    get_scanner_symbols,
    is_execution_enabled,
)
from config.system_config import ACTIVE_SESSIONS, CYCLE_SLEEP_SECONDS
from domain.models.internal_order import InternalOrder
from core.orchestrator import CoreOrchestrator
from adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from ibkr.read_only_guard import validate_read_only_guard


def main() -> None:
    """Run the minimal teaching-first entry point."""
    print("[BOOT] Starting the IBKR Trading System skeleton.")
    run_mode = get_run_mode()
    if run_mode == RunMode.LIVE_READ_ONLY:
        print("[PHASE] PHASE 22 — Live Read-Only Runtime (Authoritative).")
        print("[INTENT] Enforce live read-only runtime authority and IBKR data access.")
    else:
        print("[PHASE] PHASE 4 — Minimal Live-Capable System (Teaching-First).")
        print("[INTENT] Demonstrate a clean, observable entry point without trading logic.")
    print("[CONFIG] Baseline teaching defaults (pre-resolution):")
    print(f"  - RUN_MODE: {DEFAULT_RUN_MODE.value} (baseline)")
    print(f"  - EVENT_REPLAY_MODE: {DEFAULT_EVENT_REPLAY_MODE.value} (baseline)")
    event_replay_mode = get_event_replay_mode(run_mode)
    print("[CONFIG] Resolved runtime configuration (authoritative):")
    print(f"  - RUN_MODE: {run_mode.value} (resolved)")
    if run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}:
        print(
            f"  - EVENT_REPLAY_MODE: {event_replay_mode.value} "
            "(resolved; forced OFF in LIVE/LIVE_READ_ONLY/LIVE_MICRO for safety)"
        )
    else:
        print(f"  - EVENT_REPLAY_MODE: {event_replay_mode.value} (resolved)")
    print(f"  - CYCLE_SLEEP_SECONDS: {CYCLE_SLEEP_SECONDS}")
    print(f"  - ACTIVE_SESSIONS: {', '.join(ACTIVE_SESSIONS)}")
    ibkr_readonly_enabled = get_ibkr_readonly_enabled()
    ibkr_api_write_allowed = get_ibkr_api_write_allowed()
    execution_enabled = is_execution_enabled(run_mode)
    print(f"  - IBKR_READONLY_ENABLED: {ibkr_readonly_enabled}")
    print(f"  - IBKR_API_WRITE_ALLOWED: {ibkr_api_write_allowed}")
    print(f"  - EXECUTION_ENABLED: {get_execution_enabled()}")
    print(f"  - IBKR_HOST: {get_ibkr_host()}")
    print(f"  - IBKR_PORT: {get_ibkr_port()}")
    print(f"  - IBKR_CLIENT_ID: {get_ibkr_client_id()}")
    print(f"  - IBKR_SNAPSHOT_TIMEOUT_SECONDS: {get_ibkr_snapshot_timeout_seconds()}")
    print(f"  - IBKR_MARKET_DATA_TYPE: {get_ibkr_market_data_type()}")
    print(f"  - IBKR_MAX_SYMBOLS_PER_CYCLE: {get_ibkr_max_symbols_per_cycle()}")
    print(f"  - SCANNER_MODE: {get_scanner_mode()}")
    print(f"  - SCANNER_SYMBOLS: {get_scanner_symbols()}")
    print(f"  - INTENT_DEDUP_SELFTEST_ENABLED: {get_intent_dedup_selftest_enabled()}")
    ibkr_order_translation_enabled = get_ibkr_order_translation_enabled()
    print(f"  - IBKR_ORDER_TRANSLATION_ENABLED: {ibkr_order_translation_enabled}")
    ibkr_default_exchange = get_ibkr_default_exchange()
    ibkr_default_currency = get_ibkr_default_currency()
    print(f"  - IBKR_DEFAULT_EXCHANGE: {ibkr_default_exchange}")
    print(f"  - IBKR_DEFAULT_CURRENCY: {ibkr_default_currency}")
    print(
        "[SAFETY] IBKR API WRITE: "
        f"{'ENABLED' if ibkr_api_write_allowed else 'DISABLED'}"
    )
    if not execution_enabled:
        print("[SAFETY] EXECUTION: HARD DISABLED")
        print("[SAFETY] ORDER ROUTING: BLOCKED")
    if run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}:
        print("[SAFETY] MARKET DATA: LIVE IBKR")
    if ibkr_readonly_enabled:
        print(
            "[CONFIG] IBKR_READONLY_ENABLED=True — broker order routing to IBKR "
            "is disabled. SIM execution is internal-only."
        )
    if run_mode == RunMode.LIVE_READ_ONLY:
        print("[SAFETY] LIVE READ-ONLY MODE ACTIVE")
        print("[SAFETY] LIVE DATA — READ ONLY MODE")
    if run_mode == RunMode.LIVE_MICRO:
        print("[SAFETY] LIVE MICRO-EXECUTION MODE ACTIVE")
        print("[SAFETY] 1-SHARE LIMIT ENFORCED")
    if run_mode == RunMode.LIVE and ibkr_readonly_enabled:
        print("[SAFETY] LIVE DATA — READ ONLY MODE")
        print("[SAFETY] NO ORDERS WILL BE SENT")
    validate_read_only_guard()

    translation_test_symbol = (
        os.getenv("IBKR_TRANSLATION_TEST_SYMBOL") or ""
    ).strip().upper()
    translation_test_direction = (
        os.getenv("IBKR_TRANSLATION_TEST_DIRECTION") or "LONG"
    ).strip().upper()
    translation_test_order_type = (
        os.getenv("IBKR_TRANSLATION_TEST_ORDER_TYPE") or "MKT"
    ).strip().upper()
    translation_test_quantity_raw = (os.getenv("IBKR_TRANSLATION_TEST_QUANTITY") or "").strip()
    if translation_test_quantity_raw:
        try:
            translation_test_quantity = int(translation_test_quantity_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid IBKR_TRANSLATION_TEST_QUANTITY='{translation_test_quantity_raw}'"
            ) from exc
    else:
        translation_test_quantity = 1
    translation_test_limit_price_raw = os.getenv("IBKR_TRANSLATION_TEST_LIMIT_PRICE")
    if translation_test_limit_price_raw not in {None, ""}:
        try:
            translation_test_limit_price = float(translation_test_limit_price_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid IBKR_TRANSLATION_TEST_LIMIT_PRICE='{translation_test_limit_price_raw}'"
            ) from exc
    else:
        translation_test_limit_price = None
    translation_test_tif = (os.getenv("IBKR_TRANSLATION_TEST_TIF") or "DAY").strip().upper()
    translation_client_order_id = (
        os.getenv("IBKR_TRANSLATION_TEST_CLIENT_ORDER_ID") or "dry-run-ibkr-translation"
    ).strip()
    translation_strategy_name = (
        os.getenv("IBKR_TRANSLATION_TEST_STRATEGY_NAME") or "DRY_RUN"
    ).strip()
    translation_trader_type = (
        os.getenv("IBKR_TRANSLATION_TEST_TRADER_TYPE") or "MANUAL"
    ).strip()

    if ibkr_order_translation_enabled and translation_test_symbol:
        translator = IbkrOrderTranslator(
            order_translation_enabled=ibkr_order_translation_enabled,
            default_exchange=ibkr_default_exchange,
            default_currency=ibkr_default_currency,
        )
        internal_order = InternalOrder(
            client_order_id=translation_client_order_id,
            symbol=translation_test_symbol,
            direction=translation_test_direction,
            quantity=translation_test_quantity,
            order_type=translation_test_order_type,
            limit_price=translation_test_limit_price,
            time_in_force=translation_test_tif,
            strategy_name=translation_strategy_name,
            trader_type=translation_trader_type,
        )
        translator.translate(internal_order)
        print("[IBKR][DRY-RUN] Translation complete. Exiting before any broker connectivity.")
        return

    smoke_symbol = (os.getenv("IBKR_SMOKE_SYMBOL") or "").strip().upper()
    if (
        run_mode in {RunMode.SIM, RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}
        and ibkr_readonly_enabled
        and smoke_symbol
    ):
        print(
            "[IBKR] READ-ONLY smoke test starting "
            f"run_mode={run_mode.value} symbol={smoke_symbol}"
        )
        from brokers.ibkr_broker import IbkrBroker

        broker = IbkrBroker()
        try:
            broker.connect()
            details = broker.resolve_contract(smoke_symbol)
            print(
                f"[IBKR] Resolved contract: symbol={smoke_symbol} conId={details.contract.conId}"
            )
            snapshot = broker.get_market_snapshot(smoke_symbol)
            print(
                "[IBKR] Market snapshot: "
                f"bid={snapshot.bid} ask={snapshot.ask} last={snapshot.last} "
                f"asof_utc={snapshot.asof_utc.isoformat()}"
            )
        finally:
            broker.disconnect()
        print("[IBKR] READ-ONLY smoke test complete. Exiting without starting orchestrator.")
        return

    orchestrator = CoreOrchestrator()
    print("[LOOP] Entering continuous run loop. Press Ctrl+C to stop safely.")

    orchestrator.run_forever()

    print("[SHUTDOWN] Exiting gracefully. Goodbye!")


if __name__ == "__main__":
    main()
