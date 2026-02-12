"""Verification script for M8 change control."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import collect_certified_epoch_statuses, update_system_state_statuses
from src.metadata.m7_epoch_audit_certifier import verify_m7_epoch_audit_and_certification
from src.metadata.m8_change_control_verifier import (
    EPOCH,
    EVIDENCE_DIR_REL,
    STATE_FILE_REL,
    verify_m8_change_control,
    write_outputs,
)


def _normalize_output(command: list[str], text: str) -> str:
    if "pytest" in command:
        text = re.sub(r"in\s+\d+\.\d+s", "in <DURATION>", text)
        text = re.sub(r"\(0:0\d:0\d\)", "(<ELAPSED>)", text)
    return text


def _run_to_file(command: list[str], output_path: Path) -> int:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout = _normalize_output(command, completed.stdout)
    stderr = _normalize_output(command, completed.stderr)
    rendered = [f"$ {' '.join(command)}", "", stdout, stderr]
    output_path.write_text("\n".join(rendered).strip() + "\n", encoding="utf-8")
    return completed.returncode


def _stable_payload(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k != "generated_at_utc"}


def _write_verdict(evidence_dir: Path, certified: bool, reasons: list[str]) -> None:
    payload = {
        "epoch": EPOCH,
        "verdict": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reasons": sorted(set(reasons)),
        "evidence": [
            "verification_output.json",
            "verification_summary.md",
            "compileall.txt",
            "pytest_full.txt",
            "m7_verifier_output.json",
            "m8_verifier_output.json",
            "M8_EVIDENCE_INDEX.json",
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

    compileall_rc = _run_to_file([sys.executable, "-m", "compileall", "-q", "src", "tests", "verification_scripts"], evidence_dir / "compileall.txt")
    pytest_rc = _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    m7_result = verify_m7_epoch_audit_and_certification(include_core=False)
    (evidence_dir / "m7_verifier_output.json").write_text(json.dumps(m7_result, indent=2) + "\n", encoding="utf-8")

    first = verify_m8_change_control(include_core=False)
    second = verify_m8_change_control(include_core=False)
    status = 0
    if _stable_payload(first) != _stable_payload(second):
        status |= 1
        first = dict(first)
        violations = list(first.get("violations", []))
        violations.append(
            {
                "check": "M8_VERIFIER_SCRIPT_DETERMINISTIC_OUTPUT",
                "expected": "stable_result",
                "actual": "non_deterministic_output_detected",
            }
        )
        first["violations"] = sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"]))
        first["valid"] = False
    (evidence_dir / "m8_verifier_output.json").write_text(json.dumps(first, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M8_EVIDENCE_INDEX.json"
    write_outputs(first, output_json, output_md, evidence_index_json)

    status |= compileall_rc
    status |= pytest_rc
    certified = status == 0 and bool(m7_result.get("valid")) and bool(first.get("valid"))
    reasons: list[str] = []
    if compileall_rc != 0:
        reasons.append("compileall_failed")
    if pytest_rc != 0:
        reasons.append("pytest_failed")
    if not m7_result.get("valid"):
        reasons.append("m7_verifier_failed")
    reasons.extend(f"{v['check']}:{v['actual']}" for v in first.get("violations", []))

    _write_verdict(evidence_dir, certified=certified, reasons=reasons)
    _reconcile_system_state(REPO_ROOT)

    print(json.dumps(first, indent=2))
    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())
