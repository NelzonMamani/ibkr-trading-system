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

from src.metadata.m0_canon_helpers import write_json
from src.metadata.m9_signal_semantics_registry_verifier import EPOCH, verify_m9_signal_semantics_registry

EVIDENCE_DIR_REL = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M9_SIGNAL_SEMANTICS_REGISTRY")
STATE_FILE_REL = Path("TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md")


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


def _build_evidence_index(evidence_dir: Path, index_name: str) -> dict:
    files = [
        path
        for path in evidence_dir.iterdir()
        if path.is_file() and path.name != index_name
    ]
    return {
        "epoch": EPOCH,
        "files": [
            {
                "file": path.name,
                "bytes": path.stat().st_size,
            }
            for path in sorted(files, key=lambda p: p.name)
        ],
    }


def _write_summary(result: dict, output_path: Path) -> None:
    lines = [
        "# M9 Signal Semantics Registry Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Signals: {result.get('counts', {}).get('signals', 0)}",
        f"- Violations: {len(result.get('violations', []))}",
    ]
    violations = result.get("violations", [])
    if violations:
        lines.extend(["", "## Violations"])
        for violation in violations:
            lines.append(
                "- {check} (expected={expected}, actual={actual})".format(
                    check=violation.get("check"),
                    expected=violation.get("expected"),
                    actual=violation.get("actual"),
                )
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
            "M9_EVIDENCE_INDEX.json",
        ],
    }
    write_json(evidence_dir / "certification_verdict.json", payload)


def _update_system_state_if_certified(certified: bool) -> None:
    if not certified:
        return
    state_file = REPO_ROOT / STATE_FILE_REL
    if not state_file.exists():
        return
    updated: list[str] = []
    for line in state_file.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("- M9_SIGNAL_SEMANTICS_REGISTRY:"):
            updated.append("- M9_SIGNAL_SEMANTICS_REGISTRY: CERTIFIED")
        else:
            updated.append(line)
    state_file.write_text("\n".join(updated) + "\n", encoding="utf-8")


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
    status |= _run_to_file([sys.executable, "-m", "compileall", "-q", "src", "tests", "verification_scripts"], evidence_dir / "compileall.txt")
    status |= _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    first_result = verify_m9_signal_semantics_registry(REPO_ROOT)
    second_result = verify_m9_signal_semantics_registry(REPO_ROOT)
    if first_result != second_result:
        status |= 1
        result = dict(first_result)
        violations = list(result.get("violations", []))
        violations.append(
            {
                "check": "DETERMINISTIC_OUTPUT",
                "expected": "stable_across_runs",
                "actual": "results_differ_between_two_calls",
            }
        )
        result["violations"] = sorted(violations, key=lambda x: (x["check"], x["actual"], x["expected"]))
        result["valid"] = False
    else:
        result = dict(first_result)

    output_json = evidence_dir / "verification_output.json"
    write_json(output_json, result)

    output_md = evidence_dir / "verification_summary.md"
    _write_summary(result, output_md)

    evidence_index_path = evidence_dir / "M9_EVIDENCE_INDEX.json"
    write_json(evidence_index_path, _build_evidence_index(evidence_dir, evidence_index_path.name))

    certified = status == 0 and bool(result.get("valid"))
    reasons: list[str] = []
    if status != 0:
        reasons.append("execution_checks_failed")
    reasons.extend(f"{v['check']}:{v['actual']}" for v in result.get("violations", []))
    _write_verdict(evidence_dir, certified=certified, reasons=reasons)

    _update_system_state_if_certified(certified)

    print(json.dumps(result, indent=2))
    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())
