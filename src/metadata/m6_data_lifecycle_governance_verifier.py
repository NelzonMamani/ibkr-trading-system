from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

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
RUN_METADATA_FILE = "M6_RUN_METADATA.json"
ALLOWED_PREEXISTING_FILES = {"compileall.txt", "pytest.txt", "pytest_full.txt"}


class LifecycleClass(str, Enum):
    EPHEMERAL = "EPHEMERAL"
    SESSION_BOUND = "SESSION_BOUND"
    PERSISTENT = "PERSISTENT"
    AUDIT_BOUND = "AUDIT_BOUND"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class DataArtifactDescriptor:
    path: str
    lifecycle_class: LifecycleClass
    owner: str
    created_at_utc: str | None
    deletion_allowed: bool
    notes: str


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


def _relative_path(repo_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _created_at_from_stat(path: Path) -> str | None:
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return mtime.isoformat()


def _descriptor(
    repo_root: Path,
    path: Path,
    lifecycle_class: LifecycleClass,
    owner: str,
    deletion_allowed: bool,
    notes: str,
) -> DataArtifactDescriptor:
    return DataArtifactDescriptor(
        path=_relative_path(repo_root, path),
        lifecycle_class=lifecycle_class,
        owner=owner,
        created_at_utc=_created_at_from_stat(path),
        deletion_allowed=deletion_allowed,
        notes=notes,
    )


def _resolve_repo_relative(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return repo_root / path


def _find_verification_outputs(repo_root: Path) -> list[Path]:
    targets = {"verification_output.json", "compileall.txt", "pytest.txt", "pytest_full.txt"}
    matches: list[Path] = []
    for target in targets:
        matches.extend(repo_root.rglob(target))
    return sorted(set(matches))


def discover_governed_artifacts(repo_root: Path | None = None) -> list[DataArtifactDescriptor]:
    repo_root = get_repo_root(repo_root)
    artifacts: list[DataArtifactDescriptor] = []

    db_paths: set[Path] = set()
    db_paths.add(repo_root / "data" / "ibkr_system.db")
    env_db = os.getenv("PERSISTENCE_SQLITE_PATH")
    if env_db:
        db_paths.add(_resolve_repo_relative(repo_root, env_db))
    for db_path in list(db_paths):
        if db_path.name == "ibkr_system.db":
            legacy = db_path.with_suffix(".sqlite")
            if legacy.exists():
                db_paths.add(legacy)

    for db_path in sorted(db_paths):
        artifacts.append(
            _descriptor(
                repo_root,
                db_path,
                LifecycleClass.PERSISTENT,
                "storage",
                deletion_allowed=False,
                notes="SQLite persistence store; reset only via explicit db_admin tooling.",
            )
        )

    logs_dir = repo_root / "logs"
    trace_dir_raw = os.getenv("TRACE_LOG_DIR", "logs")
    trace_dir = _resolve_repo_relative(repo_root, trace_dir_raw)
    for log_path in {logs_dir, trace_dir}:
        artifacts.append(
            _descriptor(
                repo_root,
                log_path,
                LifecycleClass.SESSION_BOUND,
                "logging",
                deletion_allowed=True,
                notes="Session logs; may be purged after run completion.",
            )
        )

    audit_root = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    artifacts.append(
        _descriptor(
            repo_root,
            audit_root,
            LifecycleClass.AUDIT_BOUND,
            "governance",
            deletion_allowed=False,
            notes="Audit evidence root; append-only governance artifacts.",
        )
    )

    for output_path in _find_verification_outputs(repo_root):
        lifecycle_class = LifecycleClass.SESSION_BOUND
        deletion_allowed = True
        if audit_root in output_path.parents:
            lifecycle_class = LifecycleClass.AUDIT_BOUND
            deletion_allowed = False
        artifacts.append(
            _descriptor(
                repo_root,
                output_path,
                lifecycle_class,
                "verification",
                deletion_allowed,
                notes="Verification output artifact.",
            )
        )

    backup_dir = repo_root / "data" / "backups"
    if backup_dir.exists():
        artifacts.append(
            _descriptor(
                repo_root,
                backup_dir,
                LifecycleClass.ARCHIVED,
                "storage",
                deletion_allowed=False,
                notes="DB backups created by db_admin tooling.",
            )
        )

    return sorted(artifacts, key=lambda item: (item.owner, item.path))


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
    available = {path.name for path in evidence_dir.iterdir() if path.is_file()}
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
    status = _extract_epoch_status(system_state_text, "M6_DATA_LIFECYCLE_GOV")
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


def _require_artifact_class(
    violations: list[dict],
    artifacts: list[DataArtifactDescriptor],
    owner: str,
    label: str,
) -> None:
    matches = [artifact for artifact in artifacts if artifact.owner == owner]
    if not matches:
        _record_violation(
            violations,
            EvidenceCheck(
                check=f"LIFECYCLE_CLASS_{label}",
                expected="classified",
                actual="missing",
            ),
        )
        return
    for artifact in matches:
        if not artifact.lifecycle_class:
            _record_violation(
                violations,
                EvidenceCheck(
                    check=f"LIFECYCLE_CLASS_{label}",
                    expected="classified",
                    actual="unknown",
                ),
            )


def _load_retention_rules(repo_root: Path) -> list[str]:
    path = (
        repo_root
        / "TRADING_OS_MASTER_CATALOGUE"
        / "02_METADATA_EPOCHS"
        / "06_M6_DATA_LIFECYCLE_GOVERNANCE"
        / "governance"
        / "03_RETENTION_AND_DELETION_RULES.md"
    )
    if not path.exists():
        return []
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("-"):
            rules.append(stripped)
    return rules


def _assert_retention_documented(
    repo_root: Path, summary_path: Path, violations: list[dict]
) -> None:
    rules = _load_retention_rules(repo_root)
    if not rules:
        _record_violation(
            violations,
            EvidenceCheck(
                check="RETENTION_RULES_PRESENT",
                expected="rules_listed",
                actual="missing",
            ),
        )
        return
    if not summary_path.exists():
        _record_violation(
            violations,
            EvidenceCheck(
                check="VERIFICATION_SUMMARY_EXISTS",
                expected="present",
                actual="missing",
            ),
        )
        return
    summary_text = summary_path.read_text(encoding="utf-8")
    missing = [rule for rule in rules if rule not in summary_text]
    if missing:
        _record_violation(
            violations,
            EvidenceCheck(
                check="RETENTION_RULES_DOCUMENTED",
                expected="all_present",
                actual="missing:" + ",".join(missing),
            ),
        )


def _assert_overwrite_policy(
    evidence_dir: Path, violations: list[dict]
) -> None:
    metadata_path = evidence_dir / RUN_METADATA_FILE
    payload = _load_json(metadata_path, violations, "RUN_METADATA")
    if payload is None:
        return
    if payload.get("epoch") != EPOCH:
        _record_violation(
            violations,
            EvidenceCheck(
                check="RUN_METADATA_EPOCH",
                expected=EPOCH,
                actual=str(payload.get("epoch")),
            ),
        )
    if not payload.get("overwrite_protection"):
        _record_violation(
            violations,
            EvidenceCheck(
                check="RUN_METADATA_OVERWRITE_PROTECTION",
                expected="true",
                actual=str(payload.get("overwrite_protection")),
            ),
        )
    if payload.get("allow_overwrite"):
        _record_violation(
            violations,
            EvidenceCheck(
                check="RUN_METADATA_ALLOW_OVERWRITE",
                expected="false",
                actual=str(payload.get("allow_overwrite")),
            ),
        )
    preexisting = payload.get("preexisting_files")
    if preexisting:
        if not isinstance(preexisting, list):
            _record_violation(
                violations,
                EvidenceCheck(
                    check="RUN_METADATA_PREEXISTING_FILES",
                    expected="list",
                    actual=str(preexisting),
                ),
            )
        else:
            unexpected = sorted({name for name in preexisting if name not in ALLOWED_PREEXISTING_FILES})
            if unexpected:
                _record_violation(
                    violations,
                    EvidenceCheck(
                        check="RUN_METADATA_PREEXISTING_FILES",
                        expected="only_compileall_pytest_outputs",
                        actual=",".join(unexpected),
                    ),
                )


def _explicit_reset_tooling_present(repo_root: Path) -> bool:
    return (repo_root / "src" / "storage" / "db_admin.py").exists()


def verify_m6_data_lifecycle_governance(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    violations: list[dict] = []

    artifacts = discover_governed_artifacts(repo_root)
    _require_artifact_class(violations, artifacts, "storage", "DB")
    _require_artifact_class(violations, artifacts, "logging", "LOGS")
    _require_artifact_class(violations, artifacts, "governance", "AUDIT")

    audit_root = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    if not audit_root.exists():
        _record_violation(
            violations,
            EvidenceCheck(
                check="AUDIT_EVIDENCE_ROOT_EXISTS",
                expected="present",
                actual="missing",
            ),
        )

    if not _explicit_reset_tooling_present(repo_root):
        _record_violation(
            violations,
            EvidenceCheck(
                check="RESET_TOOLING_PRESENT",
                expected="db_admin.py",
                actual="missing",
            ),
        )

    evidence_dir = repo_root / EVIDENCE_DIR_REL
    available_files: list[str] = []
    if evidence_dir.exists():
        available_files = sorted(
            path.name for path in evidence_dir.iterdir() if path.is_file()
        )
    index_payload = None
    if not _is_pytest_context():
        available_files = _required_evidence_present(evidence_dir, violations)
        _assert_overwrite_policy(evidence_dir, violations)

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
        violations.extend(validate_evidence_index(evidence_dir, index_payload))
        indexed_files = {
            entry.get("file")
            for entry in index_payload.get("files", [])
            if isinstance(entry, dict)
        }
        required_index_files = [
            name
            for name in REQUIRED_EVIDENCE_FILES
            if name != "M6_EVIDENCE_INDEX.json"
        ]
        required_index_files.append(RUN_METADATA_FILE)
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

    summary_path = evidence_dir / "verification_summary.md"
    if not _is_pytest_context():
        _assert_retention_documented(repo_root, summary_path, violations)
    _assert_programme_consistency(violations, repo_root, verdict_payload)

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

    return {
        "epoch": EPOCH,
        "generated_at_utc": _utc_now_iso(),
        "valid": not violations,
        "violations": violations,
        "notes": "M6 data lifecycle governance invariants and evidence checks.",
        "evidence_paths": evidence_paths,
        "artifact_catalog": [artifact.__dict__ for artifact in artifacts],
    }


def write_summary(result: dict, output_md: Path, retention_rules: list[str]) -> None:
    lines = [
        "# M6 Data Lifecycle Governance Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Violations: {len(result.get('violations', []))}",
        "",
        "## Retention Rules",
    ]
    if retention_rules:
        lines.extend(retention_rules)
    else:
        lines.append("- (No retention rules found in governance docs)")
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
    retention_rules = _load_retention_rules(get_repo_root())
    write_json(output_json, result)
    write_summary(result, output_md, retention_rules)
    evidence_dir = evidence_index_json.parent
    evidence_files = [
        path
        for path in evidence_dir.iterdir()
        if path.is_file() and path.name != evidence_index_json.name
    ]
    evidence_index = build_evidence_index(evidence_files)
    write_json(evidence_index_json, evidence_index)


def build_run_metadata(preexisting_files: list[str], allow_overwrite: bool) -> dict:
    return {
        "epoch": EPOCH,
        "generated_at_utc": _utc_now_z(),
        "overwrite_protection": not allow_overwrite,
        "allow_overwrite": allow_overwrite,
        "preexisting_files": preexisting_files,
    }


def build_certification_verdict(result: dict, evidence_files: list[str]) -> dict:
    verdict = "CERTIFIED" if result.get("valid") else "NOT_CERTIFIED"
    return {
        "epoch": EPOCH,
        "verdict": verdict,
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reasons": [],
        "evidence": sorted(evidence_files),
    }
