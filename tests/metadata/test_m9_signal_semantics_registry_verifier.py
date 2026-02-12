from __future__ import annotations

import json
from pathlib import Path

from src.metadata.m9_signal_semantics_registry_verifier import REGISTRY_REL, verify_m9_signal_semantics_registry


def _write_registry(repo_root: Path, payload: dict | str) -> None:
    path = repo_root / REGISTRY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
        return
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _valid_registry() -> dict:
    return {
        "epoch": "M9_SIGNAL_SEMANTICS_REGISTRY",
        "version": "1.0",
        "signals": [
            {
                "name": "ENTRY_TRIGGER",
                "class": "TRIGGER",
                "timeframe": "INTRADAY",
                "description": "Entry trigger signal.",
                "payload_schema": {"symbol": "string", "price": "float"},
                "producer_strategies": ["P01_ROSS_MOMENTUM"],
                "lifecycle": {"ttl_seconds": 120},
                "compatibility": {"introduced": "2026-02-12", "deprecated": None},
            }
        ],
    }


def test_valid_registry_passes(tmp_path: Path) -> None:
    _write_registry(tmp_path, _valid_registry())

    result = verify_m9_signal_semantics_registry(tmp_path)

    assert result["valid"]
    assert result["violations"] == []


def test_duplicate_signal_names_fails(tmp_path: Path) -> None:
    payload = _valid_registry()
    payload["signals"].append(dict(payload["signals"][0]))
    _write_registry(tmp_path, payload)

    result = verify_m9_signal_semantics_registry(tmp_path)

    assert not result["valid"]
    assert any(v["check"] == "SIGNAL_NAMES_UNIQUE" for v in result["violations"])


def test_missing_required_field_fails(tmp_path: Path) -> None:
    payload = _valid_registry()
    payload["signals"][0].pop("description")
    _write_registry(tmp_path, payload)

    result = verify_m9_signal_semantics_registry(tmp_path)

    assert not result["valid"]
    assert any(v["check"] == "SIGNAL_FIELDS_PRESENT" for v in result["violations"])


def test_invalid_enum_value_fails(tmp_path: Path) -> None:
    payload = _valid_registry()
    payload["signals"][0]["timeframe"] = "WEEKLY"
    _write_registry(tmp_path, payload)

    result = verify_m9_signal_semantics_registry(tmp_path)

    assert not result["valid"]
    assert any(v["check"] == "SIGNAL_ENUM_FIELDS_VALID" for v in result["violations"])


def test_invalid_json_fails(tmp_path: Path) -> None:
    _write_registry(tmp_path, "{not-json")

    result = verify_m9_signal_semantics_registry(tmp_path)

    assert not result["valid"]
    assert any(v["check"] == "REGISTRY_JSON_VALID" for v in result["violations"])
