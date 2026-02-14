"""
Main entry point for PHASE 4 — Minimal Live-Capable System (Teaching-First).

This file provides a minimal, runnable starting point that prints clear,
teaching-style logs when executed via `python src/main.py`. It intentionally
avoids importing other project modules, performing any trading logic, loading
configuration, or connecting to brokers or data sources.
"""

from __future__ import annotations

import argparse
import os
import sys

from src.config.config_resolver import get_config, set_config_overrides
from src.config.runtime_config import (
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
    get_ibkr_order_submission_enabled,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
    get_intent_dedup_selftest_enabled,
    get_risk_profile_name,
    get_persistence_sqlite_path,
    get_run_mode,
    get_scanner_mode,
    get_scanner_symbols,
    is_execution_enabled,
)
from src.core.managers.runtime_mode_manager import RuntimeModeManager
from src.config.system_config import ACTIVE_SESSIONS, CYCLE_SLEEP_SECONDS
from src.domain.models.internal_order import InternalOrder
from src.core.orchestrator import CoreOrchestrator
from src.core.readiness import run_readiness_check
from src.adapters.brokers.ibkr.ibkr_order_translator import IbkrOrderTranslator
from src.ibkr.read_only_guard import validate_read_only_guard
from src.storage.sqlite_store import SCHEMA_VERSION
from src.storage.storage_engine import StorageEngine


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IBKR Trading System entrypoint")
    parser.add_argument(
        "--mode",
        choices=[
            "SIM",
            "READ_ONLY",
            "PAPER",
            "LIVE",
        ],
        help="Run mode override (SIM, READ_ONLY, PAPER, LIVE).",
    )
    parser.add_argument(
        "--strategy",
        choices=[
            "cross_sectional_relative_strength_rotation",
            "event_earnings_reaction",
            "event_news_shock_continuation",
            "long_horizon_quality_compounder",
            "long_horizon_value",
            "mean_reversion",
            "opening_drive",
            "pairs_divergence_reversion",
            "power_hour",
            "range_bound_fade",
            "regime_adaptive_meta_allocator",
            "ross_momentum",
            "statistical_intraday_momentum",
            "support_resistance_channel",
            "time_based_seasonality",
            "trend_following_classic",
            "volatility_carry_risk_premium",
            "volatility_contraction_breakout",
            "volatility_expansion",
            "vwap_reclaim",
        ],
        help="Strategy key to enable.",
    )
    parser.add_argument("--cycles", type=int, default=None, help="Max cycles to run.")
    parser.add_argument(
        "--session",
        help="Force a market session phase (e.g., PREMARKET, MORNING, CLOSED).",
    )
    parser.add_argument(
        "--regime-layer",
        action="store_true",
        help="Enable the adaptive regime/microstructure layer.",
    )
    parser.add_argument(
        "--regime-policy",
        action="store_true",
        help="Enable regime policy application (requires --regime-layer).",
    )
    parser.add_argument(
        "--readiness-check",
        action="store_true",
        help="Run readiness checks and exit with status code.",
    )
    return parser.parse_args()


def _apply_cli_overrides(args: argparse.Namespace) -> None:
    overrides: dict[str, object] = {}
    if args.mode:
        mode_map = {
            "READONLY": "READ_ONLY",
        }
        overrides["RUN_MODE"] = mode_map.get(args.mode, args.mode)
    if args.strategy:
        overrides["SELECTED_STRATEGY"] = args.strategy
    if args.strategy == "ross_momentum":
        overrides["ROSS_MOMENTUM_STRATEGY_ENABLED"] = True
    if args.strategy == "mean_reversion":
        overrides["MEAN_REVERSION_STRATEGY_ENABLED"] = True
    if args.regime_layer:
        overrides["ADAPTIVE_REGIME_LAYER_ENABLED"] = True
    if args.regime_policy:
        overrides["ADAPTIVE_REGIME_POLICY_ENABLED"] = True
    if args.session:
        overrides["SESSION_PHASE_OVERRIDE"] = str(args.session).upper()
    if overrides:
        set_config_overrides(overrides)


def _print_startup_banner(run_mode: RunMode, event_replay_mode) -> None:
    sqlite_raw = get_persistence_sqlite_path()
    sqlite_path = StorageEngine._resolve_repo_relative_path(sqlite_raw)
    db_exists = os.path.exists(sqlite_path)
    print("[STARTUP] Runtime banner")
    print(f"[STARTUP] Run mode: {run_mode.value}")
    print(f"[STARTUP] Event replay: {event_replay_mode.value}")
    print(f"[STARTUP] Active sessions: {', '.join(ACTIVE_SESSIONS)}")
    print("[STARTUP] Execution flags")
    print(f"  - EXECUTION_ENABLED: {get_execution_enabled()}")
    print(f"  - IBKR_READONLY_ENABLED: {get_ibkr_readonly_enabled()}")
    print(f"  - IBKR_ORDER_TRANSLATION_ENABLED: {get_ibkr_order_translation_enabled()}")
    print(f"  - IBKR_ORDER_SUBMISSION_ENABLED: {get_ibkr_order_submission_enabled()}")
    print("[STARTUP] Risk profile guardrails")
    print(f"  - RISK_PROFILE: {get_risk_profile_name()}")
    print("[STARTUP] Broker connectivity")
    print(f"  - IBKR_HOST: {get_ibkr_host()}")
    print(f"  - IBKR_PORT: {get_ibkr_port()}")
    print(f"  - IBKR_CLIENT_ID: {get_ibkr_client_id()}")
    print(f"  - IBKR_MARKET_DATA_TYPE: {get_ibkr_market_data_type()}")
    print("[STARTUP] Storage")
    print(f"  - SQLITE_PATH: {sqlite_path}")
    print(f"  - SCHEMA_VERSION: {SCHEMA_VERSION}")
    print(f"  - DB_EXISTS: {'Y' if db_exists else 'N'}")


def main() -> None:
    """Run the minimal teaching-first entry point."""
    args = _parse_args()
    _apply_cli_overrides(args)
    if args.readiness_check:
        report = run_readiness_check()
        print(report.to_text())
        raise SystemExit(0 if report.is_pass else 1)
    print("[BOOT] Starting the IBKR Trading System skeleton.")
    run_mode = get_run_mode()
    if run_mode == RunMode.READ_ONLY:
        print("[PHASE] PHASE 23 — Live Read-Only Runtime (Authoritative).")
        print("[INTENT] Enforce live read-only runtime authority and IBKR data access.")
    else:
        print("[PHASE] PHASE 4 — Minimal Live-Capable System (Teaching-First).")
        print("[INTENT] Demonstrate a clean, observable entry point without trading logic.")
    print("[CONFIG] Baseline teaching defaults (pre-resolution):")
    print(f"  - RUN_MODE: {DEFAULT_RUN_MODE.value} (baseline)")
    print(f"  - EVENT_REPLAY_MODE: {DEFAULT_EVENT_REPLAY_MODE.value} (baseline)")
    event_replay_mode = get_event_replay_mode(run_mode)
    mode_manager = RuntimeModeManager.resolve()
    print("[CONFIG] Resolved runtime configuration (authoritative):")
    print(f"  - RUN_MODE: {run_mode.value} (resolved)")
    if run_mode in {RunMode.LIVE, RunMode.READ_ONLY}:
        print(
            f"  - EVENT_REPLAY_MODE: {event_replay_mode.value} "
            "(resolved; forced OFF in live-like modes for safety)"
        )
    else:
        print(f"  - EVENT_REPLAY_MODE: {event_replay_mode.value} (resolved)")
    print(f"[CONFIG] Runtime mode manager: {mode_manager.describe()}")
    if mode_manager.is_live_like:
        print("[STARTUP] EVENT_REPLAY_MODE forced OFF for live-like modes")
    print(f"  - CYCLE_SLEEP_SECONDS: {CYCLE_SLEEP_SECONDS}")
    print(f"  - ACTIVE_SESSIONS: {', '.join(ACTIVE_SESSIONS)}")
    _print_startup_banner(run_mode, event_replay_mode)
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
    print(
        "  - ADAPTIVE_REGIME_LAYER_ENABLED: "
        f"{bool(get_config('ADAPTIVE_REGIME_LAYER_ENABLED'))}"
    )
    print(
        "  - ADAPTIVE_REGIME_POLICY_ENABLED: "
        f"{bool(get_config('ADAPTIVE_REGIME_POLICY_ENABLED'))}"
    )
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
    if run_mode in {RunMode.LIVE, RunMode.READ_ONLY}:
        print("[SAFETY] MARKET DATA: LIVE IBKR")
    if ibkr_readonly_enabled:
        print(
            "[CONFIG] IBKR_READONLY_ENABLED=True — broker order routing to IBKR "
            "is disabled. SIM execution is internal-only."
        )
    if run_mode == RunMode.READ_ONLY:
        print("[SAFETY] LIVE READ-ONLY MODE ACTIVE")
        print("[SAFETY] LIVE DATA — READ ONLY MODE")
    if run_mode == RunMode.LIVE and ibkr_readonly_enabled:
        print("[SAFETY] LIVE DATA — READ ONLY MODE")
        print("[SAFETY] NO ORDERS WILL BE SENT")
    validate_read_only_guard()

    translation_test_symbol = str(get_config("IBKR_TRANSLATION_TEST_SYMBOL") or "").strip().upper()
    translation_test_direction = str(
        get_config("IBKR_TRANSLATION_TEST_DIRECTION") or "LONG"
    ).strip().upper()
    translation_test_order_type = str(
        get_config("IBKR_TRANSLATION_TEST_ORDER_TYPE") or "MKT"
    ).strip().upper()
    translation_test_quantity = int(get_config("IBKR_TRANSLATION_TEST_QUANTITY") or 1)
    translation_test_limit_price = get_config("IBKR_TRANSLATION_TEST_LIMIT_PRICE")
    translation_test_tif = str(get_config("IBKR_TRANSLATION_TEST_TIF") or "DAY").strip().upper()
    translation_client_order_id = str(
        get_config("IBKR_TRANSLATION_TEST_CLIENT_ORDER_ID") or "dry-run-ibkr-translation"
    ).strip()
    translation_strategy_name = str(
        get_config("IBKR_TRANSLATION_TEST_STRATEGY_NAME") or "DRY_RUN"
    ).strip()
    translation_trader_type = str(
        get_config("IBKR_TRANSLATION_TEST_TRADER_TYPE") or "MANUAL"
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

    smoke_symbol = str(get_config("IBKR_SMOKE_SYMBOL") or "").strip().upper()
    if (
        run_mode in {
            RunMode.SIM,
            RunMode.LIVE,
            RunMode.READ_ONLY,
        }
        and ibkr_readonly_enabled
        and smoke_symbol
    ):
        print(
            "[IBKR] READ-ONLY smoke test starting "
            f"run_mode={run_mode.value} symbol={smoke_symbol}"
        )
        from src.brokers.ibkr_broker import IbkrBroker

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

    orchestrator.run_forever(max_cycles=args.cycles)

    print("[SHUTDOWN] Exiting gracefully. Goodbye!")


if __name__ == "__main__":
    main()
