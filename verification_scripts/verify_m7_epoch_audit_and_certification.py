"""Verification script for M7 epoch audit and certification."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import collect_certified_epoch_statuses, update_system_state_statuses
from src.metadata.m7_epoch_audit_certifier import (
    EVIDENCE_DIR_REL,
    STATE_FILE_REL,
    verify_m7_epoch_audit_and_certification,
    write_outputs,
)


def _stable_payload(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k != "generated_at_utc"}


def _write_verdict(evidence_dir: Path, epoch: str, certified: bool, reasons: list[str]) -> None:
    payload = {
        "epoch": epoch,
        "verdict": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reasons": sorted(set(reasons)),
        "evidence": [
            "verification_output.json",
            "verification_summary.md",
            "M7_EVIDENCE_INDEX.json",
            "certification_verdict.json",
        ],
    }
    (evidence_dir / "certification_verdict.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _reconcile_system_state(repo_root: Path) -> None:
    state_file = repo_root / STATE_FILE_REL
    certified = collect_certified_epoch_statuses(repo_root)
    updates = {epoch: "CERTIFIED" for epoch in ("M7_EPOCH_AUDIT_CERTIFICATION", "M8_CHANGE_CONTROL", "M9_SIGNAL_SEMANTICS_REGISTRY", "M10_DATA_PROVENANCE_LEDGER") if certified.get(epoch) == "CERTIFIED"}
    if certified.get("M0_CANON") == "CERTIFIED":
        updates["M0_CANON"] = "CERTIFIED"
    update_system_state_statuses(state_file, updates)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M7 epoch audit and certification")
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument("--include-core", action="store_true", default=False)
    args = parser.parse_args()

    evidence_dir = REPO_ROOT / EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)

    if not args.allow_overwrite and any(
        (evidence_dir / name).exists()
        for name in (
            "verification_output.json",
            "verification_summary.md",
            "M7_EVIDENCE_INDEX.json",
            "certification_verdict.json",
        )
    ):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    first = verify_m7_epoch_audit_and_certification(include_core=args.include_core)
    second = verify_m7_epoch_audit_and_certification(include_core=args.include_core)

    status = 0
    if _stable_payload(first) != _stable_payload(second):
        status = 1
        first = dict(first)
        violations = list(first.get("violations", []))
        violations.append(
            {
                "check": "M7_VERIFIER_SCRIPT_DETERMINISTIC_OUTPUT",
                "expected": "stable_result",
                "actual": "non_deterministic_output_detected",
            }
        )
        first["violations"] = sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"]))
        first["valid"] = False

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M7_EVIDENCE_INDEX.json"
    write_outputs(first, output_json, output_md, evidence_index_json)

    certified = status == 0 and bool(first.get("valid"))
    reasons = [] if certified else [f"{v['check']}:{v['actual']}" for v in first.get("violations", [])]
    if not certified and status != 0:
        reasons.append("execution_checks_failed")
    _write_verdict(evidence_dir, first["epoch"], certified=certified, reasons=reasons)
    _reconcile_system_state(REPO_ROOT)

    print(json.dumps(first, indent=2))
    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())
