from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = (
    _ROOT
    / "scripts"
    / "certification"
    / "pr1040_real_readonly_runtime_observation_adapter.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("pr1040_adapter_pr1045", _SCRIPT_PATH)
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


def _strategy_decision(decision_type: str = "NO_ACTION"):
    return ns(
        symbol="REAL1",
        strategy_id="ross_momentum",
        decision_type=decision_type,
        confidence=0.0,
        rationale_text="Canonical Ross strategy READ_ONLY observation.",
        risk_flags=[],
        intents=[],
    )


def _focus_row(symbol: str = "REAL1") -> dict:
    return {
        "symbol": symbol,
        "session_label": "PRE",
        "catalyst_present": True,
        "fresh_news_count": 1,
        "news_source_mode": "REAL_RUNTIME_NEWS_PIPELINE",
        "last_price": 12.34,
        "bid": 12.30,
        "ask": 12.35,
        "volume": 123456,
        "rvol": 5.4,
        "float_millions": 8.2,
        "manual_focus": False,
        "manual_focus_injected": False,
        "synthetic_focus": False,
        "prep_seeded": False,
        "data_quality_flags": [],
    }


def _scanner_payload_focus() -> dict:
    row = _focus_row()
    return {
        "provider_source": "IBKR",
        "symbols": ["REAL1"],
        "topn_count": 1,
        "survivors_count": 1,
        "watchlist_k_symbols": ["REAL1"],
        "focus_m_symbols": ["REAL1"],
        "candidate_metrics": [row],
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


def _scanner_payload_missing_price_no_focus() -> dict:
    row = {
        "symbol": "MISS1",
        "last_price": 0,
        "bid": 0,
        "ask": 0,
        "volume": 0,
        "float_millions": 8.2,
        "drop_reasons": ["DROP_MISSING_PRICE"],
    }
    return {
        "provider_source": "IBKR",
        "symbols": ["MISS1"],
        "topn_count": 1,
        "survivors_count": 0,
        "watchlist_k_symbols": [],
        "focus_m_symbols": [],
        "candidate_metrics": [row],
        "watchlist_k": [],
        "focus_m": [],
        "watchlist_rows": [],
        "focus_rows": [],
        "drop_ledger": {"DROP_MISSING_PRICE": ["MISS1"]},
        "diagnostics": {
            "scanner_contract": {
                "top_n": 1,
                "watchlist_k": 0,
                "focus_m": 0,
                "contract_valid": True,
            }
        },
    }


def _pattern_input() -> dict:
    return {
        "symbol": "REAL1",
        "source": "REAL_RUNTIME_PATTERN_INPUTS",
        "timeframe_provenance": {"10s": "PRESENT", "1m": "PRESENT", "5m": "PRESENT"},
        "freshness_status": "FRESH",
        "missing_data_action": "NONE",
        "indicator_provenance": {"ema9": "PRESENT", "vwap": "PRESENT"},
        "level_provenance": {"hod": "PRESENT"},
        "data_quality_flags": [],
        "liquidity_context": {"rvol": 5.4, "float_millions": 8.2},
        "news_context": {"catalyst_status": "CONFIRMED"},
    }


def _scope(symbols=None) -> dict:
    return pr1040.build_operator_observation_scope(
        max_observation_symbols=3,
        max_observation_seconds=7.5,
        max_snapshot_failures=2,
        observation_symbols=symbols or ["REAL1", "MISS1"],
    )


def _evidence(*, scanner=None, pattern_inputs=None, storage: bool = True, scope=None):
    scanner_payload = scanner if scanner is not None else _scanner_payload_focus()
    source = pr1040.REAL_STORAGE_EVIDENCE_SOURCE if storage else "UNAVAILABLE"
    return pr1040.RuntimeObservationEvidence(
        operator="TEST_OP",
        scenario_id="REAL_READ_ONLY_RUNTIME_OBSERVATION_PR1045_TEST",
        env=_safe_env(),
        captured_at_utc="2026-07-08T12:00:00+00:00",
        scanner_payload=scanner_payload,
        focus_rows=scanner_payload.get("focus_rows", []),
        watchlist_rows=scanner_payload.get("watchlist_rows", []),
        pattern_input_evidence=pattern_inputs if pattern_inputs is not None else [_pattern_input()],
        pattern_summaries=[_strategy_decision()],
        intent_records=[],
        risk_decisions=[],
        execution_events=[],
        broker_before={
            "connected": True,
            "readonly_connection": True,
            "open_orders": [],
            "metadata": {"readonly": True},
        },
        broker_after={
            "connected": True,
            "readonly_connection": True,
            "open_orders": [],
            "metadata": {"readonly": True},
        },
        session_label="PRE",
        storage_write_verified=storage,
        storage_readback_verified=storage,
        storage_evidence_source=source,
        storage_evidence_detail={"path": "analytics/runtime/proof.json"} if storage else {},
        operator_observation_scope=scope or _scope(),
    )


def test_pr1045_help_contains_all_runtime_cli_arguments() -> None:
    help_text = pr1040.build_arg_parser().format_help()

    assert "--max-observation-symbols" in help_text
    assert "--max-observation-seconds" in help_text
    assert "--max-snapshot-failures" in help_text
    assert "--observation-symbols" in help_text


def test_pr1045_parser_returns_values_for_all_runtime_arguments() -> None:
    args = pr1040.build_arg_parser().parse_args(
        [
            "--operator",
            "TEST_OP",
            "--max-observation-symbols",
            "4",
            "--max-observation-seconds",
            "12.5",
            "--max-snapshot-failures",
            "3",
            "--observation-symbols",
            "real1, miss1,REAL1",
        ]
    )

    assert args.max_observation_symbols == 4
    assert args.max_observation_seconds == 12.5
    assert args.max_snapshot_failures == 3
    assert args.observation_symbols == ["REAL1", "MISS1"]


def test_pr1045_observation_output_includes_operator_observation_scope() -> None:
    spec = pr1040.build_pr1039_observation_input(_evidence(scope=_scope(["REAL1"])))

    scope = spec["operator_observation_scope"]
    assert scope["scope_type"] == "OPERATOR_OBSERVATION_SCOPE_ONLY"
    assert scope["max_observation_symbols"] == 3
    assert scope["max_observation_seconds"] == 7.5
    assert scope["max_snapshot_failures"] == 2
    assert scope["observation_symbols"] == ["REAL1"]
    assert scope["manual_focus_symbols_set"] is False
    assert scope["synthetic_trade_intents_set"] is False


def test_pr1045_observation_output_includes_market_data_observation_diagnostics() -> None:
    spec = pr1040.build_pr1039_observation_input(_evidence())

    diagnostics = spec["market_data_observation_diagnostics"]
    assert set(diagnostics) >= {
        "candidate_count",
        "watchlist_k_count",
        "focus_m_count",
        "dominant_drop_reason",
        "drop_reason_counts",
        "symbols_dropped_missing_price",
        "symbols_with_snapshot_timeout",
        "symbols_with_reference_only",
        "symbols_with_valid_last_price",
        "symbols_with_valid_bid_ask",
        "symbols_with_valid_volume",
        "symbols_with_float",
        "observation_scope",
        "outcome",
    }
    assert diagnostics["candidate_count"] == 1
    assert diagnostics["watchlist_k_count"] == 1
    assert diagnostics["focus_m_count"] == 1
    assert diagnostics["symbols_with_valid_last_price"] == ["REAL1"]
    assert diagnostics["symbols_with_valid_bid_ask"] == ["REAL1"]
    assert diagnostics["symbols_with_valid_volume"] == ["REAL1"]
    assert diagnostics["symbols_with_float"] == ["REAL1"]
    assert diagnostics["outcome"] == "FOCUS_PATTERN_INPUT_CAPTURED"


def test_pr1045_observation_symbols_do_not_set_manual_or_synthetic_markers() -> None:
    env = _safe_env()
    scope = pr1040.build_operator_observation_scope(observation_symbols="real1,miss1")

    for key in pr1040.EMPTY_OR_ABSENT_ENV_KEYS:
        assert env[key] == ""
    assert scope["observation_symbols"] == ["REAL1", "MISS1"]
    assert scope["manual_focus_symbols_set"] is False
    assert scope["synthetic_trade_intents_set"] is False
    assert "MANUAL_FOCUS_SYMBOLS" not in scope
    assert "ROSS_MANUAL_FOCUS_SYMBOLS" not in scope
    assert "SYNTHETIC_TRADE_INTENTS" not in scope
    assert "ROSS_SYNTHETIC_TRADE_INTENTS" not in scope


def test_pr1045_no_focus_missing_price_is_insufficient_real_market_data_unusable() -> None:
    evidence = _evidence(scanner=_scanner_payload_missing_price_no_focus(), pattern_inputs=[], storage=True)

    spec = pr1040.build_pr1039_observation_input(evidence)

    diagnostics = spec["market_data_observation_diagnostics"]
    assert spec["classification"] == "INSUFFICIENT_EVIDENCE"
    assert diagnostics["focus_m_count"] == 0
    assert diagnostics["dominant_drop_reason"] == "DROP_MISSING_PRICE"
    assert diagnostics["symbols_dropped_missing_price"] == ["MISS1"]
    assert diagnostics["outcome"] == "REAL_MARKET_DATA_UNUSABLE"
    assert pr1040.MARKET_DATA_UNUSABLE_BLOCKER in " ".join(spec["final_verdict"]["blockers"])
    assert spec["final_verdict"]["READ_ONLY_FULL_STRATEGY_OBSERVATION_CAPTURED"] == "NO"


def test_pr1045_focus_m_zero_preserves_paper_ready_no_and_gate_fail() -> None:
    evidence = _evidence(scanner=_scanner_payload_missing_price_no_focus(), pattern_inputs=[], storage=True)

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "INSUFFICIENT_EVIDENCE"
    assert spec["final_verdict"]["paper_ready"] == "NO"
    assert spec["final_verdict"]["paper_readiness_gate"] == "FAIL"


def test_pr1045_focus_without_pattern_input_is_insufficient_evidence() -> None:
    evidence = _evidence(scanner=_scanner_payload_focus(), pattern_inputs=[], storage=True)

    spec = pr1040.build_pr1039_observation_input(evidence)

    assert spec["classification"] == "INSUFFICIENT_EVIDENCE"
    assert spec["market_data_observation_diagnostics"]["outcome"] == "NO_PATTERN_INPUT_EVIDENCE"
    assert pr1040.NO_PATTERN_INPUT_EVIDENCE_BLOCKER in " ".join(spec["final_verdict"]["blockers"])
    assert spec["final_verdict"]["paper_ready"] == "NO"
    assert spec["final_verdict"]["paper_readiness_gate"] == "FAIL"
