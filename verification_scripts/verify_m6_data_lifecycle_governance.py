"""Verification script for M6 data lifecycle governance."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m6_data_lifecycle_governance_verifier import (
    ALLOWED_PREEXISTING_FILES,
    EVIDENCE_DIR_REL,
    REQUIRED_EVIDENCE_FILES,
    RUN_METADATA_FILE,
    build_certification_verdict,
    build_run_metadata,
    verify_m6_data_lifecycle_governance,
    write_outputs,
)
from src.metadata.m0_canon_helpers import write_json


def _list_existing_files(evidence_dir: Path) -> list[str]:
    if not evidence_dir.exists():
        return []
    return sorted([path.name for path in evidence_dir.iterdir() if path.is_file()])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify M6 data lifecycle governance and write evidence bundle."
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Allow overwriting existing evidence files in the M6 audit folder.",
    )
    args = parser.parse_args()

    evidence_dir = REPO_ROOT / EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)

    preexisting_files = _list_existing_files(evidence_dir)
    unexpected_preexisting = [
        name for name in preexisting_files if name not in ALLOWED_PREEXISTING_FILES
    ]
    if unexpected_preexisting and not args.allow_overwrite:
        print(
            "[M6][ERROR] Evidence files already exist. "
            "Use --allow-overwrite to overwrite."
        )
        return 1

    run_metadata = build_run_metadata(preexisting_files, args.allow_overwrite)
    write_json(evidence_dir / RUN_METADATA_FILE, run_metadata)

    result = verify_m6_data_lifecycle_governance()

    evidence_files = [
        name
        for name in REQUIRED_EVIDENCE_FILES
        if name != "M6_EVIDENCE_INDEX.json"
    ] + [RUN_METADATA_FILE]
    verdict_payload = build_certification_verdict(result, evidence_files)
    write_json(evidence_dir / "certification_verdict.json", verdict_payload)

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M6_EVIDENCE_INDEX.json"

    write_outputs(result, output_json, output_md, evidence_index_json)

    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
