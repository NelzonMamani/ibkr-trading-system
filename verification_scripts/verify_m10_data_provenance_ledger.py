"""Verification entrypoint for M10 data provenance ledger."""

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
from src.metadata.m10_data_provenance_ledger_verifier import (
    EPOCH,
    EVIDENCE_DIR_REL,
    STATE_FILE_REL,
    build_evidence_index,
    verify_m10_data_provenance_ledger,
    write_outputs,
)
from src.metadata.m7_epoch_audit_certifier import verify_m7_epoch_audit_and_certification
from src.metadata.m8_change_control_verifier import verify_m8_change_control
from src.metadata.m9_signal_semantics_registry_verifier import verify_m9_signal_semantics_registry


def _run_to_file(command: list[str], output_path: Path) -> int:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    rendered = [f"$ {' '.join(command)}", "", completed.stdout, completed.stderr]
    output_path.write_text("\n".join(rendered).strip() + "\n", encoding="utf-8")
    return completed.returncode


def _stable(payload: dict) -> dict:
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
            "sample_data_provenance_ledger.jsonl",
            "certification_verdict.json",
        ],
    }
    (evidence_dir / "certification_verdict.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _update_system_state_if_certified(repo_root: Path, certified: bool) -> None:
    if not certified:
        return
    path = repo_root / STATE_FILE_REL
    if not path.exists():
        return
    updated: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("- M10_DATA_PROVENANCE_LEDGER:"):
            updated.append("- M10_DATA_PROVENANCE_LEDGER: CERTIFIED")
        else:
            updated.append(line)
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


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
        "sample_data_provenance_ledger.jsonl",
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

    result = verify_m10_data_provenance_ledger()
    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M10_EVIDENCE_INDEX.json"
    write_outputs(result, output_json, output_md, evidence_index_json)

    m7 = verify_m7_epoch_audit_and_certification(include_core=True)
    m8 = verify_m8_change_control()
    m9 = verify_m9_signal_semantics_registry()
    if _stable(m7) != _stable(verify_m7_epoch_audit_and_certification(include_core=True)):
        status |= 1
    if _stable(m8) != _stable(verify_m8_change_control()):
        status |= 1
    if _stable(m9) != _stable(verify_m9_signal_semantics_registry()):
        status |= 1

    certified = status == 0 and bool(result.get("valid"))
    reasons: list[str] = []
    if status != 0:
        reasons.append("execution_checks_failed")
    reasons.extend(f"{v['check']}:{v['actual']}" for v in result.get("violations", []))

    _write_verdict(evidence_dir, certified=certified, reasons=sorted(set(reasons)))
    evidence_files = [
        evidence_dir / "compileall.txt",
        evidence_dir / "pytest_full.txt",
        evidence_dir / "verification_output.json",
        evidence_dir / "verification_summary.md",
        evidence_dir / "sample_data_provenance_ledger.jsonl",
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
