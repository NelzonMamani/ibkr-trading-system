"""
Main entry point for PHASE 4 — Minimal Live-Capable System (Teaching-First).

This file provides a minimal, runnable starting point that prints clear,
teaching-style logs when executed via `python src/main.py`. It intentionally
avoids importing other project modules, performing any trading logic, loading
configuration, or connecting to brokers or data sources.
"""

import time

from config.runtime_config import RunMode, get_run_mode
from config.system_config import (
    ACTIVE_SESSIONS,
    CYCLE_SLEEP_SECONDS,
    RUN_MODE,
    get_current_market_session,
)
from core.orchestrator import CoreOrchestrator


def main() -> None:
    """Run the minimal teaching-first entry point."""
    print("[BOOT] Starting the IBKR Trading System skeleton.")
    print("[PHASE] PHASE 4 — Minimal Live-Capable System (Teaching-First).")
    print("[INTENT] Demonstrate a clean, observable entry point without trading logic.")
    print("[CONFIG] Teaching-first configuration preview:")
    print(f"  - RUN_MODE (baseline string): {RUN_MODE}")
    print(f"  - CYCLE_SLEEP_SECONDS: {CYCLE_SLEEP_SECONDS} (seconds)")
    print(f"  - ACTIVE_SESSIONS: {', '.join(ACTIVE_SESSIONS)}")
    run_mode = get_run_mode()
    print(f"[MODE] RUN_MODE = {run_mode.value} (safe default)")
    orchestrator = CoreOrchestrator()
    print("[LOOP] Entering continuous run loop. Press Ctrl+C to stop safely.")

    try:
        while True:
            print("[CYCLE] Starting orchestrator cycle.")
            current_session = get_current_market_session()
            print(f"[SESSION] Detected market session: {current_session}")
            if current_session in ACTIVE_SESSIONS:
                print("[SESSION] System WOULD consider trading allowed in this session (teaching-only).")
            else:
                print("[SESSION] System WOULD treat market as closed (teaching-only).")
            if run_mode == RunMode.LIVE and current_session == "CLOSED":
                print(
                    "[GATE] RUN_MODE is LIVE while session is CLOSED. Skipping orchestrator.run_once() "
                    "to maintain teaching-first safety."
                )
                print("[GATE] Teaching note: SIM/PAPER would still run for education, but LIVE waits for an open session.")
            else:
                print("[SAFETY] RUN_MODE and session allow safe progression to orchestrator.run_once().")
                orchestrator.run_once()
            print(
                f"[SLEEP] Sleeping for {CYCLE_SLEEP_SECONDS} seconds before next cycle."
            )
            time.sleep(CYCLE_SLEEP_SECONDS)
    except KeyboardInterrupt:
        print("[SHUTDOWN] KeyboardInterrupt received. Stopping continuous run loop.")

    print("[SHUTDOWN] Exiting gracefully. Goodbye!")


if __name__ == "__main__":
    main()
