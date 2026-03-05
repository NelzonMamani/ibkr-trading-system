"""Continuous loop runner that executes one orchestrator cycle per iteration."""

from __future__ import annotations

import argparse
import subprocess
import time
from src.core_engine import orchestrator as core_orchestrator
from src.core_engine.state import SessionState
from src.runtime.bootstrap import bootstrap_runtime


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run orchestrator in a continuous loop")
    parser.add_argument("--mode", choices=["SIM", "PAPER", "READ_ONLY", "LIVE"], default="READ_ONLY")
    parser.add_argument("--cadence-seconds", type=float, default=10.0)
    parser.add_argument("--max-cycles", type=int, default=0, help="0 means run until stopped")
    parser.add_argument("--session-override", choices=["PRE", "REGULAR", "AFTER", "OVN"], default=None)
    parser.add_argument("--preflight", action="store_true", help="Run setup-family verification scripts before loop")
    return parser.parse_args()


def _run_preflight() -> None:
    checks = [
        ["python", "verification_scripts/setup_families_completeness_verifier.py"],
        ["python", "verification_scripts/p01_all_setup_families_trigger_harness.py"],
    ]
    for cmd in checks:
        print(f"[PREFLIGHT] running: {' '.join(cmd)}")
        completed = subprocess.run(cmd, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)


def _forced_session(session_override: str | None) -> SessionState | None:
    if session_override is None:
        return None
    mapping = {
        "PRE": SessionState.PRE,
        "REGULAR": SessionState.REG,
        "AFTER": SessionState.AFTER,
        "OVN": SessionState.AFTER,
    }
    return mapping[session_override]


def main() -> int:
    args = _parse_args()
    if args.preflight:
        _run_preflight()

    bootstrap_runtime()

    forced_session = _forced_session(args.session_override)

    cycle_id = 1
    try:
        while args.max_cycles == 0 or cycle_id <= args.max_cycles:
            core_orchestrator.run_cycle(
                cycle_id=cycle_id,
                mode_value=args.mode,
                forced_session_state=forced_session,
            )
            cycle_id += 1
            if args.max_cycles and cycle_id > args.max_cycles:
                break
            time.sleep(max(0.0, args.cadence_seconds))
    except KeyboardInterrupt:
        print("[LOOP] KeyboardInterrupt received; shutting down gracefully.")
    finally:
        time.sleep(0.05)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
