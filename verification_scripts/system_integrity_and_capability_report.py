"""System integrity and capability reconciliation report generator."""

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

from src.metadata.m0_canon_helpers import write_json
from src.metadata.m7_epoch_audit_certifier import verify_m7_epoch_audit_and_certification

EPOCH = "SYSTEM_INTEGRITY_AND_CAPABILITY_REPORT"
EVIDENCE_DIR = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / EPOCH

EPOCH_ALIAS_MAP = {
    "M0_CANON_AND_SOURCES_OF_TRUTH": "M0_CANON",
    "M3_MODE_SEMANTICS_CERTIFICATION": "M3_MODE_SEMANTICS_CERT",
    "M9_SIGNAL_SEMANTICS_REGISTRY": "M9_SIGNAL_SEMANTICS_REGISTRY",
}

RUNTIME_WARNING_PATTERNS = (
    "RuntimeWarning: coroutine",
    "was never awaited",
)


def _utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_epoch_id(raw_epoch: str) -> str:
    return EPOCH_ALIAS_MAP.get(raw_epoch, raw_epoch)


def _run_to_file(command: list[str], output_path: Path) -> tuple[int, str]:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    rendered = [f"$ {' '.join(command)}", "", completed.stdout, completed.stderr]
    output = "\n".join(rendered).strip() + "\n"
    output_path.write_text(output, encoding="utf-8")
    return completed.returncode, output


def _contains_unawaited_runtime_warning(text: str) -> bool:
    lowered = text.lower()
    return all(pattern.lower() in lowered for pattern in RUNTIME_WARNING_PATTERNS)


def _collect_capabilities() -> list[dict]:
    evidence_root = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    rows: list[dict] = []
    for verdict_path in sorted(evidence_root.glob("*/certification_verdict.json")):
        try:
            verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(verdict, dict):
            continue
        raw_epoch = str(verdict.get("epoch") or verdict_path.parent.name)
        epoch = _canonical_epoch_id(raw_epoch)
        date_utc = verdict.get("date_utc") or verdict.get("date") or verdict.get("generated_at_utc")
        if isinstance(date_utc, str) and "T" in date_utc:
            date_utc = date_utc.split("T", 1)[0]
        rows.append(
            {
                "epoch": epoch,
                "verdict": verdict.get("verdict") or verdict.get("status") or "UNKNOWN",
                "date_utc": date_utc if date_utc else _utc_date(),
                "source": str(verdict_path.relative_to(REPO_ROOT)),
            }
        )
    deduped: dict[str, dict] = {}
    for row in rows:
        existing = deduped.get(row["epoch"])
        if existing is None:
            deduped[row["epoch"]] = row
            continue
        existing_date = str(existing.get("date_utc") or "")
        row_date = str(row.get("date_utc") or "")
        if row_date >= existing_date:
            deduped[row["epoch"]] = row
    return [deduped[key] for key in sorted(deduped)]


def _write_summary(path: Path, certified: bool, reasons: list[str], m7_result: dict, warnings_found: bool) -> None:
    lines = [
        "# System Integrity and Capability Report",
        "",
        f"- Verdict: {'CERTIFIED' if certified else 'NOT_CERTIFIED'}",
        f"- Generated at (UTC): {_utc_timestamp()}",
        f"- Runtime warning gate triggered: {warnings_found}",
        "- M7 scope (default): metadata + core (include_core=True)",
        f"- M7 valid: {m7_result.get('valid')}",
        "",
    ]
    if reasons:
        lines.append("## Reasons")
        for reason in reasons:
            lines.append(f"- {reason}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate system integrity and capability report")
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument("--allow-runtime-warnings", action="store_true", default=False)
    args = parser.parse_args()

    outputs = (
        "compileall.txt",
        "pytest_full.txt",
        "capability_report.json",
        "integrity_report.json",
        "certification_verdict.json",
        "verification_summary.md",
    )

    if EVIDENCE_DIR.exists() and args.allow_overwrite:
        for child in sorted(EVIDENCE_DIR.iterdir()):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    if not args.allow_overwrite and any((EVIDENCE_DIR / name).exists() for name in outputs):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    compile_rc, _ = _run_to_file(
        [sys.executable, "-m", "compileall", "-q", "src", "tests", "verification_scripts"],
        EVIDENCE_DIR / "compileall.txt",
    )
    pytest_rc, pytest_output = _run_to_file([sys.executable, "-m", "pytest", "-q"], EVIDENCE_DIR / "pytest_full.txt")

    runtime_warning_detected = _contains_unawaited_runtime_warning(pytest_output)
    m7_result = verify_m7_epoch_audit_and_certification(include_core=True)
    capability_rows = _collect_capabilities()

    write_json(
        EVIDENCE_DIR / "capability_report.json",
        {
            "generated_at_utc": _utc_timestamp(),
            "epochs": capability_rows,
            "alias_map": EPOCH_ALIAS_MAP,
        },
    )

    reasons: list[str] = []
    if compile_rc != 0:
        reasons.append("compileall_failed")
    if pytest_rc != 0:
        reasons.append("pytest_failed")
    if runtime_warning_detected and not args.allow_runtime_warnings:
        reasons.append("runtime_warning_unawaited_coroutine_detected")
    if not m7_result.get("valid"):
        reasons.append("m7_epoch_audit_invalid")

    certified = len(reasons) == 0
    integrity_report = {
        "epoch": EPOCH,
        "generated_at_utc": _utc_timestamp(),
        "verdict": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "include_core_default": True,
        "runtime_warning_gate": {
            "allow_runtime_warnings": args.allow_runtime_warnings,
            "runtime_warning_detected": runtime_warning_detected,
        },
        "checks": {
            "compileall_exit_code": compile_rc,
            "pytest_exit_code": pytest_rc,
            "m7_valid": bool(m7_result.get("valid")),
        },
        "reasons": reasons,
    }
    write_json(EVIDENCE_DIR / "integrity_report.json", integrity_report)

    write_json(
        EVIDENCE_DIR / "certification_verdict.json",
        {
            "epoch": EPOCH,
            "verdict": integrity_report["verdict"],
            "date_utc": _utc_date(),
            "reasons": reasons,
            "evidence": list(outputs),
        },
    )

    _write_summary(EVIDENCE_DIR / "verification_summary.md", certified, reasons, m7_result, runtime_warning_detected)
    print(json.dumps(integrity_report, indent=2))
    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())
