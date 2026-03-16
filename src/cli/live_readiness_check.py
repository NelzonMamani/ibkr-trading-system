from __future__ import annotations

import argparse
from typing import Sequence

from src.cli.ibkr_scanner_diagnostics import run_diagnostics
from src.cli.test_trade_pipeline import run_pipeline
from src.scanner.session_pct_change import resolve_session_diagnostics


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only live readiness sweep")
    parser.add_argument("--symbol", default="AAPL", help="Representative symbol for pipeline verification")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic dry-run checks")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    session_diag = resolve_session_diagnostics()
    scanner = run_diagnostics(dry_run=args.dry_run)
    pipeline = run_pipeline(
        symbol=args.symbol.upper(),
        dry_run=args.dry_run,
        execute_live=False,
        dangerous_submit_live_order=False,
    )

    broker_connected = scanner["broker"]["connection"] in {"ACTIVE", "DRY_RUN"}
    scanner_operational = bool(scanner["scanner"]["scanner_operational"])
    scanner_symbols = int(scanner["scanner"]["returned_symbols"])
    raw_zero = scanner["scanner"].get("raw_zero_attribution") or {}

    prep_operational = bool(scanner["scanner"].get("diagnostics", {}).get("prep", True))
    pipeline_operational = pipeline["hydration"] in {"SUCCESS", "PARTIAL"}
    pattern_engine_operational = "detected_patterns" in pipeline["pattern"]
    strategy_engine_operational = pipeline["strategy"]["strategies_evaluated"] != []
    risk_engine_operational = pipeline["risk"]["first_decision_result"] in {"ALLOW", "DENY"}
    execution_path_operational = "order_would_be_placed" in pipeline["execution"]

    blockers: list[str] = []
    if not broker_connected:
        blockers.append("BROKER_CONNECTION_FAILED")
    if not scanner_operational:
        blockers.append("SCANNER_NOT_OPERATIONAL")
    if not prep_operational:
        blockers.append("PREP_NOT_OPERATIONAL")
    if not pipeline_operational:
        blockers.append("PIPELINE_DATA_HYDRATION_FAILED")
    if not pattern_engine_operational:
        blockers.append("PATTERN_ENGINE_NOT_OPERATIONAL")
    if not strategy_engine_operational:
        blockers.append("STRATEGY_ENGINE_NOT_OPERATIONAL")
    if not risk_engine_operational:
        blockers.append("RISK_ENGINE_NOT_OPERATIONAL")
    if not execution_path_operational:
        blockers.append("EXECUTION_PATH_NOT_OPERATIONAL")

    overall_ready = not blockers

    print("[LIVE_READINESS]")
    print(f"broker_connected={broker_connected}")
    print(f"session_resolved={session_diag.resolved_session}")
    print(f"session_source={session_diag.override_source}")
    print(f"scanner_operational={scanner_operational}")
    print(f"scanner_symbols_returned={scanner_symbols}")
    print(f"scanner_broker_returned_zero={bool(raw_zero.get('broker_returned_zero', scanner_symbols == 0))}")
    print(f"prep_operational={prep_operational}")
    print(f"pipeline_operational={pipeline_operational}")
    print(f"pattern_engine_operational={pattern_engine_operational}")
    print(f"strategy_engine_operational={strategy_engine_operational}")
    print(f"risk_engine_operational={risk_engine_operational}")
    print(f"execution_path_operational={execution_path_operational}")
    print(f"overall_ready={overall_ready}")
    if blockers:
        print(f"blockers={blockers}")

    return 0 if overall_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
