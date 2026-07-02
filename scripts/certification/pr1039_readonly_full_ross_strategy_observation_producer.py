#!/usr/bin/env python
"""PR1039 READ_ONLY full Ross strategy observation producer.

Certification-only producer/adapter for controlled READ_ONLY Ross observation
artifacts. It writes the raw artifact bundle required by PR1038 and immediately
validates that bundle with the PR1038 validator.

This script does not connect to IBKR by itself, does not submit/cancel/modify
orders, does not alter Ross thresholds, does not enable PAPER/LIVE, and keeps
PAPER_READY=NO.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "PR1039.readonly_full_ross_strategy_observation_producer.v1"
INPUT_SCHEMA_VERSION = "PR1039.controlled_readonly_observation_input.v1"

RAW_OUTPUT_DEFAULT = Path("artifacts/certification/pr1039/raw_readonly_full_ross_observation")
VALIDATED_OUTPUT_DEFAULT = Path(
    "artifacts/certification/pr1039/validated_readonly_full_ross_observation"
)

PR1038_SCRIPT_NAME = "pr1038_readonly_full_ross_strategy_observation_collector.py"
PR1038_RUNBOOK_PATH = Path(
    "docs/certification/PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md"
)
PR1038_MANIFEST_PATH = Path(
    "docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_MANIFEST.example.json"
)

FALSE_VALUES = {"0", "false", "no", "off", ""}
TRUE_VALUES = {"1", "true", "yes", "on"}

REQUIRED_ARTIFACT_IDS = (
    "operator_runbook_acknowledgement",
    "runtime_config_snapshot",
    "broker_connection_snapshot",
    "scanner_cycle_artifact",
    "catalyst_news_artifact",
    "watchlist_focus_artifact",
    "pattern_input_artifact",
    "setup_decision_artifact",
    "risk_gate_artifact",
    "execution_gate_artifact",
    "broker_order_audit",
    "analytics_storage_artifact",
    "final_verdict",
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

ACCEPTED_DECISION_REASONS = {
    "ACCEPT",
    "ACCEPTED",
    "APPROVED",
    "ROSS_SETUP_ACCEPTED",
    "READ_ONLY_NORMAL_DECISION_PATH",
    "TRADE_READY",
    "SETUP_ACCEPTED",
}

NO_TRADE_DECISION_REASONS = {
    "NO_TRADE",
    "REJECT",
    "REJECTED",
    "BLOCK",
    "DROP",
    "DROP_NO_CATALYST",
    "PATTERN_INPUT_BLOCK",
    "INVALID_RISK_GEOMETRY",
    "MISSING_TARGET",
}

CATALYST_ACCEPT_VALUES = {
    "CONFIRMED",
    "FRESH_CONFIRMED",
    "CATALYST_CONFIRMED",
    "VALID_CATALYST",
}

REAL_RISK_SOURCE_VALUES = {
    "READ_ONLY_RISK_ENGINE",
    "RISK_GATE",
    "ROSS_RISK_GATE",
    "REAL_RISK_GATE",
    "DAILY_RISK_GOVERNOR",
}

FAKE_RISK_SOURCE_VALUES = {
    "FORCE",
    "FORCED",
    "FORCED_APPROVAL",
    "SYNTHETIC",
    "OVERRIDE",
    "DEBUG_OVERRIDE",
    "VALIDATION_OVERRIDE",
}


def _load_pr1038_validator():
    try:
        import pr1038_readonly_full_ross_strategy_observation_collector as validator  # type: ignore

        return validator
    except ModuleNotFoundError:
        validator_path = Path(__file__).with_name(PR1038_SCRIPT_NAME)
        spec = importlib.util.spec_from_file_location("pr1038_validator", validator_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"unable to load PR1038 validator: {validator_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


pr1038 = _load_pr1038_validator()


class PR1039ProducerError(RuntimeError):
    """Raised when PR1039 cannot safely produce a READ_ONLY observation bundle."""


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


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise PR1039ProducerError(f"{path} must contain a JSON object")
    return payload


def _require_false(mapping: Mapping[str, Any], key: str, scope: str) -> None:
    if _normalize_bool(mapping.get(key)) is not False:
        raise PR1039ProducerError(f"{scope}.{key} must be false")


def _require_zero(mapping: Mapping[str, Any], key: str, scope: str) -> None:
    try:
        value = int(mapping.get(key, -1))
    except (TypeError, ValueError) as exc:
        raise PR1039ProducerError(f"{scope}.{key} must be numeric zero") from exc
    if value != 0:
        raise PR1039ProducerError(f"{scope}.{key} must be zero")


def assert_safe_environment(env: Mapping[str, str]) -> None:
    if _normalize_upper(env.get("RUN_MODE")) != "READ_ONLY":
        raise PR1039ProducerError("RUN_MODE must be READ_ONLY")
    if _normalize_upper(env.get("RUN_MODE_EFFECTIVE")) != "READ_ONLY":
        raise PR1039ProducerError("RUN_MODE_EFFECTIVE must be READ_ONLY")
    for key in (
        "EXECUTION_ENABLED",
        "EXECUTION_ENABLED_EFFECTIVE",
        "IBKR_API_WRITE_ALLOWED",
        "IBKR_ORDER_SUBMISSION_ENABLED",
        "FORCE_CLEAN_START",
    ):
        if _normalize_bool(env.get(key)) is not False:
            raise PR1039ProducerError(f"{key} must be false")
    for key in FALSE_OR_ABSENT_ENV_KEYS:
        if _normalize_bool(env.get(key)) is True:
            raise PR1039ProducerError(f"{key} must be false or absent")
    for key in EMPTY_OR_ABSENT_ENV_KEYS:
        if str(env.get(key, "") or "").strip():
            raise PR1039ProducerError(f"{key} must be empty or absent")


def safe_runtime_config_from_env(env: Mapping[str, str]) -> dict[str, Any]:
    assert_safe_environment(env)
    return {
        "RUN_MODE": "READ_ONLY",
        "RUN_MODE_EFFECTIVE": "READ_ONLY",
        "EXECUTION_ENABLED": False,
        "EXECUTION_ENABLED_EFFECTIVE": False,
        "EVENT_REPLAY_MODE": _normalize_upper(env.get("EVENT_REPLAY_MODE") or "OFF"),
        "EVENT_REPLAY_MODE_EFFECTIVE": _normalize_upper(env.get("EVENT_REPLAY_MODE_EFFECTIVE") or "OFF"),
        "IBKR_API_WRITE_ALLOWED": False,
        "IBKR_ORDER_SUBMISSION_ENABLED": False,
        "FORCE_CLEAN_START": False,
        "FORCE_EXECUTION_ON_TRADE_READY": False,
        "FORCE_RISK_APPROVAL_FOR_TRADE_READY": False,
        "VALIDATION_SESSION_OVERRIDE": False,
        "ROSS_VALIDATION_OVERRIDE": False,
        "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
        "ROSS_THRESHOLD_OVERRIDE": False,
        "ROSS_CATALYST_BYPASS": False,
        "ROSS_FLOAT_RELAXATION": False,
        "ROSS_RVOL_RELAXATION": False,
        "MANUAL_FOCUS_ENABLED": False,
        "SYNTHETIC_TRADE_INTENT_ENABLED": False,
        "MANUAL_FOCUS_SYMBOLS": "",
        "ROSS_MANUAL_FOCUS_SYMBOLS": "",
        "SYNTHETIC_TRADE_INTENTS": "",
        "ROSS_SYNTHETIC_TRADE_INTENTS": "",
        "producer_schema_version": SCHEMA_VERSION,
        "captured_at_utc": utc_now_iso(),
    }


def _has_meaningful_setup_value(value: Any) -> bool:
    normalized = _normalize_upper(value)
    return normalized not in {"", "NONE", "NO_SETUP", "NO_ENTRY_NO_TRADE", "NONE_COLLECTOR_ONLY"}


def _has_detected_setup(setup: Mapping[str, Any]) -> bool:
    detected = setup.get("detected_setups", []) or []
    if isinstance(detected, str):
        detected = [detected]
    return any(_has_meaningful_setup_value(item) for item in detected)


def _decision_key(setup: Mapping[str, Any]) -> str:
    return _normalize_upper(setup.get("decision_verdict") or setup.get("decision_reason"))


def _decision_is_accept(setup: Mapping[str, Any]) -> bool:
    decision = _decision_key(setup)
    if decision in ACCEPTED_DECISION_REASONS:
        return True
    if decision in NO_TRADE_DECISION_REASONS:
        return False
    return _has_meaningful_setup_value(setup.get("selected_setup")) or _has_detected_setup(setup)


def _focused_symbols(focus_artifact: Mapping[str, Any]) -> list[str]:
    return [
        str(symbol).upper()
        for symbol in (focus_artifact.get("focus_m_symbols", []) or [])
        if str(symbol).strip()
    ]


def _catalyst_statuses(catalyst_artifact: Mapping[str, Any]) -> dict[str, str]:
    raw = catalyst_artifact.get("catalyst_status_by_symbol", {}) or {}
    if not isinstance(raw, Mapping):
        raise PR1039ProducerError("catalyst_status_by_symbol must be a mapping")
    return {str(key).upper(): _normalize_upper(value) for key, value in raw.items()}


def build_valid_no_trade_spec(operator: str) -> dict[str, Any]:
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "scenario_id": "CONTROLLED_VALID_NO_TRADE",
        "operator": operator,
        "broker_connection_snapshot": {
            "connected": True,
            "readonly_connection": True,
            "host": "127.0.0.1",
            "port": 7497,
            "client_id": 1039,
            "market_data_type": "IBKR_READ_ONLY",
            "account_id_redacted": "REDACTED",
            "provider_name": "PR1039_CONTROLLED_READONLY_PROVIDER",
        },
        "scanner_cycle_artifact": {
            "provider_source": "PR1039_CONTROLLED_READONLY_OBSERVATION",
            "scanner_contract": {"contract_valid": True},
            "candidate_count": 1,
            "accepted_candidate_count": 1,
            "rejected_candidate_count": 0,
            "top_n_symbols": ["PR39A"],
            "drop_ledger": {},
            "selection_spec": {
                "ranking_intent": "ROSS_MOMENTUM_STOCK_SELECTION",
                "threshold_override": False,
            },
            "ross_policy_thresholds_used": {
                "source": "RossPolicy",
                "threshold_override": False,
                "validation_override": False,
            },
            "session_classification": "PREMARKET_OR_OPEN",
            "threshold_override": False,
            "validation_override": False,
        },
        "catalyst_news_artifact": {
            "news_source_mode": "PR1039_CONTROLLED_READONLY_OBSERVATION",
            "news_asof": utc_now_iso(),
            "catalyst_status_by_symbol": {"PR39A": "CONFIRMED"},
            "fresh_news_count": 1,
            "catalyst_bypass": False,
        },
        "watchlist_focus_artifact": {
            "watchlist_k_symbols": ["PR39A"],
            "focus_m_symbols": ["PR39A"],
            "watchlist_rows": [
                {
                    "symbol": "PR39A",
                    "manual_focus": False,
                    "manual_focus_injected": False,
                    "prep_seeded": False,
                    "execution_ineligible_if_not_focus": True,
                }
            ],
            "focus_rows": [
                {
                    "symbol": "PR39A",
                    "manual_focus": False,
                    "manual_focus_injected": False,
                    "prep_seeded": False,
                    "synthetic_focus": False,
                    "synthetic_intent": False,
                }
            ],
            "manual_focus_injection": False,
            "synthetic_focus": False,
            "non_focus_execution_ineligible": True,
        },
        "pattern_input_artifact": {
            "symbol": "PR39A",
            "timeframe_provenance": {"10s": "MISSING", "1m": "FRESH", "5m": "FRESH"},
            "freshness_status": "MISSING",
            "missing_data_action": "BLOCK",
            "indicator_provenance": {"VWAP": "OBSERVED", "EMA": "OBSERVED", "MACD": "OBSERVED"},
            "data_quality_flags": ["NO_10S_INPUT_AVAILABLE"],
            "liquidity_context": {"rvol": 6.2, "float_millions": 7.0},
            "news_context": {"catalyst_status": "CONFIRMED"},
            "stale_input_execution": False,
        },
        "setup_decision_artifact": {
            "detected_setups": [],
            "selected_setup": "NONE",
            "entry_model": "NO_ENTRY_NO_TRADE",
            "stop_model": "NO_STOP_NO_TRADE",
            "target_model": "NO_TARGET_NO_TRADE",
            "rationale_text": "READ_ONLY no-trade observation: pattern input block.",
            "decision_verdict": "NO_TRADE",
            "decision_reason": "PATTERN_INPUT_BLOCK",
            "no_setup_reason": "10s input missing",
            "fallback_trade_intent": False,
        },
        "risk_gate_artifact": {
            "risk_gate_called": False,
            "risk_approved": False,
            "risk_reason": "NO_SETUP_NO_RISK_APPROVAL",
            "risk_profile": "NONE",
            "risk_approval_source": "NOT_EVALUATED_NO_TRADE",
            "position_size_proposed": 0,
            "daily_governor_state": "NOT_EVALUATED_NO_TRADE",
        },
        "execution_gate_artifact": {
            "execution_enabled": False,
            "order_submission_enabled": False,
            "api_write_allowed": False,
            "execution_path": "READ_ONLY_ORDER_PATH_DISABLED",
            "order_attempt_count": 0,
            "broker_order_mutation_allowed": False,
        },
        "broker_order_audit": {
            "submitted_orders_count": 0,
            "cancelled_orders_count": 0,
            "modified_orders_count": 0,
            "order_attempt_count": 0,
            "open_orders_before": [],
            "open_orders_after": [],
        },
        "analytics_storage_artifact": {
            "storage_write_count": 1,
            "storage_readback_count": 1,
            "storage_key": "PR1039_CONTROLLED_VALID_NO_TRADE",
            "readback_proof": True,
            "trade_plan_records": [],
            "no_trade_records": [{"symbol": "PR39A", "reason": "PATTERN_INPUT_BLOCK"}],
            "artifact_paths": ["capture_manifest.json"],
        },
        "final_verdict": {
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED": "YES",
            "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED": "YES",
            "ZERO_BROKER_ORDER_MUTATIONS": "YES",
            "EXECUTION_DISABLED": "YES",
            "remaining_blockers": [
                "Human review required before PAPER decision.",
                "Real operator production-runtime adapter remains required before PAPER readiness.",
            ],
            "blockers": [
                "Human review required before PAPER decision.",
                "Real operator production-runtime adapter remains required before PAPER readiness.",
            ],
            "operator_signature": operator,
        },
    }


def build_valid_accepted_setup_spec(operator: str) -> dict[str, Any]:
    spec = build_valid_no_trade_spec(operator)
    spec["scenario_id"] = "CONTROLLED_VALID_ACCEPTED_SETUP_READ_ONLY"
    spec["pattern_input_artifact"].update(
        {
            "timeframe_provenance": {"10s": "FRESH", "1m": "FRESH", "5m": "FRESH"},
            "freshness_status": "FRESH",
            "missing_data_action": "NONE",
            "data_quality_flags": [],
        }
    )
    spec["setup_decision_artifact"].update(
        {
            "detected_setups": ["Micro Pullback"],
            "selected_setup": "Micro Pullback",
            "entry_model": "Break over pullback high",
            "stop_model": "Below pullback low",
            "target_model": "HOD extension target",
            "rationale_text": "READ_ONLY accepted setup observation with execution disabled.",
            "decision_verdict": "ACCEPT",
            "decision_reason": "ROSS_SETUP_ACCEPTED",
            "no_setup_reason": "",
            "fallback_trade_intent": False,
        }
    )
    spec["risk_gate_artifact"].update(
        {
            "risk_gate_called": True,
            "risk_approved": True,
            "risk_reason": "READ_ONLY_RISK_APPROVED_NO_EXECUTION",
            "risk_profile": "MICRO_READ_ONLY",
            "risk_approval_source": "READ_ONLY_RISK_ENGINE",
            "position_size_proposed": 1,
            "daily_governor_state": "READ_ONLY_EVALUATED",
        }
    )
    spec["analytics_storage_artifact"].update(
        {
            "storage_key": "PR1039_CONTROLLED_VALID_ACCEPTED_SETUP_READ_ONLY",
            "trade_plan_records": [
                {
                    "symbol": "PR39A",
                    "setup": "Micro Pullback",
                    "risk_approved": True,
                    "execution_enabled": False,
                    "order_attempt_count": 0,
                }
            ],
            "no_trade_records": [],
        }
    )
    return spec


def _load_observation_spec(path: Path | None, *, scenario: str, operator: str) -> dict[str, Any]:
    if path is not None:
        spec = _read_json(path)
        if spec.get("schema_version") != INPUT_SCHEMA_VERSION:
            raise PR1039ProducerError(
                f"observation input schema_version must be {INPUT_SCHEMA_VERSION}"
            )
        return spec

    if scenario == "valid_no_trade":
        return build_valid_no_trade_spec(operator)
    if scenario == "valid_accepted_setup":
        return build_valid_accepted_setup_spec(operator)
    raise PR1039ProducerError(f"unsupported scenario: {scenario}")


def _artifact_from_spec(spec: Mapping[str, Any], artifact_id: str) -> dict[str, Any]:
    payload = spec.get(artifact_id)
    if not isinstance(payload, dict):
        raise PR1039ProducerError(f"observation spec missing object: {artifact_id}")
    return dict(payload)


def assert_broker_and_execution_safe(spec: Mapping[str, Any]) -> None:
    broker = _artifact_from_spec(spec, "broker_connection_snapshot")
    audit = _artifact_from_spec(spec, "broker_order_audit")
    execution = _artifact_from_spec(spec, "execution_gate_artifact")

    if broker.get("connected") is not True:
        raise PR1039ProducerError("broker_connection_snapshot.connected must be true")
    if broker.get("readonly_connection") is not True:
        raise PR1039ProducerError("broker_connection_snapshot.readonly_connection must be true")

    for key in (
        "submitted_orders_count",
        "cancelled_orders_count",
        "modified_orders_count",
        "order_attempt_count",
    ):
        _require_zero(audit, key, "broker_order_audit")

    _require_false(execution, "execution_enabled", "execution_gate_artifact")
    _require_false(execution, "order_submission_enabled", "execution_gate_artifact")
    _require_false(execution, "api_write_allowed", "execution_gate_artifact")
    _require_zero(execution, "order_attempt_count", "execution_gate_artifact")


def assert_selection_and_focus_safe(spec: Mapping[str, Any]) -> None:
    scanner = _artifact_from_spec(spec, "scanner_cycle_artifact")
    catalyst = _artifact_from_spec(spec, "catalyst_news_artifact")
    focus = _artifact_from_spec(spec, "watchlist_focus_artifact")

    if _normalize_bool(catalyst.get("catalyst_bypass")) is True:
        raise PR1039ProducerError("catalyst bypass is forbidden")

    for key in ("threshold_override", "validation_override"):
        if _normalize_bool(scanner.get(key)) is True:
            raise PR1039ProducerError(f"scanner {key} is forbidden")

    for nested_key in ("selection_spec", "ross_policy_thresholds_used"):
        nested = scanner.get(nested_key, {})
        if isinstance(nested, Mapping):
            for key in ("threshold_override", "validation_override"):
                if _normalize_bool(nested.get(key)) is True:
                    raise PR1039ProducerError(f"{nested_key}.{key} is forbidden")

    for key in ("manual_focus_injection", "synthetic_focus", "manual_focus", "prep_seeded"):
        if _normalize_bool(focus.get(key)) is True:
            raise PR1039ProducerError(f"unsafe focus flag: {key}")

    for row_key in ("watchlist_rows", "focus_rows"):
        for row in focus.get(row_key, []) or []:
            if not isinstance(row, Mapping):
                continue
            for key in (
                "manual_focus",
                "manual_focus_injected",
                "synthetic_focus",
                "synthetic_intent",
                "prep_seeded",
            ):
                if _normalize_bool(row.get(key)) is True:
                    raise PR1039ProducerError(f"unsafe focus row flag: {key}")


def assert_decision_and_risk_safe(spec: Mapping[str, Any]) -> None:
    catalyst = _artifact_from_spec(spec, "catalyst_news_artifact")
    focus = _artifact_from_spec(spec, "watchlist_focus_artifact")
    pattern = _artifact_from_spec(spec, "pattern_input_artifact")
    setup = _artifact_from_spec(spec, "setup_decision_artifact")
    risk = _artifact_from_spec(spec, "risk_gate_artifact")

    if _normalize_bool(setup.get("fallback_trade_intent")) is True:
        raise PR1039ProducerError("fallback trade intent is forbidden")

    accepted = _decision_is_accept(setup)
    risk_source = _normalize_upper(risk.get("risk_approval_source") or risk.get("risk_source"))

    if risk_source in FAKE_RISK_SOURCE_VALUES:
        raise PR1039ProducerError("fake or forced risk approval source is forbidden")

    if accepted:
        statuses = _catalyst_statuses(catalyst)
        for symbol in _focused_symbols(focus):
            if statuses.get(symbol) not in CATALYST_ACCEPT_VALUES:
                raise PR1039ProducerError(f"accepted setup requires confirmed catalyst for {symbol}")

        if _normalize_upper(pattern.get("missing_data_action")) in {"BLOCK", "DROP", "NO_TRADE"}:
            raise PR1039ProducerError("accepted setup cannot use blocked pattern inputs")
        if _normalize_upper(pattern.get("freshness_status")) in {"MISSING", "STALE"}:
            raise PR1039ProducerError("accepted setup cannot use missing or stale pattern inputs")

        for key in ("entry_model", "stop_model", "target_model"):
            if not str(setup.get(key, "")).strip():
                raise PR1039ProducerError(f"accepted setup missing {key}")

        if _normalize_bool(risk.get("risk_approved")) is not True:
            raise PR1039ProducerError("accepted setup requires real risk evaluation")
        if risk_source not in REAL_RISK_SOURCE_VALUES:
            raise PR1039ProducerError("accepted setup requires real risk approval source")
    else:
        if _normalize_bool(risk.get("risk_approved")) is True:
            raise PR1039ProducerError("no-trade observation cannot have risk_approved=true")


def assert_final_safe(spec: Mapping[str, Any]) -> None:
    final = _artifact_from_spec(spec, "final_verdict")
    if final.get("paper_ready") != "NO":
        raise PR1039ProducerError("final_verdict.paper_ready must be NO")
    if final.get("paper_readiness_gate") != "FAIL":
        raise PR1039ProducerError("final_verdict.paper_readiness_gate must be FAIL")


def assert_observation_spec_safe(spec: Mapping[str, Any]) -> None:
    assert_broker_and_execution_safe(spec)
    assert_selection_and_focus_safe(spec)
    assert_decision_and_risk_safe(spec)
    assert_final_safe(spec)


def write_raw_artifact_bundle(
    *,
    spec: Mapping[str, Any],
    raw_output_dir: Path,
    operator: str,
    env: Mapping[str, str],
    force: bool = False,
) -> dict[str, Path]:
    assert_safe_environment(env)
    assert_observation_spec_safe(spec)

    if raw_output_dir.exists() and any(raw_output_dir.iterdir()) and not force:
        raise PR1039ProducerError(f"raw output directory is not empty: {raw_output_dir}")

    raw_output_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths: dict[str, Path] = {}

    runtime_config = safe_runtime_config_from_env(env)
    runtime_config["operator"] = operator
    runtime_config["scenario_id"] = str(spec.get("scenario_id", "UNSPECIFIED"))

    operator_ack = {
        "runbook_path": str(PR1038_RUNBOOK_PATH),
        "operator": operator,
        "acknowledged_at_utc": utc_now_iso(),
        "pre_run_checklist_status": "PASS",
        "abort_conditions_reviewed": True,
        "paper_ready": "NO",
        "paper_readiness_gate": "FAIL",
        "producer_schema_version": SCHEMA_VERSION,
    }

    artifacts: dict[str, dict[str, Any]] = {
        "operator_runbook_acknowledgement": operator_ack,
        "runtime_config_snapshot": runtime_config,
    }

    for artifact_id in REQUIRED_ARTIFACT_IDS:
        if artifact_id in artifacts:
            continue
        artifacts[artifact_id] = _artifact_from_spec(spec, artifact_id)

    for artifact_id, payload in artifacts.items():
        path = raw_output_dir / f"{artifact_id}.json"
        _write_json(path, payload)
        artifact_paths[artifact_id] = path

    return artifact_paths


def produce_and_validate_observation(
    *,
    raw_output_dir: Path,
    validated_output_dir: Path,
    operator: str,
    env: Mapping[str, str] | None = None,
    observation_input: Path | None = None,
    scenario: str = "valid_no_trade",
    force: bool = False,
) -> dict[str, Any]:
    runtime_env = env or os.environ
    spec = _load_observation_spec(observation_input, scenario=scenario, operator=operator)

    write_raw_artifact_bundle(
        spec=spec,
        raw_output_dir=raw_output_dir,
        operator=operator,
        env=runtime_env,
        force=force,
    )

    manifest = pr1038.validate_full_observation_bundle(
        source_dir=raw_output_dir,
        output_dir=validated_output_dir,
        operator=operator,
        env=runtime_env,
        template_path=PR1038_MANIFEST_PATH,
        runbook_path=PR1038_RUNBOOK_PATH,
        force=force,
    )

    manifest["pr1039_schema_version"] = SCHEMA_VERSION
    manifest["pr1039_scenario_id"] = str(spec.get("scenario_id", scenario))
    manifest["paper_ready"] = "NO"
    manifest["paper_readiness_gate"] = "FAIL"
    _write_json(validated_output_dir / "capture_manifest.json", manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Produce and validate PR1039 READ_ONLY full Ross observation artifacts."
    )
    parser.add_argument("--raw-output-dir", type=Path, default=RAW_OUTPUT_DEFAULT)
    parser.add_argument("--validated-output-dir", type=Path, default=VALIDATED_OUTPUT_DEFAULT)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--observation-input", type=Path, default=None)
    parser.add_argument(
        "--scenario",
        choices=("valid_no_trade", "valid_accepted_setup"),
        default="valid_no_trade",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = produce_and_validate_observation(
            raw_output_dir=args.raw_output_dir,
            validated_output_dir=args.validated_output_dir,
            operator=args.operator,
            observation_input=args.observation_input,
            scenario=args.scenario,
            force=args.force,
        )
    except (PR1039ProducerError, pr1038.PR1038ValidationError, pr1038.pr1033.CaptureValidationError) as exc:
        print(f"[PR1039][ABORT] {exc}", file=sys.stderr)
        return 2

    print(
        "[PR1039][OBSERVE] "
        f"status={manifest['status']} "
        f"paper_ready={manifest['paper_ready']} "
        f"output={args.validated_output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
