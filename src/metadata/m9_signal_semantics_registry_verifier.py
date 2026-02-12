from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.metadata.m0_canon_helpers import get_repo_root, write_json

EPOCH = "M9_SIGNAL_SEMANTICS_REGISTRY"
EVIDENCE_DIR_REL = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M9_SIGNAL_SEMANTICS_REGISTRY")
STATE_FILE_REL = Path("TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md")
REGISTRY_FILE_REL = Path(
    "TRADING_OS_MASTER_CATALOGUE/02_METADATA_EPOCHS/09_M9_SIGNAL_SEMANTICS_REGISTRY/governance/SIGNAL_SEMANTICS_REGISTRY.json"
)

ALLOWED_SIGNAL_CLASSES = ("S1_SETUP", "S2_TRIGGER", "S3_CONDITION_ZONE", "S4_CONFIRMATION", "S5_RISK_CONTROL", "S6_EXECUTION_RATIONALE")
ALLOWED_TIMEFRAMES = ("TICK", "1M", "5M", "15M", "30M", "SESSION")
ALLOWED_SCHEMA_TYPES = ("string", "number", "integer", "boolean", "object", "array")
REQUIRED_SIGNAL_FIELDS = (
    "name",
    "signal_type",
    "signal_class",
    "timeframe",
    "producer_strategies",
    "payload_schema",
    "description",
)


@dataclass(frozen=True)
class RegistryViolation:
    check: str
    expected: str
    actual: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(violations: list[dict], violation: RegistryViolation) -> None:
    violations.append({"check": violation.check, "expected": violation.expected, "actual": violation.actual})


def _load_registry(path: Path, violations: list[dict]) -> dict | None:
    if not path.exists():
        _record(
            violations,
            RegistryViolation(
                check="REGISTRY_FILE_EXISTS",
                expected=str(REGISTRY_FILE_REL),
                actual="missing",
            ),
        )
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _record(
            violations,
            RegistryViolation(
                check="REGISTRY_JSON_SYNTAX",
                expected="valid_json",
                actual=str(exc),
            ),
        )
        return None
    if not isinstance(payload, dict):
        _record(
            violations,
            RegistryViolation(
                check="REGISTRY_ROOT_OBJECT",
                expected="object",
                actual=type(payload).__name__,
            ),
        )
        return None
    return payload


def _collect_known_strategy_names(repo_root: Path) -> set[str]:
    known: set[str] = set()
    pattern = re.compile(r"(?:strategy_name|name)\s*=\s*\"([^\"]+)\"")
    for py_path in sorted((repo_root / "src").glob("**/*.py")):
        text = py_path.read_text(encoding="utf-8")
        for match in pattern.findall(text):
            if match:
                known.add(match)
    return known


def _validate_payload_schema(schema: object, idx: int, violations: list[dict]) -> None:
    if not isinstance(schema, dict):
        _record(
            violations,
            RegistryViolation(
                check="REGISTRY_PAYLOAD_SCHEMA_OBJECT",
                expected="object",
                actual=f"entry:{idx}:{type(schema).__name__}",
            ),
        )
        return

    if schema.get("type") != "object":
        _record(
            violations,
            RegistryViolation(
                check="REGISTRY_PAYLOAD_SCHEMA_TYPE",
                expected="object",
                actual=f"entry:{idx}:{schema.get('type')}",
            ),
        )

    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        _record(
            violations,
            RegistryViolation(
                check="REGISTRY_PAYLOAD_SCHEMA_PROPERTIES",
                expected="non_empty_object",
                actual=f"entry:{idx}:{type(properties).__name__}",
            ),
        )
        return

    required = schema.get("required")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        _record(
            violations,
            RegistryViolation(
                check="REGISTRY_PAYLOAD_SCHEMA_REQUIRED_LIST",
                expected="list[str]",
                actual=f"entry:{idx}:{type(required).__name__}",
            ),
        )
        required_names: set[str] = set()
    else:
        required_names = set(required)

    property_names = set(properties)
    if not required_names.issubset(property_names):
        _record(
            violations,
            RegistryViolation(
                check="REGISTRY_PAYLOAD_SCHEMA_REQUIRED_IN_PROPERTIES",
                expected="required_subset_properties",
                actual=f"entry:{idx}:{sorted(required_names - property_names)}",
            ),
        )

    for prop_name, prop_schema in sorted(properties.items()):
        if not isinstance(prop_schema, dict):
            _record(
                violations,
                RegistryViolation(
                    check="REGISTRY_PAYLOAD_SCHEMA_PROPERTY_OBJECT",
                    expected="object",
                    actual=f"entry:{idx}:{prop_name}:{type(prop_schema).__name__}",
                ),
            )
            continue
        prop_type = prop_schema.get("type")
        if prop_type not in ALLOWED_SCHEMA_TYPES:
            _record(
                violations,
                RegistryViolation(
                    check="REGISTRY_PAYLOAD_SCHEMA_PROPERTY_TYPE",
                    expected=f"one_of:{','.join(ALLOWED_SCHEMA_TYPES)}",
                    actual=f"entry:{idx}:{prop_name}:{prop_type}",
                ),
            )


def _validate_signals(repo_root: Path, signals: object, violations: list[dict]) -> None:
    if not isinstance(signals, list):
        _record(
            violations,
            RegistryViolation(check="REGISTRY_SIGNALS_LIST", expected="list", actual=type(signals).__name__),
        )
        return

    known_strategy_names = _collect_known_strategy_names(repo_root)
    seen_names: set[str] = set()

    for idx, item in enumerate(signals):
        if not isinstance(item, dict):
            _record(
                violations,
                RegistryViolation(
                    check="REGISTRY_SIGNAL_OBJECT",
                    expected="object",
                    actual=f"entry:{idx}:{type(item).__name__}",
                ),
            )
            continue

        for field in REQUIRED_SIGNAL_FIELDS:
            if field not in item:
                _record(
                    violations,
                    RegistryViolation(
                        check="REGISTRY_SIGNAL_REQUIRED_FIELD",
                        expected=field,
                        actual=f"entry:{idx}:missing",
                    ),
                )

        name = item.get("name")
        if isinstance(name, str) and name in seen_names:
            _record(
                violations,
                RegistryViolation(
                    check="REGISTRY_SIGNAL_DUPLICATE_NAME",
                    expected="unique",
                    actual=name,
                ),
            )
        if isinstance(name, str):
            seen_names.add(name)

        signal_class = item.get("signal_class")
        if signal_class not in ALLOWED_SIGNAL_CLASSES:
            _record(
                violations,
                RegistryViolation(
                    check="REGISTRY_SIGNAL_CLASS_ENUM",
                    expected=f"one_of:{','.join(ALLOWED_SIGNAL_CLASSES)}",
                    actual=f"entry:{idx}:{signal_class}",
                ),
            )

        timeframe = item.get("timeframe")
        if timeframe not in ALLOWED_TIMEFRAMES:
            _record(
                violations,
                RegistryViolation(
                    check="REGISTRY_TIMEFRAME_ENUM",
                    expected=f"one_of:{','.join(ALLOWED_TIMEFRAMES)}",
                    actual=f"entry:{idx}:{timeframe}",
                ),
            )

        producers = item.get("producer_strategies")
        if not isinstance(producers, list) or not producers or not all(isinstance(x, str) for x in producers):
            _record(
                violations,
                RegistryViolation(
                    check="REGISTRY_PRODUCER_STRATEGIES_LIST",
                    expected="non_empty_list[str]",
                    actual=f"entry:{idx}:{type(producers).__name__}",
                ),
            )
        else:
            unknown = sorted(name for name in producers if name not in known_strategy_names)
            if unknown:
                _record(
                    violations,
                    RegistryViolation(
                        check="REGISTRY_PRODUCER_STRATEGY_EXISTS",
                        expected="all_producers_known",
                        actual=f"entry:{idx}:{','.join(unknown)}",
                    ),
                )

        _validate_payload_schema(item.get("payload_schema"), idx, violations)


def _verify_once(repo_root: Path) -> dict:
    violations: list[dict] = []
    payload = _load_registry(repo_root / REGISTRY_FILE_REL, violations)
    if payload is not None:
        signals = payload.get("signals")
        _validate_signals(repo_root, signals, violations)
    return {
        "epoch": EPOCH,
        "valid": not violations,
        "violations": sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"])),
        "registry_file": str(REGISTRY_FILE_REL),
    }


def verify_m9_signal_semantics_registry(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    first = _verify_once(repo_root)
    second = _verify_once(repo_root)
    if first != second:
        merged = dict(first)
        violations = list(merged.get("violations", []))
        violations.append({
            "check": "M9_VERIFIER_DETERMINISTIC_OUTPUT",
            "expected": "stable_result",
            "actual": "non_deterministic_output_detected",
        })
        merged["violations"] = sorted(violations, key=lambda v: (v["check"], v["actual"], v["expected"]))
        merged["valid"] = False
        first = merged

    first["generated_at_utc"] = _utc_now_iso()
    return first


def build_evidence_index(files: list[Path]) -> dict:
    entries = [{"file": path.name, "bytes": path.stat().st_size} for path in sorted(files, key=lambda item: item.name)]
    return {"epoch": EPOCH, "files": entries, "generated_at_utc": _utc_now_z()}


def write_summary(result: dict, output_md: Path) -> None:
    lines = [
        "# M9 Signal Semantics Registry Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Registry file: {result.get('registry_file')}",
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
    evidence_payload = build_evidence_index([output_json, output_md])
    write_json(evidence_index_json, evidence_payload)
