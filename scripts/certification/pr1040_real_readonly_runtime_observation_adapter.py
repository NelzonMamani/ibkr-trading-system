#!/usr/bin/env python
"""PR1040 real READ_ONLY Ross runtime observation adapter.

Certification-only adapter that runs the real READ_ONLY Ross observation path
far enough to produce a PR1039-compatible observation-input JSON. It does not
submit, cancel, modify, preview-submit, or stage broker orders. It fails closed
when the observed evidence is incomplete or unsafe.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.certification.pr1046_ibkr_market_data_diagnostics import (  # noqa: E402
    build_ibkr_market_data_diagnostic,
)

SCHEMA_VERSION = "PR1040.real_readonly_runtime_observation_adapter.v1"
PR1039_INPUT_SCHEMA_VERSION = "PR1039.controlled_readonly_observation_input.v1"
CANONICAL_DECISION_AUTHORITY = "RossMomentumStrategy.evaluate"
REAL_STORAGE_EVIDENCE_SOURCE = "REAL_ANALYTICS_STORAGE_WRITE_READBACK"
STORAGE_EVIDENCE_UNAVAILABLE_BLOCKER = "Real analytics/storage write-readback evidence is unavailable."
PRICED_INTENT_BLOCKER = "Accepted setup risk evidence missing numeric entry price."
BROKER_AUDIT_INCOMPLETE_BLOCKER = "Broker before/after audit evidence is incomplete."
MARKET_DATA_UNUSABLE_BLOCKER = "Real market data unusable before Focus M pattern evaluation."
NO_PATTERN_INPUT_EVIDENCE_BLOCKER = "No real pattern input evidence was captured for Focus M candidates."

DEFAULT_OBSERVATION_OUTPUT = Path(
    "artifacts/certification/pr1040/real_runtime_observation/real_runtime_observation.json"
)
DEFAULT_RAW_OUTPUT_DIR = Path(
    "artifacts/certification/pr1040/raw_real_runtime_observation"
)
DEFAULT_VALIDATED_OUTPUT_DIR = Path(
    "artifacts/certification/pr1040/validated_real_runtime_observation"
)
DEFAULT_MAX_OBSERVATION_SYMBOLS = 50
DEFAULT_MAX_OBSERVATION_SECONDS = 30.0
DEFAULT_MAX_SNAPSHOT_FAILURES = 10

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}
ENTRY_PRICE_METADATA_KEYS = (
    "entry_price",
    "priced_entry",
    "priced_sizing_input",
    "sizing_entry_price",
    "canonical_entry_price",
    "entry_level",
    "trigger_price",
    "trigger_level",
    "limit_price",
)
NUMERIC_PRICE_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")
MARKET_DATA_UNUSABLE_DROP_REASONS = {"DROP_MISSING_PRICE", "DATA_QUALITY_FAIL_SNAPSHOT"}

PR1050_FLOAT_DISCOVERY_COUNT_FIELDS = (
    "float_discovery_requested_count",
    "float_discovery_success_count",
    "float_discovery_failed_count",
    "float_discovery_cache_hit_count",
    "float_discovery_same_cycle_rehydrated_count",
    "float_discovery_pending_count",
    "float_unknown_after_bounded_discovery_count",
)
PR1050_FLOAT_DISCOVERY_SYMBOL_FIELDS = (
    "symbols_rehydrated_from_same_cycle_float_discovery",
    "symbols_still_dropped_float_unknown",
    "symbols_pending_same_cycle_float_discovery",
    "symbols_failed_same_cycle_float_discovery",
)
PR1050_FLOAT_FOCUS_DIAGNOSTIC_SYMBOL_FIELDS = (
    "symbols_with_usable_market_data",
    "missing_market_data_symbols",
    "usable_market_data_but_unknown_float_symbols",
    "usable_market_data_but_over_float_symbols",
    "usable_market_data_but_rvol_failure_symbols",
    "usable_market_data_but_catalyst_news_failure_symbols",
)

READ_ONLY_ENV_DEFAULTS: dict[str, str] = {
    "RUN_MODE": "READ_ONLY",
    "RUN_MODE_EFFECTIVE": "READ_ONLY",
    "EXECUTION_ENABLED": "false",
    "EXECUTION_ENABLED_EFFECTIVE": "false",
    "EVENT_REPLAY_MODE": "OFF",
    "EVENT_REPLAY_MODE_EFFECTIVE": "OFF",
    "IBKR_READONLY_ENABLED": "true",
    "IBKR_API_WRITE_ALLOWED": "false",
    "IBKR_ORDER_SUBMISSION_ENABLED": "false",
    "FORCE_CLEAN_START": "false",
    "FORCE_EXECUTION_ON_TRADE_READY": "false",
    "FORCE_RISK_APPROVAL_FOR_TRADE_READY": "false",
    "VALIDATION_SESSION_OVERRIDE": "false",
    "ROSS_VALIDATION_OVERRIDE": "false",
    "ROSS_VALIDATION_OVERRIDE_ENABLED": "false",
    "ROSS_THRESHOLD_OVERRIDE": "false",
    "ROSS_CATALYST_BYPASS": "false",
    "ROSS_FLOAT_RELAXATION": "false",
    "ROSS_RVOL_RELAXATION": "false",
    "MANUAL_FOCUS_ENABLED": "false",
    "SYNTHETIC_TRADE_INTENT_ENABLED": "false",
    "MANUAL_FOCUS_SYMBOLS": "",
    "ROSS_MANUAL_FOCUS_SYMBOLS": "",
    "SYNTHETIC_TRADE_INTENTS": "",
    "ROSS_SYNTHETIC_TRADE_INTENTS": "",
    "SCANNER_DATA_SOURCE": "IBKR",
    "SCANNER_MODE": "LIVE_READONLY",
}

FALSE_REQUIRED_ENV_KEYS = (
    "EXECUTION_ENABLED",
    "EXECUTION_ENABLED_EFFECTIVE",
    "IBKR_API_WRITE_ALLOWED",
    "IBKR_ORDER_SUBMISSION_ENABLED",
    "FORCE_CLEAN_START",
)

FALSE_OR_ABSENT_ENV_KEYS = (
    "FORCE_EXECUTION_ON_TRADE_READY",
    "FORCE_RISK_APPROVAL_FOR_TRADE_READY",
    "VALIDATION_SESSION_OVERRIDE",
    "ROSS_VALIDATION_OVERRIDE",
    "ROSS_VALIDATION_OVERRIDE_ENABLED",
    "ROSS_THRESHOLD_OVERRIDE",
    "ROSS_CATALYST_BYPASS",
    "ROSS_FLOAT_RELAXATION",
    "ROSS_RVOL_RELAXATION",
    "MANUAL_FOCUS_ENABLED",
    "SYNTHETIC_TRADE_INTENT_ENABLED",
)

EMPTY_OR_ABSENT_ENV_KEYS = (
    "MANUAL_FOCUS_SYMBOLS",
    "ROSS_MANUAL_FOCUS_SYMBOLS",
    "SYNTHETIC_TRADE_INTENTS",
    "ROSS_SYNTHETIC_TRADE_INTENTS",
)

CATALYST_ACCEPT_VALUES = {
    "CONFIRMED",
    "FRESH_CONFIRMED",
    "CATALYST_CONFIRMED",
    "VALID_CATALYST",
}
NEWS_DIAGNOSTIC_DATA_UNAVAILABLE_STATUSES = {
    "data_unavailable",
    "not_requested",
    "provider_disabled",
    "provider_request_failure",
    "provider_unavailable",
    "budget_exhausted",
}
NEWS_DIAGNOSTIC_ABSENT_STATUSES = {
    "no_recent_news",
    "news_present_non_qualifying",
}
NEWS_DIAGNOSTIC_CONFIRMED_STATUSES = {
    "catalyst_confirmed",
}
NEWS_DIAGNOSTIC_ARTIFACT_KEYS = (
    "provider_status",
    "result_status_counts",
    "symbols_by_status",
    "rss_sources",
    "rss_failures",
    "rss_failure_summary",
    "rss_failure_reason",
    "no_recent_news_count",
    "news_present_non_qualifying_count",
    "confirmed_catalyst_count",
    "queried_source_count",
    "queried_sources_count",
    "total_source_count",
    "total_sources",
    "queried_source_tiers",
    "fast_tier_source_count",
    "extended_tier_source_count",
    "fast_tier_match_count",
    "extended_tier_match_count",
    "extended_fallback_requested",
    "extended_fallback_symbol_count",
    "ticker_token_match_count",
    "company_name_match_count",
    "description_summary_match_count",
    "qualifying_headline_count",
    "non_qualifying_headline_count",
    "max_entries_per_symbol",
    "total_news_budget_seconds",
    "news_elapsed_seconds",
    "news_budget_exhausted",
    "fast_budget_seconds",
    "extended_budget_seconds",
    "extended_budget_reserved_seconds",
    "fast_budget_exhausted",
    "extended_budget_exhausted",
    "fast_sources_attempted_count",
    "extended_sources_attempted_count",
    "sources_skipped_due_to_budget_count",
    "symbols_unresolved_at_budget_exhaustion",
    "news_source_mode",
    "cache_state",
    "cache_hits_by_symbol",
    "cache_hit_symbols",
    "stale_cache_miss_symbols",
    "cache_miss_symbols",
    "prep_reuse_symbols",
    "prep_stale_symbols",
    "refresh_requested_count",
    "refresh_symbols",
    "source_provenance_by_symbol",
    "match_types_by_symbol",
    "reliability_by_symbol",
    "heat_by_symbol",
    "velocity_by_symbol",
    "evidence_count_by_symbol",
    "freshest_evidence_age_seconds_by_symbol",
    "cache_read_failed",
    "cache_write_failed",
    "news_intelligence_diagnostics",
)

UNSAFE_FOCUS_FLAGS = (
    "manual_focus",
    "manual_focus_injected",
    "manual_focus_injection",
    "synthetic_focus",
    "prep_seeded",
)

UNSAFE_INTENT_MARKERS = (
    "FORCE",
    "FORCED",
    "DEBUG_FORCE",
    "SYNTHETIC",
    "VALIDATION_OVERRIDE",
    "OVERRIDE",
)


class PR1040AdapterError(RuntimeError):
    """Raised when real READ_ONLY observation evidence is unsafe."""


@dataclass
class RuntimeObservationEvidence:
    operator: str
    scenario_id: str
    env: Mapping[str, str]
    captured_at_utc: str
    scanner_payload: Mapping[str, Any]
    focus_rows: list[Any]
    watchlist_rows: list[Any]
    pattern_input_evidence: list[dict[str, Any]]
    pattern_summaries: list[Any]
    intent_records: list[Any]
    risk_decisions: list[Any]
    execution_events: list[Any]
    broker_before: Mapping[str, Any]
    broker_after: Mapping[str, Any]
    session_label: str
    storage_write_verified: bool = False
    storage_readback_verified: bool = False
    storage_evidence_source: str = "UNAVAILABLE"
    storage_evidence_detail: Mapping[str, Any] | None = None
    operator_observation_scope: Mapping[str, Any] | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return None


def _normalize_upper(value: Any) -> str:
    if hasattr(value, "value"):
        value = getattr(value, "value")
    return str(value or "").strip().upper()


def _text_value(value: Any) -> str:
    if hasattr(value, "value"):
        value = getattr(value, "value")
    return str(value or "")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return _json_safe(getattr(value, "value"))
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(_json_safe(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise PR1040AdapterError(f"{path} must contain a JSON object")
    return payload


def parse_observation_symbols(value: Any) -> list[str]:
    if value is None:
        return []
    values: list[str] = []
    if isinstance(value, (list, tuple, set)):
        for item in value:
            values.extend(parse_observation_symbols(item))
    else:
        values.extend(str(value or "").split(","))
    symbols: list[str] = []
    seen: set[str] = set()
    for item in values:
        symbol = str(item or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def _nonnegative_int(value: Any, *, default: int) -> int:
    parsed = _safe_int(value, default)
    return parsed if parsed >= 0 else default


def _nonnegative_float(value: Any, *, default: float) -> float:
    parsed = _safe_float(value, default)
    return parsed if parsed >= 0.0 else default


def build_operator_observation_scope(
    *,
    max_observation_symbols: int = DEFAULT_MAX_OBSERVATION_SYMBOLS,
    max_observation_seconds: float = DEFAULT_MAX_OBSERVATION_SECONDS,
    max_snapshot_failures: int = DEFAULT_MAX_SNAPSHOT_FAILURES,
    observation_symbols: Sequence[str] | str | None = None,
) -> dict[str, Any]:
    return {
        "scope_type": "OPERATOR_OBSERVATION_SCOPE_ONLY",
        "max_observation_symbols": _nonnegative_int(max_observation_symbols, default=DEFAULT_MAX_OBSERVATION_SYMBOLS),
        "max_observation_seconds": _nonnegative_float(max_observation_seconds, default=DEFAULT_MAX_OBSERVATION_SECONDS),
        "max_snapshot_failures": _nonnegative_int(max_snapshot_failures, default=DEFAULT_MAX_SNAPSHOT_FAILURES),
        "observation_symbols": parse_observation_symbols(observation_symbols),
        "manual_focus_symbols_set": False,
        "synthetic_trade_intents_set": False,
    }


def _operator_observation_scope(evidence: RuntimeObservationEvidence) -> dict[str, Any]:
    scope = evidence.operator_observation_scope if isinstance(evidence.operator_observation_scope, Mapping) else {}
    return build_operator_observation_scope(
        max_observation_symbols=scope.get("max_observation_symbols", DEFAULT_MAX_OBSERVATION_SYMBOLS),
        max_observation_seconds=scope.get("max_observation_seconds", DEFAULT_MAX_OBSERVATION_SECONDS),
        max_snapshot_failures=scope.get("max_snapshot_failures", DEFAULT_MAX_SNAPSHOT_FAILURES),
        observation_symbols=scope.get("observation_symbols", []),
    ) | {
        "observed_focus_symbols": parse_observation_symbols(scope.get("observed_focus_symbols", [])),
        "evaluated_pattern_symbols": parse_observation_symbols(scope.get("evaluated_pattern_symbols", [])),
        "snapshot_failure_count": _nonnegative_int(scope.get("snapshot_failure_count", 0), default=0),
        "stopped_by_max_observation_symbols": bool(scope.get("stopped_by_max_observation_symbols", False)),
        "stopped_by_max_observation_seconds": bool(scope.get("stopped_by_max_observation_seconds", False)),
        "stopped_by_max_snapshot_failures": bool(scope.get("stopped_by_max_snapshot_failures", False)),
    }


def build_safe_readonly_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)
    env.update(READ_ONLY_ENV_DEFAULTS)
    return {key: str(value) for key, value in env.items()}


def assert_safe_runtime_env(env: Mapping[str, str]) -> None:
    if _normalize_upper(env.get("RUN_MODE")) != "READ_ONLY":
        raise PR1040AdapterError("RUN_MODE must be READ_ONLY")
    if _normalize_upper(env.get("RUN_MODE_EFFECTIVE")) != "READ_ONLY":
        raise PR1040AdapterError("RUN_MODE_EFFECTIVE must be READ_ONLY")
    for key in FALSE_REQUIRED_ENV_KEYS:
        if _normalize_bool(env.get(key)) is not False:
            raise PR1040AdapterError(f"{key} must be false")
    for key in FALSE_OR_ABSENT_ENV_KEYS:
        if _normalize_bool(env.get(key)) is True:
            raise PR1040AdapterError(f"{key} must be false or absent")
    for key in EMPTY_OR_ABSENT_ENV_KEYS:
        if str(env.get(key, "") or "").strip():
            raise PR1040AdapterError(f"{key} must be empty or absent")


def _config_registry() -> Mapping[str, Mapping[str, Any]]:
    try:
        from src.config.config_registry import CONFIG_REGISTRY
    except Exception:
        return {}
    return CONFIG_REGISTRY if isinstance(CONFIG_REGISTRY, Mapping) else {}


def _sequence_override(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _coerce_config_override_value(key: str, value: Any, type_hint: Any) -> object:
    if type_hint is bool:
        parsed = _normalize_bool(value)
        if parsed is None:
            raise PR1040AdapterError(f"{key} must be boolean-compatible for config override")
        return parsed
    if type_hint is int:
        return int(str(value).strip())
    if type_hint is float:
        return float(str(value).strip())
    if type_hint is list:
        return _sequence_override(value)
    if type_hint is set:
        return set(_sequence_override(value))
    if type_hint is dict:
        if isinstance(value, Mapping):
            return dict(value)
        text = str(value or "").strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise PR1040AdapterError(f"{key} must decode to a JSON object for config override")
        return parsed
    return str(value)


def build_readonly_config_overrides(env: Mapping[str, str]) -> dict[str, object]:
    registry = _config_registry()
    overrides: dict[str, object] = {}
    for key in READ_ONLY_ENV_DEFAULTS:
        if key not in env:
            continue
        entry = registry.get(key, {})
        type_hint = entry.get("type") if isinstance(entry, Mapping) else None
        overrides[key] = _coerce_config_override_value(key, env.get(key), type_hint)
    return overrides


def apply_readonly_runtime_overrides(env: Mapping[str, str]) -> None:
    assert_safe_runtime_env(env)
    os.environ.update({key: str(value) for key, value in env.items()})
    try:
        from src.config.config_resolver import set_config_overrides
    except Exception:
        return

    # Keep inherited environment at ENV precedence; only PR1040 launch guards get override precedence.
    set_config_overrides(build_readonly_config_overrides(env))


def _stable_json(value: Any) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))


def _symbol(value: Any) -> str:
    return str(_get_value(value, "symbol", "") or "").strip().upper()


def _scanner_rows(payload: Mapping[str, Any], keys: Sequence[str]) -> list[Any]:
    rows: list[Any] = []
    seen: set[str] = set()
    for key in keys:
        for row in payload.get(key, []) or []:
            symbol = _symbol(row)
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            rows.append(row)
    return rows


def _scanner_symbols(payload: Mapping[str, Any], key: str) -> list[str]:
    symbols: list[str] = []
    for value in payload.get(key, []) or []:
        symbol = _symbol(value) if not isinstance(value, str) else value.strip().upper()
        if symbol:
            symbols.append(symbol)
    return symbols


def _session_label_from_payload(payload: Mapping[str, Any], rows: Sequence[Any]) -> str:
    for row in rows:
        for key in ("session_label", "session_phase", "session"):
            value = _get_value(row, key)
            if str(value or "").strip():
                return _normalize_upper(value)
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload.get("diagnostics"), Mapping) else {}
    for key in ("session_label", "session_phase", "market_session"):
        value = diagnostics.get(key)
        if str(value or "").strip():
            return _normalize_upper(value)
    return "UNKNOWN"


def _worst_status(values: Sequence[str], *, default: str = "MISSING") -> str:
    order = {
        "BLOCK": 5,
        "DROP": 5,
        "NO_TRADE": 5,
        "STALE": 4,
        "MISSING": 3,
        "UNAVAILABLE": 3,
        "DEGRADE": 2,
        "WARN": 1,
        "PRESENT": 0,
        "COMPUTED": 0,
        "FRESH": 0,
        "NONE": 0,
    }
    normalized = [_normalize_upper(value) for value in values if str(value or "").strip()]
    if not normalized:
        return default
    return max(normalized, key=lambda item: order.get(item, 0))


def _has_unsafe_focus_rows(rows: Sequence[Any]) -> str | None:
    for row in rows:
        for key in UNSAFE_FOCUS_FLAGS:
            if _normalize_bool(_get_value(row, key)) is True:
                return key
    return None


def _has_synthetic_intent(intent: Any) -> str | None:
    tags = list(_get_value(intent, "tags", []) or [])
    tags.extend(list(_get_value(intent, "risk_flags", []) or []))
    metadata = _get_value(intent, "metadata", {}) or {}
    text = " ".join(str(item).upper() for item in tags)
    if isinstance(metadata, Mapping):
        text = f"{text} {_stable_json(metadata).upper()}"
    for marker in UNSAFE_INTENT_MARKERS:
        if marker in text:
            return marker
    return None


def _assert_no_manual_or_synthetic_evidence(evidence: RuntimeObservationEvidence) -> None:
    focus_flag = _has_unsafe_focus_rows(evidence.watchlist_rows + evidence.focus_rows)
    if focus_flag:
        raise PR1040AdapterError(f"manual/synthetic focus evidence is forbidden: {focus_flag}")
    for intent in evidence.intent_records:
        marker = _has_synthetic_intent(intent)
        if marker:
            raise PR1040AdapterError(f"synthetic or forced trade intent is forbidden: {marker}")


def _broker_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "connected": False,
        "readonly_connection": True,
        "provider_name": "PR1040_REAL_READONLY_RUNTIME_ADAPTER",
        "open_orders": [],
        "metadata": {},
    }
    try:
        from src.adapters.brokers.ibkr.ibkr_connection_manager import (
            get_shared_ibkr_connection_manager,
        )

        manager = get_shared_ibkr_connection_manager(readonly_enabled=True)
        metadata = manager.connection_metadata() if hasattr(manager, "connection_metadata") else {}
        snapshot["metadata"] = _json_safe(metadata)
        client = manager.get_client()
        snapshot["connected"] = True
        open_orders: list[Any] = []
        if hasattr(client, "openTrades"):
            open_orders.extend(client.openTrades() or [])
        elif hasattr(client, "openOrders"):
            open_orders.extend(client.openOrders() or [])
        snapshot["open_orders"] = _normalize_open_order_rows(open_orders)
    except Exception as exc:
        snapshot["error"] = f"{type(exc).__name__}: {exc}"
    return snapshot


def _normalize_open_order_rows(open_orders: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in open_orders:
        order = getattr(item, "order", item)
        contract = getattr(item, "contract", None)
        rows.append(
            {
                "order_id": _get_value(order, "orderId"),
                "perm_id": _get_value(order, "permId"),
                "action": _get_value(order, "action"),
                "order_type": _get_value(order, "orderType"),
                "total_quantity": _get_value(order, "totalQuantity"),
                "symbol": _get_value(contract, "symbol", _get_value(order, "symbol")),
                "status": _get_value(getattr(item, "orderStatus", None), "status"),
            }
        )
    return sorted(rows, key=lambda row: (str(row.get("symbol")), str(row.get("order_id")), str(row.get("perm_id"))))


def _broker_before_connected(evidence: RuntimeObservationEvidence) -> bool:
    return bool(evidence.broker_before.get("connected"))


def _broker_after_connected(evidence: RuntimeObservationEvidence) -> bool:
    return bool(evidence.broker_after.get("connected"))


def _broker_audit_complete(evidence: RuntimeObservationEvidence) -> bool:
    return _broker_before_connected(evidence) and _broker_after_connected(evidence)


def _broker_connected(evidence: RuntimeObservationEvidence) -> bool:
    return _broker_audit_complete(evidence)


def _order_mutation_count(evidence: RuntimeObservationEvidence) -> int:
    count = 0
    for event in evidence.execution_events:
        action = _normalize_upper(_get_value(event, "action"))
        if action in {"SUBMITTED", "ACKNOWLEDGED", "WORKING", "FILLED", "CANCELLED", "MODIFIED"}:
            count += 1
    if _stable_json(evidence.broker_before.get("open_orders", [])) != _stable_json(evidence.broker_after.get("open_orders", [])):
        count += 1
    return count


def _storage_evidence_verified(evidence: RuntimeObservationEvidence) -> bool:
    return bool(
        evidence.storage_write_verified
        and evidence.storage_readback_verified
        and _normalize_upper(getattr(evidence, "storage_evidence_source", "")) == REAL_STORAGE_EVIDENCE_SOURCE
    )


def _intent_metadata(intent: Any) -> Mapping[str, Any]:
    metadata = _get_value(intent, "metadata", {}) or {}
    return metadata if isinstance(metadata, Mapping) else {}


def _intent_decision_authority(intent: Any) -> str:
    return str(_intent_metadata(intent).get("decision_authority") or "")


def _coerce_positive_price(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if parsed > 0.0 else None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
        return parsed if parsed > 0.0 else None
    except ValueError:
        pass
    for token in NUMERIC_PRICE_PATTERN.findall(text):
        try:
            parsed = float(token)
        except ValueError:
            continue
        if parsed > 0.0:
            return parsed
    return None


def _intent_entry_price(intent: Any) -> float | None:
    metadata = _intent_metadata(intent)
    for key in ENTRY_PRICE_METADATA_KEYS:
        if key in metadata:
            price = _coerce_positive_price(metadata.get(key))
            if price is not None:
                return price
    for key in ENTRY_PRICE_METADATA_KEYS:
        price = _coerce_positive_price(_get_value(intent, key))
        if price is not None:
            return price
    for key in ("entry", "entry_model"):
        price = _coerce_positive_price(_get_value(intent, key))
        if price is not None:
            return price
    return None


def _strategy_decision_rows(evidence: RuntimeObservationEvidence) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for decision in evidence.pattern_summaries:
        decision_type = _text_value(_get_value(decision, "decision_type", ""))
        strategy_id = str(_get_value(decision, "strategy_id", "") or "")
        if not decision_type and not strategy_id:
            continue
        intents = list(_get_value(decision, "intents", []) or [])
        rows.append(
            {
                "symbol": _symbol(decision),
                "strategy_id": strategy_id,
                "decision_type": decision_type,
                "confidence": _safe_float(_get_value(decision, "confidence", 0.0), 0.0),
                "rationale_text": str(_get_value(decision, "rationale_text", "") or ""),
                "risk_flags": list(_get_value(decision, "risk_flags", []) or []),
                "intent_count": len(intents),
                "decision_authority": CANONICAL_DECISION_AUTHORITY,
            }
        )
    return rows


def _scanner_news_diagnostics(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload.get("diagnostics"), Mapping) else {}
    news = diagnostics.get("news", {}) if isinstance(diagnostics.get("news"), Mapping) else {}
    return news if isinstance(news, Mapping) else {}


def _news_diagnostics_for_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    news = _scanner_news_diagnostics(payload)
    return {key: _json_safe(news[key]) for key in NEWS_DIAGNOSTIC_ARTIFACT_KEYS if key in news}


def _normalize_news_diagnostic_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _news_diagnostic_status_priority(status: str) -> int:
    normalized = _normalize_news_diagnostic_status(status)
    if normalized in NEWS_DIAGNOSTIC_CONFIRMED_STATUSES:
        return 40
    if normalized == "budget_exhausted":
        return 35
    if normalized == "news_present_non_qualifying":
        return 30
    if normalized == "no_recent_news":
        return 20
    if normalized in NEWS_DIAGNOSTIC_DATA_UNAVAILABLE_STATUSES:
        return 10
    return 0


def _merge_news_diagnostic_status(statuses: dict[str, str], symbol: Any, status: Any) -> None:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_status = _normalize_news_diagnostic_status(status)
    if not normalized_symbol or not normalized_status:
        return
    existing = statuses.get(normalized_symbol)
    if existing is None or _news_diagnostic_status_priority(normalized_status) >= _news_diagnostic_status_priority(existing):
        statuses[normalized_symbol] = normalized_status


def _scanner_news_status_by_symbol(payload: Mapping[str, Any]) -> dict[str, str]:
    news = _scanner_news_diagnostics(payload)
    symbols_by_status = news.get("symbols_by_status", {})
    if not isinstance(symbols_by_status, Mapping):
        return {}
    statuses: dict[str, str] = {}
    for status, raw_symbols in symbols_by_status.items():
        values = raw_symbols if isinstance(raw_symbols, (list, tuple, set)) else [raw_symbols]
        for symbol in values:
            _merge_news_diagnostic_status(statuses, symbol, status)
    return statuses


def _row_news_diagnostic_status(row: Any) -> str:
    if _normalize_bool(_get_value(row, "catalyst_present")) is True:
        return "catalyst_confirmed"
    if _normalize_bool(_get_value(row, "ross_catalyst_valid")) is True:
        return "catalyst_confirmed"
    explicit_status = _normalize_news_diagnostic_status(_get_value(row, "news_diagnostic_status"))
    if explicit_status:
        return explicit_status
    if _normalize_bool(_get_value(row, "news_available")) is False:
        provider_status = _normalize_news_diagnostic_status(_get_value(row, "news_provider_status"))
        return provider_status or "data_unavailable"
    if _safe_int(_get_value(row, "fresh_news_count", 0), 0) > 0:
        return "news_present_non_qualifying"
    if _normalize_bool(_get_value(row, "news_present")) is True:
        return "news_present_non_qualifying"
    if _normalize_bool(_get_value(row, "news_available")) is True:
        return "no_recent_news"
    return ""


def _row_news_status_by_symbol(payload: Mapping[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for row in _scanner_rows(payload, ("focus_m", "watchlist_k", "candidate_metrics", "candidates", "focus_rows", "watchlist_rows")):
        _merge_news_diagnostic_status(statuses, _symbol(row), _row_news_diagnostic_status(row))
    return statuses


def _fallback_news_diagnostic_status(payload: Mapping[str, Any]) -> str:
    news = _scanner_news_diagnostics(payload)
    provider_status = _normalize_news_diagnostic_status(news.get("provider_status"))
    if provider_status in NEWS_DIAGNOSTIC_DATA_UNAVAILABLE_STATUSES:
        return provider_status
    counts = news.get("result_status_counts", {})
    if isinstance(counts, Mapping):
        if _safe_int(counts.get("news_present_non_qualifying"), 0) > 0:
            return "news_present_non_qualifying"
        if _safe_int(counts.get("budget_exhausted"), 0) > 0:
            return "budget_exhausted"
        if _safe_int(counts.get("no_recent_news"), 0) > 0:
            return "no_recent_news"
        for status in NEWS_DIAGNOSTIC_DATA_UNAVAILABLE_STATUSES:
            if _safe_int(counts.get(status), 0) > 0:
                return status
    if provider_status in {"available", "partial_request_failure"} and _safe_int(news.get("no_recent_news_count"), 0) > 0:
        return "no_recent_news"
    return ""


def _catalyst_diagnostic_statuses(payload: Mapping[str, Any], symbols: Sequence[str]) -> dict[str, str]:
    statuses = _row_news_status_by_symbol(payload)
    for symbol, status in _scanner_news_status_by_symbol(payload).items():
        _merge_news_diagnostic_status(statuses, symbol, status)
    normalized_symbols = [str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()]
    fallback_status = _fallback_news_diagnostic_status(payload)
    for symbol in normalized_symbols:
        if symbol not in statuses and fallback_status:
            statuses[symbol] = fallback_status
    if normalized_symbols:
        return {symbol: statuses[symbol] for symbol in normalized_symbols if symbol in statuses}
    return statuses


def _artifact_catalyst_status_for_news_status(status: str) -> str | None:
    normalized = _normalize_news_diagnostic_status(status)
    if normalized in NEWS_DIAGNOSTIC_CONFIRMED_STATUSES:
        return "CONFIRMED"
    if normalized in NEWS_DIAGNOSTIC_ABSENT_STATUSES:
        return "ABSENT"
    if normalized in NEWS_DIAGNOSTIC_DATA_UNAVAILABLE_STATUSES:
        return "DATA_UNAVAILABLE"
    return None


def _artifact_catalyst_reason_for_news_status(status: str) -> str:
    normalized = _normalize_news_diagnostic_status(status)
    if normalized == "news_present_non_qualifying":
        return "non_qualifying"
    if normalized == "no_recent_news":
        return "no_recent_news"
    if normalized in NEWS_DIAGNOSTIC_CONFIRMED_STATUSES:
        return "confirmed"
    if normalized in NEWS_DIAGNOSTIC_DATA_UNAVAILABLE_STATUSES:
        return normalized
    return normalized or "unknown"


def _catalyst_status_reasons(payload: Mapping[str, Any], symbols: Sequence[str]) -> dict[str, str]:
    return {
        symbol: _artifact_catalyst_reason_for_news_status(status)
        for symbol, status in _catalyst_diagnostic_statuses(payload, symbols).items()
    }


def _catalyst_statuses(payload: Mapping[str, Any], symbols: Sequence[str]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    diagnostic_statuses = _catalyst_diagnostic_statuses(payload, symbols)
    for symbol, diagnostic_status in diagnostic_statuses.items():
        artifact_status = _artifact_catalyst_status_for_news_status(diagnostic_status)
        if artifact_status:
            statuses[symbol] = artifact_status
    for symbol in symbols:
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            continue
        statuses.setdefault(normalized_symbol, "UNAVAILABLE")
    return statuses


def _catalyst_news_artifact(payload: Mapping[str, Any], symbols: Sequence[str], *, news_asof: str) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "news_source_mode": _news_source_mode(payload),
        "news_asof": news_asof,
        "catalyst_status_by_symbol": _catalyst_statuses(payload, symbols),
        "catalyst_diagnostic_status_by_symbol": _catalyst_diagnostic_statuses(payload, symbols),
        "catalyst_status_reason_by_symbol": _catalyst_status_reasons(payload, symbols),
        "fresh_news_count": _fresh_news_count(payload),
        "catalyst_bypass": False,
    }
    artifact.update(_news_diagnostics_for_artifact(payload))
    raw_news_diagnostics = _scanner_news_diagnostics(payload)
    if raw_news_diagnostics:
        artifact["scanner_news_diagnostics"] = _json_safe(dict(raw_news_diagnostics))
    return artifact


def _fresh_news_count(payload: Mapping[str, Any]) -> int:
    total = 0
    for row in _scanner_rows(payload, ("focus_m", "watchlist_k", "candidate_metrics", "candidates")):
        try:
            total += int(_get_value(row, "fresh_news_count", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _news_source_mode(payload: Mapping[str, Any]) -> str:
    for row in _scanner_rows(payload, ("focus_m", "watchlist_k", "candidate_metrics", "candidates")):
        value = _get_value(row, "news_source_mode")
        if str(value or "").strip():
            return str(value)
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload.get("diagnostics"), Mapping) else {}
    news = diagnostics.get("news", {}) if isinstance(diagnostics.get("news"), Mapping) else {}
    return str(news.get("news_source_mode") or "REAL_RUNTIME_NEWS_PIPELINE")


def _scanner_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload.get("diagnostics"), Mapping) else {}
    contract = diagnostics.get("scanner_contract", {}) if isinstance(diagnostics.get("scanner_contract"), Mapping) else {}
    if contract:
        return dict(contract)
    top_n = int(payload.get("topn_count", len(payload.get("symbols", []) or [])) or 0)
    watchlist = len(payload.get("watchlist_k_symbols", []) or payload.get("watchlist", []) or [])
    focus = len(payload.get("focus_m_symbols", []) or [])
    return {
        "top_n": top_n,
        "watchlist_k": watchlist,
        "focus_m": focus,
        "contract_valid": 0 <= focus <= watchlist <= max(top_n, watchlist),
    }


def _drop_reasons_from_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_normalize_upper(value)] if value.strip() else []
    if isinstance(value, Mapping):
        reasons: list[str] = []
        for key in ("reason", "drop_reason", "drop_reasons", "reasons", "code"):
            if key in value:
                reasons.extend(_drop_reasons_from_value(value.get(key)))
        return reasons
    if isinstance(value, (list, tuple, set)):
        reasons: list[str] = []
        for item in value:
            reasons.extend(_drop_reasons_from_value(item))
        return reasons
    return [_normalize_upper(value)] if str(value or "").strip() else []


def _scanner_candidate_rows(payload: Mapping[str, Any]) -> list[Any]:
    return _scanner_rows(
        payload,
        (
            "candidate_metrics",
            "candidates",
            "top_n",
            "top_n_rows",
            "symbols_rows",
            "watchlist_k",
            "watchlist_rows",
            "focus_m",
            "focus_rows",
        ),
    )


def _drop_reason_symbol_map(payload: Mapping[str, Any]) -> dict[str, set[str]]:
    reason_symbols: dict[str, set[str]] = {}
    drop_ledger = payload.get("drop_ledger", {})
    if isinstance(drop_ledger, Mapping):
        for key, value in drop_ledger.items():
            key_text = _normalize_upper(key)
            if key_text.startswith("DROP") or key_text.startswith("DATA_QUALITY") or key_text in MARKET_DATA_UNUSABLE_DROP_REASONS:
                symbols = parse_observation_symbols(value)
                reason_symbols.setdefault(key_text, set()).update(symbols)
            else:
                symbol = str(key or "").strip().upper()
                for reason in _drop_reasons_from_value(value):
                    reason_symbols.setdefault(reason, set()).add(symbol)
    for row in _scanner_candidate_rows(payload):
        symbol = _symbol(row)
        for reason in _drop_reasons_from_value(_get_value(row, "drop_reasons", [])):
            reason_symbols.setdefault(reason, set()).add(symbol)
        for reason in _drop_reasons_from_value(_get_value(row, "drop_reason", None)):
            reason_symbols.setdefault(reason, set()).add(symbol)
    return reason_symbols


def _drop_reason_counts(payload: Mapping[str, Any]) -> dict[str, int]:
    reason_symbols = _drop_reason_symbol_map(payload)
    return {reason: len(symbols) for reason, symbols in sorted(reason_symbols.items()) if reason}


def _dominant_drop_reason(payload: Mapping[str, Any]) -> str:
    counts = _drop_reason_counts(payload)
    if not counts:
        return "NONE"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _symbols_for_reasons(payload: Mapping[str, Any], reasons: set[str]) -> list[str]:
    reason_symbols = _drop_reason_symbol_map(payload)
    symbols: set[str] = set()
    for reason in reasons:
        symbols.update(reason_symbols.get(reason, set()))
    return sorted(symbol for symbol in symbols if symbol)


def _row_has_valid_last_price(row: Any) -> bool:
    return any(_safe_float(_get_value(row, key), 0.0) > 0.0 for key in ("last_price", "price", "last", "mark"))


def _row_has_valid_bid_ask(row: Any) -> bool:
    bid = max(_safe_float(_get_value(row, "bid"), 0.0), _safe_float(_get_value(row, "bid_price"), 0.0))
    ask = max(_safe_float(_get_value(row, "ask"), 0.0), _safe_float(_get_value(row, "ask_price"), 0.0))
    return bid > 0.0 and ask > 0.0 and ask >= bid


def _row_has_valid_volume(row: Any) -> bool:
    return any(_safe_float(_get_value(row, key), 0.0) > 0.0 for key in ("volume", "day_volume", "relative_volume_base"))


def _row_has_float(row: Any) -> bool:
    return any(_safe_float(_get_value(row, key), 0.0) > 0.0 for key in ("float", "float_millions", "shares_float", "float_shares"))


def _symbols_matching(rows: Sequence[Any], predicate: Any) -> list[str]:
    symbols: set[str] = set()
    for row in rows:
        symbol = _symbol(row)
        if symbol and predicate(row):
            symbols.add(symbol)
    return sorted(symbols)


def _nested_mapping(payload: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key, {})
    return current if isinstance(current, Mapping) else {}


def _first_present_from_mappings(mappings: Sequence[Mapping[str, Any]], key: str, default: Any = None) -> Any:
    for mapping in mappings:
        if isinstance(mapping, Mapping) and key in mapping:
            return mapping.get(key)
    return default


def _float_discovery_proof(payload: Mapping[str, Any]) -> dict[str, Any]:
    sources = (
        _nested_mapping(payload, "float_discovery"),
        _nested_mapping(payload, "diagnostics", "float_discovery"),
        payload if isinstance(payload, Mapping) else {},
    )
    proof: dict[str, Any] = {
        field: max(0, _safe_int(_first_present_from_mappings(sources, field, 0), 0))
        for field in PR1050_FLOAT_DISCOVERY_COUNT_FIELDS
    }
    for field in PR1050_FLOAT_DISCOVERY_SYMBOL_FIELDS:
        proof[field] = parse_observation_symbols(_first_present_from_mappings(sources, field, []))
    proof["max_same_cycle_float_discovery_requests"] = max(
        0,
        _safe_int(_first_present_from_mappings(sources, "max_same_cycle_float_discovery_requests", 0), 0),
    )
    return proof


def _float_focus_diagnostics(payload: Mapping[str, Any]) -> dict[str, Any]:
    sources = (
        _nested_mapping(payload, "float_focus_diagnostics"),
        _nested_mapping(payload, "diagnostics", "float_focus_diagnostics"),
        payload if isinstance(payload, Mapping) else {},
    )
    diagnostics: dict[str, Any] = {
        field: parse_observation_symbols(_first_present_from_mappings(sources, field, []))
        for field in PR1050_FLOAT_FOCUS_DIAGNOSTIC_SYMBOL_FIELDS
    }
    diagnostics["focus_empty_explanation"] = str(
        _first_present_from_mappings(sources, "focus_empty_explanation", "UNKNOWN") or "UNKNOWN"
    )
    counts = _first_present_from_mappings(sources, "focus_drop_reason_counts", {})
    diagnostics["focus_drop_reason_counts"] = _json_safe(counts if isinstance(counts, Mapping) else {})
    return diagnostics


def _market_data_observation_outcome(evidence: RuntimeObservationEvidence) -> str:
    focus_count = len(_scanner_symbols(evidence.scanner_payload, "focus_m_symbols") or _scanner_rows(evidence.scanner_payload, ("focus_m", "focus_rows")))
    if focus_count == 0:
        dominant = _dominant_drop_reason(evidence.scanner_payload)
        if dominant in MARKET_DATA_UNUSABLE_DROP_REASONS:
            return "REAL_MARKET_DATA_UNUSABLE"
        return "NO_FOCUS_CANDIDATES"
    if not evidence.pattern_input_evidence:
        return "NO_PATTERN_INPUT_EVIDENCE"
    return "FOCUS_PATTERN_INPUT_CAPTURED"


def _market_data_observation_diagnostics(evidence: RuntimeObservationEvidence) -> dict[str, Any]:
    payload = evidence.scanner_payload
    top_symbols = _scanner_symbols(payload, "symbols") or _scanner_symbols(payload, "top_n_symbols")
    watchlist_symbols = _scanner_symbols(payload, "watchlist_k_symbols") or _scanner_symbols(payload, "watchlist")
    focus_symbols = _scanner_symbols(payload, "focus_m_symbols")
    candidate_rows = _scanner_candidate_rows(payload)
    reason_counts = _drop_reason_counts(payload)
    float_discovery_proof = _float_discovery_proof(payload)
    float_focus_diagnostics = _float_focus_diagnostics(payload)
    ibkr_diagnostic = build_ibkr_market_data_diagnostic(
        scanner_payload=payload,
        env=evidence.env,
        candidate_rows=candidate_rows,
        drop_reason_counts=reason_counts,
    )
    return {
        **float_discovery_proof,
        "float_discovery": dict(float_discovery_proof),
        "float_focus_diagnostics": dict(float_focus_diagnostics),
        "candidate_count": int(payload.get("topn_count", len(top_symbols) or len(candidate_rows)) or 0),
        "watchlist_k_count": len(watchlist_symbols) or len(_scanner_rows(payload, ("watchlist_k", "watchlist_rows"))),
        "focus_m_count": len(focus_symbols) or len(_scanner_rows(payload, ("focus_m", "focus_rows"))),
        "dominant_drop_reason": _dominant_drop_reason(payload),
        "drop_reason_counts": reason_counts,
        "symbols_dropped_missing_price": _symbols_for_reasons(payload, {"DROP_MISSING_PRICE"}),
        "symbols_with_snapshot_timeout": _symbols_for_reasons(payload, {"DATA_QUALITY_FAIL_SNAPSHOT", "SNAPSHOT_TIMEOUT"}),
        "symbols_with_reference_only": sorted(
            set(_symbols_for_reasons(payload, {"REFERENCE_ONLY", "REFERENCE_DATA_ONLY"}))
            | set(_symbols_matching(candidate_rows, lambda row: _normalize_bool(_get_value(row, "reference_only")) is True))
        ),
        "symbols_with_valid_last_price": _symbols_matching(candidate_rows, _row_has_valid_last_price),
        "symbols_with_valid_bid_ask": _symbols_matching(candidate_rows, _row_has_valid_bid_ask),
        "symbols_with_valid_volume": _symbols_matching(candidate_rows, _row_has_valid_volume),
        "symbols_with_float": _symbols_matching(candidate_rows, _row_has_float),
        "observation_scope": _operator_observation_scope(evidence),
        "ibkr_market_data_diagnostic": ibkr_diagnostic,
        "outcome": _market_data_observation_outcome(evidence),
    }


def _pattern_input_artifact(evidence: RuntimeObservationEvidence) -> dict[str, Any]:
    pattern_rows = evidence.pattern_input_evidence
    if not pattern_rows:
        return {
            "symbol": "NONE",
            "symbols": [],
            "input_source": "REAL_RUNTIME_NO_FOCUS_OR_NO_PATTERN_INPUT_ATTEMPT",
            "timeframe_provenance": {},
            "freshness_status": "MISSING",
            "missing_data_action": "BLOCK",
            "indicator_provenance": {},
            "data_quality_flags": ["NO_REAL_PATTERN_INPUT_EVIDENCE"],
            "liquidity_context": {},
            "news_context": {},
            "stale_input_execution": False,
        }
    primary = pattern_rows[0]
    all_actions = [_normalize_upper(row.get("missing_data_action")) for row in pattern_rows]
    all_freshness = [_normalize_upper(row.get("freshness_status")) for row in pattern_rows]
    flags: set[str] = set()
    for row in pattern_rows:
        flags.update(str(flag) for flag in row.get("data_quality_flags", []) or [])
    return {
        "symbol": primary.get("symbol"),
        "symbols": [row.get("symbol") for row in pattern_rows],
        "input_source": "REAL_RUNTIME_PATTERN_INPUTS",
        "timeframe_provenance": primary.get("timeframe_provenance", {}),
        "timeframe_provenance_by_symbol": {
            str(row.get("symbol")): row.get("timeframe_provenance", {}) for row in pattern_rows
        },
        "freshness_status": _worst_status(all_freshness, default="FRESH"),
        "missing_data_action": _worst_status(all_actions, default="NONE"),
        "indicator_provenance": primary.get("indicator_provenance", {}),
        "level_provenance": primary.get("level_provenance", {}),
        "data_quality_flags": sorted(flags),
        "liquidity_context": primary.get("liquidity_context", {}),
        "news_context": primary.get("news_context", {}),
        "stale_input_execution": False,
    }


def _intent_target_model(intent: Any) -> str:
    value = _intent_metadata(intent).get("target_model")
    if str(value or "").strip():
        return str(value)
    value = _get_value(intent, "target_model")
    return str(value or "")


def _setup_decision_artifact(evidence: RuntimeObservationEvidence) -> dict[str, Any]:
    strategy_decisions = _strategy_decision_rows(evidence)
    if evidence.intent_records:
        intent = evidence.intent_records[0]
        entry_price = _intent_entry_price(intent)
        detected = [
            str(_get_value(summary, "best_setup", "") or "")
            for summary in evidence.pattern_summaries
            if str(_get_value(summary, "best_setup", "") or "").strip()
            and str(_get_value(summary, "best_setup", "")).upper() != "NONE"
        ]
        authority = _intent_decision_authority(intent)
        return {
            "detected_setups": detected or [str(_get_value(intent, "setup_id", "REAL_RUNTIME_SETUP"))],
            "selected_setup": str(_get_value(intent, "setup_id", detected[0] if detected else "REAL_RUNTIME_SETUP")),
            "entry_model": str(_get_value(intent, "entry", _get_value(intent, "entry_model", "")) or ""),
            "entry_price": entry_price,
            "priced_sizing_input": entry_price,
            "priced_intent": entry_price is not None,
            "stop_model": str(_get_value(intent, "stop", _get_value(intent, "stop_model", "")) or ""),
            "target_model": _intent_target_model(intent),
            "rationale_text": str(_get_value(intent, "rationale", _get_value(intent, "rationale_text", "")) or ""),
            "decision_verdict": "ACCEPT",
            "decision_reason": "REAL_READ_ONLY_RUNTIME_SETUP_ACCEPTED_EXECUTION_DISABLED",
            "decision_authority": authority or "UNKNOWN",
            "decision_path_canonical": authority == CANONICAL_DECISION_AUTHORITY,
            "strategy_decisions": strategy_decisions,
            "fallback_trade_intent": False,
        }
    no_trade_reason = "NO_FOCUS_CANDIDATES"
    if strategy_decisions:
        primary = strategy_decisions[0]
        decision_type = _normalize_upper(primary.get("decision_type")) or "NO_INTENT_CREATED"
        no_trade_reason = f"CANONICAL_STRATEGY_{decision_type}"
    elif evidence.pattern_input_evidence:
        no_trade_reason = "NO_INTENT_CREATED"
    if evidence.pattern_input_evidence and _pattern_input_artifact(evidence).get("missing_data_action") in {"BLOCK", "DROP", "NO_TRADE"}:
        no_trade_reason = "PATTERN_INPUT_BLOCKED"
    return {
        "detected_setups": [
            str(_get_value(summary, "best_setup", "") or "")
            for summary in evidence.pattern_summaries
            if str(_get_value(summary, "best_setup", "") or "").strip()
            and str(_get_value(summary, "best_setup", "")).upper() != "NONE"
        ],
        "selected_setup": "NONE",
        "entry_model": "NO_ENTRY_NO_TRADE",
        "stop_model": "NO_STOP_NO_TRADE",
        "target_model": "NO_TARGET_NO_TRADE",
        "rationale_text": f"Real READ_ONLY no-trade observation: {no_trade_reason}.",
        "decision_verdict": "NO_TRADE",
        "decision_reason": no_trade_reason,
        "decision_authority": CANONICAL_DECISION_AUTHORITY if strategy_decisions else "NOT_EVALUATED",
        "decision_path_canonical": bool(strategy_decisions),
        "strategy_decisions": strategy_decisions,
        "no_setup_reason": no_trade_reason,
        "fallback_trade_intent": False,
    }


def _risk_gate_artifact(evidence: RuntimeObservationEvidence) -> dict[str, Any]:
    if evidence.risk_decisions:
        decision = evidence.risk_decisions[0]
        decision_value = _normalize_upper(_get_value(decision, "decision"))
        approved = decision_value in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"} and int(_get_value(decision, "approved_quantity", 0) or 0) > 0
        return {
            "risk_gate_called": True,
            "risk_approved": approved,
            "risk_reason": str(_get_value(decision, "block_reason", "") or _get_value(decision, "rationale", "")),
            "risk_profile": "READ_ONLY_REAL_RUNTIME",
            "risk_approval_source": "READ_ONLY_RISK_ENGINE",
            "position_size_proposed": int(_get_value(decision, "approved_quantity", 0) or 0),
            "daily_governor_state": "READ_ONLY_EVALUATED",
            "triggered_rules": list(_get_value(decision, "triggered_rules", []) or []),
        }
    return {
        "risk_gate_called": False,
        "risk_approved": False,
        "risk_reason": "NO_SETUP_NO_RISK_APPROVAL",
        "risk_profile": "NONE",
        "risk_approval_source": "NOT_EVALUATED_NO_TRADE",
        "position_size_proposed": 0,
        "daily_governor_state": "NOT_EVALUATED_NO_TRADE",
    }


def _classify_observation(evidence: RuntimeObservationEvidence, setup_artifact: Mapping[str, Any], risk_artifact: Mapping[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = ["Human review required before PAPER decision."]
    mutation_count = _order_mutation_count(evidence)
    if mutation_count:
        blockers.append("Broker order mutation or execution event observed during READ_ONLY adapter run.")
        return "READ_ONLY_OBSERVATION_INVALID", blockers
    if not _broker_audit_complete(evidence):
        blockers.append(BROKER_AUDIT_INCOMPLETE_BLOCKER)
        return "INSUFFICIENT_EVIDENCE", blockers

    scanner_contract = _scanner_contract(evidence.scanner_payload)
    if scanner_contract.get("contract_valid") is not True:
        blockers.append("Scanner contract is missing or invalid.")
        return "INSUFFICIENT_EVIDENCE", blockers

    focus_symbols = _scanner_symbols(evidence.scanner_payload, "focus_m_symbols")
    diagnostics = _market_data_observation_diagnostics(evidence)
    if not focus_symbols:
        if diagnostics.get("outcome") == "REAL_MARKET_DATA_UNUSABLE":
            blockers.append(MARKET_DATA_UNUSABLE_BLOCKER)
        else:
            blockers.append("No Focus M candidates reached real pattern input evaluation.")
        return "INSUFFICIENT_EVIDENCE", blockers
    if not evidence.pattern_input_evidence:
        blockers.append(NO_PATTERN_INPUT_EVIDENCE_BLOCKER)
        return "INSUFFICIENT_EVIDENCE", blockers

    pattern_artifact = _pattern_input_artifact(evidence)
    accepted = _normalize_upper(setup_artifact.get("decision_verdict")) in {"ACCEPT", "ACCEPTED", "SETUP_ACCEPTED"}
    if accepted:
        if setup_artifact.get("decision_authority") != CANONICAL_DECISION_AUTHORITY:
            blockers.append("Accepted setup evidence did not come from the canonical Ross strategy decision authority.")
            return "READ_ONLY_OBSERVATION_INVALID", blockers
        if pattern_artifact.get("input_source") != "REAL_RUNTIME_PATTERN_INPUTS":
            blockers.append("Accepted setup missing real runtime pattern input evidence.")
            return "READ_ONLY_OBSERVATION_INVALID", blockers
        if _normalize_upper(pattern_artifact.get("missing_data_action")) in {"BLOCK", "DROP", "NO_TRADE", "MISSING", "UNAVAILABLE"}:
            blockers.append("Accepted setup used blocked or unavailable pattern input evidence.")
            return "READ_ONLY_OBSERVATION_INVALID", blockers
        selected = str(setup_artifact.get("selected_setup") or "").strip()
        if not selected or selected.upper() == "NONE":
            blockers.append("Accepted setup missing real selected setup evidence.")
            return "READ_ONLY_OBSERVATION_INVALID", blockers
        if not str(setup_artifact.get("target_model") or "").strip():
            blockers.append("Accepted setup missing target model evidence from the real strategy output.")
            return "READ_ONLY_OBSERVATION_INVALID", blockers
        if setup_artifact.get("priced_intent") is not True:
            blockers.append(PRICED_INTENT_BLOCKER)
            return "READ_ONLY_OBSERVATION_INVALID", blockers
        statuses = _catalyst_statuses(evidence.scanner_payload, focus_symbols)
        for symbol in focus_symbols:
            if statuses.get(symbol) not in CATALYST_ACCEPT_VALUES:
                blockers.append(f"Accepted setup lacks confirmed catalyst evidence for {symbol}.")
                return "READ_ONLY_OBSERVATION_INVALID", blockers
        if risk_artifact.get("risk_gate_called") is not True:
            blockers.append("Accepted setup did not call the real READ_ONLY risk gate.")
            return "READ_ONLY_OBSERVATION_INVALID", blockers
        if risk_artifact.get("risk_approved") is not True:
            blockers.append("Accepted setup did not receive a real READ_ONLY risk decision.")
            return "READ_ONLY_OBSERVATION_INVALID", blockers
        if risk_artifact.get("risk_approval_source") != "READ_ONLY_RISK_ENGINE":
            blockers.append("Accepted setup risk decision was not produced by the READ_ONLY risk engine.")
            return "READ_ONLY_OBSERVATION_INVALID", blockers

    if not _storage_evidence_verified(evidence):
        blockers.append(STORAGE_EVIDENCE_UNAVAILABLE_BLOCKER)
        return "INSUFFICIENT_EVIDENCE", blockers

    return "READ_ONLY_OBSERVATION_VALID", blockers


def build_pr1039_observation_input(evidence: RuntimeObservationEvidence) -> dict[str, Any]:
    assert_safe_runtime_env(evidence.env)
    _assert_no_manual_or_synthetic_evidence(evidence)
    if _order_mutation_count(evidence):
        raise PR1040AdapterError("broker order mutation evidence is forbidden in READ_ONLY observation")

    watchlist_symbols = _scanner_symbols(evidence.scanner_payload, "watchlist_k_symbols") or _scanner_symbols(evidence.scanner_payload, "watchlist")
    focus_symbols = _scanner_symbols(evidence.scanner_payload, "focus_m_symbols")
    top_symbols = _scanner_symbols(evidence.scanner_payload, "symbols") or _scanner_symbols(evidence.scanner_payload, "top_n_symbols")
    setup_artifact = _setup_decision_artifact(evidence)
    risk_artifact = _risk_gate_artifact(evidence)
    classification, blockers = _classify_observation(evidence, setup_artifact, risk_artifact)
    captured = classification == "READ_ONLY_OBSERVATION_VALID"
    broker_before_connected = _broker_before_connected(evidence)
    broker_after_connected = _broker_after_connected(evidence)
    broker_audit_complete = _broker_audit_complete(evidence)

    broker = {
        "connected": broker_audit_complete,
        "broker_before_connected": broker_before_connected,
        "broker_after_connected": broker_after_connected,
        "broker_audit_complete": broker_audit_complete,
        "readonly_connection": True,
        "host": evidence.env.get("IBKR_HOST", "127.0.0.1"),
        "port": int(evidence.env.get("IBKR_PORT", "7497") or 7497),
        "client_id": int(evidence.env.get("IBKR_CLIENT_ID", "1040") or 1040),
        "market_data_type": evidence.env.get("IBKR_MARKET_DATA_TYPE", "IBKR_READ_ONLY"),
        "account_id_redacted": "REDACTED",
        "provider_name": "PR1040_REAL_READONLY_RUNTIME_ADAPTER",
        "connection_before": _json_safe(evidence.broker_before.get("metadata", {})),
        "connection_after": _json_safe(evidence.broker_after.get("metadata", {})),
    }

    order_mutation_count = _order_mutation_count(evidence)
    pattern_artifact = _pattern_input_artifact(evidence)
    float_discovery_proof = _float_discovery_proof(evidence.scanner_payload)
    float_focus_diagnostics = _float_focus_diagnostics(evidence.scanner_payload)
    storage_verified = _storage_evidence_verified(evidence)
    storage_count = 1 if storage_verified else 0
    readback_count = 1 if storage_verified else 0

    return {
        "schema_version": PR1039_INPUT_SCHEMA_VERSION,
        "adapter_schema_version": SCHEMA_VERSION,
        "scenario_id": evidence.scenario_id,
        "operator": evidence.operator,
        "classification": classification,
        "operator_observation_scope": _operator_observation_scope(evidence),
        "market_data_observation_diagnostics": _market_data_observation_diagnostics(evidence),
        "broker_connection_snapshot": broker,
        "scanner_cycle_artifact": {
            **float_discovery_proof,
            "float_discovery": dict(float_discovery_proof),
            "provider_source": evidence.scanner_payload.get("provider_source") or evidence.env.get("SCANNER_DATA_SOURCE", "IBKR"),
            "scanner_contract": _scanner_contract(evidence.scanner_payload),
            "candidate_count": int(evidence.scanner_payload.get("topn_count", len(top_symbols)) or 0),
            "accepted_candidate_count": int(evidence.scanner_payload.get("survivors_count", len(watchlist_symbols)) or 0),
            "rejected_candidate_count": max(0, int(evidence.scanner_payload.get("topn_count", len(top_symbols)) or 0) - int(evidence.scanner_payload.get("survivors_count", len(watchlist_symbols)) or 0)),
            "top_n_symbols": top_symbols,
            "drop_ledger": _json_safe(evidence.scanner_payload.get("drop_ledger", {})),
            "selection_spec": {"ranking_intent": "ROSS_MOMENTUM_STOCK_SELECTION", "threshold_override": False},
            "ross_policy_thresholds_used": {"source": "RossPolicy", "threshold_override": False, "validation_override": False},
            "session_classification": evidence.session_label,
            "threshold_override": False,
            "validation_override": False,
        },
        "catalyst_news_artifact": _catalyst_news_artifact(
            evidence.scanner_payload,
            focus_symbols or watchlist_symbols,
            news_asof=evidence.captured_at_utc,
        ),
        "watchlist_focus_artifact": {
            **float_discovery_proof,
            "float_discovery": dict(float_discovery_proof),
            "float_focus_diagnostics": dict(float_focus_diagnostics),
            "watchlist_k_symbols": watchlist_symbols,
            "focus_m_symbols": focus_symbols,
            "watchlist_rows": _json_safe(evidence.watchlist_rows),
            "focus_rows": _json_safe(evidence.focus_rows),
            "manual_focus_injection": False,
            "synthetic_focus": False,
            "non_focus_execution_ineligible": True,
        },
        "pattern_input_artifact": pattern_artifact,
        "setup_decision_artifact": setup_artifact,
        "risk_gate_artifact": risk_artifact,
        "execution_gate_artifact": {
            "execution_enabled": False,
            "order_submission_enabled": False,
            "api_write_allowed": False,
            "execution_path": "READ_ONLY_ORDER_PATH_DISABLED",
            "order_attempt_count": order_mutation_count,
            "broker_order_mutation_allowed": False,
        },
        "broker_order_audit": {
            "submitted_orders_count": order_mutation_count,
            "cancelled_orders_count": 0,
            "modified_orders_count": 0,
            "order_attempt_count": order_mutation_count,
            "broker_before_connected": broker_before_connected,
            "broker_after_connected": broker_after_connected,
            "broker_audit_complete": broker_audit_complete,
            "open_orders_before": _json_safe(evidence.broker_before.get("open_orders", [])),
            "open_orders_after": _json_safe(evidence.broker_after.get("open_orders", [])),
        },
        "analytics_storage_artifact": {
            "storage_write_count": storage_count,
            "storage_readback_count": readback_count,
            "storage_key": evidence.scenario_id,
            "storage_evidence_source": evidence.storage_evidence_source if storage_verified else "UNAVAILABLE",
            "storage_evidence_detail": _json_safe(evidence.storage_evidence_detail or {}),
            "readback_proof": storage_verified,
            "trade_plan_records": _json_safe(evidence.intent_records),
            "no_trade_records": [] if evidence.intent_records else [{"reason": setup_artifact.get("decision_reason"), "symbols": focus_symbols or watchlist_symbols}],
            "artifact_paths": [str(DEFAULT_OBSERVATION_OUTPUT)],
        },
        "final_verdict": {
            "classification": classification,
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED": "YES" if captured else "NO",
            "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED": "YES" if broker_audit_complete else "NO",
            "ZERO_BROKER_ORDER_MUTATIONS": "YES" if order_mutation_count == 0 else "NO",
            "EXECUTION_DISABLED": "YES",
            "remaining_blockers": blockers + ["PAPER readiness remains blocked after PR1040 adapter output."],
            "blockers": blockers + ["PAPER readiness remains blocked after PR1040 adapter output."],
            "operator_signature": evidence.operator,
        },
    }


def _pattern_evidence_from_inputs(symbol: str, inputs: Any, quality_flags: Sequence[str]) -> dict[str, Any]:
    timeframe_provenance = dict(getattr(inputs, "timeframe_provenance", {}) or {})
    missing_actions = dict(getattr(inputs, "missing_data_actions", {}) or {})
    indicator_provenance = dict(getattr(inputs, "indicator_provenance", {}) or {})
    level_provenance = dict(getattr(inputs, "level_provenance", {}) or {})
    freshness = _worst_status(list(timeframe_provenance.values()), default="FRESH")
    action = _worst_status(list(missing_actions.values()), default="NONE")
    liquidity = getattr(inputs, "liquidity_context", None)
    return {
        "symbol": symbol,
        "source": "REAL_RUNTIME_PATTERN_INPUTS",
        "timeframe_provenance": timeframe_provenance,
        "freshness_status": freshness,
        "missing_data_action": action,
        "indicator_provenance": indicator_provenance,
        "level_provenance": level_provenance,
        "data_quality_flags": sorted(set(list(getattr(inputs, "data_quality_flags", []) or []) + list(quality_flags))),
        "liquidity_context": {
            "spread": _get_value(liquidity, "spread"),
            "float_millions": _get_value(liquidity, "float_millions"),
            "rvol": _get_value(liquidity, "rvol"),
            "volume": _get_value(liquidity, "volume"),
        },
        "news_context": _json_safe(getattr(inputs, "news_context", {}) or {}),
    }


def _unavailable_pattern_evidence(symbol: str, reason: str, quality_flags: Sequence[str]) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "source": "REAL_RUNTIME_PATTERN_INPUTS",
        "timeframe_provenance": {"10s": "UNAVAILABLE", "1m": "UNAVAILABLE", "5m": "UNAVAILABLE"},
        "freshness_status": "UNAVAILABLE",
        "missing_data_action": "BLOCK",
        "indicator_provenance": {},
        "level_provenance": {},
        "data_quality_flags": sorted(set(list(quality_flags) + [reason])),
        "liquidity_context": {},
        "news_context": {},
    }


def _scope_allows_symbol(scope: Mapping[str, Any], symbol: str) -> bool:
    requested = set(parse_observation_symbols(scope.get("observation_symbols", [])))
    return not requested or symbol in requested


def collect_real_readonly_runtime_evidence(
    *,
    operator: str,
    env: Mapping[str, str],
    cycle_id: int = 1,
    operator_observation_scope: Mapping[str, Any] | None = None,
) -> RuntimeObservationEvidence:
    apply_readonly_runtime_overrides(env)
    captured_at = utc_now_iso()
    broker_before = _broker_snapshot()
    scope = build_operator_observation_scope(
        max_observation_symbols=(operator_observation_scope or {}).get("max_observation_symbols", DEFAULT_MAX_OBSERVATION_SYMBOLS),
        max_observation_seconds=(operator_observation_scope or {}).get("max_observation_seconds", DEFAULT_MAX_OBSERVATION_SECONDS),
        max_snapshot_failures=(operator_observation_scope or {}).get("max_snapshot_failures", DEFAULT_MAX_SNAPSHOT_FAILURES),
        observation_symbols=(operator_observation_scope or {}).get("observation_symbols", []),
    )

    from src.core_engine.events import TradeIntentRecord
    from src.core_engine.state import RunMode
    from src.risk.risk_audit import AccountSnapshot, evaluate_trade_intents
    from src.scanner.scanner_runner import run_scanner_cycle
    from src.strategies.ross_momentum.patterns.pattern_trace import build_runtime_pattern_inputs
    from src.strategies.ross_momentum.strategy import RossMomentumStrategy
    from src.strategies.strategy_contracts import (
        MarketContext,
        ScannerContext,
        SessionContext,
        StrategyInput,
    )

    scanner_payload = run_scanner_cycle(mode="READ_ONLY")
    watchlist_rows = _scanner_rows(scanner_payload, ("watchlist_k", "watchlist_rows"))
    focus_rows = _scanner_rows(scanner_payload, ("focus_m", "focus_rows"))
    session_label = _session_label_from_payload(scanner_payload, focus_rows + watchlist_rows)
    strategy = RossMomentumStrategy()
    pattern_inputs: list[dict[str, Any]] = []
    strategy_decisions: list[Any] = []
    intent_records: list[TradeIntentRecord] = []
    observed_focus_symbols = [_symbol(row) for row in focus_rows if _symbol(row)]
    evaluated_pattern_symbols: list[str] = []
    snapshot_failure_count = 0
    stopped_by_max_observation_symbols = False
    stopped_by_max_observation_seconds = False
    stopped_by_max_snapshot_failures = False
    observation_started = time.monotonic()

    def session_context(label: str) -> Any:
        normalized = _normalize_upper(label)
        if normalized in {"PRE", "PREMARKET"}:
            return SessionContext.PRE
        if normalized in {"AH", "AFTER", "AFTER_HOURS"}:
            return SessionContext.AFTER
        return SessionContext.REGULAR

    for index, row in enumerate(focus_rows, start=1):
        if len(evaluated_pattern_symbols) >= int(scope["max_observation_symbols"]):
            stopped_by_max_observation_symbols = True
            break
        if time.monotonic() - observation_started > float(scope["max_observation_seconds"]):
            stopped_by_max_observation_seconds = True
            break
        if snapshot_failure_count >= int(scope["max_snapshot_failures"]):
            stopped_by_max_snapshot_failures = True
            break
        symbol = _symbol(row)
        if not symbol or not _scope_allows_symbol(scope, symbol):
            continue
        try:
            inputs, quality_flags = build_runtime_pattern_inputs(
                symbol=symbol,
                row=row,
                snapshot=None,
                session_label=session_label,
                session_phase=session_label,
            )
        except Exception as exc:
            snapshot_failure_count += 1
            pattern_inputs.append(_unavailable_pattern_evidence(symbol, f"pattern_input_exception:{type(exc).__name__}", []))
            if snapshot_failure_count >= int(scope["max_snapshot_failures"]):
                stopped_by_max_snapshot_failures = True
                break
            continue
        if inputs is None:
            snapshot_failure_count += 1
            pattern_inputs.append(_unavailable_pattern_evidence(symbol, "pattern_inputs_unavailable", quality_flags))
            if snapshot_failure_count >= int(scope["max_snapshot_failures"]):
                stopped_by_max_snapshot_failures = True
                break
            continue
        evaluated_pattern_symbols.append(symbol)
        pattern_inputs.append(_pattern_evidence_from_inputs(symbol, inputs, quality_flags))
        liquidity = getattr(inputs, "liquidity_context", None)
        levels = getattr(inputs, "levels", None)
        key_levels = dict(getattr(levels, "key_levels", {}) or {}) if levels is not None else {}
        market_context = MarketContext(
            price=_safe_float(_get_value(row, "last_price", _get_value(row, "price", 0.0)), 0.0),
            spread=_safe_float(_get_value(liquidity, "spread"), 0.0),
            volume=_safe_float(_get_value(liquidity, "volume", _get_value(row, "volume", 0.0)), 0.0),
            rvol=_safe_float(_get_value(liquidity, "rvol", _get_value(row, "rvol", 0.0)), 0.0),
            session_label=session_label,
            float=_safe_float(_get_value(liquidity, "float_millions"), 0.0),
            key_levels=key_levels,
        )
        scanner_context = ScannerContext(
            score=_safe_float(_get_value(row, "score", _get_value(row, "rank_score", 0.0)), 0.0),
            rank=_safe_int(_get_value(row, "rank", index), index),
            drop_reasons=list(_get_value(row, "drop_reasons", []) or []),
        )
        strategy_input = StrategyInput(
            symbol=symbol,
            session_context=session_context(session_label),
            scanner_context=scanner_context,
            market_context=market_context,
            news_context=dict(getattr(inputs, "news_context", {}) or {}),
            data_quality_flags=sorted(set(list(getattr(inputs, "data_quality_flags", []) or []) + list(quality_flags))),
            pattern_inputs=[inputs],
            pattern_results=None,
        )
        decision = strategy.evaluate(symbol, strategy_input)
        strategy_decisions.append(decision)
        for intent in getattr(decision, "intents", []) or []:
            setup_id = str(getattr(intent, "intent_id", "REAL_RUNTIME_SETUP")).split(":")[-1] or "REAL_RUNTIME_SETUP"
            entry_price = _coerce_positive_price(intent.entry_model)
            intent_records.append(
                TradeIntentRecord(
                    symbol=symbol,
                    intent_id=intent.intent_id,
                    setup_id=setup_id,
                    side=getattr(intent.direction, "value", str(intent.direction)),
                    entry=intent.entry_model,
                    stop=intent.stop_model,
                    rationale=intent.rationale_text,
                    tags=list(intent.risk_flags or []),
                    metadata={
                        "target_model": intent.target_model,
                        "pattern_input_source": "REAL_RUNTIME_PATTERN_INPUTS",
                        "decision_authority": CANONICAL_DECISION_AUTHORITY,
                        "strategy_id": getattr(decision, "strategy_id", "ross_momentum"),
                        "entry_price": entry_price,
                        "priced_sizing_input": entry_price,
                    },
                )
            )

    account = AccountSnapshot(
        available_funds=0.0,
        source="READ_ONLY_RUNTIME_ADAPTER",
        canonical=False,
        broker_connection_state="READ_ONLY",
    )
    risk_decisions = evaluate_trade_intents(
        intents=intent_records,
        mode=RunMode.READ_ONLY,
        health_status=None,
        account=account,
    )
    broker_after = _broker_snapshot()
    scope.update(
        {
            "observed_focus_symbols": observed_focus_symbols,
            "evaluated_pattern_symbols": evaluated_pattern_symbols,
            "snapshot_failure_count": snapshot_failure_count,
            "stopped_by_max_observation_symbols": stopped_by_max_observation_symbols,
            "stopped_by_max_observation_seconds": stopped_by_max_observation_seconds,
            "stopped_by_max_snapshot_failures": stopped_by_max_snapshot_failures,
        }
    )

    return RuntimeObservationEvidence(
        operator=operator,
        scenario_id=f"REAL_READ_ONLY_RUNTIME_OBSERVATION_{captured_at.replace(':', '').replace('+', 'Z')}",
        env=env,
        captured_at_utc=captured_at,
        scanner_payload=scanner_payload,
        focus_rows=focus_rows,
        watchlist_rows=watchlist_rows,
        pattern_input_evidence=pattern_inputs,
        pattern_summaries=strategy_decisions,
        intent_records=intent_records,
        risk_decisions=risk_decisions,
        execution_events=[],
        broker_before=broker_before,
        broker_after=broker_after,
        session_label=session_label,
        operator_observation_scope=scope,
    )


def write_observation_input(path: Path, spec: Mapping[str, Any]) -> dict[str, Any]:
    _write_json(path, spec)
    readback = _read_json(path)
    if _stable_json(readback) != _stable_json(spec):
        raise PR1040AdapterError(f"observation JSON readback mismatch: {path}")
    return readback


def _load_pr1039_producer():
    script_path = Path(__file__).with_name("pr1039_readonly_full_ross_strategy_observation_producer.py")
    spec = importlib.util.spec_from_file_location("pr1039_producer", script_path)
    if spec is None or spec.loader is None:
        raise PR1040AdapterError(f"unable to load PR1039 producer: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_with_pr1039(*, observation_input: Path, raw_output_dir: Path, validated_output_dir: Path, operator: str, env: Mapping[str, str], force: bool) -> dict[str, Any]:
    pr1039 = _load_pr1039_producer()
    return pr1039.produce_and_validate_observation(
        raw_output_dir=raw_output_dir,
        validated_output_dir=validated_output_dir,
        operator=operator,
        env=env,
        observation_input=observation_input,
        force=force,
    )


def _cleanup_scanner_runtime_after_observation() -> None:
    try:
        from src.scanner.scanner_runner import reset_scanner_runtime_state

        reset_scanner_runtime_state(clear_persistent_provider=True)
    except Exception as exc:
        print(f"[PR1040][CLEANUP_WARN] scanner_runtime_reset_failed={type(exc).__name__}", file=sys.stderr)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PR1040 real READ_ONLY Ross runtime observation adapter.")
    parser.add_argument("--operator", required=True)
    parser.add_argument("--cycle-id", type=int, default=1)
    parser.add_argument("--observation-output", type=Path, default=DEFAULT_OBSERVATION_OUTPUT)
    parser.add_argument("--raw-output-dir", type=Path, default=DEFAULT_RAW_OUTPUT_DIR)
    parser.add_argument("--validated-output-dir", type=Path, default=DEFAULT_VALIDATED_OUTPUT_DIR)
    parser.add_argument("--validate-with-pr1039", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-observation-symbols", type=int, default=DEFAULT_MAX_OBSERVATION_SYMBOLS)
    parser.add_argument("--max-observation-seconds", type=float, default=DEFAULT_MAX_OBSERVATION_SECONDS)
    parser.add_argument("--max-snapshot-failures", type=int, default=DEFAULT_MAX_SNAPSHOT_FAILURES)
    parser.add_argument("--observation-symbols", type=parse_observation_symbols, default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    env = build_safe_readonly_env()
    operator_observation_scope = build_operator_observation_scope(
        max_observation_symbols=args.max_observation_symbols,
        max_observation_seconds=args.max_observation_seconds,
        max_snapshot_failures=args.max_snapshot_failures,
        observation_symbols=args.observation_symbols,
    )
    try:
        evidence = collect_real_readonly_runtime_evidence(
            operator=args.operator,
            env=env,
            cycle_id=args.cycle_id,
            operator_observation_scope=operator_observation_scope,
        )
        spec = build_pr1039_observation_input(evidence)
        spec["analytics_storage_artifact"]["artifact_paths"] = [str(args.observation_output)]
        write_observation_input(args.observation_output, spec)
        manifest = None
        if args.validate_with_pr1039:
            manifest = validate_with_pr1039(
                observation_input=args.observation_output,
                raw_output_dir=args.raw_output_dir,
                validated_output_dir=args.validated_output_dir,
                operator=args.operator,
                env=env,
                force=args.force,
            )
    except Exception as exc:
        print(f"[PR1040][ABORT] {exc}", file=sys.stderr)
        return 2
    finally:
        _cleanup_scanner_runtime_after_observation()

    classification = spec.get("classification") or spec.get("final_verdict", {}).get("classification")
    print(
        "[PR1040][OBSERVE] "
        f"classification={classification} "
        "paper_ready=NO paper_readiness_gate=FAIL "
        f"observation_input={args.observation_output}"
    )
    if manifest is not None:
        print(
            "[PR1040][PR1039_VALIDATE] "
            f"status={manifest.get('status')} output={args.validated_output_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
