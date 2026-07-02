#!/usr/bin/env python
"""PR1038 READ_ONLY full Ross strategy observation artifact validator.

Certification-only offline validator/assembler for a full Ross READ_ONLY
observation bundle. It reads operator-captured JSON artifacts, applies extra
Ross safety gates, delegates redaction/hashing to the PR1033 validator, and
emits a PR1038 manifest overlay.

This script does not connect to any broker, does not create execution authority,
does not change production trading behavior, and keeps PAPER_READY=NO.
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

SCHEMA_VERSION = "PR1038.readonly_full_ross_strategy_observation.v1"
STATUS_VALIDATED = "READ_ONLY_FULL_STRATEGY_OBSERVATION_VALIDATED_PENDING_HUMAN_REVIEW"
STATUS_BLOCKED = "READ_ONLY_FULL_STRATEGY_OBSERVATION_BLOCKED_PENDING_HUMAN_REVIEW"

PR1032_RUNBOOK_PATH = Path(
    "docs/certification/PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md"
)
PR1032_MANIFEST_PATH = Path(
    "docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_MANIFEST.example.json"
)
PR1033_SCRIPT_NAME = "pr1033_readonly_broker_artifact_capture.py"

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

EXTRA_FALSE_OR_ABSENT_ENV_KEYS = (
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

EXTRA_EMPTY_OR_ABSENT_ENV_KEYS = (
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


def _load_pr1033_validator():
    try:
        import pr1033_readonly_broker_artifact_capture as validator  # type: ignore

        return validator
    except ModuleNotFoundError:
        validator_path = Path(__file__).with_name(PR1033_SCRIPT_NAME)
        spec = importlib.util.spec_from_file_location("pr1033_validator", validator_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"unable to load PR1033 validator: {validator_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


pr1033 = _load_pr1033_validator()


class PR1038ValidationError(RuntimeError):
    """Raised when the PR1038 bundle is unsafe or incomplete."""


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


def _read_artifact(source_dir: Path, artifact_id: str) -> dict[str, Any]:
    path = source_dir / f"{artifact_id}.json"
    if not path.exists():
        raise PR1038ValidationError(f"missing required artifact: {artifact_id}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise PR1038ValidationError(f"{artifact_id} must be a JSON object")
    return payload


def _load_required_artifacts(source_dir: Path) -> dict[str, dict[str, Any]]:
    return {artifact_id: _read_artifact(source_dir, artifact_id) for artifact_id in REQUIRED_ARTIFACT_IDS}


def assert_extra_runtime_guards(env: Mapping[str, str]) -> None:
    for key in EXTRA_FALSE_OR_ABSENT_ENV_KEYS:
        if _normalize_bool(env.get(key)) is True:
            raise PR1038ValidationError(f"{key} must be false or absent")
    for key in EXTRA_EMPTY_OR_ABSENT_ENV_KEYS:
        if str(env.get(key, "") or "").strip():
            raise PR1038ValidationError(f"{key} must be empty or absent")


def _require_zero(payload: Mapping[str, Any], key: str, artifact_id: str) -> None:
    try:
        value = int(payload.get(key, -1))
    except (TypeError, ValueError) as exc:
        raise PR1038ValidationError(f"{artifact_id}.{key} must be numeric zero") from exc
    if value != 0:
        raise PR1038ValidationError(f"{artifact_id}.{key} must be zero")


def _require_false(payload: Mapping[str, Any], key: str, artifact_id: str) -> None:
    if _normalize_bool(payload.get(key)) is not False:
        raise PR1038ValidationError(f"{artifact_id}.{key} must be false")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _focused_symbols(focus_artifact: Mapping[str, Any]) -> list[str]:
    return [
        str(symbol).upper()
        for symbol in (focus_artifact.get("focus_m_symbols", []) or [])
        if str(symbol).strip()
    ]


def _catalyst_statuses(catalyst_artifact: Mapping[str, Any]) -> dict[str, str]:
    raw = catalyst_artifact.get("catalyst_status_by_symbol", {}) or {}
    if not isinstance(raw, Mapping):
        raise PR1038ValidationError("catalyst_status_by_symbol must be a mapping")
    return {str(key).upper(): _normalize_upper(value) for key, value in raw.items()}


def assert_runtime_artifact_safe(runtime: Mapping[str, Any]) -> None:
    if _normalize_upper(runtime.get("RUN_MODE")) != "READ_ONLY":
        raise PR1038ValidationError("runtime RUN_MODE must be READ_ONLY")
    if _normalize_upper(runtime.get("RUN_MODE_EFFECTIVE")) != "READ_ONLY":
        raise PR1038ValidationError("runtime RUN_MODE_EFFECTIVE must be READ_ONLY")
    _require_false(runtime, "EXECUTION_ENABLED", "runtime_config_snapshot")
    _require_false(runtime, "EXECUTION_ENABLED_EFFECTIVE", "runtime_config_snapshot")
    _require_false(runtime, "IBKR_API_WRITE_ALLOWED", "runtime_config_snapshot")
    _require_false(runtime, "IBKR_ORDER_SUBMISSION_ENABLED", "runtime_config_snapshot")
    _require_false(runtime, "FORCE_CLEAN_START", "runtime_config_snapshot")

    for key in EXTRA_FALSE_OR_ABSENT_ENV_KEYS:
        if key in runtime and _normalize_bool(runtime.get(key)) is True:
            raise PR1038ValidationError(f"runtime_config_snapshot.{key} must be false or absent")
    for key in EXTRA_EMPTY_OR_ABSENT_ENV_KEYS:
        if str(runtime.get(key, "") or "").strip():
            raise PR1038ValidationError(f"runtime_config_snapshot.{key} must be empty or absent")


def assert_broker_evidence_safe(artifacts: Mapping[str, Mapping[str, Any]]) -> None:
    broker = artifacts["broker_connection_snapshot"]
    audit = artifacts["broker_order_audit"]

    if broker.get("connected") is not True:
        raise PR1038ValidationError("broker_connection_snapshot.connected must be true")
    if broker.get("readonly_connection") is not True:
        raise PR1038ValidationError("broker_connection_snapshot.readonly_connection must be true")

    for key in (
        "submitted_orders_count",
        "cancelled_orders_count",
        "modified_orders_count",
        "order_attempt_count",
    ):
        _require_zero(audit, key, "broker_order_audit")

    if _stable_json(audit.get("open_orders_before", [])) != _stable_json(audit.get("open_orders_after", [])):
        raise PR1038ValidationError("open orders changed during READ_ONLY observation")


def assert_no_manual_or_synthetic_focus(focus: Mapping[str, Any]) -> None:
    for key in ("manual_focus_injection", "synthetic_focus", "manual_focus", "prep_seeded"):
        if _normalize_bool(focus.get(key)) is True:
            raise PR1038ValidationError(f"unsafe focus flag: {key}")

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
                    raise PR1038ValidationError(f"unsafe focus row flag: {key}")


def assert_no_bypass_or_threshold_override(scanner: Mapping[str, Any], catalyst: Mapping[str, Any]) -> None:
    if _normalize_bool(catalyst.get("catalyst_bypass")) is True:
        raise PR1038ValidationError("catalyst bypass is forbidden")

    for key in ("threshold_override", "validation_override"):
        if _normalize_bool(scanner.get(key)) is True:
            raise PR1038ValidationError(f"scanner {key} is forbidden")

    for nested_key in ("selection_spec", "ross_policy_thresholds_used"):
        nested = scanner.get(nested_key, {})
        if isinstance(nested, Mapping):
            for key in ("threshold_override", "validation_override"):
                if _normalize_bool(nested.get(key)) is True:
                    raise PR1038ValidationError(f"{nested_key}.{key} is forbidden")


ACCEPTED_DECISION_REASONS = {
    "ACCEPT",
    "ACCEPTED",
    "APPROVED",
    "ROSS_SETUP_ACCEPTED",
    "READ_ONLY_NORMAL_DECISION_PATH",
    "TRADE_READY",
    "SETUP_ACCEPTED",
}

NO_TRADE_OR_REJECT_DECISION_REASONS = {
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


def _has_meaningful_setup_value(value: Any) -> bool:
    normalized = _normalize_upper(value)
    return normalized not in {"", "NONE", "NO_SETUP", "NONE_COLLECTOR_ONLY", "NO_ENTRY_NO_TRADE"}


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
    if decision in NO_TRADE_OR_REJECT_DECISION_REASONS:
        return False
    return _has_meaningful_setup_value(setup.get("selected_setup")) or _has_detected_setup(setup)


def _decision_is_reject_or_no_trade(setup: Mapping[str, Any]) -> bool:
    decision = _decision_key(setup)
    return decision in NO_TRADE_OR_REJECT_DECISION_REASONS


def assert_decision_and_inputs_safe(artifacts: Mapping[str, Mapping[str, Any]]) -> None:
    catalyst = artifacts["catalyst_news_artifact"]
    focus = artifacts["watchlist_focus_artifact"]
    pattern = artifacts["pattern_input_artifact"]
    setup = artifacts["setup_decision_artifact"]
    risk = artifacts["risk_gate_artifact"]
    execution = artifacts["execution_gate_artifact"]

    accepted = _decision_is_accept(setup)

    if _normalize_bool(setup.get("fallback_trade_intent")) is True:
        raise PR1038ValidationError("fallback trade intent is forbidden")

    if accepted:
        statuses = _catalyst_statuses(catalyst)
        for symbol in _focused_symbols(focus):
            if statuses.get(symbol) not in CATALYST_ACCEPT_VALUES:
                raise PR1038ValidationError(f"accepted setup requires confirmed catalyst for {symbol}")

        if _normalize_upper(pattern.get("missing_data_action")) in {"BLOCK", "DROP", "NO_TRADE"}:
            raise PR1038ValidationError("accepted setup cannot use blocked pattern inputs")
        if _normalize_upper(pattern.get("freshness_status")) in {"MISSING", "STALE"}:
            raise PR1038ValidationError("accepted setup cannot use missing or stale pattern inputs")

        for key in ("entry_model", "stop_model", "target_model"):
            if not str(setup.get(key, "")).strip():
                raise PR1038ValidationError(f"accepted setup missing {key}")

    if not accepted and _decision_is_reject_or_no_trade(setup):
        if _normalize_bool(risk.get("risk_approved")) is True:
            raise PR1038ValidationError("risk gate must not approve rejected/no-trade setup")

    _require_false(execution, "execution_enabled", "execution_gate_artifact")
    _require_false(execution, "order_submission_enabled", "execution_gate_artifact")
    _require_false(execution, "api_write_allowed", "execution_gate_artifact")
    _require_zero(execution, "order_attempt_count", "execution_gate_artifact")


def assert_storage_and_final_safe(artifacts: Mapping[str, Mapping[str, Any]]) -> None:
    storage = artifacts["analytics_storage_artifact"]
    final = artifacts["final_verdict"]

    if final.get("paper_ready") != "NO":
        raise PR1038ValidationError("final_verdict.paper_ready must be NO")
    if final.get("paper_readiness_gate") != "FAIL":
        raise PR1038ValidationError("final_verdict.paper_readiness_gate must be FAIL")

    try:
        write_count = int(storage.get("storage_write_count", 0))
        readback_count = int(storage.get("storage_readback_count", 0))
    except (TypeError, ValueError) as exc:
        raise PR1038ValidationError("storage counts must be numeric") from exc

    blockers = final.get("blockers") or final.get("remaining_blockers") or []
    if (write_count <= 0 or readback_count <= 0) and not blockers:
        raise PR1038ValidationError("missing storage readback requires an explicit final blocker")


def assert_pr1038_artifacts_safe(artifacts: Mapping[str, Mapping[str, Any]]) -> bool:
    assert_runtime_artifact_safe(artifacts["runtime_config_snapshot"])
    assert_broker_evidence_safe(artifacts)
    assert_no_manual_or_synthetic_focus(artifacts["watchlist_focus_artifact"])
    assert_no_bypass_or_threshold_override(
        artifacts["scanner_cycle_artifact"],
        artifacts["catalyst_news_artifact"],
    )
    assert_decision_and_inputs_safe(artifacts)
    assert_storage_and_final_safe(artifacts)

    final = artifacts["final_verdict"]
    captured = (
        final.get("READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED")
        or final.get("read_only_full_strategy_observation_captured")
    )
    return _normalize_upper(captured) in {"YES", "TRUE"}


def _acceptance_gates(full_observation_captured: bool) -> list[dict[str, str]]:
    return [
        {"id": "readonly_mode_only", "verdict": "PASS"},
        {"id": "execution_disabled", "verdict": "PASS"},
        {"id": "clean_start_disabled", "verdict": "PASS"},
        {"id": "no_manual_focus", "verdict": "PASS"},
        {"id": "no_synthetic_trade_intents", "verdict": "PASS"},
        {"id": "no_catalyst_bypass", "verdict": "PASS"},
        {"id": "no_threshold_override", "verdict": "PASS"},
        {"id": "zero_broker_order_mutations", "verdict": "PASS"},
        {
            "id": "read_only_full_strategy_observation_captured",
            "verdict": "PASS" if full_observation_captured else "FAIL",
        },
        {"id": "paper_ready_blocked", "verdict": "PASS"},
    ]


def write_pr1038_manifest_overlay(
    output_dir: Path,
    pr1033_manifest: Mapping[str, Any],
    *,
    operator: str,
    full_observation_captured: bool,
    blockers: Sequence[str],
) -> dict[str, Any]:
    manifest = dict(pr1033_manifest)
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["pr1033_manifest_schema_version"] = pr1033_manifest.get("schema_version")
    manifest["status"] = (
        STATUS_VALIDATED if full_observation_captured else STATUS_BLOCKED
    )
    manifest["paper_ready"] = "NO"
    manifest["paper_readiness_gate"] = "FAIL"
    manifest["operator"] = operator
    manifest["captured_at_utc"] = utc_now_iso()
    manifest["read_only_full_strategy_observation_captured"] = full_observation_captured
    manifest["broker_connected_runtime_artifact_captured"] = True
    manifest["zero_broker_order_mutations"] = True
    manifest["execution_disabled"] = True
    manifest["acceptance_gates"] = _acceptance_gates(
        full_observation_captured=full_observation_captured
    )
    manifest["blockers"] = list(blockers)

    _write_json(output_dir / "capture_manifest.json", manifest)
    return manifest


def validate_full_observation_bundle(
    *,
    source_dir: Path,
    output_dir: Path,
    operator: str,
    env: Mapping[str, str] | None = None,
    template_path: Path = PR1032_MANIFEST_PATH,
    runbook_path: Path = PR1032_RUNBOOK_PATH,
    force: bool = False,
) -> dict[str, Any]:
    runtime_env = env or os.environ
    pr1033.assert_safe_runtime_environment(runtime_env)
    assert_extra_runtime_guards(runtime_env)

    artifacts = _load_required_artifacts(source_dir)
    full_observation_captured = assert_pr1038_artifacts_safe(artifacts)

    pr1033_manifest = pr1033.capture_bundle(
        source_dir=source_dir,
        output_dir=output_dir,
        operator=operator,
        template_path=template_path,
        runbook_path=runbook_path,
        env=runtime_env,
        force=force,
    )

    final = artifacts["final_verdict"]
    blockers = (
        final.get("blockers")
        or final.get("remaining_blockers")
        or ["Human review required before PAPER decision."]
    )
    return write_pr1038_manifest_overlay(
        output_dir,
        pr1033_manifest,
        operator=operator,
        full_observation_captured=full_observation_captured,
        blockers=[str(item) for item in blockers],
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate PR1038 READ_ONLY full Ross strategy observation artifacts."
    )
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", "--validated-output-dir", required=True, type=Path)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--manifest-template", type=Path, default=PR1032_MANIFEST_PATH)
    parser.add_argument("--runbook", type=Path, default=PR1032_RUNBOOK_PATH)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = validate_full_observation_bundle(
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            operator=args.operator,
            template_path=args.manifest_template,
            runbook_path=args.runbook,
            force=args.force,
        )
    except (PR1038ValidationError, pr1033.CaptureValidationError) as exc:
        print(f"[PR1038][ABORT] {exc}", file=sys.stderr)
        return 2

    print(
        "[PR1038][VALIDATE] "
        f"status={manifest['status']} "
        f"paper_ready={manifest['paper_ready']} "
        f"artifacts={len(manifest['artifacts'])} "
        f"output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
