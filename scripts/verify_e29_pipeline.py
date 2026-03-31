from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.core.orchestrator import CoreOrchestrator


def _ensure_safe_runtime_defaults() -> None:
    os.environ.setdefault("RUN_MODE", "PAPER")
    os.environ.setdefault("SCANNER_DATA_SOURCE", "MOCK")
    os.environ.setdefault("IBKR_READONLY_ENABLED", "true")


def main() -> int:
    _ensure_safe_runtime_defaults()
    orchestrator = CoreOrchestrator()
    cycles = 3
    full_log: list[str] = []
    totals = {
        "execution_attempts": 0,
        "final_intents_nonzero_cycles": 0,
        "no_trade_reason_cycles": 0,
        "cycles_ok": 0,
    }

    for idx in range(1, cycles + 1):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cycle_ok = orchestrator.run_once()
        cycle_log = buf.getvalue()
        print(f"\n=== E29 CYCLE {idx} TRACE START ===")
        print(cycle_log, end="" if cycle_log.endswith("\n") else "\n")
        print(f"=== E29 CYCLE {idx} TRACE END ===")
        full_log.append(cycle_log)
        totals["cycles_ok"] += 1 if cycle_ok else 0
        totals["execution_attempts"] += cycle_log.count("[PIPELINE][EXECUTION_ATTEMPT]")
        totals["final_intents_nonzero_cycles"] += 1 if "final_intents_count=0" not in cycle_log else 0
        totals["no_trade_reason_cycles"] += cycle_log.count("[PIPELINE][NO_TRADE_REASON]")

    print("\n[E29][SUMMARY]")
    print(f"cycles={cycles}")
    print(f"cycles_ok={totals['cycles_ok']}")
    print(f"execution_attempts={totals['execution_attempts']}")
    print(f"cycles_with_final_intents_gt_0={totals['final_intents_nonzero_cycles']}")
    print(f"no_trade_reason_cycles={totals['no_trade_reason_cycles']}")

    success = totals["execution_attempts"] >= 1 and totals["final_intents_nonzero_cycles"] >= 1
    print(f"E29_PIPELINE_VERIFICATION_STATUS={'PASS' if success else 'FAIL'}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
