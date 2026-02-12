from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.metadata.m0_canon_helpers import get_repo_root

EPOCH = "M9_SIGNAL_SEMANTICS_REGISTRY"
REGISTRY_REL = Path(
    "TRADING_OS_MASTER_CATALOGUE/02_METADATA_EPOCHS/09_M9_SIGNAL_SEMANTICS_REGISTRY/signal_registry.json"
)
VALID_CLASSES = {
    "SETUP",
    "TRIGGER",
    "CONDITION",
    "ZONE",
    "CONFIRMATION",
    "RISK_CONTROL",
    "EXECUTION_RATIONALE",
    "STATE",
    "DIAGNOSTIC",
}
VALID_TIMEFRAMES = {"TICK", "INTRADAY", "SESSION", "DAILY", "SWING", "LONG_HORIZON"}
REQUIRED_SIGNAL_FIELDS = {
    "name",
    "class",
    "timeframe",
    "description",
    "payload_schema",
    "producer_strategies",
    "lifecycle",
    "compatibility",
}
PRIMITIVE_TYPES = {"string", "int", "float", "bool", "enum"}


def _record(violations: list[dict[str, str]], check: str, expected: str, actual: str) -> None:
    violations.append({"check": check, "expected": expected, "actual": actual})


def _is_payload_schema_lightweight(payload_schema: Any, depth: int = 1) -> bool:
    if not isinstance(payload_schema, dict):
        return False
    for value in payload_schema.values():
        if isinstance(value, str):
            if value not in PRIMITIVE_TYPES:
                return False
            continue
        if isinstance(value, dict):
            if depth >= 2:
                return False
            if not _is_payload_schema_lightweight(value, depth=depth + 1):
                return False
            continue
        return False
    return True


def _count_values(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        if isinstance(value, str):
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _verify_once(repo_root: Path) -> dict:
    registry_path = repo_root / REGISTRY_REL
    violations: list[dict[str, str]] = []

    if not registry_path.exists():
        _record(violations, "REGISTRY_EXISTS", "present", "missing")
        payload: Any = {}
    else:
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            _record(violations, "REGISTRY_JSON_VALID", "valid_json_object", "invalid_json")
            payload = {}

    if registry_path.exists() and not isinstance(payload, dict):
        _record(violations, "REGISTRY_JSON_VALID", "valid_json_object", str(type(payload).__name__))
        payload = {}

    required_top = {"epoch", "version", "signals"}
    if not required_top.issubset(payload.keys()):
        _record(
            violations,
            "REGISTRY_SCHEMA_VALID",
            "top_level_keys:epoch,version,signals",
            f"keys:{','.join(sorted(payload.keys()))}",
        )

    signals = payload.get("signals") if isinstance(payload.get("signals"), list) else []
    if payload.get("signals") is not None and not isinstance(payload.get("signals"), list):
        _record(violations, "REGISTRY_SCHEMA_VALID", "signals:list", f"signals:{type(payload.get('signals')).__name__}")

    seen_names: set[str] = set()
    dup_names: set[str] = set()
    for signal in signals:
        if not isinstance(signal, dict):
            _record(violations, "SIGNAL_FIELDS_PRESENT", "signal_object", f"invalid_type:{type(signal).__name__}")
            continue

        missing = sorted(REQUIRED_SIGNAL_FIELDS - set(signal.keys()))
        if missing:
            _record(violations, "SIGNAL_FIELDS_PRESENT", "all_required_fields", f"missing:{','.join(missing)}")

        name = signal.get("name")
        if isinstance(name, str):
            if name in seen_names:
                dup_names.add(name)
            seen_names.add(name)

        signal_class = signal.get("class")
        signal_timeframe = signal.get("timeframe")
        if isinstance(signal_class, str) and signal_class not in VALID_CLASSES:
            _record(violations, "SIGNAL_ENUM_FIELDS_VALID", f"class in {sorted(VALID_CLASSES)}", f"class:{signal_class}")
        if isinstance(signal_timeframe, str) and signal_timeframe not in VALID_TIMEFRAMES:
            _record(
                violations,
                "SIGNAL_ENUM_FIELDS_VALID",
                f"timeframe in {sorted(VALID_TIMEFRAMES)}",
                f"timeframe:{signal_timeframe}",
            )

        payload_schema = signal.get("payload_schema")
        if payload_schema is not None and not _is_payload_schema_lightweight(payload_schema):
            _record(
                violations,
                "SIGNAL_PAYLOAD_SCHEMA_LIGHTWEIGHT",
                "primitive_types_or_nested_objects_depth_2",
                f"invalid_payload_schema:{name}",
            )

        producer_strategies = signal.get("producer_strategies")
        if producer_strategies is not None:
            valid_format = (
                isinstance(producer_strategies, list)
                and len(producer_strategies) > 0
                and all(isinstance(item, str) and item for item in producer_strategies)
            )
            if not valid_format:
                _record(
                    violations,
                    "PRODUCER_STRATEGIES_VALID_FORMAT",
                    "non_empty_list_of_strings",
                    f"invalid_producer_strategies:{name}",
                )

    if dup_names:
        _record(violations, "SIGNAL_NAMES_UNIQUE", "all_signal_names_unique", f"duplicates:{','.join(sorted(dup_names))}")

    generated_at_utc = "1970-01-01T00:00:00Z"
    if registry_path.exists():
        generated_at_utc = f"mtime_ns:{registry_path.stat().st_mtime_ns}"

    return {
        "epoch": EPOCH,
        "valid": not violations,
        "violations": sorted(violations, key=lambda x: (x["check"], x["actual"], x["expected"])),
        "registry_path": str(REGISTRY_REL),
        "counts": {
            "signals": len(signals),
            "classes": _count_values(signals, "class"),
            "timeframes": _count_values(signals, "timeframe"),
        },
        "generated_at_utc": generated_at_utc,
        "notes": {
            "deterministic": True,
            "validation_scope": "metadata_only",
        },
    }


def verify_m9_signal_semantics_registry(repo_root: Path | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    first = _verify_once(repo_root)
    second = _verify_once(repo_root)
    if first != second:
        result = dict(first)
        violations = list(result.get("violations", []))
        violations.append(
            {
                "check": "DETERMINISTIC_OUTPUT",
                "expected": "stable_across_two_calls",
                "actual": "results_differ_between_calls",
            }
        )
        result["violations"] = sorted(violations, key=lambda x: (x["check"], x["actual"], x["expected"]))
        result["valid"] = False
        return result
    return first
