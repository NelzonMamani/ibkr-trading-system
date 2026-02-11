from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.metadata.m0_canon_helpers import get_repo_root, sha256_for_file, write_json

EPOCH = "M7_EPOCH_AUDIT_AND_CERTIFICATION"
EVIDENCE_DIR_REL = Path(
    "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M7_EPOCH_AUDIT_AND_CERTIFICATION"
)
REQUIRED_CERTIFICATION_ARTIFACTS = (
    "certification_verdict.json",
    "verification_output.json",
    "verification_summary.md",
)


@dataclass(frozen=True)
class EvidenceCheck:
    check: str
    expected: str
    actual: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_violation(violations: list[dict], check: str, expected: str, actual: str) -> None:
    violations.append({"check": check, "expected": expected, "actual": actual})


def _normalize(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _load_json(path: Path, violations: list[dict], label: str) -> dict | None:
    if not path.exists():
        _record_violation(violations, f"{label}_EXISTS", "present", f"missing:{path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _record_violation(violations, f"{label}_JSON", "valid_json", f"{path}:{exc}")
        return None
    if not isinstance(payload, dict):
        _record_violation(violations, f"{label}_DICT", "dict", str(type(payload)))
        return None
    return payload


def _parse_epoch_statuses(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, status = line[2:].split(":", 1)
        statuses[key.strip()] = status.strip()
    return statuses


def _extract_verdict_state(verdict: dict) -> str | None:
    verdict_value = verdict.get("verdict")
    if isinstance(verdict_value, str):
        return verdict_value.strip().upper()
    status_value = verdict.get("status")
    if isinstance(status_value, str):
        return "CERTIFIED" if status_value.strip().upper() == "CERTIFIED" else "NOT_CERTIFIED"
    certified_value = verdict.get("certified")
    if isinstance(certified_value, bool):
        return "CERTIFIED" if certified_value else "NOT_CERTIFIED"
    return None


def _extract_output_valid(output: dict) -> bool | None:
    valid = output.get("valid")
    if isinstance(valid, bool):
        return valid
    status = output.get("status")
    if isinstance(status, str):
        normalized = status.strip().upper()
        if normalized in {"PASS", "PASSED", "OK", "SUCCESS"}:
            return True
        if normalized in {"FAIL", "FAILED", "ERROR"}:
            return False
    return None


def _resolve_evidence_path(repo_root: Path, evidence_dir: Path, evidence_entry: str) -> Path:
    candidate = Path(evidence_entry)
    if candidate.is_absolute():
        return candidate
    if "/" in evidence_entry or "\\" in evidence_entry:
        return repo_root / candidate
    return evidence_dir / candidate


def _validate_index_payload(
    repo_root: Path,
    evidence_dir: Path,
    index_payload: dict,
    violations: list[dict],
    epoch_key: str,
) -> None:
    files = index_payload.get("files")
    if not isinstance(files, list):
        _record_violation(violations, "EVIDENCE_INDEX_FILES", "list", f"{epoch_key}:non_list")
        return
    for entry in files:
        if not isinstance(entry, dict):
            _record_violation(violations, "EVIDENCE_INDEX_ENTRY", "dict", f"{epoch_key}:{type(entry)}")
            continue
        file_name = entry.get("file")
        if not isinstance(file_name, str):
            _record_violation(violations, "EVIDENCE_INDEX_ENTRY_FILE", "string", f"{epoch_key}:{file_name}")
            continue
        path = _resolve_evidence_path(repo_root, evidence_dir, file_name)
        if not path.exists():
            _record_violation(
                violations,
                "EVIDENCE_INDEX_LISTED_FILE_EXISTS",
                "present",
                f"{epoch_key}:missing:{file_name}",
            )
            continue
        expected_bytes = entry.get("bytes")
        if isinstance(expected_bytes, int) and path.stat().st_size != expected_bytes:
            _record_violation(
                violations,
                "EVIDENCE_INDEX_BYTES_MATCH",
                str(expected_bytes),
                f"{epoch_key}:{path.stat().st_size}:{file_name}",
            )
        expected_sha = entry.get("sha256")
        if isinstance(expected_sha, str):
            actual_sha = sha256_for_file(path)
            if actual_sha != expected_sha:
                _record_violation(
                    violations,
                    "EVIDENCE_INDEX_SHA256_MATCH",
                    expected_sha,
                    f"{epoch_key}:{actual_sha}:{file_name}",
                )


def _find_epoch_dir(audit_root: Path, epoch_key: str, verdict_paths: list[Path]) -> Path | None:
    norm_key = _normalize(epoch_key)
    for verdict_path in verdict_paths:
        if norm_key in _normalize(verdict_path.parent.name):
            return verdict_path.parent
    for directory in sorted(audit_root.iterdir()):
        if not directory.is_dir():
            continue
        norm_dir = _normalize(directory.name)
        if norm_key in norm_dir or norm_dir in norm_key:
            return directory
    return None


def verify_m7_epoch_audit_and_certification(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    violations: list[dict] = []

    system_state = repo_root / "SYSTEM_STATE.md"
    certified_state = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "SYSTEM_STATE_CERTIFIED.md"
    audit_root = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"

    if not system_state.exists():
        _record_violation(violations, "SYSTEM_STATE_EXISTS", "present", "missing")
    if not certified_state.exists():
        _record_violation(violations, "SYSTEM_STATE_CERTIFIED_EXISTS", "present", "missing")
    if not audit_root.exists():
        _record_violation(violations, "AUDIT_EVIDENCE_ROOT_EXISTS", "present", "missing")

    statuses = _parse_epoch_statuses(certified_state.read_text(encoding="utf-8")) if certified_state.exists() else {}
    certified_epochs = sorted([key for key, status in statuses.items() if status == "CERTIFIED"])
    verdict_paths = sorted(audit_root.glob("*/certification_verdict.json")) if audit_root.exists() else []

    audited_epochs: list[dict] = []
    for epoch_key in certified_epochs:
        epoch_dir = _find_epoch_dir(audit_root, epoch_key, verdict_paths) if audit_root.exists() else None
        epoch_violations_before = len(violations)
        if epoch_dir is None:
            _record_violation(
                violations,
                "CERTIFIED_EPOCH_EVIDENCE_DIR_EXISTS",
                "present",
                f"{epoch_key}:missing",
            )
            audited_epochs.append({"epoch": epoch_key, "evidence_dir": None, "valid": False})
            continue

        for artifact in REQUIRED_CERTIFICATION_ARTIFACTS:
            artifact_path = epoch_dir / artifact
            if not artifact_path.exists():
                _record_violation(
                    violations,
                    "CERTIFIED_EPOCH_REQUIRED_ARTIFACTS",
                    artifact,
                    f"{epoch_key}:missing:{artifact}",
                )

        verdict_path = epoch_dir / "certification_verdict.json"
        output_path = epoch_dir / "verification_output.json"

        verdict_payload = _load_json(verdict_path, violations, "CERTIFICATION_VERDICT") if verdict_path.exists() else None
        output_payload = _load_json(output_path, violations, "VERIFICATION_OUTPUT") if output_path.exists() else None

        verdict_state = _extract_verdict_state(verdict_payload) if verdict_payload else None
        if verdict_state is None:
            _record_violation(
                violations,
                "CERTIFICATION_VERDICT_STRUCTURE",
                "verdict|status|certified",
                f"{epoch_key}:missing_state",
            )
        elif verdict_state != "CERTIFIED":
            _record_violation(
                violations,
                "CERTIFIED_EPOCH_VERDICT_MATCH",
                "CERTIFIED",
                f"{epoch_key}:{verdict_state}",
            )

        if output_payload:
            output_valid = _extract_output_valid(output_payload)
            if output_valid is False:
                _record_violation(
                    violations,
                    "CERTIFIED_EPOCH_VERIFICATION_VALID",
                    "true",
                    f"{epoch_key}:valid=false",
                )

        if verdict_payload:
            evidence = verdict_payload.get("evidence")
            if evidence is not None and not isinstance(evidence, list):
                _record_violation(
                    violations,
                    "CERTIFICATION_VERDICT_EVIDENCE_LIST",
                    "list",
                    f"{epoch_key}:{type(evidence)}",
                )
                evidence = []
            for entry in evidence or []:
                if not isinstance(entry, str):
                    _record_violation(
                        violations,
                        "CERTIFICATION_VERDICT_EVIDENCE_ENTRY",
                        "string",
                        f"{epoch_key}:{entry}",
                    )
                    continue
                evidence_path = _resolve_evidence_path(repo_root, epoch_dir, entry)
                if not evidence_path.exists():
                    _record_violation(
                        violations,
                        "CERTIFICATION_VERDICT_EVIDENCE_EXISTS",
                        "present",
                        f"{epoch_key}:missing:{entry}",
                    )

        index_candidates = sorted(epoch_dir.glob("*EVIDENCE_INDEX*.json"))
        evidence_mentions_index = bool(
            verdict_payload
            and isinstance(verdict_payload.get("evidence"), list)
            and any(isinstance(item, str) and "EVIDENCE_INDEX" in item.upper() for item in verdict_payload["evidence"])
        )
        index_applicable = bool(index_candidates or evidence_mentions_index)
        if index_applicable and not index_candidates:
            _record_violation(
                violations,
                "EVIDENCE_INDEX_REQUIRED",
                "present",
                f"{epoch_key}:missing",
            )
        for index_path in index_candidates:
            index_payload = _load_json(index_path, violations, "EVIDENCE_INDEX")
            if index_payload:
                _validate_index_payload(repo_root, epoch_dir, index_payload, violations, epoch_key)
                indexed_files = {
                    file_entry.get("file")
                    for file_entry in index_payload.get("files", [])
                    if isinstance(file_entry, dict)
                }
                if verdict_payload and isinstance(verdict_payload.get("evidence"), list):
                    for evidence_entry in verdict_payload["evidence"]:
                        if not isinstance(evidence_entry, str):
                            continue
                        if "/" in evidence_entry or "\\" in evidence_entry:
                            continue
                        if "EVIDENCE_INDEX" in evidence_entry.upper():
                            continue
                        if evidence_entry not in indexed_files:
                            _record_violation(
                                violations,
                                "VERDICT_EVIDENCE_INDEX_DRIFT",
                                "listed_in_index",
                                f"{epoch_key}:{evidence_entry}",
                            )

        if statuses.get(epoch_key) == "CERTIFIED" and verdict_state and verdict_state != statuses.get(epoch_key):
            _record_violation(
                violations,
                "SYSTEM_STATE_VERDICT_DRIFT",
                statuses.get(epoch_key, "CERTIFIED"),
                f"{epoch_key}:{verdict_state}",
            )

        audited_epochs.append(
            {
                "epoch": epoch_key,
                "evidence_dir": str(epoch_dir.relative_to(repo_root)),
                "valid": len(violations) == epoch_violations_before,
            }
        )

    evidence_paths = sorted(
        str(path.relative_to(repo_root))
        for path in verdict_paths
        if path.exists()
    )

    return {
        "epoch": EPOCH,
        "generated_at_utc": _utc_now_iso(),
        "valid": not violations,
        "certified_epochs_discovered": certified_epochs,
        "audited_epochs": audited_epochs,
        "violations": violations,
        "notes": "M7 meta-certification authority checks certification integrity and drift.",
        "evidence_paths": evidence_paths,
    }


def write_summary(result: dict, output_md: Path) -> None:
    lines = [
        "# M7 Epoch Audit and Certification Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Certified epochs discovered: {len(result.get('certified_epochs_discovered', []))}",
        f"- Audited epochs: {len(result.get('audited_epochs', []))}",
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


def build_evidence_index(files: list[Path]) -> dict:
    entries = [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_for_file(path)}
        for path in sorted(files, key=lambda item: item.name)
    ]
    return {"epoch": EPOCH, "files": entries, "generated_at_utc": _utc_now_z()}


def write_outputs(result: dict, output_json: Path, output_md: Path, evidence_index_json: Path) -> None:
    write_json(output_json, result)
    write_summary(result, output_md)
    evidence_dir = evidence_index_json.parent
    files = [
        path
        for path in evidence_dir.iterdir()
        if path.is_file() and path.name != evidence_index_json.name
    ]
    write_json(evidence_index_json, build_evidence_index(files))
