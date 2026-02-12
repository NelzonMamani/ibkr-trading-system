from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.metadata.m0_canon_helpers import get_repo_root, write_json

EPOCH = "M10_DATA_PROVENANCE_LEDGER"
EVIDENCE_DIR_REL = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M10_DATA_PROVENANCE_LEDGER")
STATE_FILE_REL = Path("TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md")
GOVERNANCE_DIR_REL = Path("TRADING_OS_MASTER_CATALOGUE/02_METADATA_EPOCHS/10_M10_DATA_PROVENANCE_LEDGER/governance")

DATA_SOURCE_REGISTRY_REL = GOVERNANCE_DIR_REL / "DATA_SOURCE_REGISTRY.json"
MODE_TRUTH_MATRIX_REL = GOVERNANCE_DIR_REL / "MODE_TRUTH_MATRIX.json"
PROVENANCE_EVENT_SCHEMA_REL = GOVERNANCE_DIR_REL / "PROVENANCE_EVENT_SCHEMA.json"
HYDRATION_EVENT_TEMPLATE_REL = GOVERNANCE_DIR_REL / "HYDRATION_EVENT_TEMPLATE.json"

REQUIRED_MODES = ("SIM", "PAPER", "READ_ONLY", "LIVE")
REQUIRED_SOURCE_FIELDS = ("source_id", "source_class", "expected_latency", "availability_constraints")
REQUIRED_EVENT_FIELDS = (
    "event_id",
    "symbol",
    "data_type",
    "timeframe_scope",
    "timeframe_resolution",
    "source_id",
    "mode",
    "session_state",
    "timestamp_observed",
    "timestamp_used",
    "freshness_class",
    "confidence_level",
    "known_limitations",
    "checksum_or_fingerprint",
    "linkage",
)


@dataclass(frozen=True)
class M10Violation:
    check: str
    expected: str
    actual: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(violations: list[dict], violation: M10Violation) -> None:
    violations.append({"check": violation.check, "expected": violation.expected, "actual": violation.actual})


def _load_json(repo_root: Path, rel_path: Path, violations: list[dict], check_prefix: str) -> dict | None:
    path = repo_root / rel_path
    if not path.exists():
        _record(violations, M10Violation(f"{check_prefix}_FILE_EXISTS", str(rel_path), "missing"))
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _record(violations, M10Violation(f"{check_prefix}_JSON_SYNTAX", "valid_json", str(exc)))
        return None
    if not isinstance(payload, dict):
        _record(violations, M10Violation(f"{check_prefix}_ROOT_OBJECT", "object", type(payload).__name__))
        return None
    return payload


def _validate_data_source_registry(payload: dict, violations: list[dict]) -> None:
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        _record(violations, M10Violation("DATA_SOURCE_REGISTRY_SOURCES", "non_empty_list", type(sources).__name__))
        return

    seen_ids: set[str] = set()
    for idx, source in enumerate(sources):
        if not isinstance(source, dict):
            _record(violations, M10Violation("DATA_SOURCE_REGISTRY_SOURCE_OBJECT", "object", f"entry:{idx}:{type(source).__name__}"))
            continue
        for field in REQUIRED_SOURCE_FIELDS:
            if field not in source:
                _record(violations, M10Violation("DATA_SOURCE_REGISTRY_REQUIRED_FIELD", field, f"entry:{idx}:missing"))
        source_id = source.get("source_id")
        if isinstance(source_id, str):
            if source_id in seen_ids:
                _record(violations, M10Violation("DATA_SOURCE_REGISTRY_UNIQUE_SOURCE_ID", "unique", source_id))
            seen_ids.add(source_id)


def _validate_mode_truth_matrix(payload: dict, violations: list[dict]) -> None:
    modes = payload.get("modes")
    if not isinstance(modes, dict):
        _record(violations, M10Violation("MODE_TRUTH_MATRIX_MODES_OBJECT", "object", type(modes).__name__))
        return

    missing_modes = [mode for mode in REQUIRED_MODES if mode not in modes]
    if missing_modes:
        _record(violations, M10Violation("MODE_TRUTH_MATRIX_REQUIRED_MODES", ",".join(REQUIRED_MODES), ",".join(missing_modes)))

    for mode in REQUIRED_MODES:
        definition = modes.get(mode)
        if not isinstance(definition, dict):
            _record(violations, M10Violation("MODE_TRUTH_MATRIX_MODE_OBJECT", "object", f"{mode}:{type(definition).__name__}"))
            continue
        for field in ("expected_sources", "expected_latency", "allowed_fallbacks"):
            value = definition.get(field)
            if field == "expected_latency":
                if not isinstance(value, str) or not value:
                    _record(violations, M10Violation("MODE_TRUTH_MATRIX_EXPECTED_LATENCY", "non_empty_string", f"{mode}:{value}"))
            elif not isinstance(value, list):
                _record(violations, M10Violation(f"MODE_TRUTH_MATRIX_{field.upper()}", "list", f"{mode}:{type(value).__name__}"))


def _validate_event_schema(payload: dict, violations: list[dict]) -> None:
    required_fields = payload.get("required_fields")
    if not isinstance(required_fields, list):
        _record(violations, M10Violation("PROVENANCE_EVENT_SCHEMA_REQUIRED_FIELDS", "list", type(required_fields).__name__))
        return
    missing = [field for field in REQUIRED_EVENT_FIELDS if field not in required_fields]
    if missing:
        _record(violations, M10Violation("PROVENANCE_EVENT_SCHEMA_MINIMUM_REQUIRED_FIELDS", ",".join(REQUIRED_EVENT_FIELDS), ",".join(missing)))


def _validate_hydration_template(payload: dict, violations: list[dict]) -> None:
    events = payload.get("hydration_events")
    required = {
        "SYMBOL_COMMITTED",
        "DATA_HYDRATION_REQUESTED",
        "DATA_HYDRATION_PARTIAL",
        "DATA_HYDRATION_READY",
        "DATA_SOURCE_DEGRADED",
        "DATA_STALE",
    }
    if not isinstance(events, list):
        _record(violations, M10Violation("HYDRATION_TEMPLATE_EVENTS_LIST", "list", type(events).__name__))
        return
    names = {entry.get("event_name") for entry in events if isinstance(entry, dict)}
    missing = sorted(required - names)
    if missing:
        _record(violations, M10Violation("HYDRATION_TEMPLATE_REQUIRED_EVENTS", ",".join(sorted(required)), ",".join(missing)))


def _verify_once(repo_root: Path) -> dict:
    violations: list[dict] = []

    source_registry = _load_json(repo_root, DATA_SOURCE_REGISTRY_REL, violations, "DATA_SOURCE_REGISTRY")
    if source_registry is not None:
        _validate_data_source_registry(source_registry, violations)

    mode_truth = _load_json(repo_root, MODE_TRUTH_MATRIX_REL, violations, "MODE_TRUTH_MATRIX")
    if mode_truth is not None:
        _validate_mode_truth_matrix(mode_truth, violations)

    event_schema = _load_json(repo_root, PROVENANCE_EVENT_SCHEMA_REL, violations, "PROVENANCE_EVENT_SCHEMA")
    if event_schema is not None:
        _validate_event_schema(event_schema, violations)

    hydration_template = _load_json(repo_root, HYDRATION_EVENT_TEMPLATE_REL, violations, "HYDRATION_EVENT_TEMPLATE")
    if hydration_template is not None:
        _validate_hydration_template(hydration_template, violations)

    return {
        "epoch": EPOCH,
        "valid": not violations,
        "violations": sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"])),
        "governance_dir": str(GOVERNANCE_DIR_REL),
    }


def verify_m10_data_provenance_ledger(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    first = _verify_once(repo_root)
    second = _verify_once(repo_root)
    if first != second:
        merged = dict(first)
        violations = list(merged.get("violations", []))
        violations.append(
            {
                "check": "M10_VERIFIER_DETERMINISTIC_OUTPUT",
                "expected": "stable_result",
                "actual": "non_deterministic_output_detected",
            }
        )
        merged["violations"] = sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"]))
        merged["valid"] = False
        first = merged

    first["generated_at_utc"] = _utc_now_iso()
    return first


def build_evidence_index(files: list[Path]) -> dict:
    return {
        "epoch": EPOCH,
        "files": [{"file": path.name, "bytes": path.stat().st_size} for path in sorted(files, key=lambda item: item.name)],
        "generated_at_utc": _utc_now_z(),
    }


def write_summary(result: dict, output_md: Path) -> None:
    lines = [
        "# M10 Data Provenance Ledger Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Governance dir: {result.get('governance_dir')}",
        f"- Violations: {len(result.get('violations', []))}",
    ]
    if result.get("violations"):
        lines.extend(["", "## Violations"])
        lines.extend(
            f"- {v['check']} (expected={v['expected']}, actual={v['actual']})" for v in result["violations"]
        )
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(result: dict, output_json: Path, output_md: Path, evidence_index_json: Path) -> None:
    write_json(output_json, result)
    write_summary(result, output_md)
    write_json(evidence_index_json, build_evidence_index([output_json, output_md]))
