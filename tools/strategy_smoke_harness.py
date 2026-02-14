#!/usr/bin/env python3
"""Deterministic strategy smoke harness for SIM/PAPER using MOCK scanner data."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator


def _extract_count(pattern: str, logs: str) -> int:
    match = re.search(pattern, logs)
    if not match:
        return 0
    return int(match.group(1))


def _extract_symbols(pattern: str, logs: str) -> list[str]:
    match = re.search(pattern, logs)
    if not match:
        return []
    symbols_raw = match.group(1)
    return [item.strip().strip("'") for item in symbols_raw.split(",") if item.strip()]


def run_smoke(strategy: str, mode: str, output_dir: Path) -> dict:
    overrides = {
        "RUN_MODE": mode,
        "SCANNER_DATA_SOURCE": "MOCK",
        "IBKR_FALLBACK_ENABLED": True,
        "SELECTED_STRATEGY": strategy,
        "SESSION_PHASE_OVERRIDE": "MORNING",
        "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED": strategy == "statistical_intraday_momentum",
        "MEAN_REVERSION_STRATEGY_ENABLED": strategy == "mean_reversion",
        "LONG_HORIZON_VALUE_STRATEGY_ENABLED": strategy == "long_horizon_value",
    }
    set_config_overrides(overrides)

    stream = io.StringIO()
    success = False
    try:
        with redirect_stdout(stream):
            orchestrator = CoreOrchestrator()
            success = bool(orchestrator.run_once())
        logs = stream.getvalue()

        watchlist = _extract_symbols(r"WATCHLIST_K_SELECTED \(K=\d+\): \[(.*?)\]", logs)
        focus = _extract_symbols(r"\[TRACE\] stage=FOCUS .*? symbols=\[(.*?)\]", logs)
        watchlist_count = _extract_count(r"\[TRACE\] stage=WATCHLIST .*? watchlist=(\d+)", logs) or len(watchlist)
        focus_count = _extract_count(r"\[TRACE\] stage=FOCUS .*? focus=(\d+)", logs) or len(focus)
        intents_count = _extract_count(r"\[TRACE\] stage=ACTION .*? intents=(\d+)", logs)

        summary = {
            "strategy": strategy,
            "mode": mode,
            "success": success,
            "pipeline": {
                "scanner": "[TRACE] stage=UNIVERSE" in logs,
                "watchlist_k": "[WATCHLIST]" in logs,
                "focus_m": "[TRACE] stage=FOCUS" in logs,
                "strategy_runner": "STRATEGY_RUNNER_RECEIVED" in logs,
                "intents": intents_count > 0,
                "execution": "[EXECUTION]" in logs,
            },
            "counts": {
                "watchlist_k": watchlist_count,
                "focus_m": focus_count,
                "normalised_intents": intents_count,
                "execution_events": orchestrator.event_collector.count("EXECUTION_COMPLETE"),
            },
            "watchlist_symbols": watchlist,
            "focus_symbols": focus,
        }
    finally:
        set_config_overrides({})

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"smoke_{strategy}_{mode.lower()}.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--mode", required=True, choices=["SIM", "PAPER"])
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    summary = run_smoke(args.strategy, args.mode, output_dir)
    print(json.dumps(summary, indent=2))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
