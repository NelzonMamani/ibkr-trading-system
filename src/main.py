"""
Main entry point for PHASE 4 — Minimal Live-Capable System (Teaching-First).

This file provides a minimal, runnable starting point that prints clear,
teaching-style logs when executed via `python src/main.py`. It intentionally
avoids importing other project modules, performing any trading logic, loading
configuration, or connecting to brokers or data sources.
"""

import time

from config.runtime_config import get_run_mode
from core.orchestrator import CoreOrchestrator


def main() -> None:
    """Run the minimal teaching-first entry point."""
    print("[BOOT] Starting the IBKR Trading System skeleton.")
    print("[PHASE] PHASE 4 — Minimal Live-Capable System (Teaching-First).")
    print("[INTENT] Demonstrate a clean, observable entry point without trading logic.")
    run_mode = get_run_mode()
    print(f"[MODE] RUN_MODE = {run_mode.value} (safe default)")
    orchestrator = CoreOrchestrator()
    print("[LOOP] Entering continuous run loop. Press Ctrl+C to stop safely.")

    try:
        while True:
            print("[CYCLE] Starting orchestrator cycle.")
            orchestrator.run_once()
            print("[SLEEP] Sleeping for 3 seconds before next cycle.")
            time.sleep(3)
    except KeyboardInterrupt:
        print("[SHUTDOWN] KeyboardInterrupt received. Stopping continuous run loop.")

    print("[SHUTDOWN] Exiting gracefully. Goodbye!")


if __name__ == "__main__":
    main()
