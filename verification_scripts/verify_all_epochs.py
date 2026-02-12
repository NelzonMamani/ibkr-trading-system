"""Run all metadata epoch verifiers and capture an aggregate summary."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import collect_certification_verdicts, get_repo_root
from src.metadata.m7_epoch_audit_certifier import verify_m7_epoch_audit_and_certification
from src.metadata.m8_change_control_verifier import verify_m8_change_control
from src.metadata.m9_signal_semantics_registry_verifier import verify_m9_signal_semantics_registry
from src.metadata.m10_data_provenance_ledger_verifier import verify_m10_data_provenance_ledger


EPOCHS = [
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


def _run_epoch(epoch: str) -> dict:
    if epoch == "M7_EPOCH_AUDIT_CERTIFICATION":
        return verify_m7_epoch_audit_and_certification(include_core=True)
    if epoch == "M8_CHANGE_CONTROL":
        return verify_m8_change_control(include_core=True)
    if epoch == "M9_SIGNAL_SEMANTICS_REGISTRY":
        return verify_m9_signal_semantics_registry()
    if epoch == "M10_DATA_PROVENANCE_LEDGER":
        return verify_m10_data_provenance_ledger()
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
    results = [_run_epoch(epoch) for epoch in EPOCHS]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    verdicts = collect_certification_verdicts(repo_root)

    summary_lines = [
        "# Verification Summary Dashboard",
        "",
        f"Generated: {now} UTC",
        "",
        "| Epoch | Certified | Last Certified Date | Notes |",
        "|---|---|---|---|",
    ]
    for epoch in EPOCHS:
        verdict = verdicts.get(epoch, {})
        certified = verdict.get("verdict") == "CERTIFIED"
        certified_date = verdict.get("date_utc", "-") if certified else "-"
        notes = "-"
        verifier_result = next((item for item in results if item.get("epoch") == epoch), None)
        if verifier_result and not verifier_result.get("valid"):
            notes = "; ".join(v.get("check", "") for v in verifier_result.get("violations", [])[:2]) or "-"
        summary_lines.append(f"| {epoch} | {'yes' if certified else 'no'} | {certified_date} | {notes} |")

    output_path = repo_root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(json.dumps({"results": results, "verdicts": verdicts}, indent=2))
    required = {"M7_EPOCH_AUDIT_CERTIFICATION", "M8_CHANGE_CONTROL", "M9_SIGNAL_SEMANTICS_REGISTRY", "M10_DATA_PROVENANCE_LEDGER"}
    return 0 if all(verdicts.get(epoch, {}).get("verdict") == "CERTIFIED" for epoch in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
