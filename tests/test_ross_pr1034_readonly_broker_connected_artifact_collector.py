from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _ROOT / "scripts" / "certification" / "pr1034_readonly_broker_connected_artifact_collector.py"
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
    / "PR1034_READ_ONLY_BROKER_CONNECTED_ARTIFACT_COLLECTOR.md"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("pr1034_collector", _SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pr1034 = _load_script_module()


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
    }


def _broker_snapshot(**overrides):
    snapshot = {
        "provider_name": "PR1034_TEST_PROVIDER",
        "connected": True,
        "host": "127.0.0.1",
        "port": 7497,
        "client_id": 1034,
        "market_data_type": "TEST_READ_ONLY",
        "account_id_redacted": "REDACTED",
        "submitted_orders_count": 0,
        "cancelled_orders_count": 0,
        "modified_orders_count": 0,
        "open_orders_before": [],
        "open_orders_after": [],
    }
    snapshot.update(overrides)
    return snapshot


class ScriptedReadOnlyProvider:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.connect_calls = 0
        self.collect_calls = 0
        self.disconnect_calls = 0
        self.connected = False

    def connect_readonly(self):
        self.connect_calls += 1
        self.connected = True

    def collect_snapshot(self):
        assert self.connected is True
        self.collect_calls += 1
        return dict(self.snapshot)

    def disconnect(self):
        self.disconnect_calls += 1
        self.connected = False


def test_pr1034_collector_writes_raw_and_validated_readonly_bundle(tmp_path: Path) -> None:
    provider = ScriptedReadOnlyProvider(_broker_snapshot())
    raw_dir = tmp_path / "raw"
    validated_dir = tmp_path / "validated"

    manifest = pr1034.collect_with_provider(
        provider=provider,
        raw_output_dir=raw_dir,
        validated_output_dir=validated_dir,
        operator="TEST_OP",
        template_path=_TEMPLATE_PATH,
        runbook_path=_RUNBOOK_PATH,
        env=_safe_env(),
    )

    assert provider.connect_calls == 1
    assert provider.collect_calls == 1
    assert provider.disconnect_calls == 1
    assert manifest["schema_version"] == "PR1033.readonly_broker_artifact_capture.v1"
    assert manifest["status"] == "CAPTURE_BUNDLE_VALIDATED_PENDING_HUMAN_REVIEW"
    assert manifest["paper_ready"] == "NO"
    assert manifest["paper_readiness_gate"] == "FAIL"
    assert manifest["broker_connected_runtime_artifact_captured"] is True
    assert len(manifest["artifacts"]) == len(pr1034.pr1033.REQUIRED_ARTIFACT_IDS)
    assert (raw_dir / "pr1034_collector_manifest.json").exists()
    assert (validated_dir / "capture_manifest.json").exists()

    raw_broker = json.loads((raw_dir / "broker_connection_snapshot.json").read_text(encoding="utf-8"))
    raw_final = json.loads((raw_dir / "final_verdict.json").read_text(encoding="utf-8"))
    validated_execution = json.loads((validated_dir / "execution_gate_artifact.json").read_text(encoding="utf-8"))
    assert raw_broker["connected"] is True
    assert raw_broker["readonly_connection"] is True
    assert raw_broker["collector_schema_version"] == "PR1034.readonly_broker_connected_artifact_collector.v1"
    assert raw_final["paper_ready"] == "NO"
    assert raw_final["paper_readiness_gate"] == "FAIL"
    assert "broker connection and zero-order audit shell" in raw_final["blockers"][0]
    assert validated_execution["execution_enabled"] is False
    assert validated_execution["order_attempt_count"] == 0


def test_pr1034_collector_aborts_before_connect_for_unsafe_env(tmp_path: Path) -> None:
    provider = ScriptedReadOnlyProvider(_broker_snapshot())
    unsafe_env = _safe_env()
    unsafe_env["RUN_MODE_EFFECTIVE"] = "PAPER"

    with pytest.raises(pr1034.pr1033.CaptureValidationError, match="RUN_MODE_EFFECTIVE"):
        pr1034.collect_with_provider(
            provider=provider,
            raw_output_dir=tmp_path / "raw",
            validated_output_dir=tmp_path / "validated",
            operator="TEST_OP",
            template_path=_TEMPLATE_PATH,
            runbook_path=_RUNBOOK_PATH,
            env=unsafe_env,
        )

    assert provider.connect_calls == 0
    assert provider.collect_calls == 0
    assert provider.disconnect_calls == 0


def test_pr1034_collector_rejects_nonzero_order_mutation_counts(tmp_path: Path) -> None:
    provider = ScriptedReadOnlyProvider(_broker_snapshot(submitted_orders_count=1))

    with pytest.raises(pr1034.CollectorValidationError, match="submitted_orders_count"):
        pr1034.collect_with_provider(
            provider=provider,
            raw_output_dir=tmp_path / "raw",
            validated_output_dir=tmp_path / "validated",
            operator="TEST_OP",
            template_path=_TEMPLATE_PATH,
            runbook_path=_RUNBOOK_PATH,
            env=_safe_env(),
        )

    assert provider.connect_calls == 1
    assert provider.collect_calls == 1
    assert provider.disconnect_calls == 1


def test_pr1034_collector_rejects_open_order_snapshot_change(tmp_path: Path) -> None:
    provider = ScriptedReadOnlyProvider(
        _broker_snapshot(open_orders_before=[], open_orders_after=[{"order_id": "1"}])
    )

    with pytest.raises(pr1034.CollectorValidationError, match="open order snapshot changed"):
        pr1034.collect_with_provider(
            provider=provider,
            raw_output_dir=tmp_path / "raw",
            validated_output_dir=tmp_path / "validated",
            operator="TEST_OP",
            template_path=_TEMPLATE_PATH,
            runbook_path=_RUNBOOK_PATH,
            env=_safe_env(),
        )

    assert provider.disconnect_calls == 1


def test_pr1034_cli_refuses_without_explicit_broker_connect_flag(tmp_path: Path) -> None:
    result = pr1034.main(
        [
            "--raw-output-dir",
            str(tmp_path / "raw"),
            "--validated-output-dir",
            str(tmp_path / "validated"),
            "--operator",
            "TEST_OP",
        ]
    )

    assert result == 2


def test_pr1034_runbook_lists_broker_collector_command() -> None:
    runbook = _RUNBOOK_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "## PR1034 READ_ONLY Broker-Connected Collector Command",
        ".\\.venv\\Scripts\\python.exe scripts\\certification\\pr1034_readonly_broker_connected_artifact_collector.py `",
        "--connect-ibkr-readonly `",
        "--raw-output-dir artifacts\\certification\\pr1034\\raw_readonly_broker_collect `",
        "--validated-output-dir artifacts\\certification\\pr1034\\validated_readonly_broker_collect `",
        "--operator NELZON `",
        "--host 127.0.0.1 `",
        "--port 7497 `",
        "--client-id 1034",
        "PR1034 collector output is not PAPER readiness evidence by itself.",
    )

    for fragment in required_fragments:
        assert fragment in runbook


def test_pr1034_report_keeps_scope_and_paper_blocked() -> None:
    report = _REPORT_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "PAPER_READY: NO",
        "READ_ONLY_BROKER_CONNECTED_ARTIFACT_COLLECTOR: ADDED",
        "CI_CONNECTS_TO_IBKR: NO",
        "SCRIPT_SUBMITS_ORDERS: NO",
        "SCRIPT_CANCELS_OR_MODIFIES_ORDERS: NO",
        "SCRIPT_FLATTENS_POSITIONS: NO",
        "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: NO",
        "PAPER_LIVE_ENABLED: NO",
        "PAPER_READINESS_GATE: FAIL",
        "broker connection and zero-order audit shell",
        "Ross Momentum remains `PAPER_READY: NO`.",
    )
    forbidden_fragments = (
        "PAPER_READY: YES",
        "CI_CONNECTS_TO_IBKR: YES",
        "SCRIPT_SUBMITS_ORDERS: YES",
        "SCRIPT_CANCELS_OR_MODIFIES_ORDERS: YES",
        "SCRIPT_FLATTENS_POSITIONS: YES",
        "BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED_BY_THIS_PR: YES",
        "PAPER_LIVE_ENABLED: YES",
        "PAPER_READINESS_GATE: PASS",
    )

    for fragment in required_fragments:
        assert fragment in report
    for fragment in forbidden_fragments:
        assert fragment not in report
