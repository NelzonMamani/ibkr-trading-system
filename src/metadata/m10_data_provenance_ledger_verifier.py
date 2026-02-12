from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.metadata.m0_canon_helpers import get_repo_root, write_json

EPOCH = "M10_DATA_PROVENANCE_LEDGER"
EVIDENCE_DIR_REL = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M10_DATA_PROVENANCE_LEDGER")
STATE_FILE_REL = Path("TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md")
M10_ROOT_REL = Path("TRADING_OS_MASTER_CATALOGUE/02_METADATA_EPOCHS/10_M10_DATA_PROVENANCE_LEDGER")

REQUIRED_GOVERNANCE_FILES = (
    "00_READ_ORDER.md",
    "01_ARCHITECTURAL_INTENT.md",
    "02_SOURCES_OF_TRUTH_AND_MODE_RELATIVITY.md",
    "03_PROVENANCE_EVENT_MODEL.md",
    "04_FRESHNESS_CONFIDENCE_AND_LIMITATIONS.md",
    "05_PREMARKET_PREPARATION_AND_HYDRATION.md",
    "06_SIGNAL_INTEGRATION_AND_QUALITY_BRIDGE.md",
    "07_LEDGER_ARTIFACTS_AND_RETENTION.md",
    "08_ENFORCED_INVARIANTS.md",
    "09_VERIFICATION_COMMANDS.md",
    "10_AUDIT_REPORT.md",
)

REQUIRED_CODEX_FILES = (
    "00_READ_ORDER.md",
    "01_CONTEXT_AND_OBJECTIVE.md",
    "02_SCOPE_AND_NON_GOALS.md",
    "03_IMPLEMENTATION_TASKS.md",
    "04_MANDATORY_VERIFICATION_COMMANDS.md",
    "05_SUCCESS_CRITERIA.md",
    "99_CODEX_MASTER_INSTRUCTION_BLOCK.md",
)

REQUIRED_CONTENT_CHECKS = (
    (
        Path("governance/03_PROVENANCE_EVENT_MODEL.md"),
        ("event", "provenance", "required", "source", "mode"),
        "PROVENANCE_EVENT_MODEL_CONTENT",
    ),
    (
        Path("governance/05_PREMARKET_PREPARATION_AND_HYDRATION.md"),
        ("premarket", "hydration", "watchlist", "commit"),
        "PREMARKET_HYDRATION_CONTENT",
    ),
    (
        Path("governance/06_SIGNAL_INTEGRATION_AND_QUALITY_BRIDGE.md"),
        ("signal", "quality", "provenance", "decision"),
        "SIGNAL_INTEGRATION_CONTENT",
    ),
    (
        Path("governance/07_LEDGER_ARTIFACTS_AND_RETENTION.md"),
        ("ledger", "retention", "append", "audit"),
        "LEDGER_RETENTION_CONTENT",
    ),
    (
        Path("governance/08_ENFORCED_INVARIANTS.md"),
        ("invariant", "mode", "append", "provenance"),
        "ENFORCED_INVARIANTS_CONTENT",
    ),
    (
        Path("governance/10_AUDIT_REPORT.md"),
        ("certified", "provenance", "query", "execution"),
        "AUDIT_REPORT_CONTENT",
    ),
)


@dataclass(frozen=True)
class ProvenanceViolation:
    check: str
    expected: str
    actual: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(violations: list[dict], violation: ProvenanceViolation) -> None:
    violations.append({"check": violation.check, "expected": violation.expected, "actual": violation.actual})


def _ensure_required_files(base: Path, subdir: str, required_files: tuple[str, ...], violations: list[dict]) -> None:
    folder = base / subdir
    if not folder.exists():
        _record(
            violations,
            ProvenanceViolation(
                check="M10_REQUIRED_FOLDER_EXISTS",
                expected=f"present:{subdir}",
                actual=f"missing:{subdir}",
            ),
        )
        return

    for name in required_files:
        target = folder / name
        if not target.exists():
            _record(
                violations,
                ProvenanceViolation(
                    check="M10_REQUIRED_FILE_EXISTS",
                    expected=f"present:{subdir}/{name}",
                    actual=f"missing:{subdir}/{name}",
                ),
            )


def _contains_required_tokens(path: Path, tokens: tuple[str, ...], violations: list[dict], check_name: str) -> None:
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8").lower()
    missing = [token for token in tokens if token not in content]
    if missing:
        _record(
            violations,
            ProvenanceViolation(
                check=check_name,
                expected=f"contains:{','.join(tokens)}",
                actual=f"missing:{','.join(missing)}",
            ),
        )


def _verify_once(repo_root: Path) -> dict:
    violations: list[dict] = []

    m10_root = repo_root / M10_ROOT_REL
    if not m10_root.exists():
        _record(
            violations,
            ProvenanceViolation(
                check="M10_ROOT_EXISTS",
                expected=str(M10_ROOT_REL),
                actual="missing",
            ),
        )
    else:
        _ensure_required_files(m10_root, "governance", REQUIRED_GOVERNANCE_FILES, violations)
        _ensure_required_files(m10_root, "codex_instructions", REQUIRED_CODEX_FILES, violations)

        for rel_path, tokens, check_name in REQUIRED_CONTENT_CHECKS:
            _contains_required_tokens(m10_root / rel_path, tokens, violations, check_name)

    return {
        "epoch": EPOCH,
        "valid": not violations,
        "violations": sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"])),
        "m10_root": str(M10_ROOT_REL),
    }


def verify_m10_data_provenance_ledger(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    first = _verify_once(repo_root)
    second = _verify_once(repo_root)

    if first != second:
        violations = list(first.get("violations", []))
        violations.append(
            {
                "check": "M10_VERIFIER_DETERMINISTIC_OUTPUT",
                "expected": "stable_result",
                "actual": "non_deterministic_output_detected",
            }
        )
        first = dict(first)
        first["violations"] = sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"]))
        first["valid"] = False

    first["generated_at_utc"] = _utc_now_iso()
    return first


def build_evidence_index(files: list[Path]) -> dict:
    entries = [{"file": path.name, "bytes": path.stat().st_size} for path in sorted(files, key=lambda item: item.name)]
    return {"epoch": EPOCH, "files": entries, "generated_at_utc": _utc_now_z()}


def write_summary(result: dict, output_md: Path) -> None:
    lines = [
        "# M10 Data Provenance Ledger Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- M10 root: {result.get('m10_root')}",
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
    write_json(evidence_index_json, build_evidence_index([output_json, output_md]))
