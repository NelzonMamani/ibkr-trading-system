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
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "PR1040.real_readonly_runtime_observation_adapter.v1"
PR1039_INPUT_SCHEMA_VERSION = "PR1039.controlled_readonly_observation_input.v1"

DEFAULT_OBSERVATION_OUTPUT = Path(
    "artifacts/certification/pr1040/real_runtime_observation/real_runtime_observation.json"
)
DEFAULT_RAW_OUTPUT_DIR = Path(
    "artifacts/certification/pr1040/raw_real_runtime_observation"
)
DEFAULT_VALIDATED_OUTPUT_DIR = Path(
    "artifacts/certification/pr1040/validated_real_runtime_observation"
)

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}

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
    "SCANNER_MODE": "READ_ONLY",
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
    return str(value or "").strip().upper()


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


def apply_readonly_runtime_overrides(env: Mapping[str, str]) -> None:
    assert_safe_runtime_env(env)
    os.environ.update({key: str(value) for key, value in env.items()})
    try:
        from src.config.config_resolver import set_config_overrides
    except Exception:
        return

    typed: dict[str, object] = {}
    for key, value in env.items():
        parsed = _normalize_bool(value)
        typed[key] = parsed if parsed is not None and str(value).strip().lower() in TRUE_VALUES | FALSE_VALUES else value
    set_config_overrides(typed)


def _stable_json(value: Any) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))


def _symbol(value: Any) -> str:
    return str(_get_value(value, "symbol", "") or "").strip().upper()


def _rows_by_symbol(rows: Sequence[Any]) -> dict[str, Any]:
    return {symbol: row for row in rows if (symbol := _symbol(row))}


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


def _broker_connected(evidence: RuntimeObservationEvidence) -> bool:
    return bool(evidence.broker_before.get("connected") or evidence.broker_after.get("connected"))


def _order_mutation_count(evidence: RuntimeObservationEvidence) -> int:
    count = 0
    for event in evidence.execution_events:
        action = _normalize_upper(_get_value(event, "action"))
        if action in {"SUBMITTED", "ACKNOWLEDGED", "WORKING", "FILLED", "CANCELLED", "MODIFIED"}:
            count += 1
    if _stable_json(evidence.broker_before.get("open_orders", [])) != _stable_json(evidence.broker_after.get("open_orders", [])):
        count += 1
    return count


def _catalyst_statuses(payload: Mapping[str, Any], symbols: Sequence[str]) -> dict[str, str]:
    rows = _scanner_rows(payload, ("focus_m", "watchlist_k", "candidate_metrics", "candidates", "focus_rows", "watchlist_rows"))
    statuses: dict[str, str] = {}
    for row in rows:
        symbol = _symbol(row)
        if not symbol:
            continue
        if _normalize_bool(_get_value(row, "catalyst_present")) is True:
            statuses[symbol] = "CONFIRMED"
        elif int(_get_value(row, "fresh_news_count", 0) or 0) > 0:
            statuses[symbol] = "NEWS_PRESENT_NOT_CONFIRMED"
        else:
            statuses[symbol] = "UNAVAILABLE"
    for symbol in symbols:
        statuses.setdefault(str(symbol).upper(), "UNAVAILABLE")
    return statuses


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
    metadata = _get_value(intent, "metadata", {}) or {}
    if isinstance(metadata, Mapping):
        value = metadata.get("target_model")
        if str(value or "").strip():
            return str(value)
    value = _get_value(intent, "target_model")
    return str(value or "")


def _setup_decision_artifact(evidence: RuntimeObservationEvidence) -> dict[str, Any]:
    if evidence.intent_records:
        intent = evidence.intent_records[0]
        detected = [
            str(_get_value(summary, "best_setup", "") or "")
            for summary in evidence.pattern_summaries
            if str(_get_value(summary, "best_setup", "") or "").strip()
            and str(_get_value(summary, "best_setup", "")).upper() != "NONE"
        ]
        return {
            "detected_setups": detected or [str(_get_value(intent, "setup_id", "REAL_RUNTIME_SETUP"))],
            "selected_setup": str(_get_value(intent, "setup_id", detected[0] if detected else "REAL_RUNTIME_SETUP")),
            "entry_model": str(_get_value(intent, "entry", _get_value(intent, "entry_model", "")) or ""),
            "stop_model": str(_get_value(intent, "stop", _get_value(intent, "stop_model", "")) or ""),
            "target_model": _intent_target_model(intent),
            "rationale_text": str(_get_value(intent, "rationale", _get_value(intent, "rationale_text", "")) or ""),
            "decision_verdict": "ACCEPT",
            "decision_reason": "REAL_READ_ONLY_RUNTIME_SETUP_ACCEPTED_EXECUTION_DISABLED",
            "fallback_trade_intent": False,
        }
    no_trade_reason = "NO_FOCUS_CANDIDATES"
    if evidence.pattern_input_evidence:
        no_trade_reason = "NO_INTENT_CREATED"
        if _pattern_input_artifact(evidence).get("missing_data_action") in {"BLOCK", "DROP", "NO_TRADE"}:
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
    if not _broker_connected(evidence):
        blockers.append("Broker connection evidence is unavailable; real operator runtime evidence is incomplete.")
        return "INSUFFICIENT_EVIDENCE", blockers

    scanner_contract = _scanner_contract(evidence.scanner_payload)
    if scanner_contract.get("contract_valid") is not True:
        blockers.append("Scanner contract is missing or invalid.")
        return "INSUFFICIENT_EVIDENCE", blockers

    focus_symbols = _scanner_symbols(evidence.scanner_payload, "focus_m_symbols")
    if not focus_symbols:
        blockers.append("No Focus M candidates reached real pattern input evaluation.")
        return "INSUFFICIENT_EVIDENCE", blockers
    if not evidence.pattern_input_evidence:
        blockers.append("No real pattern input evidence was captured for Focus M candidates.")
        return "INSUFFICIENT_EVIDENCE", blockers

    accepted = _normalize_upper(setup_artifact.get("decision_verdict")) in {"ACCEPT", "ACCEPTED", "SETUP_ACCEPTED"}
    if accepted:
        selected = str(setup_artifact.get("selected_setup") or "").strip()
        if not selected or selected.upper() == "NONE":
            blockers.append("Accepted setup missing real selected setup evidence.")
            return "READ_ONLY_OBSERVATION_INVALID", blockers
        if not str(setup_artifact.get("target_model") or "").strip():
            blockers.append("Accepted setup missing target model evidence from the real strategy output.")
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

    broker = {
        "connected": _broker_connected(evidence),
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
    storage_count = 1 if evidence.storage_write_verified else 0
    readback_count = 1 if evidence.storage_readback_verified else 0

    return {
        "schema_version": PR1039_INPUT_SCHEMA_VERSION,
        "adapter_schema_version": SCHEMA_VERSION,
        "scenario_id": evidence.scenario_id,
        "operator": evidence.operator,
        "classification": classification,
        "broker_connection_snapshot": broker,
        "scanner_cycle_artifact": {
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
        "catalyst_news_artifact": {
            "news_source_mode": _news_source_mode(evidence.scanner_payload),
            "news_asof": evidence.captured_at_utc,
            "catalyst_status_by_symbol": _catalyst_statuses(evidence.scanner_payload, focus_symbols or watchlist_symbols),
            "fresh_news_count": _fresh_news_count(evidence.scanner_payload),
            "catalyst_bypass": False,
        },
        "watchlist_focus_artifact": {
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
            "open_orders_before": _json_safe(evidence.broker_before.get("open_orders", [])),
            "open_orders_after": _json_safe(evidence.broker_after.get("open_orders", [])),
        },
        "analytics_storage_artifact": {
            "storage_write_count": storage_count,
            "storage_readback_count": readback_count,
            "storage_key": evidence.scenario_id,
            "readback_proof": bool(evidence.storage_readback_verified),
            "trade_plan_records": _json_safe(evidence.intent_records),
            "no_trade_records": [] if evidence.intent_records else [{"reason": setup_artifact.get("decision_reason"), "symbols": focus_symbols or watchlist_symbols}],
            "artifact_paths": [str(DEFAULT_OBSERVATION_OUTPUT)],
        },
        "final_verdict": {
            "classification": classification,
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED": "YES" if captured else "NO",
            "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED": "YES" if _broker_connected(evidence) else "NO",
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


def collect_real_readonly_runtime_evidence(*, operator: str, env: Mapping[str, str], cycle_id: int = 1) -> RuntimeObservationEvidence:
    apply_readonly_runtime_overrides(env)
    captured_at = utc_now_iso()
    broker_before = _broker_snapshot()

    from src.core_engine.events import TradeIntentRecord
    from src.core_engine.state import RunMode
    from src.risk.risk_audit import AccountSnapshot, evaluate_trade_intents
    from src.scanner.scanner_runner import run_scanner_cycle
    from src.strategies.ross_momentum.decision_policy import build_trade_intents
    from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
    from src.strategies.ross_momentum.patterns.pattern_trace import build_runtime_pattern_inputs

    scanner_payload = run_scanner_cycle(mode="READ_ONLY")
    watchlist_rows = _scanner_rows(scanner_payload, ("watchlist_k", "watchlist_rows"))
    focus_rows = _scanner_rows(scanner_payload, ("focus_m", "focus_rows"))
    session_label = _session_label_from_payload(scanner_payload, focus_rows + watchlist_rows)
    evaluator = PatternEvaluator()
    pattern_inputs: list[dict[str, Any]] = []
    pattern_summaries: list[Any] = []
    intent_records: list[TradeIntentRecord] = []

    for row in focus_rows:
        symbol = _symbol(row)
        if not symbol:
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
            pattern_inputs.append(_unavailable_pattern_evidence(symbol, f"pattern_input_exception:{type(exc).__name__}", []))
            continue
        if inputs is None:
            pattern_inputs.append(_unavailable_pattern_evidence(symbol, "pattern_inputs_unavailable", quality_flags))
            continue
        pattern_inputs.append(_pattern_evidence_from_inputs(symbol, inputs, quality_flags))
        summary = evaluator.evaluate([inputs])
        pattern_summaries.append(summary)
        best_setup = summary.best_long_setup or summary.best_short_setup
        setup_detected = bool(best_setup and getattr(best_setup, "pattern_name", ""))
        best_conf = float(getattr(best_setup, "confidence", 0.0) or 0.0) if best_setup else 0.0
        trigger_ready_now = setup_detected and best_conf >= 0.20
        strategy_intents = build_trade_intents(
            "RossMomentumStrategy",
            symbol,
            summary,
            trigger_ready_now=trigger_ready_now,
            session=session_label,
        )
        for intent in strategy_intents:
            intent_records.append(
                TradeIntentRecord(
                    symbol=symbol,
                    intent_id=intent.intent_id,
                    setup_id=str(getattr(best_setup, "pattern_name", "REAL_RUNTIME_SETUP") or "REAL_RUNTIME_SETUP"),
                    side=getattr(intent.direction, "value", str(intent.direction)),
                    entry=intent.entry_model,
                    stop=intent.stop_model,
                    rationale=intent.rationale_text,
                    tags=list(intent.risk_flags or []),
                    metadata={
                        "target_model": intent.target_model,
                        "pattern_input_source": "REAL_RUNTIME_PATTERN_INPUTS",
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

    return RuntimeObservationEvidence(
        operator=operator,
        scenario_id=f"REAL_READ_ONLY_RUNTIME_OBSERVATION_{captured_at.replace(':', '').replace('+', 'Z')}",
        env=env,
        captured_at_utc=captured_at,
        scanner_payload=scanner_payload,
        focus_rows=focus_rows,
        watchlist_rows=watchlist_rows,
        pattern_input_evidence=pattern_inputs,
        pattern_summaries=pattern_summaries,
        intent_records=intent_records,
        risk_decisions=risk_decisions,
        execution_events=[],
        broker_before=broker_before,
        broker_after=broker_after,
        session_label=session_label,
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PR1040 real READ_ONLY Ross runtime observation adapter.")
    parser.add_argument("--operator", required=True)
    parser.add_argument("--cycle-id", type=int, default=1)
    parser.add_argument("--observation-output", type=Path, default=DEFAULT_OBSERVATION_OUTPUT)
    parser.add_argument("--raw-output-dir", type=Path, default=DEFAULT_RAW_OUTPUT_DIR)
    parser.add_argument("--validated-output-dir", type=Path, default=DEFAULT_VALIDATED_OUTPUT_DIR)
    parser.add_argument("--validate-with-pr1039", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    env = build_safe_readonly_env()
    try:
        evidence = collect_real_readonly_runtime_evidence(
            operator=args.operator,
            env=env,
            cycle_id=args.cycle_id,
        )
        spec = build_pr1039_observation_input(evidence)
        evidence.storage_write_verified = True
        evidence.storage_readback_verified = True
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
