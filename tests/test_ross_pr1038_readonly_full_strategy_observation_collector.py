from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = (
    _ROOT
    / "scripts"
    / "certification"
    / "pr1038_readonly_full_ross_strategy_observation_collector.py"
)
_TEMPLATE_PATH = (
    _ROOT
    / "docs"
    / "certification"
    / "PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_MANIFEST.example.json"
)
_RUNBOOK_PATH = (
    _ROOT
    / "docs"
    / "certification"
    / "PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md"
)
_REPORT_PATH = (
    _ROOT
    / "docs"
    / "certification"
    / "PR1038_READ_ONLY_FULL_ROSS_STRATEGY_OBSERVATION_COLLECTOR.md"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("pr1038_validator", _SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pr1038 = _load_script_module()


def _safe_env() -> dict[str, str]:
    return {
        "RUN_MODE": "READ_ONLY",
        "RUN_MODE_EFFECTIVE": "READ_ONLY",
        "EXECUTION_ENABLED": "false",
        "EXECUTION_ENABLED_EFFECTIVE": "false",
        "EVENT_REPLAY_MODE": "OFF",
        "EVENT_REPLAY_MODE_EFFECTIVE": "OFF",
        "IBKR_API_WRITE_ALLOWED": "false",
        "IBKR_ORDER_SUBMISSION_ENABLED": "false",
        "FORCE_CLEAN_START": "false",
        "FORCE_EXECUTION_ON_TRADE_READY": "false",
        "FORCE_RISK_APPROVAL_FOR_TRADE_READY": "false",
        "VALIDATION_SESSION_OVERRIDE": "false",
        "ROSS_VALIDATION_OVERRIDE": "false",
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
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _minimal_artifacts() -> dict[str, dict]:
    return {
        "operator_runbook_acknowledgement": {
            "runbook_path": "docs/certification/PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md",
            "operator": "TEST_OP",
            "acknowledged_at_utc": "2026-07-02T08:00:00+00:00",
            "pre_run_checklist_status": "PASS",
            "abort_conditions_reviewed": True,
            "paper_ready": "NO",
        },
        "runtime_config_snapshot": {
            "RUN_MODE": "READ_ONLY",
            "RUN_MODE_EFFECTIVE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "EXECUTION_ENABLED_EFFECTIVE": False,
            "EVENT_REPLAY_MODE": "OFF",
            "EVENT_REPLAY_MODE_EFFECTIVE": "OFF",
            "IBKR_API_WRITE_ALLOWED": False,
            "IBKR_ORDER_SUBMISSION_ENABLED": False,
            "FORCE_CLEAN_START": False,
            "FORCE_EXECUTION_ON_TRADE_READY": False,
            "FORCE_RISK_APPROVAL_FOR_TRADE_READY": False,
            "VALIDATION_SESSION_OVERRIDE": False,
            "ROSS_VALIDATION_OVERRIDE": False,
            "ROSS_THRESHOLD_OVERRIDE": False,
            "ROSS_CATALYST_BYPASS": False,
            "ROSS_FLOAT_RELAXATION": False,
            "ROSS_RVOL_RELAXATION": False,
            "MANUAL_FOCUS_SYMBOLS": "",
            "SYNTHETIC_TRADE_INTENTS": "",
        },
        "broker_connection_snapshot": {
            "connected": True,
            "readonly_connection": True,
            "host": "127.0.0.1",
            "port": 7497,
            "client_id": 1038,
            "market_data_type": "IBKR_READ_ONLY",
            "account_id_redacted": "REDACTED",
            "provider_name": "PR1038_TEST_PROVIDER",
        },
        "scanner_cycle_artifact": {
            "provider_source": "READ_ONLY_OBSERVATION_FIXTURE",
            "scanner_contract": {"contract_valid": True},
            "candidate_count": 1,
            "accepted_candidate_count": 1,
            "rejected_candidate_count": 0,
            "top_n_symbols": ["PR38A"],
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
            "news_source_mode": "READ_ONLY_OBSERVATION_FIXTURE",
            "news_asof": "2026-07-02T08:00:00+00:00",
            "catalyst_status_by_symbol": {"PR38A": "CONFIRMED"},
            "fresh_news_count": 1,
            "catalyst_bypass": False,
        },
        "watchlist_focus_artifact": {
            "watchlist_k_symbols": ["PR38A"],
            "focus_m_symbols": ["PR38A"],
            "watchlist_rows": [
                {
                    "symbol": "PR38A",
                    "manual_focus": False,
                    "prep_seeded": False,
                    "execution_ineligible_if_not_focus": True,
                }
            ],
            "focus_rows": [
                {
                    "symbol": "PR38A",
                    "manual_focus": False,
                    "prep_seeded": False,
                    "synthetic_focus": False,
                }
            ],
            "manual_focus_injection": False,
            "synthetic_focus": False,
            "non_focus_execution_ineligible": True,
        },
        "pattern_input_artifact": {
            "symbol": "PR38A",
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
            "rationale_text": "READ_ONLY no-trade observation fixture.",
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
            "storage_key": "PR1038_TEST_NO_TRADE_RECORD",
            "readback_proof": True,
            "trade_plan_records": [],
            "no_trade_records": [{"symbol": "PR38A", "reason": "PATTERN_INPUT_BLOCK"}],
            "artifact_paths": ["capture_manifest.json"],
        },
        "final_verdict": {
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED": "YES",
            "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED": "YES",
            "ZERO_BROKER_ORDER_MUTATIONS": "YES",
            "EXECUTION_DISABLED": "YES",
            "remaining_blockers": ["Human review required before PAPER decision."],
            "blockers": ["Human review required before PAPER decision."],
            "operator_signature": "TEST_OP",
        },
    }


def _write_artifact_dir(source_dir: Path, artifacts: dict[str, dict] | None = None) -> None:
    for artifact_id, payload in (artifacts or _minimal_artifacts()).items():
        _write_json(source_dir / f"{artifact_id}.json", payload)


def _validate(source_dir: Path, output_dir: Path, env: dict[str, str] | None = None):
    return pr1038.validate_full_observation_bundle(
        source_dir=source_dir,
        output_dir=output_dir,
        operator="TEST_OP",
        env=env or _safe_env(),
        template_path=_TEMPLATE_PATH,
        runbook_path=_RUNBOOK_PATH,
    )


def test_pr1038_valid_no_trade_observation_bundle_hashes_and_keeps_paper_blocked(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    _write_artifact_dir(source_dir)

    manifest = _validate(source_dir, output_dir)

    assert manifest["schema_version"] == "PR1038.readonly_full_ross_strategy_observation.v1"
    assert manifest["pr1033_manifest_schema_version"] == "PR1033.readonly_broker_artifact_capture.v1"
    assert manifest["status"] == "READ_ONLY_FULL_STRATEGY_OBSERVATION_VALIDATED_PENDING_HUMAN_REVIEW"
    assert manifest["paper_ready"] == "NO"
    assert manifest["paper_readiness_gate"] == "FAIL"
    assert manifest["broker_connected_runtime_artifact_captured"] is True
    assert manifest["read_only_full_strategy_observation_captured"] is True
    assert manifest["zero_broker_order_mutations"] is True
    assert manifest["execution_disabled"] is True
    assert {row["id"] for row in manifest["artifacts"]} == set(pr1038.REQUIRED_ARTIFACT_IDS)
    assert all(row["sha256"] for row in manifest["artifacts"])
    assert (output_dir / "capture_manifest.json").exists()


def test_pr1038_aborts_for_paper_env_before_validation(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    _write_artifact_dir(source_dir)
    env = _safe_env()
    env["RUN_MODE_EFFECTIVE"] = "PAPER"

    with pytest.raises(pr1038.pr1033.CaptureValidationError, match="RUN_MODE_EFFECTIVE"):
        _validate(source_dir, output_dir, env)


def test_pr1038_aborts_for_execution_enabled_env(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    _write_artifact_dir(source_dir)
    env = _safe_env()
    env["EXECUTION_ENABLED"] = "true"

    with pytest.raises(pr1038.pr1033.CaptureValidationError, match="EXECUTION_ENABLED"):
        _validate(source_dir, output_dir, env)


def test_pr1038_aborts_for_extra_force_or_validation_override_env(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    _write_artifact_dir(source_dir)
    env = _safe_env()
    env["ROSS_VALIDATION_OVERRIDE"] = "true"

    with pytest.raises(pr1038.PR1038ValidationError, match="ROSS_VALIDATION_OVERRIDE"):
        _validate(source_dir, output_dir, env)


def test_pr1038_aborts_for_nonzero_broker_mutation_count(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts["broker_order_audit"]["submitted_orders_count"] = 1
    _write_artifact_dir(source_dir, artifacts)

    with pytest.raises(pr1038.PR1038ValidationError, match="submitted_orders_count"):
        _validate(source_dir, output_dir)


def test_pr1038_aborts_for_manual_focus(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts["watchlist_focus_artifact"]["manual_focus_injection"] = True
    _write_artifact_dir(source_dir, artifacts)

    with pytest.raises(pr1038.PR1038ValidationError, match="manual_focus"):
        _validate(source_dir, output_dir)


def test_pr1038_aborts_for_synthetic_focus_row(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts["watchlist_focus_artifact"]["focus_rows"][0]["synthetic_focus"] = True
    _write_artifact_dir(source_dir, artifacts)

    with pytest.raises(pr1038.PR1038ValidationError, match="synthetic_focus"):
        _validate(source_dir, output_dir)


def test_pr1038_aborts_for_catalyst_bypass(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts["catalyst_news_artifact"]["catalyst_bypass"] = True
    _write_artifact_dir(source_dir, artifacts)

    with pytest.raises(pr1038.PR1038ValidationError, match="catalyst bypass"):
        _validate(source_dir, output_dir)


def test_pr1038_missing_catalyst_no_trade_is_allowed(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts["catalyst_news_artifact"]["catalyst_status_by_symbol"] = {"PR38A": "DROP_NO_CATALYST"}
    artifacts["setup_decision_artifact"]["decision_verdict"] = "NO_TRADE"
    artifacts["setup_decision_artifact"]["decision_reason"] = "DROP_NO_CATALYST"
    artifacts["risk_gate_artifact"]["risk_approved"] = False
    _write_artifact_dir(source_dir, artifacts)

    manifest = _validate(source_dir, output_dir)

    assert manifest["paper_ready"] == "NO"
    assert manifest["read_only_full_strategy_observation_captured"] is True


def test_pr1038_accepted_setup_requires_confirmed_catalyst(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts["catalyst_news_artifact"]["catalyst_status_by_symbol"] = {"PR38A": "DROP_NO_CATALYST"}
    artifacts["pattern_input_artifact"]["freshness_status"] = "FRESH"
    artifacts["pattern_input_artifact"]["missing_data_action"] = "NONE"
    artifacts["setup_decision_artifact"].update(
        {
            "detected_setups": ["Micro Pullback"],
            "selected_setup": "Micro Pullback",
            "entry_model": "Break over pullback high",
            "stop_model": "Below pullback low",
            "target_model": "HOD extension target",
            "decision_verdict": "ACCEPT",
            "decision_reason": "ROSS_SETUP_ACCEPTED",
        }
    )
    artifacts["risk_gate_artifact"]["risk_gate_called"] = True
    artifacts["risk_gate_artifact"]["risk_approved"] = True
    _write_artifact_dir(source_dir, artifacts)

    with pytest.raises(pr1038.PR1038ValidationError, match="confirmed catalyst"):
        _validate(source_dir, output_dir)


def test_pr1038_accepted_setup_still_keeps_execution_disabled(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts["pattern_input_artifact"]["freshness_status"] = "FRESH"
    artifacts["pattern_input_artifact"]["missing_data_action"] = "NONE"
    artifacts["setup_decision_artifact"].update(
        {
            "detected_setups": ["Flat Top Breakout"],
            "selected_setup": "Flat Top Breakout",
            "entry_model": "Break flat-top trigger",
            "stop_model": "Below consolidation low",
            "target_model": "Measured extension",
            "decision_verdict": "ACCEPT",
            "decision_reason": "ROSS_SETUP_ACCEPTED",
        }
    )
    artifacts["risk_gate_artifact"]["risk_gate_called"] = True
    artifacts["risk_gate_artifact"]["risk_approved"] = True
    _write_artifact_dir(source_dir, artifacts)

    manifest = _validate(source_dir, output_dir)

    assert manifest["paper_ready"] == "NO"
    assert manifest["execution_disabled"] is True
    assert manifest["zero_broker_order_mutations"] is True


def test_pr1038_missing_storage_readback_requires_blocker(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts["analytics_storage_artifact"]["storage_write_count"] = 0
    artifacts["analytics_storage_artifact"]["storage_readback_count"] = 0
    artifacts["final_verdict"]["blockers"] = []
    artifacts["final_verdict"]["remaining_blockers"] = []
    _write_artifact_dir(source_dir, artifacts)

    with pytest.raises(pr1038.PR1038ValidationError, match="storage readback"):
        _validate(source_dir, output_dir)


def test_pr1038_report_keeps_scope_and_paper_blocked() -> None:
    report = _REPORT_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "PAPER_READY: NO",
        "PAPER_READINESS_GATE: FAIL",
        "READ_ONLY_FULL_STRATEGY_OBSERVATION_VALIDATOR_ADDED: YES",
        "PRODUCTION_TRADING_BEHAVIOR_CHANGED: NO",
        "TRADING_THRESHOLDS_CHANGED: NO",
        "ROSS_GATES_WEAKENED: NO",
        "PAPER_LIVE_ENABLED: NO",
        "BROKER_ORDER_MUTATION_ALLOWED: NO",
        "CI_CONNECTS_TO_IBKR: NO",
        "REAL_OPERATOR_CAPTURE_COMPLETED_BY_THIS_PR: NO",
        "Ross Momentum remains `PAPER_READY: NO`.",
    )
    forbidden_fragments = (
        "PAPER_READY: YES",
        "PAPER_READINESS_GATE: PASS",
        "PRODUCTION_TRADING_BEHAVIOR_CHANGED: YES",
        "TRADING_THRESHOLDS_CHANGED: YES",
        "ROSS_GATES_WEAKENED: YES",
        "PAPER_LIVE_ENABLED: YES",
        "BROKER_ORDER_MUTATION_ALLOWED: YES",
        "CI_CONNECTS_TO_IBKR: YES",
    )

    for fragment in required_fragments:
        assert fragment in report
    for fragment in forbidden_fragments:
        assert fragment not in report
