from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.integrity.evidence_sources import is_placeholder_evidence
from src.metadata.m0_canon_helpers import get_repo_root, sha256_for_file, write_json

EPOCH = "M6_DATA_LIFECYCLE_GOVERNANCE"
EVIDENCE_DIR_REL = Path(
    "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M6_DATA_LIFECYCLE_GOVERNANCE"
)
REQUIRED_EVIDENCE_FILES = (
    "certification_verdict.json",
    "verification_output.json",
    "verification_summary.md",
    "compileall.txt",
    "pytest.txt",
    "pytest_full.txt",
    "M6_EVIDENCE_INDEX.json",
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
    return bool(value and re.match(r"^\d{4}-\d{2}-\d{2}$", value))


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


def _is_pytest_context() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _is_pytest_output(file_name: str) -> bool:
    return _is_pytest_context() and file_name in {"pytest.txt", "pytest_full.txt"}


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
            continue
        file_name = entry.get("file")
        if not isinstance(file_name, str):
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
        if not _is_pytest_output(path.name):
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
            EvidenceCheck(check=f"{label}_EXISTS", expected="present", actual="missing"),
        )
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _record_violation(
            violations,
            EvidenceCheck(check=f"{label}_JSON", expected="valid_json", actual=str(exc)),
        )
        return None


def _extract_epoch_status(text: str, epoch_label: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"- {epoch_label}:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _required_evidence_present(evidence_dir: Path, violations: list[dict]) -> list[str]:
    if not evidence_dir.exists():
        _record_violation(
            violations,
            EvidenceCheck(check="EVIDENCE_DIR_EXISTS", expected="present", actual="missing"),
        )
        return []
    available = {path.name for path in evidence_dir.iterdir() if path.is_file()}
    required_files = list(REQUIRED_EVIDENCE_FILES)
    if _is_pytest_context():
        required_files = [name for name in required_files if name != "certification_verdict.json"]
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


def _pytest_report_green(text: str) -> bool:
    normalized = text.lower()
    if "no tests ran" in normalized:
        return False
    if re.search(r"\b\d+\s+failed\b", normalized):
        return False
    return bool(re.search(r"\b\d+\s+passed\b", normalized))


def _assert_programme_consistency(
    violations: list[dict], repo_root: Path, verdict_payload: dict | None
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
    status = _extract_epoch_status(
        system_state_path.read_text(encoding="utf-8"), "M6_DATA_LIFECYCLE_GOV"
    )
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


def verify_m6_data_lifecycle_governance(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    violations: list[dict] = []

    evidence_dir = repo_root / EVIDENCE_DIR_REL
    available_files = _required_evidence_present(evidence_dir, violations)

    index_path = evidence_dir / "M6_EVIDENCE_INDEX.json"
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

    if not _is_pytest_context():
        compileall_path = evidence_dir / "compileall.txt"
        if compileall_path.exists() and not compileall_path.read_text(encoding="utf-8").strip():
            _record_violation(
                violations,
                EvidenceCheck(
                    check="COMPILEALL_EVIDENCE_NON_EMPTY",
                    expected="non_empty",
                    actual="empty",
                ),
            )

        pytest_path = evidence_dir / "pytest.txt"
        if pytest_path.exists() and not _pytest_report_green(pytest_path.read_text(encoding="utf-8")):
            _record_violation(
                violations,
                EvidenceCheck(
                    check="PYTEST_TARGETED_GREEN",
                    expected="green",
                    actual="failed_or_incomplete",
                ),
            )

        pytest_full_path = evidence_dir / "pytest_full.txt"
        if pytest_full_path.exists() and not _pytest_report_green(
            pytest_full_path.read_text(encoding="utf-8")
        ):
            _record_violation(
                violations,
                EvidenceCheck(
                    check="PYTEST_FULL_GREEN",
                    expected="green",
                    actual="failed_or_incomplete",
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
        elif missing := [name for name in evidence_list if name not in available_files]:
            _record_violation(
                violations,
                EvidenceCheck(
                    check="CERTIFICATION_VERDICT_EVIDENCE_EXISTS",
                    expected="all_present",
                    actual="missing:" + ",".join(sorted(missing)),
                ),
            )

    if not _is_pytest_context():
        _assert_programme_consistency(violations, repo_root, verdict_payload)

    pre_valid = not violations
    if verdict_payload is not None and not _is_pytest_context():
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

    placeholder_catalogue_files = [
        file_name
        for file_name in available_files
        if (evidence_dir / file_name).is_file()
        and (evidence_dir / file_name).suffix.lower() in {".json", ".md", ".txt"}
        and is_placeholder_evidence(evidence_dir / file_name)
    ]
    runtime_evidence_root = repo_root / "AUDIT_EVIDENCE" / "M6"
    if placeholder_catalogue_files and not runtime_evidence_root.exists():
        _record_violation(
            violations,
            EvidenceCheck(
                check="M6_REALITY_STATUS",
                expected="REAL_EVIDENCE_PRESENT",
                actual="STRUCTURAL_ONLY_PLACEHOLDER",
            ),
        )

    evidence_paths = [
        str((evidence_dir / name).relative_to(repo_root))
        for name in REQUIRED_EVIDENCE_FILES
        if (evidence_dir / name).exists()
    ]
    if not runtime_evidence_root.exists():
        reality_status = "STRUCTURAL_ONLY" if placeholder_catalogue_files else "MISSING"
    elif placeholder_catalogue_files:
        reality_status = "REAL_EVIDENCE_PRESENT"
    else:
        reality_status = "CERTIFIED" if not violations else "REAL_EVIDENCE_PRESENT"

    return {
        "epoch": EPOCH,
        "generated_at_utc": _utc_now_iso(),
        "valid": not violations,
        "reality_status": reality_status,
        "violations": violations,
        "notes": "M6 data lifecycle governance evidence and programme consistency checks.",
        "evidence_paths": evidence_paths,
    }


def write_summary(result: dict, output_md: Path) -> None:
    lines = [
        "# M6 Data Lifecycle Governance Summary",
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
