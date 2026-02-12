from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

from src.metadata.m0_canon_helpers import get_repo_root, write_json
from src.metadata.m7_epoch_audit_certifier import METADATA_EVIDENCE_DIR_MAP

EPOCH = "M8_CHANGE_CONTROL"
EVIDENCE_DIR_REL = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M8_CHANGE_CONTROL")
STATE_FILE_REL = Path("TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md")


@dataclass(frozen=True)
class ChangeControlViolation:
    check: str
    expected: str
    actual: str


def _record(violations: list[dict], violation: ChangeControlViolation) -> None:
    violations.append(
        {
            "check": violation.check,
            "expected": violation.expected,
            "actual": violation.actual,
        }
    )


def _sorted_violations(violations: list[dict]) -> list[dict]:
    return sorted(
        violations,
        key=lambda item: (
            str(item.get("check", "")),
            str(item.get("actual", "")),
            str(item.get("expected", "")),
        ),
    )


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _is_certified(payload: dict | list | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return (
        payload.get("verdict") == "CERTIFIED"
        or payload.get("status") == "CERTIFIED"
        or payload.get("certified") is True
    )


def _state_certified_epochs(repo_root: Path) -> set[str]:
    path = repo_root / STATE_FILE_REL
    if not path.exists():
        return set()
    certified: set[str] = set()
    pattern = re.compile(r"^-\s+([ME]\d+_[A-Z0-9_]+):\s+([A-Z_]+)$")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(raw_line.strip())
        if match and match.group(2) == "CERTIFIED":
            certified.add(match.group(1))
    return certified


def _epoch_to_evidence_dir(repo_root: Path, epoch: str) -> Path:
    root = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    if epoch.startswith("M"):
        return root / METADATA_EVIDENCE_DIR_MAP.get(epoch, epoch)
    core_match = re.match(r"^E(\d+)_", epoch)
    if core_match:
        return root / f"EPOCH_{int(core_match.group(1)):02d}"
    return root / epoch


def _extract_required_evidence_index_name(verdict_payload: dict | list | None) -> str | None:
    if not isinstance(verdict_payload, dict):
        return None
    evidence = verdict_payload.get("evidence")
    if not isinstance(evidence, list):
        return None
    for entry in evidence:
        if not isinstance(entry, str):
            continue
        name = Path(entry).name
        if "EVIDENCE_INDEX" in name.upper() and name.lower().endswith(".json"):
            return name
    return None


def _discover_certified_epochs_from_verdicts(repo_root: Path) -> set[str]:
    evidence_root = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    if not evidence_root.exists():
        return set()

    discovered: set[str] = set()
    folder_to_metadata_epoch = {
        folder_name: epoch_name
        for epoch_name, folder_name in METADATA_EVIDENCE_DIR_MAP.items()
    }
    for verdict_path in sorted(evidence_root.glob("*/certification_verdict.json")):
        payload = _read_json(verdict_path)
        if not _is_certified(payload):
            continue
        folder_name = verdict_path.parent.name
        if folder_name in folder_to_metadata_epoch:
            discovered.add(folder_to_metadata_epoch[folder_name])
            continue
        epoch_name = payload.get("epoch") if isinstance(payload, dict) else None
        if isinstance(epoch_name, str) and re.match(r"^[ME]\d+_[A-Z0-9_]+$", epoch_name):
            discovered.add(epoch_name)
            continue
        core_match = re.match(r"^EPOCH_(\d{2})$", folder_name)
        if core_match:
            discovered.add(f"E{int(core_match.group(1))}_UNKNOWN")
    return discovered


def verify_m8_change_control(repo_root: Path | None = None, include_core: bool = False) -> dict:
    repo_root = get_repo_root(repo_root)
    violations: list[dict] = []

    state_certified = _state_certified_epochs(repo_root)
    evidence_certified = _discover_certified_epochs_from_verdicts(repo_root)

    audited_epochs = sorted(
        epoch for epoch in state_certified if include_core or epoch.startswith("M")
    )
    for epoch in audited_epochs:
        evidence_dir = _epoch_to_evidence_dir(repo_root, epoch)
        if not evidence_dir.exists():
            _record(
                violations,
                ChangeControlViolation(
                    check="CERTIFIED_EPOCH_EVIDENCE_DIR_EXISTS",
                    expected="present",
                    actual=f"missing:{epoch}:{evidence_dir.name}",
                ),
            )
            continue

        verdict_path = evidence_dir / "certification_verdict.json"
        verdict_payload = _read_json(verdict_path)
        if not isinstance(verdict_payload, dict):
            _record(
                violations,
                ChangeControlViolation(
                    check="CERTIFIED_EPOCH_VERDICT_EXISTS",
                    expected="present_json",
                    actual=f"missing_or_invalid:{epoch}",
                ),
            )
            continue

        if not _is_certified(verdict_payload):
            _record(
                violations,
                ChangeControlViolation(
                    check="SYSTEM_STATE_CERTIFIED_MATCHES_VERDICT",
                    expected="CERTIFIED",
                    actual=f"not_certified:{epoch}",
                ),
            )

        required_index_name = _extract_required_evidence_index_name(verdict_payload)
        if required_index_name and not (evidence_dir / required_index_name).exists():
            _record(
                violations,
                ChangeControlViolation(
                    check="CERTIFIED_EPOCH_EVIDENCE_INDEX_EXISTS",
                    expected=f"present:{required_index_name}",
                    actual=f"missing:{epoch}:{required_index_name}",
                ),
            )

    for epoch in sorted(evidence_certified - state_certified):
        _record(
            violations,
            ChangeControlViolation(
                check="VERDICT_CERTIFIED_MATCHES_SYSTEM_STATE",
                expected="state_declares_CERTIFIED",
                actual=f"missing_in_state:{epoch}",
            ),
        )

    sorted_violations = _sorted_violations(violations)

    return {
        "epoch": EPOCH,
        "valid": not sorted_violations,
        "violations": sorted_violations,
        "include_core": include_core,
        "audited_state_certified_epochs": audited_epochs,
        "evidence_certified_epochs": sorted(evidence_certified),
        "evidence_paths": sorted(
            str(_epoch_to_evidence_dir(repo_root, epoch).relative_to(repo_root))
            for epoch in audited_epochs
            if _epoch_to_evidence_dir(repo_root, epoch).exists()
        ),
    }


def build_evidence_index(files: list[Path]) -> dict:
    return {
        "epoch": EPOCH,
        "files": [
            {
                "file": path.name,
                "bytes": path.stat().st_size,
            }
            for path in sorted(files, key=lambda p: p.name)
        ],
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_summary(result: dict, output_md: Path) -> None:
    lines = [
        "# M8 Change Control Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Audited certified epochs: {len(result.get('audited_state_certified_epochs', []))}",
        f"- Violations: {len(result.get('violations', []))}",
    ]
    if result.get("violations"):
        lines.extend(["", "## Violations"])
        for violation in result["violations"]:
            lines.append(
                "- {check} (expected={expected}, actual={actual})".format(
                    check=violation.get("check"),
                    expected=violation.get("expected"),
                    actual=violation.get("actual"),
                )
            )
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(result: dict, output_json: Path, output_md: Path, evidence_index_json: Path) -> None:
    write_json(output_json, result)
    write_summary(result, output_md)
    evidence_dir = evidence_index_json.parent
    evidence_files = [
        path
        for path in evidence_dir.iterdir()
        if path.is_file() and path.name != evidence_index_json.name
    ]
    write_json(evidence_index_json, build_evidence_index(evidence_files))
