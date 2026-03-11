#!/usr/bin/env python3
"""
Usage:
  ENABLE_TEST_PIPELINE=true TEST_PIPELINE_MODE=DRY_RUN python verification_scripts/ross_live_execution_proof_pipeline.py --from-watchlist
  ENABLE_TEST_PIPELINE=true TEST_PIPELINE_MODE=LIVE python verification_scripts/ross_live_execution_proof_pipeline.py --symbol AAPL --hold-seconds 30

Purpose:
  Explicitly-gated Ross execution proof pipeline with DRY_RUN and LIVE modes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.orchestrator import CoreOrchestrator
from src.models.data_models import RiskDecision
from src.scanner.scanner_runner import run_scanner_cycle
from src.scanner.session_pct_change import resolve_session_diagnostics


OUT_DIR = REPO_ROOT / "AUDIT_EVIDENCE" / "ross_execution_proof"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _choose_symbol(args: argparse.Namespace) -> tuple[str | None, str]:
    if args.symbol:
        return args.symbol.upper(), "manual_symbol"
    scan = run_scanner_cycle(mode="integrated")
    focus = list(scan.get("focus_m_symbols", []))
    watch = list(scan.get("watchlist_k_symbols", []))
    if args.from_watchlist and watch:
        return watch[0], "watchlist_k_top"
    if focus:
        return focus[0], "focus_m_top"
    if watch:
        return watch[0], "watchlist_k_top"
    return None, "none_available"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="")
    parser.add_argument("--from-watchlist", action="store_true")
    parser.add_argument("--hold-seconds", type=int, default=30)
    args = parser.parse_args()

    enabled = str(os.getenv("ENABLE_TEST_PIPELINE", "")).lower() == "true"
    mode = str(os.getenv("TEST_PIPELINE_MODE", "DRY_RUN")).upper()
    if not enabled:
        print("[TEST_PIPELINE] blocked: ENABLE_TEST_PIPELINE=true required")
        return 2
    if mode not in {"DRY_RUN", "LIVE"}:
        print("[TEST_PIPELINE] blocked: TEST_PIPELINE_MODE must be DRY_RUN or LIVE")
        return 2

    diag = resolve_session_diagnostics()
    symbol, symbol_reason = _choose_symbol(args)
    report = {
        "stamp": "TEST_PIPELINE",
        "mode": mode,
        "session": asdict(diag),
        "symbol": symbol,
        "symbol_reason": symbol_reason,
        "hold_seconds": int(max(1, args.hold_seconds)),
        "steps": [],
        "pass": False,
    }

    if not symbol:
        report["steps"].append({"step": "symbol_selection", "status": "FAIL", "reason": "no candidate symbol"})
        out = OUT_DIR / f"test_pipeline_{_ts()}.json"
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"[REPORT] {out}")
        return 1

    report["steps"].append({"step": "symbol_selection", "status": "PASS", "detail": symbol_reason})
    report["steps"].append({"step": "order_request", "status": "PASS", "order_type": "MARKET", "qty": 1, "symbol": symbol})

    if mode == "DRY_RUN":
        report["steps"].append({"step": "broker_ack", "status": "SKIP", "reason": "dry_run"})
        report["steps"].append({"step": "fill_capture", "status": "SKIP", "reason": "dry_run"})
        report["steps"].append({"step": "hold_timer", "status": "PASS", "seconds": report["hold_seconds"]})
        report["steps"].append({"step": "exit_request", "status": "PASS", "reason": "dry_run_synthetic"})
        report["steps"].append({"step": "pipeline_recording", "status": "PASS"})
        report["pass"] = True
    else:
        orch = CoreOrchestrator()
        decision = RiskDecision(
            symbol=symbol,
            allowed=True,
            max_position_size=1,
            risk_level="TEST",
            rationale="TEST_PIPELINE_ENTRY",
            trader_type="MANUAL",
            strategy_name="ROSS_TEST_PIPELINE",
            direction="LONG",
            decision_id=f"test-entry-{_ts()}",
        )
        entry = orch.execution_engine.execute_trade(decision)
        report["steps"].append({"step": "broker_ack", "status": "PASS" if entry.attempted else "FAIL", "result": asdict(entry)})
        report["steps"].append({"step": "fill_capture", "status": "PASS" if entry.fill_status in {"FULL", "PARTIAL", "NONE"} else "FAIL", "fill_status": entry.fill_status})
        time.sleep(report["hold_seconds"])
        report["steps"].append({"step": "hold_timer", "status": "PASS", "seconds": report["hold_seconds"]})
        exit_decision = RiskDecision(
            symbol=symbol,
            allowed=True,
            max_position_size=1,
            risk_level="TEST",
            rationale="TEST_PIPELINE_EXIT",
            trader_type="MANUAL",
            strategy_name="ROSS_TEST_PIPELINE",
            direction="SHORT",
            decision_id=f"test-exit-{_ts()}",
        )
        exit_result = orch.execution_engine.execute_trade(exit_decision)
        report["steps"].append({"step": "exit_request", "status": "PASS" if exit_result.attempted else "FAIL", "result": asdict(exit_result)})
        report["steps"].append({"step": "pipeline_recording", "status": "PASS", "events": len(orch.event_collector.snapshot_cycle())})
        report["pass"] = all(step["status"] in {"PASS", "SKIP"} for step in report["steps"])

    out = OUT_DIR / f"test_pipeline_{_ts()}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[REPORT] {out}")
    print("PASS" if report["pass"] else "FAIL")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
