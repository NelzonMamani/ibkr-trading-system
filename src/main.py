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
    get_ibkr_client_id,
    get_ibkr_host,
    get_ibkr_market_data_type,
    get_ibkr_port,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_timeout_seconds,
    get_run_mode,
)
from config.system_config import ACTIVE_SESSIONS, CYCLE_SLEEP_SECONDS
from core.orchestrator import CoreOrchestrator


def main() -> None:
    """Run the minimal teaching-first entry point."""
    print("[BOOT] Starting the IBKR Trading System skeleton.")
    print("[PHASE] PHASE 4 — Minimal Live-Capable System (Teaching-First).")
    print("[INTENT] Demonstrate a clean, observable entry point without trading logic.")
    print("[CONFIG] Baseline teaching defaults (pre-resolution):")
    print(f"  - RUN_MODE: {DEFAULT_RUN_MODE.value} (baseline)")
    print(f"  - EVENT_REPLAY_MODE: {DEFAULT_EVENT_REPLAY_MODE.value} (baseline)")
    run_mode = get_run_mode()
    event_replay_mode = get_event_replay_mode(run_mode)
    print("[CONFIG] Resolved runtime configuration (authoritative):")
    print(f"  - RUN_MODE: {run_mode.value} (resolved)")
    if run_mode == RunMode.LIVE:
        print(
            f"  - EVENT_REPLAY_MODE: {event_replay_mode.value} "
            "(resolved; forced OFF in LIVE for safety)"
        )
    else:
        print(f"  - EVENT_REPLAY_MODE: {event_replay_mode.value} (resolved)")
    print(f"  - CYCLE_SLEEP_SECONDS: {CYCLE_SLEEP_SECONDS}")
    print(f"  - ACTIVE_SESSIONS: {', '.join(ACTIVE_SESSIONS)}")
    ibkr_readonly_enabled = get_ibkr_readonly_enabled()
    print(f"  - IBKR_READONLY_ENABLED: {ibkr_readonly_enabled}")
    print(f"  - IBKR_HOST: {get_ibkr_host()}")
    print(f"  - IBKR_PORT: {get_ibkr_port()}")
    print(f"  - IBKR_CLIENT_ID: {get_ibkr_client_id()}")
    print(f"  - IBKR_SNAPSHOT_TIMEOUT_SECONDS: {get_ibkr_snapshot_timeout_seconds()}")
    print(f"  - IBKR_MARKET_DATA_TYPE: {get_ibkr_market_data_type()}")

    smoke_symbol = (os.getenv("IBKR_SMOKE_SYMBOL") or "").strip().upper()
    if (
        run_mode in {RunMode.SIM, RunMode.LIVE}
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
