"""Verification script for M7 epoch audit and certification."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import update_system_state_statuses
from src.metadata.m7_epoch_audit_certifier import (
    EVIDENCE_DIR_REL,
    STATE_FILE_REL,
    verify_m7_epoch_audit_and_certification,
    write_outputs,
)


def _write_verdict(evidence_dir: Path, epoch: str, certified: bool, reasons: list[str]) -> None:
    payload = {
        "epoch": epoch,
        "verdict": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reasons": reasons,
        "evidence": [
            "verification_output.json",
            "verification_summary.md",
            "M7_EVIDENCE_INDEX.json",
        ],
    }
    (evidence_dir / "certification_verdict.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _update_m7_state_if_certified(repo_root: Path, certified: bool) -> None:
    if not certified:
        return
    state_file = repo_root / STATE_FILE_REL
    update_system_state_statuses(state_file, {"M7_EPOCH_AUDIT_CERTIFICATION": "CERTIFIED"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M7 epoch audit and certification")
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument("--metadata-only", action="store_true", default=False)
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

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M7_EVIDENCE_INDEX.json"

    include_core = not args.metadata_only
    result = verify_m7_epoch_audit_and_certification(include_core=include_core)
    write_outputs(result, output_json, output_md, evidence_index_json)

    certified = bool(result.get("valid"))
    reasons = [] if certified else [f"{v['check']}:{v['actual']}" for v in result.get("violations", [])]
    _write_verdict(evidence_dir, result["epoch"], certified=certified, reasons=reasons)

    final_result = verify_m7_epoch_audit_and_certification(include_core=include_core)
    write_outputs(final_result, output_json, output_md, evidence_index_json)

    _update_m7_state_if_certified(REPO_ROOT, certified=bool(final_result.get("valid")))

    print(json.dumps(final_result, indent=2))
    return 0 if final_result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
