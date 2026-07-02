from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = (
    _ROOT
    / "scripts"
    / "certification"
    / "pr1040_real_readonly_runtime_observation_adapter.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("pr1040_adapter", _SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pr1040 = _load_script_module()


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def _safe_env() -> dict[str, str]:
    return pr1040.build_safe_readonly_env({})


def _scanner_payload(*, catalyst: str = "CONFIRMED", manual_focus: bool = False) -> dict:
    catalyst_present = catalyst == "CONFIRMED"
    row = {
        "symbol": "REAL1",
        "session_label": "PRE",
        "catalyst_present": catalyst_present,
        "fresh_news_count": 1 if catalyst_present else 0,
        "news_source_mode": "REAL_RUNTIME_NEWS_PIPELINE",
        "manual_focus": manual_focus,
        "manual_focus_injected": False,
        "synthetic_focus": False,
        "synthetic_intent": False,
        "prep_seeded": False,
        "rvol": 5.4,
        "float_millions": 8.2,
        "data_quality_flags": [],
    }
    return {
        "provider_source": "IBKR",
        "symbols": ["REAL1"],
        "topn_count": 1,
        "survivors_count": 1,
        "watchlist_k_symbols": ["REAL1"],
        "focus_m_symbols": ["REAL1"],
        "watchlist_k": [row],
        "focus_m": [row],
        "watchlist_rows": [row],
        "focus_rows": [row],
        "drop_ledger": {},
        "diagnostics": {
            "scanner_contract": {
                "top_n": 1,
                "watchlist_k": 1,
                "focus_m": 1,
                "contract_valid": True,
            }
        },
    }


def _pattern_input(action: str = "BLOCK") -> dict:
    return {
        "symbol": "REAL1",
        "source": "REAL_RUNTIME_PATTERN_INPUTS",
        "timeframe_provenance": {"10s": "MISSING", "1m": "PRESENT", "5m": "PRESENT"},
        "freshness_status": "MISSING" if action == "BLOCK" else "FRESH",
        "missing_data_action": action,
        "indicator_provenance": {"ema9": "PRESENT", "vwap": "PRESENT"},
        "level_provenance": {"hod": "PRESENT"},
        "data_quality_flags": [],
        "liquidity_context": {"rvol": 5.4, "float_millions": 8.2},
        "news_context": {"catalyst_status": "CONFIRMED"},
    }


def _evidence(*, intents=None, risks=None, scanner=None, pattern_inputs=None, execution_events=None):
    scanner_payload = scanner if scanner is not None else _scanner_payload()
    watchlist_rows = scanner_payload.get("watchlist_rows", [])
    focus_rows = scanner_payload.get("focus_rows", [])
    return pr1040.RuntimeObservationEvidence(
        operator="TEST_OP",
        scenario_id="REAL_READ_ONLY_RUNTIME_OBSERVATION_TEST",
        env=_safe_env(),
        captured_at_utc="2026-07-02T12:00:00+00:00",
        scanner_payload=scanner_payload,
        focus_rows=focus_rows,
        watchlist_rows=watchlist_rows,
        pattern_input_evidence=pattern_inputs if pattern_inputs is not None else [_pattern_input()],
        pattern_summaries=[ns(symbol="REAL1", best_setup="NONE", confidence=0.0, rationale="no setup", all_patterns=[])],
        intent_records=intents or [],
        risk_decisions=risks or [],
        execution_events=execution_events or [],
        broker_before={"connected": True, "readonly_connection": True, "open_orders": [], "metadata": {"readonly": True}},
        broker_after={"connected": True, "readonly_connection": True, "open_orders": [], "metadata": {"readonly": True}},
        session_label="PRE",
        storage_write_verified=True,
        storage_readback_verified=True,
    )


def _accepted_intent(*, target_model: str | None = "HOD extension target", tags=None):
    return ns(
        symbol="REAL1",
        intent_id="RossMomentumStrategy:REAL1:MICRO_PULLBACK",
        setup_id="MICRO_PULLBACK",
        side="LONG",
        entry="Break over pullback high",
        stop="Below pullback low",
        rationale="Real READ_ONLY accepted setup observation.",
        tags=tags or [],
        metadata={"target_model": target_model, "pattern_input_source": "REAL_RUNTIME_PATTERN_INPUTS"},
    )


def _risk_allowed(*, called: bool = True):
    if not called:
        return []
    return [
        ns(
            symbol="REAL1",
            intent_id="RossMomentumStrategy:REAL1:MICRO_PULLBACK",
            decision="ALLOW_WITH_CONSTRAINTS",
            approved_quantity=1,
            block_reason="",
            rationale="READ_ONLY risk evaluated.",
            triggered_rules=["MODE_READONLY"],
        )
    ]


def test_pr1040_env_is_readonly_and_execution_disabled() -> None:
    env = _safe_env()

    pr1040.assert_safe_runtime_env(env)

    assert env["RUN_MODE"] == "READ_ONLY"
    assert env["RUN_MODE_EFFECTIVE"] == "READ_ONLY"
    assert env["EXECUTION_ENABLED"] == "false"
    assert env["EXECUTION_ENABLED_EFFECTIVE"] == "false"
    assert env["IBKR_API_WRITE_ALLOWED"] == "false"
    assert env["IBKR_ORDER_SUBMISSION_ENABLED"] == "false"


def test_pr1040_rejects_non_readonly_env() -> None:
    env = _safe_env()
    env["RUN_MODE"] = "PAPER"

    with pytest.raises(pr1040.PR1040AdapterError, match="RUN_MODE"):
        pr1040.assert_safe_runtime_env(env)


def test_pr1040_zero_broker_order_mutations_are_required() -> None:
    evidence = _evidence()
    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["execution_gate_artifact"]["execution_enabled"] is False
    assert spec["execution_gate_artifact"]["order_attempt_count"] == 0
    assert spec["broker_order_audit"]["submitted_orders_count"] == 0
    assert spec["broker_order_audit"]["open_orders_before"] == []
    assert spec["broker_order_audit"]["open_orders_after"] == []


def test_pr1040_rejects_broker_order_mutation_evidence() -> None:
    evidence = _evidence(execution_events=[ns(symbol="REAL1", action="SUBMITTED", detail="not allowed")])

    with pytest.raises(pr1040.PR1040AdapterError, match="broker order mutation"):
        pr1040.build_pr1039_observation_input(evidence)


def test_pr1040_rejects_manual_focus_readiness_proof() -> None:
    evidence = _evidence(scanner=_scanner_payload(manual_focus=True))

    with pytest.raises(pr1040.PR1040AdapterError, match="manual/synthetic focus"):
        pr1040.build_pr1039_observation_input(evidence)


def test_pr1040_rejects_synthetic_trade_intent() -> None:
    evidence = _evidence(
        intents=[_accepted_intent(tags=["SYNTHETIC_TRADE_INTENT"])],
        risks=_risk_allowed(),
        pattern_inputs=[_pattern_input(action="NONE")],
    )

    with pytest.raises(pr1040.PR1040AdapterError, match="synthetic or forced"):
        pr1040.build_pr1039_observation_input(evidence)


def test_pr1040_marks_accepted_setup_without_target_as_invalid() -> None:
    evidence = _evidence(
        intents=[_accepted_intent(target_model=None)],
        risks=_risk_allowed(),
        pattern_inputs=[_pattern_input(action="NONE")],
    )

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "READ_ONLY_OBSERVATION_INVALID"
    assert spec["final_verdict"]["READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED"] == "NO"
    assert "target model" in " ".join(spec["final_verdict"]["blockers"])


def test_pr1040_accepted_setup_requires_focused_symbol_confirmed_catalyst_and_risk_gate() -> None:
    evidence = _evidence(
        scanner=_scanner_payload(catalyst="UNAVAILABLE"),
        intents=[_accepted_intent()],
        risks=_risk_allowed(),
        pattern_inputs=[_pattern_input(action="NONE")],
    )

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "READ_ONLY_OBSERVATION_INVALID"
    assert "confirmed catalyst" in " ".join(spec["final_verdict"]["blockers"])

    missing_risk = _evidence(
        intents=[_accepted_intent()],
        risks=_risk_allowed(called=False),
        pattern_inputs=[_pattern_input(action="NONE")],
    )
    missing_risk_spec = pr1040.build_pr1039_observation_input(missing_risk)
    assert missing_risk_spec["classification"] == "READ_ONLY_OBSERVATION_INVALID"
    assert "risk gate" in " ".join(missing_risk_spec["final_verdict"]["blockers"])


def test_pr1040_no_trade_observation_can_pass_with_full_real_evidence() -> None:
    evidence = _evidence(pattern_inputs=[_pattern_input(action="BLOCK")])

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "READ_ONLY_OBSERVATION_VALID"
    assert spec["setup_decision_artifact"]["decision_verdict"] == "NO_TRADE"
    assert spec["risk_gate_artifact"]["risk_gate_called"] is False
    assert spec["risk_gate_artifact"]["risk_approved"] is False
    assert spec["final_verdict"]["READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED"] == "YES"


def test_pr1040_no_trade_without_focus_is_insufficient_evidence() -> None:
    scanner = _scanner_payload()
    scanner["focus_m_symbols"] = []
    scanner["focus_m"] = []
    scanner["focus_rows"] = []
    scanner["diagnostics"]["scanner_contract"]["focus_m"] = 0
    evidence = _evidence(scanner=scanner, pattern_inputs=[])

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "INSUFFICIENT_EVIDENCE"
    assert spec["final_verdict"]["READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED"] == "NO"
    assert "Focus M" in " ".join(spec["final_verdict"]["blockers"])
