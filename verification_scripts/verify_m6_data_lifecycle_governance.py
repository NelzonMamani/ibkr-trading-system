"""Verification script for M6 data lifecycle governance."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m6_data_lifecycle_governance_verifier import (
    EVIDENCE_DIR_REL,
    verify_m6_data_lifecycle_governance,
    write_outputs,
)


def _run_to_file(command: list[str], output_path: Path) -> int:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    rendered = [f"$ {' '.join(command)}", "", completed.stdout, completed.stderr]
    output_path.write_text("\n".join(rendered).strip() + "\n", encoding="utf-8")
    return completed.returncode


def _write_verdict(evidence_dir: Path, epoch: str, certified: bool, reasons: list[str]) -> None:
    payload = {
        "epoch": epoch,
        "verdict": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reasons": reasons,
        "evidence": [
            "verification_output.json",
            "verification_summary.md",
            "compileall.txt",
            "pytest.txt",
            "pytest_full.txt",
            "M6_EVIDENCE_INDEX.json",
        ],
    }
    (evidence_dir / "certification_verdict.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M6 data lifecycle governance")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    evidence_dir = REPO_ROOT / EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)

    if not args.allow_overwrite and any(
        (evidence_dir / name).exists() for name in ("compileall.txt", "pytest.txt", "pytest_full.txt")
    ):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    status = 0
    status |= _run_to_file([sys.executable, "-m", "compileall", "-q", "src"], evidence_dir / "compileall.txt")
    status |= _run_to_file(
        [sys.executable, "-m", "pytest", "tests/test_epoch3_risk_execution.py::test_idempotency_prevents_duplicate_submissions", "-q"],
        evidence_dir / "pytest.txt",
    )
    status |= _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M6_EVIDENCE_INDEX.json"

    result = verify_m6_data_lifecycle_governance()
    write_outputs(result, output_json, output_md, evidence_index_json)

    certified = status == 0
    reasons = [] if certified else [f"{v['check']}:{v['actual']}" for v in result.get("violations", [])]
    _write_verdict(evidence_dir, result["epoch"], certified=certified, reasons=reasons)

    final_result = verify_m6_data_lifecycle_governance()
    write_outputs(final_result, output_json, output_md, evidence_index_json)
    stable_result = verify_m6_data_lifecycle_governance()
    write_outputs(stable_result, output_json, output_md, evidence_index_json)
    print(json.dumps(stable_result, indent=2))
    return 0 if stable_result.get("valid") and status == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
