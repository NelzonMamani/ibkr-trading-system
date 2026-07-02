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
        "timeframe_provenance": {"10s": "PRESENT", "1m": "PRESENT", "5m": "PRESENT"},
        "freshness_status": "MISSING" if action == "BLOCK" else "FRESH",
        "missing_data_action": action,
        "indicator_provenance": {"ema9": "PRESENT", "vwap": "PRESENT"},
        "level_provenance": {"hod": "PRESENT"},
        "data_quality_flags": [],
        "liquidity_context": {"rvol": 5.4, "float_millions": 8.2},
        "news_context": {"catalyst_status": "CONFIRMED"},
    }


def _strategy_decision(decision_type: str = "NO_ACTION", intents=None):
    return ns(
        symbol="REAL1",
        strategy_id="ross_momentum",
        decision_type=decision_type,
        confidence=0.0,
        rationale_text="Canonical Ross strategy READ_ONLY observation.",
        risk_flags=[],
        intents=intents or [],
    )


def _evidence(
    *,
    intents=None,
    risks=None,
    scanner=None,
    pattern_inputs=None,
    execution_events=None,
    storage: bool = True,
    storage_source: str | None = None,
    pattern_summaries=None,
    broker_before_connected: bool = True,
    broker_after_connected: bool = True,
):
    scanner_payload = scanner if scanner is not None else _scanner_payload()
    watchlist_rows = scanner_payload.get("watchlist_rows", [])
    focus_rows = scanner_payload.get("focus_rows", [])
    source = storage_source or (pr1040.REAL_STORAGE_EVIDENCE_SOURCE if storage else "UNAVAILABLE")
    return pr1040.RuntimeObservationEvidence(
        operator="TEST_OP",
        scenario_id="REAL_READ_ONLY_RUNTIME_OBSERVATION_TEST",
        env=_safe_env(),
        captured_at_utc="2026-07-02T12:00:00+00:00",
        scanner_payload=scanner_payload,
        focus_rows=focus_rows,
        watchlist_rows=watchlist_rows,
        pattern_input_evidence=pattern_inputs if pattern_inputs is not None else [_pattern_input()],
        pattern_summaries=pattern_summaries if pattern_summaries is not None else [_strategy_decision()],
        intent_records=intents or [],
        risk_decisions=risks or [],
        execution_events=execution_events or [],
        broker_before={
            "connected": broker_before_connected,
            "readonly_connection": True,
            "open_orders": [],
            "metadata": {"readonly": True},
        },
        broker_after={
            "connected": broker_after_connected,
            "readonly_connection": True,
            "open_orders": [],
            "metadata": {"readonly": True},
        },
        session_label="PRE",
        storage_write_verified=storage,
        storage_readback_verified=storage,
        storage_evidence_source=source,
        storage_evidence_detail={"path": "analytics/runtime/proof.json"} if source == pr1040.REAL_STORAGE_EVIDENCE_SOURCE else {},
    )


def _accepted_intent(
    *,
    target_model: str | None = "HOD extension target",
    tags=None,
    decision_authority: str = pr1040.CANONICAL_DECISION_AUTHORITY,
    entry: str = "trigger=12.34",
    entry_price=12.34,
):
    return ns(
        symbol="REAL1",
        intent_id="RossMomentumStrategy:REAL1:MICRO_PULLBACK",
        setup_id="MICRO_PULLBACK",
        side="LONG",
        entry=entry,
        stop="Below pullback low",
        rationale="Real READ_ONLY accepted setup observation.",
        tags=tags or [],
        metadata={
            "target_model": target_model,
            "pattern_input_source": "REAL_RUNTIME_PATTERN_INPUTS",
            "decision_authority": decision_authority,
            "entry_price": entry_price,
            "priced_sizing_input": entry_price,
        },
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


def test_pr1040_storage_flags_without_real_source_are_insufficient() -> None:
    evidence = _evidence(storage=True, storage_source="OBSERVATION_JSON_WRITE_ONLY")

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "INSUFFICIENT_EVIDENCE"
    assert spec["analytics_storage_artifact"]["storage_write_count"] == 0
    assert spec["analytics_storage_artifact"]["storage_readback_count"] == 0
    assert spec["analytics_storage_artifact"]["readback_proof"] is False
    assert pr1040.STORAGE_EVIDENCE_UNAVAILABLE_BLOCKER in " ".join(spec["final_verdict"]["blockers"])


def test_pr1040_missing_storage_evidence_forces_insufficient_evidence() -> None:
    evidence = _evidence(storage=False)

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "INSUFFICIENT_EVIDENCE"
    assert spec["final_verdict"]["READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED"] == "NO"
    assert pr1040.STORAGE_EVIDENCE_UNAVAILABLE_BLOCKER in " ".join(spec["final_verdict"]["blockers"])


def test_pr1040_broker_after_disconnected_is_insufficient_evidence() -> None:
    evidence = _evidence(broker_before_connected=True, broker_after_connected=False)

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "INSUFFICIENT_EVIDENCE"
    assert spec["broker_connection_snapshot"]["connected"] is False
    assert spec["broker_connection_snapshot"]["broker_before_connected"] is True
    assert spec["broker_connection_snapshot"]["broker_after_connected"] is False
    assert spec["broker_connection_snapshot"]["broker_audit_complete"] is False
    assert spec["final_verdict"]["BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED"] == "NO"
    assert pr1040.BROKER_AUDIT_INCOMPLETE_BLOCKER in " ".join(spec["final_verdict"]["blockers"])


def test_pr1040_broker_before_disconnected_is_insufficient_evidence() -> None:
    evidence = _evidence(broker_before_connected=False, broker_after_connected=True)

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "INSUFFICIENT_EVIDENCE"
    assert spec["broker_connection_snapshot"]["connected"] is False
    assert spec["broker_connection_snapshot"]["broker_before_connected"] is False
    assert spec["broker_connection_snapshot"]["broker_after_connected"] is True
    assert spec["broker_order_audit"]["broker_audit_complete"] is False
    assert spec["final_verdict"]["BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED"] == "NO"
    assert pr1040.BROKER_AUDIT_INCOMPLETE_BLOCKER in " ".join(spec["final_verdict"]["blockers"])


def test_pr1040_broker_before_and_after_connected_may_proceed() -> None:
    evidence = _evidence(broker_before_connected=True, broker_after_connected=True)

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["broker_connection_snapshot"]["connected"] is True
    assert spec["broker_connection_snapshot"]["broker_audit_complete"] is True
    assert spec["final_verdict"]["BROKER_CONNECTED_RUNTIME_ARTIFACT_CAPTURED"] == "YES"
    assert spec["classification"] == "READ_ONLY_OBSERVATION_VALID"


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


def test_pr1040_rejects_accepted_setup_from_noncanonical_decision_path() -> None:
    evidence = _evidence(
        intents=[_accepted_intent(decision_authority="PatternEvaluator+build_trade_intents")],
        risks=_risk_allowed(),
        pattern_inputs=[_pattern_input(action="NONE")],
    )

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "READ_ONLY_OBSERVATION_INVALID"
    assert "canonical Ross strategy decision authority" in " ".join(spec["final_verdict"]["blockers"])


def test_pr1040_rejects_accepted_setup_missing_entry_price() -> None:
    evidence = _evidence(
        intents=[_accepted_intent(entry="Break over pullback high", entry_price=None)],
        risks=_risk_allowed(),
        pattern_inputs=[_pattern_input(action="NONE")],
    )

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "READ_ONLY_OBSERVATION_INVALID"
    assert spec["setup_decision_artifact"]["priced_intent"] is False
    assert pr1040.PRICED_INTENT_BLOCKER in " ".join(spec["final_verdict"]["blockers"])


def test_pr1040_rejects_accepted_setup_non_numeric_entry_price() -> None:
    evidence = _evidence(
        intents=[_accepted_intent(entry="entry=market_when_ready", entry_price="not-a-number")],
        risks=_risk_allowed(),
        pattern_inputs=[_pattern_input(action="NONE")],
    )

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "READ_ONLY_OBSERVATION_INVALID"
    assert spec["setup_decision_artifact"]["entry_price"] is None
    assert pr1040.PRICED_INTENT_BLOCKER in " ".join(spec["final_verdict"]["blockers"])


def test_pr1040_accepted_setup_with_numeric_entry_price_can_pass_all_gates() -> None:
    evidence = _evidence(
        intents=[_accepted_intent(entry="trigger=12.34", entry_price=12.34)],
        risks=_risk_allowed(),
        pattern_inputs=[_pattern_input(action="NONE")],
        storage=True,
        broker_before_connected=True,
        broker_after_connected=True,
    )

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "READ_ONLY_OBSERVATION_VALID"
    assert spec["setup_decision_artifact"]["decision_verdict"] == "ACCEPT"
    assert spec["setup_decision_artifact"]["decision_authority"] == pr1040.CANONICAL_DECISION_AUTHORITY
    assert spec["setup_decision_artifact"]["entry_price"] == 12.34
    assert spec["setup_decision_artifact"]["priced_intent"] is True
    assert spec["risk_gate_artifact"]["risk_gate_called"] is True
    assert spec["risk_gate_artifact"]["risk_approved"] is True
    assert spec["execution_gate_artifact"]["execution_enabled"] is False
    assert spec["broker_order_audit"]["submitted_orders_count"] == 0
    assert spec["analytics_storage_artifact"]["storage_evidence_source"] == pr1040.REAL_STORAGE_EVIDENCE_SOURCE


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
    evidence = _evidence(pattern_inputs=[_pattern_input(action="NONE")])

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "READ_ONLY_OBSERVATION_VALID"
    assert spec["setup_decision_artifact"]["decision_verdict"] == "NO_TRADE"
    assert spec["setup_decision_artifact"]["decision_authority"] == pr1040.CANONICAL_DECISION_AUTHORITY
    assert spec["analytics_storage_artifact"]["storage_evidence_source"] == pr1040.REAL_STORAGE_EVIDENCE_SOURCE
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


def test_pr1040_paper_ready_remains_no_and_gate_fail() -> None:
    spec = pr1040.build_pr1039_observation_input(_evidence())

    assert spec["final_verdict"]["paper_ready"] == "NO"
    assert spec["final_verdict"]["paper_readiness_gate"] == "FAIL"
