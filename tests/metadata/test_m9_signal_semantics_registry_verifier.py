from __future__ import annotations

import json
from pathlib import Path

from src.metadata.m9_signal_semantics_registry_verifier import REGISTRY_FILE_REL, verify_m9_signal_semantics_registry


def _bootstrap_repo_root(tmp_path: Path) -> None:
    (tmp_path / "TRADING_OS_MASTER_CATALOGUE").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/strategies/mock_strategy.py").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/strategies/mock_strategy.py").write_text(
        "class Mock:\n    strategy_name = \"SignalEngineV1\"\n", encoding="utf-8"
    )


def _write(path: Path, payload: dict | list | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
        return
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _valid_payload() -> dict:
    return {
        "epoch": "M9_SIGNAL_SEMANTICS_REGISTRY",
        "version": "1.0.0",
        "signals": [
            {
                "name": "HOD_BREAK",
                "signal_type": "HOD_BREAK",
                "signal_class": "S2_TRIGGER",
                "timeframe": "1M",
                "producer_strategies": ["SignalEngineV1"],
                "description": "d",
                "payload_schema": {
                    "type": "object",
                    "required": ["symbol"],
                    "properties": {"symbol": {"type": "string"}},
                },
            }
        ],
    }


def test_missing_registry_file_is_reported(tmp_path: Path) -> None:
    _bootstrap_repo_root(tmp_path)
    result = verify_m9_signal_semantics_registry(tmp_path)
    assert result["valid"] is False
    assert any(v["check"] == "REGISTRY_FILE_EXISTS" for v in result["violations"])


def test_invalid_registry_json_is_reported(tmp_path: Path) -> None:
    _bootstrap_repo_root(tmp_path)
    _write(tmp_path / REGISTRY_FILE_REL, "{")
    result = verify_m9_signal_semantics_registry(tmp_path)
    assert result["valid"] is False
    assert any(v["check"] == "REGISTRY_JSON_SYNTAX" for v in result["violations"])


def test_missing_required_field_is_reported(tmp_path: Path) -> None:
    _bootstrap_repo_root(tmp_path)
    payload = _valid_payload()
    del payload["signals"][0]["timeframe"]
    _write(tmp_path / REGISTRY_FILE_REL, payload)
    result = verify_m9_signal_semantics_registry(tmp_path)
    assert result["valid"] is False
    assert any(v["check"] == "REGISTRY_SIGNAL_REQUIRED_FIELD" for v in result["violations"])


def test_invalid_enum_and_duplicates_are_reported(tmp_path: Path) -> None:
    _bootstrap_repo_root(tmp_path)
    payload = _valid_payload()
    payload["signals"][0]["signal_class"] = "BAD"
    payload["signals"][0]["timeframe"] = "2M"
    payload["signals"].append(dict(payload["signals"][0]))
    _write(tmp_path / REGISTRY_FILE_REL, payload)
    result = verify_m9_signal_semantics_registry(tmp_path)
    checks = {v["check"] for v in result["violations"]}
    assert "REGISTRY_SIGNAL_CLASS_ENUM" in checks
    assert "REGISTRY_TIMEFRAME_ENUM" in checks
    assert "REGISTRY_SIGNAL_DUPLICATE_NAME" in checks


def test_valid_registry_passes_and_is_deterministic(tmp_path: Path) -> None:
    _bootstrap_repo_root(tmp_path)
    _write(tmp_path / REGISTRY_FILE_REL, _valid_payload())
    first = verify_m9_signal_semantics_registry(tmp_path)
    second = verify_m9_signal_semantics_registry(tmp_path)
    assert first["valid"] is True
    assert {k: v for k, v in first.items() if k != "generated_at_utc"} == {
        k: v for k, v in second.items() if k != "generated_at_utc"
    }
