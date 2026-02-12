"""Run all metadata epoch verifiers and capture an aggregate summary."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import get_repo_root
from src.metadata.m7_epoch_audit_certifier import verify_m7_epoch_audit_and_certification
from src.metadata.m8_change_control_verifier import verify_m8_change_control
from src.metadata.m9_signal_semantics_registry_verifier import verify_m9_signal_semantics_registry


def _run_epoch(epoch: str) -> dict:
    if epoch == "M7_EPOCH_AUDIT_CERTIFICATION":
        return verify_m7_epoch_audit_and_certification(include_core=True)
    if epoch == "M8_CHANGE_CONTROL":
        return verify_m8_change_control(include_core=True)
    if epoch == "M9_SIGNAL_SEMANTICS_REGISTRY":
        return verify_m9_signal_semantics_registry()
    return {
        "epoch": epoch,
        "valid": False,
        "violations": [
            {
                "check": "VERIFIER_IMPLEMENTED",
                "expected": "available",
                "actual": "missing_verifier",
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify metadata epochs M0-M10")
    parser.add_argument("--output", default="TRADING_OS_MASTER_CATALOGUE/VERIFICATION_SUMMARY.md")
    args = parser.parse_args()

    repo_root = get_repo_root()
    epochs = [
        "M0_CANON",
        "M1_ARCHITECTURE_MAP",
        "M2_CONTRACT_REGISTRY",
        "M3_MODE_SEMANTICS_CERT",
        "M4_TRACEABILITY_SEMANTICS",
        "M5_VERIFICATION_AUTHORITY",
        "M6_DATA_LIFECYCLE_GOV",
        "M7_EPOCH_AUDIT_CERTIFICATION",
        "M8_CHANGE_CONTROL",
        "M9_SIGNAL_SEMANTICS_REGISTRY",
        "M10_DATA_PROVENANCE_LEDGER",
    ]

    results = [_run_epoch(epoch) for epoch in epochs]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    summary_lines = [
        "# Verification Summary Dashboard",
        "",
        f"Generated: {now} UTC",
        "",
        "| Epoch | Certified | Last Certified Date | Notes |",
        "|---|---|---|---|",
    ]
    for result in results:
        valid = bool(result.get("valid"))
        notes = ""
        if not valid:
            notes = "; ".join(v.get("check", "") for v in result.get("violations", [])[:2])
        summary_lines.append(
            f"| {result.get('epoch')} | {'yes' if valid else 'no'} | {now if valid else '-'} | {notes or '-'} |"
        )

    output_path = repo_root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(json.dumps({"results": results}, indent=2))
    return 0 if all(bool(item.get("valid")) for item in results if item.get("epoch") in {"M7_EPOCH_AUDIT_CERTIFICATION", "M8_CHANGE_CONTROL", "M9_SIGNAL_SEMANTICS_REGISTRY"}) else 1


if __name__ == "__main__":
    raise SystemExit(main())
