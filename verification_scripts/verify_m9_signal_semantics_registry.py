"""Verification script for M9 signal semantics registry."""

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
from src.metadata.m8_change_control_verifier import verify_m8_change_control
from src.metadata.m0_canon_helpers import write_json
from src.metadata.m9_signal_semantics_registry_verifier import (
    EPOCH,
    EVIDENCE_DIR_REL,
    STATE_FILE_REL,
    build_evidence_index,
    verify_m9_signal_semantics_registry,
    write_outputs,
)


def _run_to_file(command: list[str], output_path: Path) -> int:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    rendered = [f"$ {' '.join(command)}", "", completed.stdout, completed.stderr]
    output_path.write_text("\n".join(rendered).strip() + "\n", encoding="utf-8")
    return completed.returncode


def _stable_payload(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k != "generated_at_utc"}


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
            "M9_EVIDENCE_INDEX.json",
            "certification_verdict.json",
        ],
    }
    (evidence_dir / "certification_verdict.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _update_system_state_if_certified(repo_root: Path, certified: bool) -> None:
    if not certified:
        return
    state_file = repo_root / STATE_FILE_REL
    update_system_state_statuses(state_file, {"M9_SIGNAL_SEMANTICS_REGISTRY": "CERTIFIED"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M9 signal semantics registry")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    evidence_dir = REPO_ROOT / EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)

    required_outputs = (
        "compileall.txt",
        "pytest_full.txt",
        "verification_output.json",
        "verification_summary.md",
        "M9_EVIDENCE_INDEX.json",
        "certification_verdict.json",
    )
    if not args.allow_overwrite and any((evidence_dir / name).exists() for name in required_outputs):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    status = 0
    status |= _run_to_file(
        [sys.executable, "-m", "compileall", "-q", "src", "tests", "verification_scripts"],
        evidence_dir / "compileall.txt",
    )
    status |= _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    m9_result = verify_m9_signal_semantics_registry()
    second_pass = verify_m9_signal_semantics_registry()
    if {k: v for k, v in m9_result.items() if k != "generated_at_utc"} != {
        k: v for k, v in second_pass.items() if k != "generated_at_utc"
    }:
        status |= 1
        violations = list(m9_result.get("violations", []))
        violations.append(
            {
                "check": "M9_VERIFIER_SCRIPT_DETERMINISTIC_OUTPUT",
                "expected": "stable_result",
                "actual": "non_deterministic_output_detected",
            }
        )
        m9_result = dict(m9_result)
        m9_result["violations"] = sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"]))
        m9_result["valid"] = False

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M9_EVIDENCE_INDEX.json"
    write_outputs(m9_result, output_json, output_md, evidence_index_json)

    # Non-regression checks for existing verifiers (must execute deterministically).
    m7_result = verify_m7_epoch_audit_and_certification(include_core=True)
    m8_result = verify_m8_change_control()
    if _stable_payload(m7_result) != _stable_payload(verify_m7_epoch_audit_and_certification(include_core=True)):
        status |= 1
    if _stable_payload(m8_result) != _stable_payload(verify_m8_change_control()):
        status |= 1

    certified = status == 0 and bool(m9_result.get("valid"))
    reasons: list[str] = []
    if status != 0:
        reasons.append("execution_checks_failed")
    reasons.extend(f"{v['check']}:{v['actual']}" for v in m9_result.get("violations", []))

    _write_verdict(evidence_dir, certified=certified, reasons=sorted(set(reasons)))

    evidence_files = [
        evidence_dir / "compileall.txt",
        evidence_dir / "pytest_full.txt",
        evidence_dir / "verification_output.json",
        evidence_dir / "verification_summary.md",
        evidence_dir / "certification_verdict.json",
    ]
    write_json(evidence_index_json, build_evidence_index(evidence_files))

    _update_system_state_if_certified(REPO_ROOT, certified=certified)

    final_result = verify_m9_signal_semantics_registry()
    write_outputs(final_result, output_json, output_md, evidence_index_json)
    write_json(evidence_index_json, build_evidence_index(evidence_files))

    print(json.dumps(final_result, indent=2))
    return 0 if certified and final_result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
