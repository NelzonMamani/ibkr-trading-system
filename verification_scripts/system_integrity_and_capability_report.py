"""Authoritative system integrity and capability reconciliation report."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import update_system_state_statuses
from src.metadata.m7_epoch_audit_certifier import verify_m7_epoch_audit_and_certification
from src.metadata.m8_change_control_verifier import verify_m8_change_control
from src.metadata.m9_signal_semantics_registry_verifier import verify_m9_signal_semantics_registry
from src.metadata.m10_data_provenance_ledger_verifier import verify_m10_data_provenance_ledger

EPOCH = "SYSTEM_INTEGRITY_AND_CAPABILITY_REPORT"
EVIDENCE_DIR_REL = "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/SYSTEM_INTEGRITY_AND_CAPABILITY_REPORT"
STATE_FILE_REL = "TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md"
CROSSWALK_FILE_REL = "TRADING_OS_MASTER_CATALOGUE/CAPABILITY_CROSSWALK.md"
DERIVED_CROSSWALK_FILE_REL = "TRADING_OS_MASTER_CATALOGUE/CAPABILITY_CROSSWALK_DERIVED.md"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_to_file(command: list[str], output_path: Path, timeout_s: int | None = None) -> int:
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
        rendered = [f"$ {' '.join(command)}", "", completed.stdout, completed.stderr]
        rc = completed.returncode
    except subprocess.TimeoutExpired as exc:
        rendered = [
            f"$ {' '.join(command)}",
            "",
            exc.stdout or "",
            exc.stderr or "",
            f"TIMEOUT after {timeout_s}s",
        ]
        rc = 124
    output_path.write_text("\n".join(rendered).strip() + "\n", encoding="utf-8")
    return rc


def _stable_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: _stable_payload(v) for k, v in payload.items() if k not in {"generated_at_utc", "generated_at"}}
    if isinstance(payload, list):
        return [_stable_payload(item) for item in payload]
    return payload


def _collect_verdicts() -> dict[str, str]:
    verdicts: dict[str, str] = {}
    evidence_root = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    for verdict_file in sorted(evidence_root.glob("*/certification_verdict.json")):
        try:
            payload = json.loads(verdict_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        epoch = payload.get("epoch")
        if not isinstance(epoch, str):
            epoch = verdict_file.parent.name

        verdict = payload.get("verdict") or payload.get("status")
        is_certified = False
        if isinstance(verdict, str):
            is_certified = verdict.upper() == "CERTIFIED"
        elif isinstance(payload.get("certified"), bool):
            is_certified = bool(payload.get("certified"))

        if not is_certified:
            continue

        date_utc = payload.get("date_utc") or payload.get("verified_at") or "UNKNOWN"
        verdicts[epoch] = str(date_utc)
    return verdicts


def _parse_system_state_epochs(state_path: Path) -> dict[str, str]:
    pattern = re.compile(r"^\s*-\s+([ME]\d+_[A-Z0-9_]+):\s+([A-Z_]+)\s*$")
    out: dict[str, str] = {}
    for line in state_path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            out[match.group(1)] = match.group(2)
    return out


def _state_aliases() -> dict[str, str]:
    return {
        "M0_CANON_AND_SOURCES_OF_TRUTH": "M0_CANON",
        "M3_MODE_SEMANTICS_CERTIFICATION": "M3_MODE_SEMANTICS_CERT",
        "M6_DATA_LIFECYCLE_GOVERNANCE": "M6_DATA_LIFECYCLE_GOV",
    }


def _write_crosswalk_notice(crosswalk_path: Path) -> bool:
    if not crosswalk_path.exists():
        return False
    content = crosswalk_path.read_text(encoding="utf-8")
    note = "> **Notice:** Status is informational; authoritative certification truth is derived from audit verdicts."
    if note in content:
        return False
    lines = content.splitlines()
    insert_at = 1 if lines and lines[0].startswith("#") else 0
    lines[insert_at:insert_at] = ["", note, ""]
    crosswalk_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return True


def _derive_crosswalk(state_epochs: dict[str, str], verdict_epochs: set[str]) -> str:
    lines = [
        "# CAPABILITY_CROSSWALK_DERIVED",
        "",
        "Derived from `SYSTEM_STATE_CERTIFIED.md` + audit `certification_verdict.json` files.",
        "",
        "| Epoch | Derived Status | Source |",
        "| --- | --- | --- |",
    ]
    for epoch in sorted(state_epochs):
        if epoch in verdict_epochs:
            status = "CERTIFIED"
            source = "audit_verdict"
        else:
            state_status = state_epochs[epoch]
            if state_status in {"IMPLEMENTED_UNCERTIFIED", "NOT_STARTED"}:
                status = state_status
            else:
                status = "UNKNOWN"
            source = "system_state"
        lines.append(f"| {epoch} | {status} | {source} |")
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _build_evidence_index(evidence_dir: Path) -> dict[str, Any]:
    files = []
    for file_path in sorted(path for path in evidence_dir.iterdir() if path.is_file()):
        files.append({"file": file_path.name, "bytes": file_path.stat().st_size})
    return {"epoch": EPOCH, "generated_at_utc": _now_utc(), "files": files}


def main() -> int:
    parser = argparse.ArgumentParser(description="System integrity and capability reconciliation report")
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

    required_files = [
        "integrity_report.json",
        "integrity_report.md",
        "capability_report.json",
        "capability_report.md",
        "compileall.txt",
        "pytest_full.txt",
        "boot_SIM.txt",
        "boot_PAPER.txt",
        "boot_READ_ONLY.txt",
        "boot_LIVE.txt",
        "verify_m7.txt",
        "verify_m8.txt",
        "verify_m9.txt",
        "verify_m10.txt",
        "certification_verdict.json",
        "EVIDENCE_INDEX.json",
    ]
    if not args.allow_overwrite and any((evidence_dir / name).exists() for name in required_files):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    compileall_rc = _run_to_file([sys.executable, "-m", "compileall", "-q", "src", "tests", "verification_scripts"], evidence_dir / "compileall.txt")
    pytest_rc = _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    verifier_commands = {
        "M7": [sys.executable, "verification_scripts/verify_m7_epoch_audit_and_certification.py", "--allow-overwrite"],
        "M8": [sys.executable, "verification_scripts/verify_m8_change_control.py", "--allow-overwrite"],
        "M9": [sys.executable, "verification_scripts/verify_m9_signal_semantics_registry.py", "--allow-overwrite"],
        "M10": [sys.executable, "verification_scripts/verify_m10_data_provenance_ledger.py", "--allow-overwrite"],
    }
    verifier_rc: dict[str, int] = {}
    for key, command in verifier_commands.items():
        verifier_rc[key] = _run_to_file(command, evidence_dir / f"verify_{key.lower()}.txt")

    verifier_payloads = {
        "M7": verify_m7_epoch_audit_and_certification(include_core=True),
        "M8": verify_m8_change_control(include_core=True),
        "M9": verify_m9_signal_semantics_registry(),
        "M10": verify_m10_data_provenance_ledger(),
    }
    deterministic = {
        "M7": _stable_payload(verifier_payloads["M7"]) == _stable_payload(verify_m7_epoch_audit_and_certification(include_core=True)),
        "M8": _stable_payload(verifier_payloads["M8"]) == _stable_payload(verify_m8_change_control(include_core=True)),
        "M9": _stable_payload(verifier_payloads["M9"]) == _stable_payload(verify_m9_signal_semantics_registry()),
        "M10": _stable_payload(verifier_payloads["M10"]) == _stable_payload(verify_m10_data_provenance_ledger()),
    }

    boot_targets = [
        ("SIM", "ross_momentum", "boot_SIM.txt"),
        ("PAPER", "ross_momentum", "boot_PAPER.txt"),
        ("READ_ONLY", "ross_momentum", "boot_READ_ONLY.txt"),
        ("LIVE", "ross_momentum", "boot_LIVE.txt"),
        ("SIM", "statistical_intraday_momentum", "boot_SIM_statistical_intraday_momentum.txt"),
        ("READ_ONLY", "statistical_intraday_momentum", "boot_READ_ONLY_statistical_intraday_momentum.txt"),
    ]
    boot_results: list[dict[str, Any]] = []
    for mode, strategy, filename in boot_targets:
        command = [sys.executable, "-m", "src.main", "--mode", mode, "--cycles", "1", "--strategy", strategy]
        rc = _run_to_file(command, evidence_dir / filename, timeout_s=120)
        boot_results.append({"mode": mode, "strategy": strategy, "file": filename, "rc": rc})

    state_path = REPO_ROOT / STATE_FILE_REL
    verdict_map = _collect_verdicts()
    state_epochs_before = _parse_system_state_epochs(state_path)
    aliases = _state_aliases()

    certified_epochs_from_verdicts = {epoch: date for epoch, date in sorted(verdict_map.items())}
    state_certified_epochs = {epoch for epoch, status in state_epochs_before.items() if status == "CERTIFIED"}
    normalized_state_certified = set(state_certified_epochs)
    verdict_certified_epochs = {aliases.get(epoch, epoch) for epoch in certified_epochs_from_verdicts}

    drift_before = {
        "epochs_certified_in_state_but_not_in_verdicts": sorted(normalized_state_certified - verdict_certified_epochs),
        "epochs_certified_in_verdicts_but_not_in_state": sorted(verdict_certified_epochs - normalized_state_certified),
    }

    recommended_updates: dict[str, str] = {}
    for verdict_epoch in verdict_certified_epochs:
        state_epoch = aliases.get(verdict_epoch, verdict_epoch)
        if state_epochs_before.get(state_epoch) != "CERTIFIED":
            recommended_updates[state_epoch] = "CERTIFIED"

    if recommended_updates:
        update_system_state_statuses(state_path, recommended_updates)

    state_epochs_after = _parse_system_state_epochs(state_path)
    state_certified_after = {epoch for epoch, status in state_epochs_after.items() if status == "CERTIFIED"}
    normalized_state_after = set(state_certified_after)
    drift_after = {
        "epochs_certified_in_state_but_not_in_verdicts": sorted(normalized_state_after - verdict_certified_epochs),
        "epochs_certified_in_verdicts_but_not_in_state": sorted(verdict_certified_epochs - normalized_state_after),
    }

    crosswalk_updated = _write_crosswalk_notice(REPO_ROOT / CROSSWALK_FILE_REL)
    derived_crosswalk_path = REPO_ROOT / DERIVED_CROSSWALK_FILE_REL
    derived_crosswalk_path.write_text(
        _derive_crosswalk(state_epochs_after, verdict_certified_epochs),
        encoding="utf-8",
    )

    integrity_report = {
        "epoch": EPOCH,
        "generated_at_utc": _now_utc(),
        "compileall_rc": compileall_rc,
        "pytest_rc": pytest_rc,
        "verifier_command_rc": verifier_rc,
        "verifier_valid": {k: bool(v.get("valid")) for k, v in verifier_payloads.items()},
        "verifier_deterministic_excluding_generated_at_utc": deterministic,
        "boot_results": boot_results,
    }

    capability_report = {
        "epoch": EPOCH,
        "generated_at_utc": _now_utc(),
        "certified_epochs_from_verdicts": certified_epochs_from_verdicts,
        "system_state_epochs": state_epochs_after,
        "drift": drift_after,
        "drift_before_reconciliation": drift_before,
        "recommended_state_updates": dict(sorted(recommended_updates.items())),
        "capability_crosswalk_notice_updated": crosswalk_updated,
        "derived_crosswalk": DERIVED_CROSSWALK_FILE_REL,
    }

    _write_json(evidence_dir / "integrity_report.json", integrity_report)
    _write_json(evidence_dir / "capability_report.json", capability_report)

    _write_markdown(
        evidence_dir / "integrity_report.md",
        [
            "# System Integrity Report",
            "",
            f"- Generated: `{integrity_report['generated_at_utc']}`",
            f"- compileall rc: `{compileall_rc}`",
            f"- pytest rc: `{pytest_rc}`",
            "",
            "## Metadata Verifiers",
            *[
                f"- {name}: rc=`{verifier_rc[name]}` valid=`{integrity_report['verifier_valid'][name]}` deterministic=`{deterministic[name]}`"
                for name in ("M7", "M8", "M9", "M10")
            ],
            "",
            "## Boot Results",
            *[
                f"- mode=`{item['mode']}` strategy=`{item['strategy']}` rc=`{item['rc']}` file=`{item['file']}`"
                for item in boot_results
            ],
        ],
    )

    _write_markdown(
        evidence_dir / "capability_report.md",
        [
            "# Capability Reconciliation Report",
            "",
            f"- Generated: `{capability_report['generated_at_utc']}`",
            f"- Drift after reconciliation: `{capability_report['drift']}`",
            f"- Recommended updates applied: `{capability_report['recommended_state_updates']}`",
            f"- Derived crosswalk: `{DERIVED_CROSSWALK_FILE_REL}`",
        ],
    )

    reasons: list[str] = []
    if compileall_rc != 0:
        reasons.append(f"compileall_failed:{compileall_rc}")
    if pytest_rc != 0:
        reasons.append(f"pytest_failed:{pytest_rc}")
    for name in ("M7", "M8", "M9", "M10"):
        if verifier_rc[name] != 0:
            reasons.append(f"{name.lower()}_command_failed:{verifier_rc[name]}")
        if not integrity_report["verifier_valid"].get(name):
            reasons.append(f"{name.lower()}_invalid")
        if not deterministic.get(name):
            reasons.append(f"{name.lower()}_non_deterministic")
    for boot in boot_results:
        if boot["rc"] != 0:
            reasons.append(f"boot_failed:{boot['mode']}:{boot['strategy']}")
    if capability_report["drift"]["epochs_certified_in_state_but_not_in_verdicts"] or capability_report["drift"]["epochs_certified_in_verdicts_but_not_in_state"]:
        reasons.append("capability_drift_not_reconciled")

    certified = not reasons
    verdict_payload = {
        "epoch": EPOCH,
        "verdict": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reasons": reasons,
        "evidence": required_files,
    }
    _write_json(evidence_dir / "certification_verdict.json", verdict_payload)

    _write_json(evidence_dir / "EVIDENCE_INDEX.json", _build_evidence_index(evidence_dir))
    print(json.dumps({"certified": certified, "reasons": reasons}, indent=2))
    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())
