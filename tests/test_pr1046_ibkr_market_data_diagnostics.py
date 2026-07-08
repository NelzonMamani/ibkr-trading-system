from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


_ROOT = Path(__file__).resolve().parents[1]
_DIAGNOSTIC_PATH = _ROOT / "scripts" / "certification" / "pr1046_ibkr_market_data_diagnostics.py"
_ADAPTER_PATH = _ROOT / "scripts" / "certification" / "pr1040_real_readonly_runtime_observation_adapter.py"
_PROBE_PATH = _ROOT / "scripts" / "certification" / "pr1046_ibkr_market_data_diagnostic_probe.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pr1046 = _load_module("pr1046_ibkr_market_data_diagnostics_test", _DIAGNOSTIC_PATH)
pr1040 = _load_module("pr1040_adapter_pr1046_test", _ADAPTER_PATH)


def _quote_row(symbol: str = "REAL1", **overrides):
    row = {
        "symbol": symbol,
        "last": 12.34,
        "close": 11.25,
        "volume": 123456,
        "bid": 12.30,
        "ask": 12.35,
        "float_millions": 8.2,
        "catalyst_present": True,
        "fresh_news_count": 1,
        "news_source_mode": "REAL_RUNTIME_NEWS_PIPELINE",
        "manual_focus": False,
        "manual_focus_injected": False,
        "synthetic_focus": False,
    }
    row.update(overrides)
    return row


def _scanner(rows, *, errors=None, drop_ledger=None, focus_symbols=None):
    symbols = [row.get("symbol") for row in rows]
    focus = focus_symbols if focus_symbols is not None else symbols
    return {
        "provider_source": "IBKR",
        "symbols": symbols,
        "topn_count": len(symbols),
        "survivors_count": len(focus),
        "watchlist_k_symbols": symbols,
        "focus_m_symbols": focus,
        "candidate_metrics": rows,
        "watchlist_k": rows,
        "focus_m": [row for row in rows if row.get("symbol") in set(focus)],
        "watchlist_rows": rows,
        "focus_rows": [row for row in rows if row.get("symbol") in set(focus)],
        "drop_ledger": drop_ledger or {},
        "diagnostics": {
            "scanner_contract": {
                "top_n": len(symbols),
                "watchlist_k": len(symbols),
                "focus_m": len(focus),
                "contract_valid": True,
            },
            "ibkr_errors": errors or [],
        },
    }


def _safe_env() -> dict[str, str]:
    return pr1040.build_safe_readonly_env({})


def _evidence(scanner_payload, *, pattern_inputs=None):
    return pr1040.RuntimeObservationEvidence(
        operator="TEST_OPERATOR",
        scenario_id="PR1046_IBKR_MARKET_DATA_DIAGNOSTIC_TEST",
        env=_safe_env(),
        captured_at_utc="2026-07-08T12:00:00+00:00",
        scanner_payload=scanner_payload,
        focus_rows=scanner_payload.get("focus_rows", []),
        watchlist_rows=scanner_payload.get("watchlist_rows", []),
        pattern_input_evidence=pattern_inputs or [],
        pattern_summaries=[
            SimpleNamespace(
                symbol="REAL1",
                strategy_id="ross_momentum",
                decision_type="NO_ACTION",
                confidence=0.0,
                rationale_text="Canonical Ross strategy READ_ONLY observation.",
                risk_flags=[],
                intents=[],
            )
        ],
        intent_records=[],
        risk_decisions=[],
        execution_events=[],
        broker_before={"connected": True, "readonly_connection": True, "open_orders": [], "metadata": {"readonly": True}},
        broker_after={"connected": True, "readonly_connection": True, "open_orders": [], "metadata": {"readonly": True}},
        session_label="PRE",
        storage_write_verified=True,
        storage_readback_verified=True,
        storage_evidence_source=pr1040.REAL_STORAGE_EVIDENCE_SOURCE,
        storage_evidence_detail={"path": "analytics/runtime/proof.json"},
        operator_observation_scope=pr1040.build_operator_observation_scope(observation_symbols="REAL1,MISS1"),
    )


def test_pr1046_classifies_ibkr_10089_subscription_required() -> None:
    row = _quote_row("MISS1", last=None, close=None, volume=None, bid=None, ask=None)
    scanner = _scanner(
        [row],
        focus_symbols=[],
        drop_ledger={"DROP_MISSING_PRICE": ["MISS1"], "DATA_QUALITY_FAIL_SNAPSHOT": ["MISS1"]},
        errors=[
            {
                "code": 10089,
                "message": "Requested market data requires additional subscription for API",
                "symbol": "MISS1",
            }
        ],
    )

    diagnostic = pr1046.build_ibkr_market_data_diagnostic(scanner_payload=scanner, env=_safe_env())

    assert diagnostic["classification"] == "MARKET_DATA_SUBSCRIPTION_REQUIRED"
    assert diagnostic["observed_error_codes"] == [10089]
    assert diagnostic["symbols_by_error_code"] == {"10089": ["MISS1"]}
    assert diagnostic["paper_ready"] == "NO"
    assert diagnostic["paper_readiness_gate"] == "FAIL"


def test_pr1046_classifies_10167_delayed_unusable_when_fields_missing() -> None:
    row = _quote_row("DELAY1", last=None, close=None, volume=None, bid=None, ask=None)
    scanner = _scanner(
        [row],
        focus_symbols=[],
        drop_ledger={"DROP_MISSING_PRICE": ["DELAY1"]},
        errors=[
            {
                "errorCode": 10167,
                "message": "Requested market data is not subscribed. Displaying delayed market data",
                "symbol": "DELAY1",
            }
        ],
    )

    diagnostic = pr1046.build_ibkr_market_data_diagnostic(scanner_payload=scanner)

    assert diagnostic["classification"] == "DELAYED_DATA_AVAILABLE_BUT_UNUSABLE"
    assert diagnostic["observed_error_codes"] == [10167]
    assert diagnostic["delayed_data_observed"] is True
    assert diagnostic["snapshot_fields_missing"] is True


def test_pr1046_classifies_10167_not_subscribed_without_delayed_unusable_signature() -> None:
    scanner = _scanner(
        [_quote_row("NOSUB1")],
        errors=[
            {
                "code": 10167,
                "message": "Requested market data is not subscribed",
                "symbol": "NOSUB1",
            }
        ],
    )

    diagnostic = pr1046.build_ibkr_market_data_diagnostic(scanner_payload=scanner)

    assert diagnostic["classification"] == "MARKET_DATA_NOT_SUBSCRIBED"
    assert diagnostic["not_subscribed_observed"] is True


def test_pr1046_classifies_snapshot_timeout() -> None:
    scanner = _scanner(
        [_quote_row("TIME1", last=None, close=None, volume=None, bid=None, ask=None)],
        focus_symbols=[],
        drop_ledger={"DATA_QUALITY_FAIL_SNAPSHOT": ["TIME1"]},
    )

    diagnostic = pr1046.build_ibkr_market_data_diagnostic(scanner_payload=scanner)

    assert diagnostic["classification"] == "SNAPSHOT_TIMEOUT"
    assert diagnostic["snapshot_timeout_observed"] is True


def test_pr1046_classifies_snapshot_fields_missing_without_ibkr_error() -> None:
    scanner = _scanner([_quote_row("MISS2", close=None, ask=None)])

    diagnostic = pr1046.build_ibkr_market_data_diagnostic(scanner_payload=scanner)

    assert diagnostic["classification"] == "SNAPSHOT_FIELDS_MISSING"
    assert diagnostic["missing_fields_by_symbol"] == {"MISS2": ["close", "ask"]}


def test_pr1046_symbol_keyed_drop_ledger_counts_actual_reason() -> None:
    scanner = {
        "provider_source": "IBKR",
        "drop_ledger": {"MISS1": "DROP_MISSING_PRICE"},
        "candidate_metrics": [],
    }

    diagnostic = pr1046.build_ibkr_market_data_diagnostic(scanner_payload=scanner)

    assert diagnostic["drop_reason_counts"] == {"DROP_MISSING_PRICE": 1}
    assert diagnostic["classification"] == "SNAPSHOT_FIELDS_MISSING"
    assert diagnostic["snapshot_fields_missing"] is True


def test_pr1046_classifies_market_data_usable() -> None:
    scanner = _scanner([_quote_row("REAL1")])

    diagnostic = pr1046.build_ibkr_market_data_diagnostic(scanner_payload=scanner)

    assert diagnostic["classification"] == "MARKET_DATA_USABLE"
    assert diagnostic["symbols_with_all_required_fields"] == ["REAL1"]
    assert diagnostic["execution_enabled"] is False
    assert diagnostic["order_submission_enabled"] is False


def test_pr1046_mixed_quote_rows_are_usable_when_any_row_is_complete() -> None:
    scanner = _scanner([_quote_row("REAL1"), _quote_row("MISS2", close=None, ask=None)])

    diagnostic = pr1046.build_ibkr_market_data_diagnostic(scanner_payload=scanner)

    assert diagnostic["classification"] == "MARKET_DATA_USABLE"
    assert diagnostic["symbols_with_all_required_fields"] == ["REAL1"]
    assert diagnostic["missing_fields_by_symbol"] == {"MISS2": ["close", "ask"]}


def test_pr1046_classifies_unknown_without_evidence() -> None:
    diagnostic = pr1046.build_ibkr_market_data_diagnostic(scanner_payload={})

    assert diagnostic["classification"] == "MARKET_DATA_DIAGNOSTIC_UNKNOWN"


def test_pr1040_observation_includes_nested_ibkr_diagnostic_block() -> None:
    row = _quote_row("MISS1", last=None, close=None, volume=None, bid=None, ask=None)
    scanner = _scanner(
        [row],
        focus_symbols=[],
        drop_ledger={"DROP_MISSING_PRICE": ["MISS1"]},
        errors=[
            {
                "code": 10089,
                "message": "Requested market data requires additional subscription for API",
                "symbol": "MISS1",
            }
        ],
    )

    spec = pr1040.build_pr1039_observation_input(_evidence(scanner))
    market_data = spec["market_data_observation_diagnostics"]
    ibkr = market_data["ibkr_market_data_diagnostic"]

    assert market_data["outcome"] == "REAL_MARKET_DATA_UNUSABLE"
    assert ibkr["classification"] == "MARKET_DATA_SUBSCRIPTION_REQUIRED"
    assert ibkr["read_only_runtime"] is True
    assert ibkr["paper_ready"] == "NO"
    assert ibkr["paper_readiness_gate"] == "FAIL"
    assert spec["final_verdict"]["paper_ready"] == "NO"
    assert spec["final_verdict"]["paper_readiness_gate"] == "FAIL"
    assert spec["execution_gate_artifact"]["execution_enabled"] is False
    assert spec["broker_order_audit"]["order_attempt_count"] == 0


def test_pr1046_probe_help_is_diagnostics_only() -> None:
    result = subprocess.run(
        [sys.executable, str(_PROBE_PATH), "--help"],
        cwd=_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Run PR1046 IBKR market-data diagnostics probe" in result.stdout
    assert "--scanner-payload" in result.stdout
    assert "--observation-input" in result.stdout
    assert "--operator" in result.stdout


def test_pr1046_probe_classifies_backward_compatible_observation_without_nested_block(tmp_path) -> None:
    observation_input = tmp_path / "legacy_observation.json"
    output = tmp_path / "diagnostic.json"
    observation_input.write_text(
        json.dumps(
            {
                "scanner_cycle_artifact": {
                    "provider_source": "IBKR",
                    "top_n_symbols": ["MISS1"],
                    "drop_ledger": {"MISS1": "DROP_MISSING_PRICE"},
                },
                "market_data_observation_diagnostics": {
                    "dominant_drop_reason": "DROP_MISSING_PRICE",
                    "drop_reason_counts": {"DROP_MISSING_PRICE": 1},
                },
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(_PROBE_PATH),
            "--observation-input",
            str(observation_input),
            "--output",
            str(output),
            "--operator",
            "TEST_OPERATOR",
        ],
        cwd=_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    diagnostic = report["diagnostic"]
    assert diagnostic["classification"] == "SNAPSHOT_FIELDS_MISSING"
    assert diagnostic["drop_reason_counts"] == {"DROP_MISSING_PRICE": 1}
    assert diagnostic["paper_ready"] == "NO"
    assert diagnostic["paper_readiness_gate"] == "FAIL"
