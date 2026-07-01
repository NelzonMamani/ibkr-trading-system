from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _ROOT / "scripts" / "certification" / "pr1033_readonly_broker_artifact_capture.py"
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
    / "PR1033_READ_ONLY_BROKER_ARTIFACT_CAPTURE_SCRIPT.md"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("pr1033_capture", _SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pr1033 = _load_script_module()


def _safe_env() -> dict[str, str]:
    return {
        "RUN_MODE": "READ_ONLY",
        "RUN_MODE_EFFECTIVE": "READ_ONLY",
        "EXECUTION_ENABLED": "false",
        "EXECUTION_ENABLED_EFFECTIVE": "false",
        "EVENT_REPLAY_MODE_EFFECTIVE": "OFF",
        "IBKR_API_WRITE_ALLOWED": "false",
        "IBKR_ORDER_SUBMISSION_ENABLED": "false",
        "FORCE_CLEAN_START": "false",
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _minimal_artifacts() -> dict[str, dict]:
    return {
        "operator_runbook_acknowledgement": {
            "runbook_path": "docs/certification/PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md",
            "operator": "TEST_OP",
            "acknowledged_at_utc": "2026-07-01T12:00:00+00:00",
            "pre_run_checklist_status": "PASS",
            "abort_conditions_reviewed": True,
            "paper_ready": "NO",
        },
        "runtime_config_snapshot": {
            "RUN_MODE": "READ_ONLY",
            "RUN_MODE_EFFECTIVE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "EXECUTION_ENABLED_EFFECTIVE": False,
            "EVENT_REPLAY_MODE_EFFECTIVE": "OFF",
            "IBKR_API_WRITE_ALLOWED": False,
            "IBKR_ORDER_SUBMISSION_ENABLED": False,
            "FORCE_CLEAN_START": False,
        },
        "broker_connection_snapshot": {
            "connected": True,
            "host": "127.0.0.1",
            "port": 7497,
            "client_id": 7,
            "market_data_type": "LIVE",
            "account_id_redacted": "REDACTED",
            "account_id": "DU1234567",
            "api_token": "secret-token-for-redaction-test",
        },
        "scanner_cycle_artifact": {
            "provider_source": "IBKR_READ_ONLY",
            "scanner_contract": {"contract_valid": True},
            "top_n_symbols": ["PR33A"],
            "drop_ledger": {},
            "selection_spec": {"ranking_intent": "ROSS_MOMENTUM_STOCK_SELECTION"},
        },
        "catalyst_news_artifact": {
            "news_source_mode": "broker_readonly_capture",
            "news_asof": "2026-07-01T12:00:00+00:00",
            "catalyst_status_by_symbol": {"PR33A": "CONFIRMED"},
            "fresh_news_count": 1,
        },
        "watchlist_focus_artifact": {
            "watchlist_k_symbols": ["PR33A"],
            "focus_m_symbols": ["PR33A"],
            "watchlist_rows": [{"symbol": "PR33A", "manual_focus": False, "prep_seeded": False}],
            "focus_rows": [{"symbol": "PR33A", "manual_focus": False, "prep_seeded": False}],
        },
        "pattern_input_artifact": {
            "symbol": "PR33A",
            "timeframe_provenance": {"10s": "FRESH", "1m": "FRESH"},
            "data_quality_flags": [],
            "liquidity_context": {"rvol": 6.2, "float_millions": 7.0},
            "news_context": {"catalyst_status": "CONFIRMED"},
        },
        "setup_decision_artifact": {
            "detected_setups": ["Micro Pullback"],
            "selected_setup": "Micro Pullback",
            "entry_model": "Break over mapped trigger",
            "stop_model": "Below pullback low",
            "target_model": "HOD extension target model",
            "rationale_text": "READ_ONLY artifact capture fixture.",
            "decision_reason": "READ_ONLY_NORMAL_DECISION_PATH",
        },
        "risk_gate_artifact": {
            "risk_gate_called": True,
            "risk_approved": True,
            "risk_reason": "READ_ONLY_RISK_CAPTURED",
            "risk_profile": "NORMAL",
        },
        "execution_gate_artifact": {
            "execution_enabled": False,
            "order_submission_enabled": False,
            "api_write_allowed": False,
            "execution_path": "READ_ONLY_ORDER_BLOCKED",
            "order_attempt_count": 0,
        },
        "broker_order_audit": {
            "submitted_orders_count": 0,
            "cancelled_orders_count": 0,
            "modified_orders_count": 0,
            "open_orders_before": [],
            "open_orders_after": [],
        },
        "analytics_storage_artifact": {
            "storage_write_count": 2,
            "storage_readback_count": 2,
            "trade_plan_records": [{"symbol": "PR33A", "target_model": "HOD extension target model"}],
            "no_trade_records": [],
            "artifact_paths": ["trade_plan_records.json", "capture_manifest.json"],
        },
        "final_verdict": {
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "blockers": ["Human review required"],
            "operator_signature": "TEST_OP",
        },
    }


def _write_artifact_dir(source_dir: Path, artifacts: dict[str, dict] | None = None) -> None:
    for artifact_id, payload in (artifacts or _minimal_artifacts()).items():
        _write_json(source_dir / f"{artifact_id}.json", payload)


def test_pr1033_capture_script_assembles_hashes_and_redacts_bundle(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    _write_artifact_dir(source_dir)

    manifest = pr1033.capture_bundle(
        source_dir=source_dir,
        output_dir=output_dir,
        operator="TEST_OP",
        template_path=_TEMPLATE_PATH,
        runbook_path=_RUNBOOK_PATH,
        env=_safe_env(),
    )

    assert manifest["schema_version"] == "PR1033.readonly_broker_artifact_capture.v1"
    assert manifest["source_schema_version"] == "PR1032.readonly_broker_runtime_artifact.v1"
    assert manifest["status"] == "CAPTURE_BUNDLE_VALIDATED_PENDING_HUMAN_REVIEW"
    assert manifest["paper_ready"] == "NO"
    assert manifest["paper_readiness_gate"] == "FAIL"
    assert manifest["broker_connected_runtime_artifact_captured"] is True
    assert len(manifest["artifacts"]) == len(pr1033.REQUIRED_ARTIFACT_IDS)
    assert {row["id"] for row in manifest["artifacts"]} == set(pr1033.REQUIRED_ARTIFACT_IDS)
    assert all(row["sha256"] for row in manifest["artifacts"])
    assert (output_dir / "capture_manifest.json").exists()

    broker_snapshot = json.loads((output_dir / "broker_connection_snapshot.json").read_text(encoding="utf-8"))
    assert broker_snapshot["account_id"] == "REDACTED"
    assert broker_snapshot["api_token"] == "REDACTED"
    broker_row = next(row for row in manifest["artifacts"] if row["id"] == "broker_connection_snapshot")
    assert broker_row["redaction_status"] == "REDACTED"
    assert broker_row["sha256"] == pr1033.sha256_file(output_dir / broker_row["path"])


def test_pr1033_capture_script_aborts_for_unsafe_runtime_env(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    _write_artifact_dir(source_dir)
    unsafe_env = _safe_env()
    unsafe_env["RUN_MODE_EFFECTIVE"] = "PAPER"

    with pytest.raises(pr1033.CaptureValidationError, match="RUN_MODE_EFFECTIVE"):
        pr1033.capture_bundle(
            source_dir=source_dir,
            output_dir=output_dir,
            operator="TEST_OP",
            template_path=_TEMPLATE_PATH,
            runbook_path=_RUNBOOK_PATH,
            env=unsafe_env,
        )


def test_pr1033_capture_script_aborts_for_missing_required_artifact(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts.pop("broker_order_audit")
    _write_artifact_dir(source_dir, artifacts)

    with pytest.raises(pr1033.CaptureValidationError, match="broker_order_audit"):
        pr1033.capture_bundle(
            source_dir=source_dir,
            output_dir=output_dir,
            operator="TEST_OP",
            template_path=_TEMPLATE_PATH,
            runbook_path=_RUNBOOK_PATH,
            env=_safe_env(),
        )


def test_pr1033_capture_script_aborts_for_nonzero_broker_order_mutation(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "validated"
    artifacts = _minimal_artifacts()
    artifacts["broker_order_audit"]["submitted_orders_count"] = 1
    _write_artifact_dir(source_dir, artifacts)

    with pytest.raises(pr1033.CaptureValidationError, match="submitted_orders_count"):
        pr1033.capture_bundle(
            source_dir=source_dir,
            output_dir=output_dir,
            operator="TEST_OP",
            template_path=_TEMPLATE_PATH,
            runbook_path=_RUNBOOK_PATH,
            env=_safe_env(),
        )


def test_pr1033_report_keeps_script_scope_and_paper_blocked() -> None:
    report = _REPORT_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "PAPER_READY: NO",
        "READ_ONLY_BROKER_ARTIFACT_CAPTURE_SCRIPT: ADDED",
        "SCRIPT_CONNECTS_TO_BROKER: NO",
        "SCRIPT_SUBMITS_ORDERS: NO",
        "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: NO",
        "PRODUCTION_TRADING_CODE_CHANGED: NO",
        "PAPER_LIVE_ENABLED: NO",
        "PAPER_READINESS_GATE: FAIL",
        "offline READ_ONLY broker artifact capture tooling",
        "Ross Momentum remains `PAPER_READY: NO`.",
    )
    forbidden_fragments = (
        "PAPER_READY: YES",
        "SCRIPT_CONNECTS_TO_BROKER: YES",
        "SCRIPT_SUBMITS_ORDERS: YES",
        "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: YES",
        "PAPER_LIVE_ENABLED: YES",
        "PAPER_READINESS_GATE: PASS",
    )

    for fragment in required_fragments:
        assert fragment in report
    for fragment in forbidden_fragments:
        assert fragment not in report
