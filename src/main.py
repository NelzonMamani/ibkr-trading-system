"""
Main entry point for PHASE 4 — Minimal Live-Capable System (Teaching-First).

This file provides a minimal, runnable starting point that prints clear,
teaching-style logs when executed via `python src/main.py`. It intentionally
avoids importing other project modules, performing any trading logic, loading
configuration, or connecting to brokers or data sources.
"""

from config.runtime_config import DEFAULT_RUN_MODE, RunMode, get_run_mode
from config.system_config import (
    DEFAULT_EVENT_REPLAY_MODE,
    ACTIVE_SESSIONS,
    CYCLE_SLEEP_SECONDS,
    get_event_replay_mode,
)
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
    orchestrator = CoreOrchestrator()
    print("[LOOP] Entering continuous run loop. Press Ctrl+C to stop safely.")

    orchestrator.run_forever()

    print("[SHUTDOWN] Exiting gracefully. Goodbye!")


if __name__ == "__main__":
    main()
