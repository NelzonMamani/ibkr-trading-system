"""Verification script for M10 data provenance ledger."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import collect_certified_epoch_statuses, update_system_state_statuses, write_json
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
            "M10_EVIDENCE_INDEX.json",
            "certification_verdict.json",
            "PR_VERIFICATION_REPORT.md",
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


def _write_verification_report(
    evidence_dir: Path,
    compileall_rc: int,
    pytest_rc: int,
    cross_results: dict[str, dict],
    determinism_ok: bool,
    certified: bool,
) -> None:
    lines = [
        "# PR Verification Report — M10_DATA_PROVENANCE_LEDGER",
        "",
        "## Commands Executed",
        "- `python -m compileall -q src tests verification_scripts`",
        "- `python -m pytest -q`",
        "- `python verification_scripts/verify_m10_data_provenance_ledger.py --allow-overwrite`",
        "",
        "## Exit Codes",
        f"- compileall: `{compileall_rc}`",
        f"- pytest: `{pytest_rc}`",
        "",
        "## Cross-Verifier Results",
    ]
    for name in ("M7", "M8", "M9", "M10"):
        result = cross_results[name]
        lines.append(f"- {name}: valid=`{result.get('valid')}` violations=`{len(result.get('violations', []))}`")
    lines.extend(
        [
            "",
            "## Determinism Confirmation",
            f"- Stable cross-verifier outputs across two runs (excluding timestamps): `{determinism_ok}`",
            "",
            "## Final Certification Status",
            f"- `{EPOCH}`: `{'CERTIFIED' if certified else 'NOT_CERTIFIED'}`",
        ]
    )
    (evidence_dir / "PR_VERIFICATION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M10 data provenance ledger")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    evidence_dir = REPO_ROOT / EVIDENCE_DIR_REL
    if evidence_dir.exists() and args.allow_overwrite:
        for child in sorted(evidence_dir.iterdir()):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    required_outputs = (
        "compileall.txt",
        "pytest_full.txt",
        "verification_output.json",
        "verification_summary.md",
        "M10_EVIDENCE_INDEX.json",
        "certification_verdict.json",
        "PR_VERIFICATION_REPORT.md",
    )
    if not args.allow_overwrite and any((evidence_dir / name).exists() for name in required_outputs):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    compileall_rc = _run_to_file([sys.executable, "-m", "compileall", "-q", "src", "tests", "verification_scripts"], evidence_dir / "compileall.txt")
    pytest_rc = _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    first = verify_m10_data_provenance_ledger()
    second = verify_m10_data_provenance_ledger()
    status = 0
    if _stable_payload(first) != _stable_payload(second):
        status |= 1
        violations = list(first.get("violations", []))
        violations.append(
            {
                "check": "M10_VERIFIER_SCRIPT_DETERMINISTIC_OUTPUT",
                "expected": "stable_result",
                "actual": "non_deterministic_output_detected",
            }
        )
        first = dict(first)
        first["violations"] = sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"]))
        first["valid"] = False

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M10_EVIDENCE_INDEX.json"
    write_outputs(first, output_json, output_md, evidence_index_json)

    m7_result = verify_m7_epoch_audit_and_certification(include_core=False)
    m8_result = verify_m8_change_control(include_core=False)
    m9_result = verify_m9_signal_semantics_registry()
    cross_results = {"M7": m7_result, "M8": m8_result, "M9": m9_result, "M10": first}

    determinism_ok = True
    determinism_ok = determinism_ok and _stable_payload(m7_result) == _stable_payload(verify_m7_epoch_audit_and_certification(include_core=False))
    determinism_ok = determinism_ok and _stable_payload(m8_result) == _stable_payload(verify_m8_change_control(include_core=False))
    determinism_ok = determinism_ok and _stable_payload(m9_result) == _stable_payload(verify_m9_signal_semantics_registry())
    determinism_ok = determinism_ok and _stable_payload(first) == _stable_payload(verify_m10_data_provenance_ledger())

    if not determinism_ok:
        status |= 1
    status |= compileall_rc
    status |= pytest_rc

    reasons: list[str] = []
    if compileall_rc != 0:
        reasons.append("compileall_failed")
    if pytest_rc != 0:
        reasons.append("pytest_failed")
    if not determinism_ok:
        reasons.append("determinism_failed")
    reasons.extend(f"{v['check']}:{v['actual']}" for v in first.get("violations", []))

    certified = status == 0 and bool(first.get("valid"))
    if not certified:
        for name, result in cross_results.items():
            if not result.get("valid"):
                reasons.append(f"{name.lower()}_verifier_invalid")
    _write_verdict(evidence_dir, certified=certified, reasons=reasons)

    _write_verification_report(
        evidence_dir,
        compileall_rc=compileall_rc,
        pytest_rc=pytest_rc,
        cross_results=cross_results,
        determinism_ok=determinism_ok,
        certified=certified,
    )

    evidence_files = [
        evidence_dir / "compileall.txt",
        evidence_dir / "pytest_full.txt",
        evidence_dir / "verification_output.json",
        evidence_dir / "verification_summary.md",
        evidence_dir / "certification_verdict.json",
        evidence_dir / "PR_VERIFICATION_REPORT.md",
    ]
    write_json(evidence_index_json, build_evidence_index(evidence_files))

    _reconcile_system_state(REPO_ROOT)

    print(json.dumps(first, indent=2))
    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())
