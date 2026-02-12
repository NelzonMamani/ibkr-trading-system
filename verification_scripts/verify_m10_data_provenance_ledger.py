"""Verification script for M10 data provenance ledger."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import write_json
from src.metadata.m7_epoch_audit_certifier import verify_m7_epoch_audit_and_certification
from src.metadata.m8_change_control_verifier import verify_m8_change_control
from src.metadata.m9_signal_semantics_registry_verifier import verify_m9_signal_semantics_registry
from src.metadata.m10_data_provenance_ledger import (
    EPOCH,
    EVIDENCE_DIR_REL,
    STATE_FILE_REL,
    build_evidence_index,
    verify_m10_data_provenance_ledger,
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
            "M10_EVIDENCE_INDEX.json",
            "certification_verdict.json",
        ],
    }
    (evidence_dir / "certification_verdict.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _update_system_state_if_certified(repo_root: Path, certified: bool) -> None:
    if not certified:
        return
    state_file = repo_root / STATE_FILE_REL
    if not state_file.exists():
        return
    updated: list[str] = []
    for line in state_file.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("- M10_DATA_PROVENANCE_LEDGER:"):
            updated.append("- M10_DATA_PROVENANCE_LEDGER: CERTIFIED")
        else:
            updated.append(line)
    state_file.write_text("\n".join(updated) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M10 data provenance ledger")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    evidence_dir = REPO_ROOT / EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)

    required_outputs = (
        "compileall.txt",
        "pytest_full.txt",
        "verification_output.json",
        "verification_summary.md",
        "M10_EVIDENCE_INDEX.json",
        "certification_verdict.json",
    )
    if not args.allow_overwrite and any((evidence_dir / name).exists() for name in required_outputs):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    status = 0
    status |= _run_to_file([sys.executable, "-m", "compileall", "-q", "src", "tests", "verification_scripts"], evidence_dir / "compileall.txt")
    status |= _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    m10_result = verify_m10_data_provenance_ledger()
    second_pass = verify_m10_data_provenance_ledger()
    if _stable_payload(m10_result) != _stable_payload(second_pass):
        status |= 1
        merged = dict(m10_result)
        violations = list(merged.get("violations", []))
        violations.append(
            {
                "check": "M10_VERIFIER_SCRIPT_DETERMINISTIC_OUTPUT",
                "expected": "stable_result",
                "actual": "non_deterministic_output_detected",
            }
        )
        merged["violations"] = sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"]))
        merged["valid"] = False
        m10_result = merged

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M10_EVIDENCE_INDEX.json"
    write_outputs(m10_result, output_json, output_md, evidence_index_json)

    m7_result = verify_m7_epoch_audit_and_certification(include_core=True)
    m8_result = verify_m8_change_control()
    m9_result = verify_m9_signal_semantics_registry()
    if _stable_payload(m7_result) != _stable_payload(verify_m7_epoch_audit_and_certification(include_core=True)):
        status |= 1
    if _stable_payload(m8_result) != _stable_payload(verify_m8_change_control()):
        status |= 1
    if _stable_payload(m9_result) != _stable_payload(verify_m9_signal_semantics_registry()):
        status |= 1

    certified = status == 0 and bool(m10_result.get("valid")) and bool(m7_result.get("valid")) and bool(m8_result.get("valid")) and bool(m9_result.get("valid"))
    reasons: list[str] = []
    if status != 0:
        reasons.append("execution_checks_failed")
    if not m7_result.get("valid"):
        reasons.append("m7_verifier_failed")
    if not m8_result.get("valid"):
        reasons.append("m8_verifier_failed")
    if not m9_result.get("valid"):
        reasons.append("m9_verifier_failed")
    reasons.extend(f"{v['check']}:{v['actual']}" for v in m10_result.get("violations", []))

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

    final_result = verify_m10_data_provenance_ledger()
    write_outputs(final_result, output_json, output_md, evidence_index_json)
    write_json(evidence_index_json, build_evidence_index(evidence_files))

    print(json.dumps(final_result, indent=2))
    return 0 if certified and final_result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
