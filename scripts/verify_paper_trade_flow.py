#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REQUIRED_MARKERS = {
    "trade_executed": ["[EXECUTION][OUTCOME]", "status=ACKED", "status=FILLED", "[ORDER][ACK]"],
    "order_submitted": ["[ORDER_SUBMIT]", "[ORDER][SUBMIT]"],
    "fill_recorded": ["[ORDER][FILL]"],
    "position_opened": ["[POSITION][OPENED]", "[ORDER][FILL]"],
}


def _contains_any(text: str, markers: list[str]) -> bool:
    return any(marker in text for marker in markers)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify PAPER trade flow evidence from a runtime log.")
    parser.add_argument("log_file", type=Path, help="Path to captured PAPER runtime log output.")
    args = parser.parse_args()

    if not args.log_file.exists():
        print(f"[FAIL] log file not found: {args.log_file}")
        return 1

    log_text = args.log_file.read_text(encoding="utf-8", errors="replace")

    checks = {
        name: _contains_any(log_text, markers) for name, markers in REQUIRED_MARKERS.items()
    }

    print("[VERIFY][PAPER_TRADE_FLOW]")
    print(f"- log_file={args.log_file}")
    for key, ok in checks.items():
        print(f"- {key}={ok}")

    if not all(checks.values()):
        missing = [key for key, ok in checks.items() if not ok]
        print(f"[FAIL] missing_required_proof={missing}")
        return 1

    print("[PASS] PAPER trade flow proof verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
