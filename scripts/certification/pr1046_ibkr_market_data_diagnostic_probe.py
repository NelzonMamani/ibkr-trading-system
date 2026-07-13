#!/usr/bin/env python
"""Diagnostics-only PR1046 IBKR market-data probe.

This script classifies already-captured scanner or observation evidence. It does
not connect to a broker, request orders, preview orders, submit orders, cancel
orders, modify orders, or enable PAPER/LIVE execution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.certification.pr1046_ibkr_market_data_diagnostics import (  # noqa: E402
    build_ibkr_market_data_diagnostic,
)

DEFAULT_OUTPUT = Path("artifacts/certification/pr1046/ibkr_market_data_diagnostic.json")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")


def _diagnostic_from_observation(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    market_data = payload.get("market_data_observation_diagnostics", {})
    if not isinstance(market_data, Mapping):
        return None
    diagnostic = market_data.get("ibkr_market_data_diagnostic")
    if isinstance(diagnostic, dict):
        return diagnostic
    return None


def _diagnostic_has_error_events(diagnostic: Mapping[str, Any]) -> bool:
    return isinstance(diagnostic.get("ibkr_market_data_error_events"), list)


def _observation_market_data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    market_data = payload.get("market_data_observation_diagnostics", {})
    return market_data if isinstance(market_data, Mapping) else {}


def _scanner_payload_from_observation(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    scanner_payload = payload.get("scanner_payload")
    if isinstance(scanner_payload, Mapping):
        return scanner_payload
    scanner_payload = payload.get("scanner_cycle_artifact")
    if isinstance(scanner_payload, Mapping):
        return scanner_payload
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PR1046 IBKR market-data diagnostics probe.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--scanner-payload", type=Path, help="Path to captured scanner JSON evidence.")
    source.add_argument("--observation-input", type=Path, help="Path to PR1040/PR1045 observation-input JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--operator", default="UNKNOWN_OPERATOR")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    source_path = args.scanner_payload or args.observation_input
    assert source_path is not None
    payload = _read_json(source_path)

    existing_diagnostic = None
    if args.observation_input is not None:
        existing_diagnostic = _diagnostic_from_observation(payload)
    if existing_diagnostic is not None and _diagnostic_has_error_events(existing_diagnostic):
        diagnostic = existing_diagnostic
    else:
        market_data = _observation_market_data(payload) if args.observation_input is not None else {}
        scanner_payload = _scanner_payload_from_observation(payload) if args.observation_input is not None else payload
        if existing_diagnostic is not None:
            scanner_payload = dict(scanner_payload)
            scanner_payload["existing_ibkr_market_data_diagnostic"] = existing_diagnostic
        diagnostic = build_ibkr_market_data_diagnostic(
            scanner_payload=scanner_payload,
            drop_reason_counts=market_data.get("drop_reason_counts") if isinstance(market_data, Mapping) else None,
        )

    report = {
        "schema_version": "PR1046.ibkr_market_data_diagnostic_probe.v1",
        "operator": args.operator,
        "source_path": str(source_path),
        "diagnostic": diagnostic,
        "final_verdict": {
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "execution_enabled": "NO",
            "broker_order_mutation_allowed": "NO",
        },
    }
    _write_json(args.output, report)
    print(
        "[PR1046][DIAGNOSTIC] "
        f"classification={diagnostic.get('classification')} "
        "paper_ready=NO paper_readiness_gate=FAIL "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
