"""Verification script for M8 change control."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import update_system_state_statuses
from src.metadata.m7_epoch_audit_certifier import verify_m7_epoch_audit_and_certification
from src.metadata.m8_change_control_verifier import (
    EVIDENCE_DIR_REL,
    EPOCH,
    STATE_FILE_REL,
    verify_m8_change_control,
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


def _write_verdict(evidence_dir: Path, certified: bool, reasons: list[str]) -> None:
    payload = {
        "epoch": EPOCH,
        "verdict": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reasons": reasons,
        "evidence": [
            "verification_output.json",
            "verification_summary.md",
            "compileall.txt",
            "pytest_full.txt",
            "m7_verifier_output.json",
            "m8_verifier_output.json",
            "M8_EVIDENCE_INDEX.json",
        ],
    }
    (evidence_dir / "certification_verdict.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _update_system_state_if_certified(repo_root: Path, certified: bool) -> None:
    if not certified:
        return
    state_file = repo_root / STATE_FILE_REL
    update_system_state_statuses(state_file, {"M8_CHANGE_CONTROL": "CERTIFIED"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M8 change control")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    evidence_dir = REPO_ROOT / EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)

    required_outputs = (
        "compileall.txt",
        "pytest_full.txt",
        "m7_verifier_output.json",
        "m8_verifier_output.json",
        "verification_output.json",
        "verification_summary.md",
        "M8_EVIDENCE_INDEX.json",
        "certification_verdict.json",
    )
    if not args.allow_overwrite and any((evidence_dir / name).exists() for name in required_outputs):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    status = 0
    status |= _run_to_file([sys.executable, "-m", "compileall", "-q", "src", "tests", "verification_scripts"], evidence_dir / "compileall.txt")
    status |= _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    m7_result = verify_m7_epoch_audit_and_certification(include_core=False)
    (evidence_dir / "m7_verifier_output.json").write_text(json.dumps(m7_result, indent=2) + "\n", encoding="utf-8")

    m8_result = verify_m8_change_control(include_core=False)
    (evidence_dir / "m8_verifier_output.json").write_text(json.dumps(m8_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    second_pass = verify_m8_change_control(include_core=False)
    if m8_result != second_pass:
        status |= 1
        m8_result = dict(m8_result)
        violations = list(m8_result.get("violations", []))
        violations.append(
            {
                "check": "M8_VERIFIER_DETERMINISTIC_OUTPUT",
                "expected": "stable_result",
                "actual": "non_deterministic_output_detected",
            }
        )
        m8_result["violations"] = violations
        m8_result["valid"] = False

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M8_EVIDENCE_INDEX.json"
    write_outputs(m8_result, output_json, output_md, evidence_index_json)

    certified = status == 0 and bool(m7_result.get("valid")) and bool(m8_result.get("valid"))
    reasons: list[str] = []
    if status != 0:
        reasons.append("execution_checks_failed")
    if not m7_result.get("valid"):
        reasons.append("m7_verifier_failed")
    reasons.extend(f"{v['check']}:{v['actual']}" for v in m8_result.get("violations", []))

    _write_verdict(evidence_dir, certified=certified, reasons=sorted(set(reasons)))
    _update_system_state_if_certified(REPO_ROOT, certified=certified)

    final_result = verify_m8_change_control(include_core=False)
    write_outputs(final_result, output_json, output_md, evidence_index_json)

    print(json.dumps(final_result, indent=2))
    return 0 if certified and final_result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
