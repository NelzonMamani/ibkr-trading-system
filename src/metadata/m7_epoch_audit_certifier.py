from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.metadata.m0_canon_helpers import get_repo_root, write_json

EPOCH = "M7_EPOCH_AUDIT_CERTIFICATION"
METADATA_EPOCH_PREFIX = "M"
CORE_EPOCH_PREFIX = "E"
EVIDENCE_DIR_REL = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M7_EPOCH_AUDIT_CERTIFICATION")
STATE_FILE_REL = Path("TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md")

METADATA_EVIDENCE_DIR_MAP = {
    "M0_CANON": "M0_CANON_AND_SOURCES_OF_TRUTH",
    "M1_ARCHITECTURE_MAP": "M1_ARCHITECTURE_MAP",
    "M2_CONTRACT_REGISTRY": "M2_CONTRACT_REGISTRY",
    "M3_MODE_SEMANTICS_CERT": "M3_MODE_SEMANTICS_CERTIFICATION",
    "M4_TRACEABILITY_SEMANTICS": "M4_TRACEABILITY_SEMANTICS",
    "M5_VERIFICATION_AUTHORITY": "M5_VERIFICATION_AUTHORITY",
    "M6_DATA_LIFECYCLE_GOV": "M6_DATA_LIFECYCLE_GOVERNANCE",
    "M7_EPOCH_AUDIT_CERTIFICATION": "M7_EPOCH_AUDIT_CERTIFICATION",
    "M8_CHANGE_CONTROL": "M8_CHANGE_CONTROL",
    "M9_SIGNAL_SEMANTICS_REGISTRY": "M9_SIGNAL_SEMANTICS_REGISTRY",
    "M10_DATA_PROVENANCE_LEDGER": "M10_DATA_PROVENANCE_LEDGER",
}


@dataclass(frozen=True)
class EvidenceCheck:
    check: str
    expected: str
    actual: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_violation(violations: list[dict], check: EvidenceCheck) -> None:
    violations.append({"check": check.check, "expected": check.expected, "actual": check.actual})


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _is_certified_verdict(payload: dict | list | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return (
        payload.get("verdict") == "CERTIFIED"
        or payload.get("status") == "CERTIFIED"
        or payload.get("certified") is True
    )


def _epoch_alias_map() -> dict[str, str]:
    aliases = {k: k for k in METADATA_EVIDENCE_DIR_MAP}
    for epoch, folder in METADATA_EVIDENCE_DIR_MAP.items():
        aliases[folder] = epoch
    return aliases


def _normalize_epoch(epoch_name: str | None, fallback: str | None = None) -> str | None:
    aliases = _epoch_alias_map()
    for candidate in (epoch_name, fallback):
        if not candidate:
            continue
        if candidate in aliases:
            return aliases[candidate]
        if re.match(r"^[ME]\d+_[A-Z0-9_]+$", candidate):
            return candidate
    return None


def _state_certified_epochs(repo_root: Path) -> set[str]:
    path = repo_root / STATE_FILE_REL
    if not path.exists():
        return set()
    certified: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^-\s+([ME]\d+_[A-Z0-9_]+):\s+([A-Z_]+)", line.strip())
        if match and match.group(2) == "CERTIFIED":
            certified.add(match.group(1))
    return certified


def _discover_certified_epochs_from_verdicts(repo_root: Path) -> set[str]:
    evidence_root = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    discovered: set[str] = set()
    if not evidence_root.exists():
        return discovered
    for verdict_path in sorted(evidence_root.glob("*/certification_verdict.json")):
        payload = _read_json(verdict_path)
        if not _is_certified_verdict(payload):
            continue
        epoch = _normalize_epoch(
            payload.get("epoch") if isinstance(payload, dict) else None,
            fallback=verdict_path.parent.name,
        )
        if epoch:
            discovered.add(epoch)
    return discovered


def _evidence_dir_for_epoch(repo_root: Path, epoch_name: str) -> Path:
    evidence_root = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    if epoch_name.startswith(METADATA_EPOCH_PREFIX):
        folder_name = METADATA_EVIDENCE_DIR_MAP.get(epoch_name, epoch_name)
        return evidence_root / folder_name
    core_match = re.match(r"^E(\d+)_", epoch_name)
    if core_match:
        return evidence_root / f"EPOCH_{int(core_match.group(1)):02d}"
    return evidence_root / epoch_name


def _extract_index_entries(payload: dict | list | None) -> list | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        files = payload.get("files")
        if isinstance(files, list):
            return files
        artifacts = payload.get("artifacts")
        if isinstance(artifacts, list):
            return artifacts
    return None


def _validate_evidence_index(
    repo_root: Path,
    evidence_dir: Path,
    epoch_name: str,
    verdict_payload: dict,
    violations: list[dict],
) -> None:
    evidence_files = verdict_payload.get("evidence")
    required_index = None
    if isinstance(evidence_files, list):
        for entry in evidence_files:
            if isinstance(entry, str) and "EVIDENCE_INDEX" in entry.upper():
                required_index = Path(entry).name
                break
    index_candidates = sorted(evidence_dir.glob("*EVIDENCE_INDEX*.json"))
    index_path = index_candidates[0] if index_candidates else None

    if required_index and index_path is None:
        _record_violation(
            violations,
            EvidenceCheck(
                check="CERTIFIED_EPOCH_EVIDENCE_INDEX_EXISTS",
                expected=f"present:{required_index}",
                actual=f"missing:{epoch_name}",
            ),
        )
        return
    if index_path is None:
        return

    payload = _read_json(index_path)
    entries = _extract_index_entries(payload)
    if entries is None:
        _record_violation(
            violations,
            EvidenceCheck(
                check="CERTIFIED_EPOCH_EVIDENCE_INDEX_SHAPE",
                expected="list_or_object_with_files",
                actual=f"invalid:{epoch_name}:{index_path.name}",
            ),
        )
        return

    for entry in entries:
        if not isinstance(entry, str):
            continue
        path = Path(entry)
        candidate = repo_root / path if not path.is_absolute() else path
        if not candidate.exists() and not (evidence_dir / path.name).exists():
            _record_violation(
                violations,
                EvidenceCheck(
                    check="CERTIFIED_EPOCH_EVIDENCE_INDEX_REFERENCES_EXIST",
                    expected="all_present",
                    actual=f"missing:{epoch_name}:{entry}",
                ),
            )


def _audit_epoch(repo_root: Path, epoch_name: str, include_core: bool, violations: list[dict]) -> None:
    is_metadata = epoch_name.startswith(METADATA_EPOCH_PREFIX)
    evidence_dir = _evidence_dir_for_epoch(repo_root, epoch_name)

    if not evidence_dir.exists():
        if is_metadata or include_core:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="CERTIFIED_EPOCH_EVIDENCE_DIR_EXISTS",
                    expected="present",
                    actual=f"missing:{epoch_name}:{evidence_dir.name}",
                ),
            )
        return

    verdict_path = evidence_dir / "certification_verdict.json"
    verdict_payload = _read_json(verdict_path)
    if is_metadata and not isinstance(verdict_payload, dict):
        _record_violation(
            violations,
            EvidenceCheck(
                check="CERTIFIED_EPOCH_CERTIFICATION_VERDICT_EXISTS",
                expected="present_json",
                actual=f"missing_or_invalid:{epoch_name}",
            ),
        )
        return

    if isinstance(verdict_payload, dict):
        _validate_evidence_index(repo_root, evidence_dir, epoch_name, verdict_payload, violations)


def verify_m7_epoch_audit_and_certification(
    repo_root: Path | None = None, include_core: bool = False
) -> dict:
    repo_root = get_repo_root(repo_root)
    violations: list[dict] = []

    state_certified = _state_certified_epochs(repo_root)
    discovered_certified = _discover_certified_epochs_from_verdicts(repo_root)

    metadata_discovered = sorted(
        epoch
        for epoch in discovered_certified
        if epoch.startswith(METADATA_EPOCH_PREFIX)
    )
    core_state_certified = sorted(
        epoch for epoch in state_certified if epoch.startswith(CORE_EPOCH_PREFIX)
    )

    audited_epochs = list(metadata_discovered)
    if include_core:
        audited_epochs.extend(core_state_certified)

    for epoch_name in audited_epochs:
        _audit_epoch(repo_root, epoch_name, include_core=include_core, violations=violations)

    supplemental_state_metadata = sorted(
        epoch
        for epoch in state_certified
        if epoch.startswith(METADATA_EPOCH_PREFIX) and epoch not in set(metadata_discovered)
    )

    evidence_paths = []
    for epoch_name in audited_epochs:
        evidence_dir = _evidence_dir_for_epoch(repo_root, epoch_name)
        if evidence_dir.exists():
            evidence_paths.append(str(evidence_dir.relative_to(repo_root)))

    return {
        "epoch": EPOCH,
        "generated_at_utc": _utc_now_iso(),
        "valid": not violations,
        "violations": violations,
        "include_core": include_core,
        "audited_epochs": audited_epochs,
        "notes": {
            "metadata_certified_discovered_from_verdicts": metadata_discovered,
            "metadata_certified_in_system_state_but_not_evidence_certified": supplemental_state_metadata,
        },
        "evidence_paths": sorted(evidence_paths),
    }


def build_evidence_index(files: list[Path]) -> dict:
    entries = [
        {
            "file": path.name,
            "bytes": path.stat().st_size,
        }
        for path in sorted(files, key=lambda item: item.name)
    ]
    return {"epoch": EPOCH, "files": entries, "generated_at_utc": _utc_now_z()}


def write_summary(result: dict, output_md: Path) -> None:
    lines = [
        "# M7 Epoch Audit & Certification Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Include core: {result.get('include_core')}",
        f"- Audited epochs: {', '.join(result.get('audited_epochs', [])) or 'none'}",
        f"- Violations: {len(result.get('violations', []))}",
    ]
    if result.get("violations"):
        lines.append("")
        lines.append("## Violations")
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
