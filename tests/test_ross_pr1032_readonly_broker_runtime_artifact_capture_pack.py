from __future__ import annotations

import json
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_PATH = (
    _ROOT
    / "docs"
    / "certification"
    / "PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_MANIFEST.example.json"
)
_REPORT_PATH = (
    _ROOT
    / "docs"
    / "certification"
    / "PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_CAPTURE_PACK.md"
)

_REQUIRED_ARTIFACT_IDS = {
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
}


def _manifest() -> dict:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_pr1032_manifest_is_readonly_template_not_captured_evidence() -> None:
    manifest = _manifest()
    constraints = manifest["run_constraints"]

    assert manifest["schema_version"] == "PR1032.readonly_broker_runtime_artifact.v1"
    assert manifest["status"] == "TEMPLATE_NOT_CAPTURED"
    assert manifest["paper_ready"] == "NO"
    assert manifest["paper_readiness_gate"] == "FAIL"
    assert manifest["broker_connected_runtime_artifact_captured"] is False
    assert constraints["allowed_run_mode"] == "READ_ONLY"
    assert constraints["forbidden_run_modes"] == ["PAPER", "LIVE"]
    assert constraints["execution_enabled_required"] is False
    assert constraints["execution_enabled_effective_required"] is False
    assert constraints["ibkr_api_write_allowed_required"] is False
    assert constraints["ibkr_order_submission_enabled_required"] is False
    assert constraints["broker_orders_allowed_required"] is False
    assert constraints["paper_live_enablement_allowed"] is False
    assert constraints["event_replay_mode_effective_required"] == "OFF"


def test_pr1032_manifest_requires_complete_broker_runtime_artifact_bundle() -> None:
    manifest = _manifest()
    artifacts = manifest["required_artifacts"]
    ids = {artifact["id"] for artifact in artifacts}

    assert ids == _REQUIRED_ARTIFACT_IDS
    assert all(artifact["required"] is True for artifact in artifacts)
    for artifact in artifacts:
        assert artifact["minimum_fields"], artifact["id"]
        assert artifact["must_prove"], artifact["id"]

    by_id = {artifact["id"]: artifact for artifact in artifacts}
    assert "submitted_orders_count=0" in by_id["broker_order_audit"]["must_prove"]
    assert "cancelled_orders_count=0" in by_id["broker_order_audit"]["must_prove"]
    assert "modified_orders_count=0" in by_id["broker_order_audit"]["must_prove"]
    assert "order_attempt_count" in by_id["execution_gate_artifact"]["minimum_fields"]
    assert "storage_readback_count" in by_id["analytics_storage_artifact"]["minimum_fields"]
    assert "PAPER_READY=NO unless every objective gate passes" in by_id["final_verdict"]["must_prove"]


def test_pr1032_manifest_requires_redaction_hashing_and_hard_rejections() -> None:
    manifest = _manifest()
    contract = manifest["artifact_file_contract"]
    forbidden = set(manifest["forbidden_evidence"])
    gates = {gate["id"]: gate for gate in manifest["acceptance_gates"]}

    assert contract["hash_required"] is True
    assert contract["redaction_required"] is True
    assert set(contract["required_fields"]) == {
        "id",
        "path",
        "sha256",
        "captured_at_utc",
        "source",
        "redaction_status",
        "description",
    }
    assert set(contract["allowed_redaction_statuses"]) == {
        "REDACTED",
        "NO_SECRET_DATA_PRESENT",
    }
    assert gates["zero_broker_order_mutations"]["required_verdict"] == "PASS"
    assert gates["redaction_and_hashing_complete"]["required_verdict"] == "PASS"
    assert "PAPER_READY: YES" in forbidden
    assert "PAPER_READINESS_GATE: PASS" in forbidden
    assert "RUN_MODE_EFFECTIVE=PAPER" in forbidden
    assert "RUN_MODE_EFFECTIVE=LIVE" in forbidden
    assert "submitted_orders_count>0" in forbidden
    assert "unredacted account id" in forbidden


def test_pr1032_report_keeps_capture_pack_scope_and_paper_blocked() -> None:
    report = _REPORT_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "PAPER_READY: NO",
        "BROKER_CONNECTED_READ_ONLY_ARTIFACT_CAPTURE_PACK: READY_TO_RUN",
        "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED: NO",
        "BROKER_ORDER_AUDIT_CAPTURED: NO",
        "DURABLE_STORAGE_READBACK_CAPTURED: NO",
        "PAPER_READINESS_GATE: FAIL",
        "PRODUCTION_CODE_CHANGED: NO",
        "This PR does not certify that a broker-connected session has already completed.",
        "No PAPER/LIVE enablement was added.",
        "Template only",
        "Final gate result: `PAPER_READINESS_GATE: FAIL`.",
        "Ross Momentum remains `PAPER_READY: NO`.",
    )
    forbidden_fragments = (
        "PAPER_READY: YES",
        "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED: YES",
        "BROKER_ORDER_AUDIT_CAPTURED: YES",
        "DURABLE_STORAGE_READBACK_CAPTURED: YES",
        "PAPER_READINESS_GATE: PASS",
        "PAPER_LIVE_ENABLED: YES",
    )

    for fragment in required_fragments:
        assert fragment in report
    for fragment in forbidden_fragments:
        assert fragment not in report
