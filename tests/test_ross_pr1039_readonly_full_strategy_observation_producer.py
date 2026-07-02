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
    / "pr1039_readonly_full_ross_strategy_observation_producer.py"
)
_REPORT_PATH = (
    _ROOT
    / "docs"
    / "certification"
    / "PR1039_READ_ONLY_FULL_ROSS_STRATEGY_OBSERVATION_PRODUCER.md"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("pr1039_producer", _SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pr1039 = _load_script_module()


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
    }


def _produce(tmp_path: Path, spec: dict | None = None, env: dict[str, str] | None = None):
    scenario_path = None
    scenario = "valid_no_trade"
    if spec is not None:
        scenario_path = tmp_path / "observation_input.json"
        scenario_path.write_text(
            json.dumps(spec, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        scenario = "valid_no_trade"

    return pr1039.produce_and_validate_observation(
        raw_output_dir=tmp_path / "raw",
        validated_output_dir=tmp_path / "validated",
        operator="TEST_OP",
        env=env or _safe_env(),
        observation_input=scenario_path,
        scenario=scenario,
        force=True,
    )


def test_pr1039_valid_no_trade_observation_produces_pr1038_validated_bundle(tmp_path: Path) -> None:
    manifest = _produce(tmp_path)

    assert manifest["schema_version"] == "PR1038.readonly_full_ross_strategy_observation.v1"
    assert manifest["pr1039_schema_version"] == "PR1039.readonly_full_ross_strategy_observation_producer.v1"
    assert manifest["paper_ready"] == "NO"
    assert manifest["paper_readiness_gate"] == "FAIL"
    assert manifest["status"] == "READ_ONLY_FULL_STRATEGY_OBSERVATION_VALIDATED_PENDING_HUMAN_REVIEW"

    for artifact_id in pr1039.REQUIRED_ARTIFACT_IDS:
        assert (tmp_path / "raw" / f"{artifact_id}.json").exists()

    assert (tmp_path / "validated" / "capture_manifest.json").exists()


def test_pr1039_valid_accepted_setup_observation_keeps_execution_disabled(tmp_path: Path) -> None:
    manifest = pr1039.produce_and_validate_observation(
        raw_output_dir=tmp_path / "raw",
        validated_output_dir=tmp_path / "validated",
        operator="TEST_OP",
        env=_safe_env(),
        scenario="valid_accepted_setup",
        force=True,
    )

    assert manifest["paper_ready"] == "NO"
    assert manifest["execution_disabled"] is True
    assert manifest["zero_broker_order_mutations"] is True

    setup = json.loads((tmp_path / "raw" / "setup_decision_artifact.json").read_text(encoding="utf-8"))
    execution = json.loads((tmp_path / "raw" / "execution_gate_artifact.json").read_text(encoding="utf-8"))

    assert setup["decision_verdict"] == "ACCEPT"
    assert execution["execution_enabled"] is False
    assert execution["order_attempt_count"] == 0


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("RUN_MODE", "PAPER", "RUN_MODE"),
        ("RUN_MODE_EFFECTIVE", "LIVE", "RUN_MODE_EFFECTIVE"),
        ("EXECUTION_ENABLED", "true", "EXECUTION_ENABLED"),
        ("EXECUTION_ENABLED_EFFECTIVE", "true", "EXECUTION_ENABLED_EFFECTIVE"),
        ("IBKR_API_WRITE_ALLOWED", "true", "IBKR_API_WRITE_ALLOWED"),
        ("IBKR_ORDER_SUBMISSION_ENABLED", "true", "IBKR_ORDER_SUBMISSION_ENABLED"),
        ("FORCE_CLEAN_START", "true", "FORCE_CLEAN_START"),
        ("ROSS_VALIDATION_OVERRIDE_ENABLED", "true", "ROSS_VALIDATION_OVERRIDE_ENABLED"),
        ("ROSS_CATALYST_BYPASS", "true", "ROSS_CATALYST_BYPASS"),
        ("MANUAL_FOCUS_SYMBOLS", "PR39A", "MANUAL_FOCUS_SYMBOLS"),
        ("SYNTHETIC_TRADE_INTENTS", "PR39A", "SYNTHETIC_TRADE_INTENTS"),
    ],
)
def test_pr1039_rejects_unsafe_environment_flags(
    tmp_path: Path,
    key: str,
    value: str,
    expected: str,
) -> None:
    env = _safe_env()
    env[key] = value

    with pytest.raises(pr1039.PR1039ProducerError, match=expected):
        _produce(tmp_path, env=env)


def test_pr1039_rejects_catalyst_bypass_in_observation(tmp_path: Path) -> None:
    spec = pr1039.build_valid_no_trade_spec("TEST_OP")
    spec["catalyst_news_artifact"]["catalyst_bypass"] = True

    with pytest.raises(pr1039.PR1039ProducerError, match="catalyst bypass"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_manual_focus_injection(tmp_path: Path) -> None:
    spec = pr1039.build_valid_no_trade_spec("TEST_OP")
    spec["watchlist_focus_artifact"]["manual_focus_injection"] = True

    with pytest.raises(pr1039.PR1039ProducerError, match="manual_focus"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_synthetic_focus_intent(tmp_path: Path) -> None:
    spec = pr1039.build_valid_no_trade_spec("TEST_OP")
    spec["watchlist_focus_artifact"]["focus_rows"][0]["synthetic_intent"] = True

    with pytest.raises(pr1039.PR1039ProducerError, match="synthetic_intent"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_threshold_override(tmp_path: Path) -> None:
    spec = pr1039.build_valid_no_trade_spec("TEST_OP")
    spec["scanner_cycle_artifact"]["ross_policy_thresholds_used"]["threshold_override"] = True

    with pytest.raises(pr1039.PR1039ProducerError, match="threshold_override"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_accepted_setup_without_confirmed_catalyst(tmp_path: Path) -> None:
    spec = pr1039.build_valid_accepted_setup_spec("TEST_OP")
    spec["catalyst_news_artifact"]["catalyst_status_by_symbol"] = {"PR39A": "DROP_NO_CATALYST"}

    with pytest.raises(pr1039.PR1039ProducerError, match="confirmed catalyst"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_accepted_setup_with_blocked_pattern_inputs(tmp_path: Path) -> None:
    spec = pr1039.build_valid_accepted_setup_spec("TEST_OP")
    spec["pattern_input_artifact"]["missing_data_action"] = "BLOCK"

    with pytest.raises(pr1039.PR1039ProducerError, match="blocked pattern inputs"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_accepted_setup_with_stale_pattern_inputs(tmp_path: Path) -> None:
    spec = pr1039.build_valid_accepted_setup_spec("TEST_OP")
    spec["pattern_input_artifact"]["freshness_status"] = "STALE"

    with pytest.raises(pr1039.PR1039ProducerError, match="stale pattern inputs"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_forced_or_fake_risk_approval(tmp_path: Path) -> None:
    spec = pr1039.build_valid_accepted_setup_spec("TEST_OP")
    spec["risk_gate_artifact"]["risk_approval_source"] = "FORCED_APPROVAL"

    with pytest.raises(pr1039.PR1039ProducerError, match="fake or forced risk"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_accepted_setup_without_real_risk_source(tmp_path: Path) -> None:
    spec = pr1039.build_valid_accepted_setup_spec("TEST_OP")
    spec["risk_gate_artifact"]["risk_approval_source"] = "UNKNOWN"

    with pytest.raises(pr1039.PR1039ProducerError, match="real risk approval source"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_no_trade_with_risk_approved_true(tmp_path: Path) -> None:
    spec = pr1039.build_valid_no_trade_spec("TEST_OP")
    spec["risk_gate_artifact"]["risk_approved"] = True

    with pytest.raises(pr1039.PR1039ProducerError, match="no-trade observation"):
        _produce(tmp_path, spec=spec)


def test_pr1039_rejects_broker_order_mutation(tmp_path: Path) -> None:
    spec = pr1039.build_valid_no_trade_spec("TEST_OP")
    spec["broker_order_audit"]["submitted_orders_count"] = 1

    with pytest.raises(pr1039.PR1039ProducerError, match="submitted_orders_count"):
        _produce(tmp_path, spec=spec)


def test_pr1039_reuses_pr1038_validation_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    def fake_validate_full_observation_bundle(**kwargs):
        calls.append(kwargs)
        output_dir = kwargs["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        return {
            "schema_version": "PR1038.readonly_full_ross_strategy_observation.v1",
            "status": "READ_ONLY_FULL_STRATEGY_OBSERVATION_VALIDATED_PENDING_HUMAN_REVIEW",
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "execution_disabled": True,
            "zero_broker_order_mutations": True,
            "artifacts": [],
            "acceptance_gates": [],
            "blockers": ["Human review required before PAPER decision."],
        }

    monkeypatch.setattr(
        pr1039.pr1038,
        "validate_full_observation_bundle",
        fake_validate_full_observation_bundle,
    )

    manifest = pr1039.produce_and_validate_observation(
        raw_output_dir=tmp_path / "raw",
        validated_output_dir=tmp_path / "validated",
        operator="TEST_OP",
        env=_safe_env(),
        scenario="valid_no_trade",
        force=True,
    )

    assert len(calls) == 1
    assert calls[0]["source_dir"] == tmp_path / "raw"
    assert calls[0]["output_dir"] == tmp_path / "validated"
    assert manifest["schema_version"] == "PR1038.readonly_full_ross_strategy_observation.v1"
    assert manifest["pr1039_schema_version"] == "PR1039.readonly_full_ross_strategy_observation_producer.v1"


def test_pr1039_rejects_invalid_input_schema(tmp_path: Path) -> None:
    input_path = tmp_path / "observation_input.json"
    input_path.write_text(json.dumps({"schema_version": "bad"}) + "\n", encoding="utf-8")

    with pytest.raises(pr1039.PR1039ProducerError, match="schema_version"):
        pr1039.produce_and_validate_observation(
            raw_output_dir=tmp_path / "raw",
            validated_output_dir=tmp_path / "validated",
            operator="TEST_OP",
            env=_safe_env(),
            observation_input=input_path,
            force=True,
        )


def test_pr1039_report_keeps_paper_blocked_and_scope_limited() -> None:
    report = _REPORT_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "PAPER_READY: NO",
        "PAPER_READINESS_GATE: FAIL",
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
