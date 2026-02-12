from __future__ import annotations

import json
from pathlib import Path

from src.metadata.m8_change_control_verifier import STATE_FILE_REL, verify_m8_change_control


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_state(repo_root: Path, lines: list[str]) -> None:
    state_path = repo_root / STATE_FILE_REL
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _state_lines(*entries: str) -> list[str]:
    return [
        "# SYSTEM_STATE_CERTIFIED.md",
        "## Certified Core Epoch Status",
        *entries,
        "## Certified Metadata Epoch Status",
    ]


def test_detects_drift_between_state_and_evidence(tmp_path: Path) -> None:
    _write_state(tmp_path, _state_lines("- M1_ARCHITECTURE_MAP: CERTIFIED"))
    _write_json(
        tmp_path / "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M1_ARCHITECTURE_MAP/certification_verdict.json",
        {"epoch": "M1_ARCHITECTURE_MAP", "verdict": "NOT_CERTIFIED"},
    )

    result = verify_m8_change_control(tmp_path)

    assert not result["valid"]
    checks = {v["check"] for v in result["violations"]}
    assert "SYSTEM_STATE_CERTIFIED_MATCHES_VERDICT" in checks


def test_detects_missing_evidence_directory(tmp_path: Path) -> None:
    _write_state(tmp_path, _state_lines("- M2_CONTRACT_REGISTRY: CERTIFIED"))

    result = verify_m8_change_control(tmp_path)

    assert not result["valid"]
    assert any(v["check"] == "CERTIFIED_EPOCH_EVIDENCE_DIR_EXISTS" for v in result["violations"])


def test_detects_missing_verdict_file(tmp_path: Path) -> None:
    _write_state(tmp_path, _state_lines("- M3_MODE_SEMANTICS_CERT: CERTIFIED"))
    (tmp_path / "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M3_MODE_SEMANTICS_CERTIFICATION").mkdir(
        parents=True, exist_ok=True
    )

    result = verify_m8_change_control(tmp_path)

    assert not result["valid"]
    assert any(v["check"] == "CERTIFIED_EPOCH_VERDICT_EXISTS" for v in result["violations"])


def test_false_positive_prevention_for_uncertified_state_epoch(tmp_path: Path) -> None:
    _write_state(tmp_path, _state_lines("- M8_CHANGE_CONTROL: IMPLEMENTED_UNCERTIFIED"))

    result = verify_m8_change_control(tmp_path)

    assert result["valid"]
    assert result["violations"] == []


def test_valid_scenario_passes_clean(tmp_path: Path) -> None:
    _write_state(
        tmp_path,
        _state_lines(
            "- E1_TRACEABILITY_OBSERVABILITY: CERTIFIED",
            "- M5_VERIFICATION_AUTHORITY: CERTIFIED",
        ),
    )
    _write_json(
        tmp_path / "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_01/certification_verdict.json",
        {"epoch": "E1_TRACEABILITY_OBSERVABILITY", "verdict": "CERTIFIED", "evidence": []},
    )
    _write_json(
        tmp_path / "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M5_VERIFICATION_AUTHORITY/certification_verdict.json",
        {
            "epoch": "M5_VERIFICATION_AUTHORITY",
            "verdict": "CERTIFIED",
            "evidence": ["M5_EVIDENCE_INDEX.json"],
        },
    )
    _write_json(
        tmp_path / "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M5_VERIFICATION_AUTHORITY/M5_EVIDENCE_INDEX.json",
        {"files": []},
    )

    result = verify_m8_change_control(tmp_path)

    assert result["valid"]
    assert result["violations"] == []


def test_core_epochs_ignored_by_default_for_legacy_drift(tmp_path: Path) -> None:
    _write_state(tmp_path, _state_lines("- E0_SYSTEM_LAW_TRUTH: CERTIFIED"))

    result = verify_m8_change_control(tmp_path)

    assert result["valid"]
    assert result["audited_state_certified_epochs"] == []


def test_include_core_detects_missing_core_evidence_directory(tmp_path: Path) -> None:
    _write_state(tmp_path, _state_lines("- E0_SYSTEM_LAW_TRUTH: CERTIFIED"))

    result = verify_m8_change_control(tmp_path, include_core=True)

    assert not result["valid"]
    assert any(v["actual"].startswith("missing:E0_SYSTEM_LAW_TRUTH") for v in result["violations"])


def test_m8_violations_sorted_deterministically(tmp_path: Path) -> None:
    _write_state(
        tmp_path,
        _state_lines(
            "- M2_CONTRACT_REGISTRY: CERTIFIED",
            "- M1_ARCHITECTURE_MAP: CERTIFIED",
        ),
    )

    result = verify_m8_change_control(tmp_path)

    assert result["violations"] == sorted(
        result["violations"],
        key=lambda v: (v["check"], v["actual"], v["expected"]),
    )
