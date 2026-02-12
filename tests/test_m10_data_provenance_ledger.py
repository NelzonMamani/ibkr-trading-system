from __future__ import annotations

import json

from src.metadata.m10_data_provenance_ledger import (
    DATA_SOURCE_REGISTRY,
    MODE_TRUTH_MATRIX,
    DataProvenanceLedger,
)


def _base_event() -> dict:
    return {
        "symbol": "AAPL",
        "data_type": "PRICE_BAR",
        "timeframe_scope": "INTRADAY",
        "timeframe_resolution": "1M",
        "source_id": "IBKR_STREAM",
        "mode": "PAPER",
        "session_state": "RTH",
        "freshness_class": "REALTIME",
        "confidence_level": "HIGH",
        "known_limitations": "",
        "checksum_or_fingerprint": "",
        "linkage": {
            "signal_ids": ["SIG-1"],
            "decision_ids": ["DEC-1"],
            "order_ids": [],
            "parent_event_ids": [],
        },
    }


def test_m10_append_only_hash_chain_and_verify(tmp_path):
    ledger = DataProvenanceLedger(tmp_path / "ledger.jsonl")
    first = ledger.append_event(_base_event())
    second_payload = _base_event()
    second_payload["data_type"] = "INDICATOR"
    second_payload["linkage"]["parent_event_ids"] = [first["event_id"]]
    second = ledger.append_event(second_payload)

    assert first["prev_event_hash"] == "GENESIS"
    assert second["prev_event_hash"] == first["event_hash"]

    result = ledger.verify()
    assert result.valid is True
    assert result.violations == []


def test_m10_requires_limitations_when_confidence_or_freshness_degraded(tmp_path):
    ledger = DataProvenanceLedger(tmp_path / "ledger.jsonl")
    bad_event = _base_event()
    bad_event["confidence_level"] = "LOW"
    bad_event["known_limitations"] = ""

    try:
        ledger.append_event(bad_event)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "known_limitations_required_when_confidence_not_high" in str(exc)


def test_m10_hydration_and_query_helpers(tmp_path):
    ledger = DataProvenanceLedger(tmp_path / "ledger.jsonl")

    ready = ledger.append_hydration_event(
        symbol="MSFT",
        mode="SIM",
        session_state="PRE",
        hydration_state="DATA_HYDRATION_READY",
        datasets_requested=["1D", "5M", "NEWS_BOOLEAN"],
        datasets_succeeded=["1D", "5M", "NEWS_BOOLEAN"],
        datasets_failed=[],
        decision_ids=["DEC-READY"],
    )
    partial = ledger.append_hydration_event(
        symbol="MSFT",
        mode="SIM",
        session_state="PRE",
        hydration_state="DATA_HYDRATION_PARTIAL",
        datasets_requested=["1D", "5M", "NEWS_BOOLEAN"],
        datasets_succeeded=["1D"],
        datasets_failed=["5M", "NEWS_BOOLEAN"],
        decision_ids=["DEC-PARTIAL"],
    )

    assert ready["confidence_level"] == "HIGH"
    assert partial["confidence_level"] == "LOW"
    assert partial["known_limitations"]

    by_symbol = ledger.query(symbol="MSFT")
    assert len(by_symbol) == 2
    by_decision = ledger.query(decision_id="DEC-READY")
    assert len(by_decision) == 1


def test_m10_registry_and_mode_truth_matrix_coverage():
    source_ids = {entry["source_id"] for entry in DATA_SOURCE_REGISTRY}
    assert {"IBKR_SNAPSHOT", "IBKR_STREAM", "HIST_BARS", "CACHE_DB", "FALLBACK_PROVIDER"}.issubset(source_ids)
    assert set(MODE_TRUTH_MATRIX) == {"SIM", "PAPER", "READ_ONLY", "LIVE"}


def test_m10_detects_tamper(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = DataProvenanceLedger(ledger_path)
    ledger.append_event(_base_event())

    rows = ledger.read_all_events()
    rows[0]["symbol"] = "EVIL"
    ledger_path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")

    result = ledger.verify()
    assert result.valid is False
    assert any("hash_mismatch" in violation for violation in result.violations)
