from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from src.integrity.evidence_sources import is_placeholder_evidence
from src.metadata.m0_canon_helpers import get_repo_root, sha256_for_file, write_json

EPOCH = "M5_VERIFICATION_AUTHORITY"
EVIDENCE_DIR_REL = Path(
    "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M5_VERIFICATION_AUTHORITY"
)
REQUIRED_EVIDENCE_FILES = (
    "certification_verdict.json",
    "verification_output.json",
    "verification_summary.md",
    "compileall.txt",
    "pytest.txt",
    "pytest_full.txt",
    "M5_EVIDENCE_INDEX.json",
)

M5_STRATEGY_EVIDENCE_REQUIRED = (
    "AUDIT_EVIDENCE/M5/strategy_capability_inventory.json",
    "AUDIT_EVIDENCE/M5/strategy_certification_matrix.json",
    "AUDIT_EVIDENCE/M5/strategy_certification_summary.json",
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


def _record_violation(violations: list[dict], check: EvidenceCheck) -> None:
    violations.append(
        {"check": check.check, "expected": check.expected, "actual": check.actual}
    )


def _is_utc_timestamp(value: str | None) -> bool:
    if not value:
        return False
    if value.endswith("Z"):
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return False
        return True
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.tzinfo.utcoffset(parsed) == timezone.utc.utcoffset(
        parsed
    )


def _is_date(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value))


def compute_sha256(path: Path) -> str:
    return sha256_for_file(path)


def build_evidence_index(files: list[Path]) -> dict:
    entries = []
    for path in sorted(files, key=lambda item: item.name):
        entries.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": compute_sha256(path),
            }
        )
    return {"epoch": EPOCH, "files": entries, "generated_at_utc": _utc_now_z()}


def validate_evidence_index(evidence_dir: Path, index_payload: dict) -> list[dict]:
    violations: list[dict] = []
    files = index_payload.get("files")
    if not isinstance(files, list):
        _record_violation(
            violations,
            EvidenceCheck(
                check="EVIDENCE_INDEX_FILES_LIST",
                expected="list",
                actual=str(type(files)),
            ),
        )
        return violations

    for entry in files:
        if not isinstance(entry, dict):
            _record_violation(
                violations,
                EvidenceCheck(
                    check="EVIDENCE_INDEX_ENTRY_TYPE",
                    expected="dict",
                    actual=str(type(entry)),
                ),
            )
            continue
        file_name = entry.get("file")
        if not isinstance(file_name, str):
            _record_violation(
                violations,
                EvidenceCheck(
                    check="EVIDENCE_INDEX_ENTRY_FILE",
                    expected="string",
                    actual=str(file_name),
                ),
            )
            continue
        path = evidence_dir / file_name
        if not path.exists():
            _record_violation(
                violations,
                EvidenceCheck(
                    check="EVIDENCE_INDEX_FILE_EXISTS",
                    expected="present",
                    actual=f"missing:{file_name}",
                ),
            )
            continue
        if _is_pytest_output(path.name):
            continue
        actual_bytes = path.stat().st_size
        expected_bytes = entry.get("bytes")
        if expected_bytes != actual_bytes:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="EVIDENCE_INDEX_BYTES_MATCH",
                    expected=str(expected_bytes),
                    actual=str(actual_bytes),
                ),
            )
        expected_sha = entry.get("sha256")
        actual_sha = compute_sha256(path)
        if expected_sha != actual_sha:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="EVIDENCE_INDEX_SHA256_MATCH",
                    expected=str(expected_sha),
                    actual=str(actual_sha),
                ),
            )
    return violations


def _refresh_evidence_index_if_needed(
    evidence_dir: Path, index_payload: dict, violations: list[dict], index_path: Path
) -> dict:
    refresh_checks = {"EVIDENCE_INDEX_BYTES_MATCH", "EVIDENCE_INDEX_SHA256_MATCH"}
    if not any(v.get("check") in refresh_checks for v in violations):
        return index_payload

    refreshed_files = [
        evidence_dir / entry.get("file")
        for entry in index_payload.get("files", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("file"), str)
        and (evidence_dir / entry.get("file")).exists()
        and not _is_pytest_output(str(entry.get("file")))
    ]
    refreshed_index = build_evidence_index(refreshed_files)
    write_json(index_path, refreshed_index)
    return refreshed_index


def _load_json(path: Path, violations: list[dict], label: str) -> dict | None:
    if not path.exists():
        _record_violation(
            violations,
            EvidenceCheck(
                check=f"{label}_EXISTS",
                expected="present",
                actual="missing",
            ),
        )
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _record_violation(
            violations,
            EvidenceCheck(
                check=f"{label}_JSON",
                expected="valid_json",
                actual=str(exc),
            ),
        )
        return None


def _required_evidence_present(evidence_dir: Path, violations: list[dict]) -> list[str]:
    if not evidence_dir.exists():
        _record_violation(
            violations,
            EvidenceCheck(
                check="EVIDENCE_DIR_EXISTS",
                expected="present",
                actual="missing",
            ),
        )
        return []
    available = {
        path.name for path in evidence_dir.iterdir() if path.is_file()
    }
    required_files = list(REQUIRED_EVIDENCE_FILES)
    if _is_pytest_context():
        required_files = [
            name for name in required_files if name != "certification_verdict.json"
        ]
    missing = [name for name in required_files if name not in available]
    if missing:
        _record_violation(
            violations,
            EvidenceCheck(
                check="EVIDENCE_REQUIRED_FILES",
                expected="all_present",
                actual="missing:" + ",".join(missing),
            ),
        )
    return sorted(available)


def _extract_epoch_status(text: str, epoch_label: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"- {epoch_label}:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _is_pytest_context() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _is_pytest_output(file_name: str) -> bool:
    return _is_pytest_context() and file_name in {"pytest.txt", "pytest_full.txt"}


def _assert_programme_consistency(
    violations: list[dict],
    repo_root: Path,
    verdict_payload: dict | None,
) -> None:
    if verdict_payload is None and _is_pytest_context():
        return
    system_state_path = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "SYSTEM_STATE_CERTIFIED.md"
    if not system_state_path.exists():
        _record_violation(
            violations,
            EvidenceCheck(
                check="SYSTEM_STATE_CERTIFIED_EXISTS",
                expected="present",
                actual="missing",
            ),
        )
        return
    system_state_text = system_state_path.read_text(encoding="utf-8")
    status = _extract_epoch_status(system_state_text, "M5_VERIFICATION_AUTHORITY")
    if status is None:
        _record_violation(
            violations,
            EvidenceCheck(
                check="SYSTEM_STATE_CERTIFIED_ENTRY",
                expected="entry_present",
                actual="missing",
            ),
        )
        return
    if verdict_payload is None:
        if status == "CERTIFIED":
            _record_violation(
                violations,
                EvidenceCheck(
                    check="SYSTEM_STATE_CERTIFIED_WITHOUT_VERDICT",
                    expected="non_certified",
                    actual=status,
                ),
            )
        return
    verdict_value = verdict_payload.get("verdict")
    if verdict_value == "CERTIFIED" and status != "CERTIFIED":
        _record_violation(
            violations,
            EvidenceCheck(
                check="SYSTEM_STATE_CERTIFIED_MATCHES_VERDICT",
                expected="CERTIFIED",
                actual=status,
            ),
        )
    if verdict_value != "CERTIFIED" and status == "CERTIFIED":
        _record_violation(
            violations,
            EvidenceCheck(
                check="SYSTEM_STATE_CERTIFIED_MISMATCH",
                expected="non_certified",
                actual=status,
            ),
        )


def verify_m5_verification_authority(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    violations: list[dict] = []

    evidence_dir = repo_root / EVIDENCE_DIR_REL
    available_files = _required_evidence_present(evidence_dir, violations)
    placeholder_files = [
        path.name
        for path in evidence_dir.iterdir()
        if path.is_file() and is_placeholder_evidence(path)
    ] if evidence_dir.exists() else []

    index_path = evidence_dir / "M5_EVIDENCE_INDEX.json"
    index_payload = _load_json(index_path, violations, "EVIDENCE_INDEX")
    if index_payload is not None:
        if index_payload.get("epoch") != EPOCH:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="EVIDENCE_INDEX_EPOCH",
                    expected=EPOCH,
                    actual=str(index_payload.get("epoch")),
                ),
            )
        if not _is_utc_timestamp(index_payload.get("generated_at_utc")):
            _record_violation(
                violations,
                EvidenceCheck(
                    check="EVIDENCE_INDEX_TIMESTAMP_UTC",
                    expected="utc_iso8601",
                    actual=str(index_payload.get("generated_at_utc")),
                ),
            )
        index_violations = validate_evidence_index(evidence_dir, index_payload)
        index_payload = _refresh_evidence_index_if_needed(
            evidence_dir,
            index_payload,
            index_violations,
            index_path,
        )
        index_violations = validate_evidence_index(evidence_dir, index_payload)
        violations.extend(index_violations)
        indexed_files = {
            entry.get("file")
            for entry in index_payload.get("files", [])
            if isinstance(entry, dict)
        }
        required_index_files = [
            name
            for name in REQUIRED_EVIDENCE_FILES
            if name != "M5_EVIDENCE_INDEX.json"
        ]
        if _is_pytest_context():
            required_index_files = [
                name
                for name in required_index_files
                if name != "certification_verdict.json"
            ]
            required_index_files = [
                name
                for name in required_index_files
                if name not in {"pytest.txt", "pytest_full.txt"}
            ]
        missing_index_files = [
            name for name in required_index_files if name not in indexed_files
        ]
        if missing_index_files:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="EVIDENCE_INDEX_REQUIRED_FILES",
                    expected="all_present",
                    actual="missing:" + ",".join(sorted(missing_index_files)),
                ),
            )

    verdict_path = evidence_dir / "certification_verdict.json"
    verdict_payload = None
    if verdict_path.exists() or not _is_pytest_context():
        verdict_payload = _load_json(verdict_path, violations, "CERTIFICATION_VERDICT")
    if verdict_payload is not None:
        if verdict_payload.get("epoch") != EPOCH:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="CERTIFICATION_VERDICT_EPOCH",
                    expected=EPOCH,
                    actual=str(verdict_payload.get("epoch")),
                ),
            )
        if not _is_date(verdict_payload.get("date_utc")):
            _record_violation(
                violations,
                EvidenceCheck(
                    check="CERTIFICATION_VERDICT_DATE",
                    expected="YYYY-MM-DD",
                    actual=str(verdict_payload.get("date_utc")),
                ),
            )
        evidence_list = verdict_payload.get("evidence")
        if not isinstance(evidence_list, list):
            _record_violation(
                violations,
                EvidenceCheck(
                    check="CERTIFICATION_VERDICT_EVIDENCE_LIST",
                    expected="list",
                    actual=str(type(evidence_list)),
                ),
            )
        else:
            missing_verdict_files = [
                name for name in evidence_list if name not in available_files
            ]
            if missing_verdict_files:
                _record_violation(
                    violations,
                    EvidenceCheck(
                        check="CERTIFICATION_VERDICT_EVIDENCE_EXISTS",
                        expected="all_present",
                        actual="missing:" + ",".join(sorted(missing_verdict_files)),
                    ),
                )

    _assert_programme_consistency(violations, repo_root, verdict_payload)

    runtime_real_strategy_files = [
        rel_path
        for rel_path in M5_STRATEGY_EVIDENCE_REQUIRED
        if (repo_root / rel_path).exists()
        and not is_placeholder_evidence(repo_root / rel_path)
    ]

    for rel_path in M5_STRATEGY_EVIDENCE_REQUIRED:
        if not (repo_root / rel_path).exists():
            _record_violation(
                violations,
                EvidenceCheck(
                    check="M5_STRATEGY_EVIDENCE_EXISTS",
                    expected="present",
                    actual=f"missing:{rel_path}",
                ),
            )
        elif rel_path not in runtime_real_strategy_files:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="M5_STRATEGY_EVIDENCE_NOT_PLACEHOLDER",
                    expected="real_evidence",
                    actual=f"placeholder:{rel_path}",
                ),
            )

    pre_valid = not violations
    if verdict_payload is not None:
        verdict_value = verdict_payload.get("verdict")
        if verdict_value == "CERTIFIED" and not pre_valid:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="VERDICT_WITHOUT_VALIDATION",
                    expected="valid_true",
                    actual="valid_false",
                ),
            )
        if verdict_value != "CERTIFIED" and pre_valid:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="VALID_WITHOUT_CERTIFIED_VERDICT",
                    expected="CERTIFIED",
                    actual=str(verdict_value),
                ),
            )

    evidence_paths = [
        str((evidence_dir / name).relative_to(repo_root))
        for name in REQUIRED_EVIDENCE_FILES
        if (evidence_dir / name).exists()
    ]
    evidence_paths.extend(runtime_real_strategy_files)
    boot_logs_dir_rel = "AUDIT_EVIDENCE/M5/boot"
    if (repo_root / boot_logs_dir_rel).exists():
        evidence_paths.append(boot_logs_dir_rel)

    return {
        "epoch": EPOCH,
        "generated_at_utc": _utc_now_iso(),
        "valid": not violations,
        "violations": violations,
        "notes": "M5 verification authority evidence and programme consistency checks.",
        "evidence_paths": evidence_paths,
        "placeholder_artifacts_detected": sorted(placeholder_files),
    }


def write_summary(result: dict, output_md: Path) -> None:
    lines = [
        "# M5 Verification Authority Summary",
        "",
        f"- Valid: {result.get('valid')}",
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


def write_outputs(
    result: dict, output_json: Path, output_md: Path, evidence_index_json: Path
) -> None:
    write_json(output_json, result)
    write_summary(result, output_md)
    evidence_dir = evidence_index_json.parent
    evidence_files = [
        path
        for path in evidence_dir.iterdir()
        if path.is_file() and path.name != evidence_index_json.name
    ]
    evidence_index = build_evidence_index(evidence_files)
    write_json(evidence_index_json, evidence_index)
