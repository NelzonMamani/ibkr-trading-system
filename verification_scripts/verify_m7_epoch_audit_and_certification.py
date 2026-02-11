"""Verification script for M7 epoch audit and certification."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m7_epoch_audit_certifier import (
    EVIDENCE_DIR_REL,
    verify_m7_epoch_audit_and_certification,
    write_outputs,
)


def _run_to_file(command: list[str], output_path: Path) -> int:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
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
            "pytest_full.txt",
            "M7_EVIDENCE_INDEX.json",
        ],
    }
    (evidence_dir / "certification_verdict.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _update_system_state_if_certified(certified: bool) -> None:
    if not certified:
        return
    certified_state_path = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "SYSTEM_STATE_CERTIFIED.md"
    root_state_path = REPO_ROOT / "SYSTEM_STATE.md"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    certified_text = certified_state_path.read_text(encoding="utf-8")
    certified_text = certified_text.replace(
        "- M7_EPOCH_AUDIT_CERTIFICATION: NOT_STARTED",
        "- M7_EPOCH_AUDIT_CERTIFICATION: CERTIFIED",
    )
    certified_text = certified_text.replace(
        "**Last updated:** 2026-02-10",
        f"**Last updated:** {today}",
    )
    certified_state_path.write_text(certified_text, encoding="utf-8")

    root_text = root_state_path.read_text(encoding="utf-8")
    root_text = root_text.replace("Last Updated: 2026-02-02", f"Last Updated: {today}")
    root_state_path.write_text(root_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M7 epoch audit and certification")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    evidence_dir = REPO_ROOT / EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)

    if not args.allow_overwrite and any(
        (evidence_dir / name).exists() for name in ("compileall.txt", "pytest_full.txt")
    ):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    status = 0
    status |= _run_to_file([sys.executable, "-m", "compileall", "-q", "src"], evidence_dir / "compileall.txt")
    status |= _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    output_json = evidence_dir / "verification_output.json"
    output_md = evidence_dir / "verification_summary.md"
    evidence_index_json = evidence_dir / "M7_EVIDENCE_INDEX.json"

    result = verify_m7_epoch_audit_and_certification()
    write_outputs(result, output_json, output_md, evidence_index_json)

    certified = status == 0 and result.get("valid", False)
    reasons = [] if certified else [f"{v['check']}:{v['actual']}" for v in result.get("violations", [])]
    if status != 0:
        reasons.append("execution:compileall_or_pytest_failed")
    _write_verdict(evidence_dir, result["epoch"], certified=certified, reasons=sorted(set(reasons)))

    final_result = verify_m7_epoch_audit_and_certification()
    write_outputs(final_result, output_json, output_md, evidence_index_json)

    stable_result = verify_m7_epoch_audit_and_certification()
    write_outputs(stable_result, output_json, output_md, evidence_index_json)

    final_certified = status == 0 and stable_result.get("valid", False)
    _write_verdict(evidence_dir, stable_result["epoch"], certified=final_certified, reasons=[] if final_certified else sorted(set(reasons)))
    _update_system_state_if_certified(final_certified)
    print(json.dumps(stable_result, indent=2))
    return 0 if final_certified else 1


if __name__ == "__main__":
    raise SystemExit(main())
