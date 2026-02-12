from __future__ import annotations

import json
from pathlib import Path

from src.metadata.m10_data_provenance_ledger import (
    DATA_SOURCE_REGISTRY_REL,
    HYDRATION_EVENT_TEMPLATE_REL,
    MODE_TRUTH_MATRIX_REL,
    PROVENANCE_EVENT_SCHEMA_REL,
    verify_m10_data_provenance_ledger,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _valid_source_registry() -> dict:
    return {
        "sources": [
            {
                "source_id": "IBKR_STREAM",
                "source_class": "PRIMARY",
                "expected_latency": "REALTIME",
                "availability_constraints": ["subscriptions", "market_hours"],
            }
        ]
    }


def _valid_mode_truth() -> dict:
    return {
        "modes": {
            "SIM": {"expected_sources": ["HIST_BARS"], "expected_latency": "DELAYED", "allowed_fallbacks": ["SYNTHETIC"]},
            "PAPER": {"expected_sources": ["IBKR_SNAPSHOT"], "expected_latency": "DELAYED", "allowed_fallbacks": ["CACHE_DB"]},
            "READ_ONLY": {"expected_sources": ["IBKR_STREAM"], "expected_latency": "REALTIME", "allowed_fallbacks": ["IBKR_SNAPSHOT"]},
            "LIVE": {"expected_sources": ["IBKR_STREAM"], "expected_latency": "REALTIME", "allowed_fallbacks": ["IBKR_SNAPSHOT"]},
        }
    }


def _valid_event_schema() -> dict:
    return {
        "required_fields": [
            "event_id",
            "symbol",
            "data_type",
            "timeframe_scope",
            "timeframe_resolution",
            "source_id",
            "mode",
            "session_state",
            "timestamp_observed",
            "timestamp_used",
            "freshness_class",
            "confidence_level",
            "known_limitations",
            "checksum_or_fingerprint",
            "linkage",
        ]
    }


def _valid_hydration_template() -> dict:
    return {
        "hydration_events": [
            {"event_name": "SYMBOL_COMMITTED"},
            {"event_name": "DATA_HYDRATION_REQUESTED"},
            {"event_name": "DATA_HYDRATION_PARTIAL"},
            {"event_name": "DATA_HYDRATION_READY"},
            {"event_name": "DATA_SOURCE_DEGRADED"},
            {"event_name": "DATA_STALE"},
        ]
    }


def _write_all_valid(repo_root: Path) -> None:
    _write_json(repo_root / DATA_SOURCE_REGISTRY_REL, _valid_source_registry())
    _write_json(repo_root / MODE_TRUTH_MATRIX_REL, _valid_mode_truth())
    _write_json(repo_root / PROVENANCE_EVENT_SCHEMA_REL, _valid_event_schema())
    _write_json(repo_root / HYDRATION_EVENT_TEMPLATE_REL, _valid_hydration_template())


def test_missing_files_fail(tmp_path: Path) -> None:
    (tmp_path / "TRADING_OS_MASTER_CATALOGUE").mkdir(parents=True, exist_ok=True)
    result = verify_m10_data_provenance_ledger(tmp_path)
    assert not result["valid"]
    assert any(v["check"] == "DATA_SOURCE_REGISTRY_FILE_EXISTS" for v in result["violations"])


def test_mode_truth_requires_all_modes(tmp_path: Path) -> None:
    _write_json(tmp_path / DATA_SOURCE_REGISTRY_REL, _valid_source_registry())
    _write_json(
        tmp_path / MODE_TRUTH_MATRIX_REL,
        {"modes": {"SIM": {"expected_sources": [], "expected_latency": "DELAYED", "allowed_fallbacks": []}}},
    )
    _write_json(tmp_path / PROVENANCE_EVENT_SCHEMA_REL, _valid_event_schema())
    _write_json(tmp_path / HYDRATION_EVENT_TEMPLATE_REL, _valid_hydration_template())

    result = verify_m10_data_provenance_ledger(tmp_path)

    assert not result["valid"]
    assert any(v["check"] == "MODE_TRUTH_MATRIX_REQUIRED_MODES" for v in result["violations"])


def test_hydration_template_requires_control_plane_events(tmp_path: Path) -> None:
    _write_json(tmp_path / DATA_SOURCE_REGISTRY_REL, _valid_source_registry())
    _write_json(tmp_path / MODE_TRUTH_MATRIX_REL, _valid_mode_truth())
    _write_json(tmp_path / PROVENANCE_EVENT_SCHEMA_REL, _valid_event_schema())
    _write_json(tmp_path / HYDRATION_EVENT_TEMPLATE_REL, {"hydration_events": [{"event_name": "SYMBOL_COMMITTED"}]})

    result = verify_m10_data_provenance_ledger(tmp_path)

    assert not result["valid"]
    assert any(v["check"] == "HYDRATION_TEMPLATE_REQUIRED_EVENTS" for v in result["violations"])


def test_valid_payload_passes(tmp_path: Path) -> None:
    _write_all_valid(tmp_path)
    result = verify_m10_data_provenance_ledger(tmp_path)
    assert result["valid"]
    assert result["violations"] == []
