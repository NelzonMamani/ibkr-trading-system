from __future__ import annotations

import json
from pathlib import Path

from src.metadata.m7_epoch_audit_certifier import verify_m7_epoch_audit_and_certification


def _write(path: Path, payload: dict | list | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
        return
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_m7_metadata_default_uses_evidence_certified_epochs_only(tmp_path: Path) -> None:
    _write(
        tmp_path / "TRADING_OS_MASTER_CATALOGUE" / "SYSTEM_STATE_CERTIFIED.md",
        "- M1_ARCHITECTURE_MAP: CERTIFIED\n- M4_TRACEABILITY_SEMANTICS: CERTIFIED\n- E0_SYSTEM_LAW_TRUTH: CERTIFIED\n",
    )
    _write(
        tmp_path
        / "TRADING_OS_MASTER_CATALOGUE"
        / "AUDIT_EVIDENCE"
        / "M1_ARCHITECTURE_MAP"
        / "certification_verdict.json",
        {"epoch": "M1_ARCHITECTURE_MAP", "status": "CERTIFIED", "evidence": []},
    )

    result = verify_m7_epoch_audit_and_certification(repo_root=tmp_path)

    assert result["valid"] is True
    assert result["audited_epochs"] == ["M1_ARCHITECTURE_MAP"]
    assert result["notes"]["metadata_certified_in_system_state_but_not_evidence_certified"] == [
        "M4_TRACEABILITY_SEMANTICS"
    ]


def test_m7_include_core_surfaces_missing_core_evidence(tmp_path: Path) -> None:
    _write(
        tmp_path / "TRADING_OS_MASTER_CATALOGUE" / "SYSTEM_STATE_CERTIFIED.md",
        "- M1_ARCHITECTURE_MAP: CERTIFIED\n- E0_SYSTEM_LAW_TRUTH: CERTIFIED\n",
    )
    _write(
        tmp_path
        / "TRADING_OS_MASTER_CATALOGUE"
        / "AUDIT_EVIDENCE"
        / "M1_ARCHITECTURE_MAP"
        / "certification_verdict.json",
        {"epoch": "M1_ARCHITECTURE_MAP", "status": "CERTIFIED", "evidence": []},
    )

    result = verify_m7_epoch_audit_and_certification(repo_root=tmp_path, include_core=True)

    assert result["valid"] is False
    assert any(v["check"] == "CERTIFIED_EPOCH_EVIDENCE_DIR_EXISTS" for v in result["violations"])


def test_m7_evidence_index_legacy_artifacts_shape_is_accepted(tmp_path: Path) -> None:
    _write(
        tmp_path / "TRADING_OS_MASTER_CATALOGUE" / "SYSTEM_STATE_CERTIFIED.md",
        "- M1_ARCHITECTURE_MAP: CERTIFIED\n",
    )
    _write(
        tmp_path
        / "TRADING_OS_MASTER_CATALOGUE"
        / "AUDIT_EVIDENCE"
        / "M1_ARCHITECTURE_MAP"
        / "certification_verdict.json",
        {
            "epoch": "M1_ARCHITECTURE_MAP",
            "status": "CERTIFIED",
            "evidence": ["M1_ARCHITECTURE_MAP_EVIDENCE_INDEX.json"],
        },
    )
    _write(
        tmp_path
        / "TRADING_OS_MASTER_CATALOGUE"
        / "AUDIT_EVIDENCE"
        / "M1_ARCHITECTURE_MAP"
        / "M1_ARCHITECTURE_MAP_EVIDENCE_INDEX.json",
        {"artifacts": ["TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M1_ARCHITECTURE_MAP/certification_verdict.json"]},
    )

    result = verify_m7_epoch_audit_and_certification(repo_root=tmp_path)

    assert result["valid"] is True
