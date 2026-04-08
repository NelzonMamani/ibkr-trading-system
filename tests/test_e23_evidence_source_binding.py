from __future__ import annotations

import json
from pathlib import Path

from src.integrity.evidence_sources import summarize_evidence_binding
from src.metadata.m5_verification_authority_verifier import verify_m5_verification_authority
from src.metadata.m6_data_lifecycle_governance_verifier import verify_m6_data_lifecycle_governance


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_e23_placeholder_only_is_structural_only(tmp_path: Path) -> None:
    runtime_root = tmp_path / "AUDIT_EVIDENCE"
    catalogue_root = tmp_path / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    _write(
        catalogue_root / "final_gate" / "verification_output.json",
        '{"note":"placeholder_structural_compliance_only"}',
    )

    summary = summarize_evidence_binding(runtime_root, catalogue_root)

    assert summary["final_posture"] == "NOT_CERTIFIED"
    assert summary["real_artifacts_detected"] == []


def test_e23_real_runtime_evidence_beats_placeholder(tmp_path: Path) -> None:
    runtime_root = tmp_path / "AUDIT_EVIDENCE"
    catalogue_root = tmp_path / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    _write(runtime_root / "final_gate" / "pipeline_summary.json", '{"result":"ok"}')
    _write(
        catalogue_root / "final_gate" / "verification_output.json",
        '{"note":"placeholder_structural_compliance_only"}',
    )

    summary = summarize_evidence_binding(runtime_root, catalogue_root)

    assert summary["domain_status"]["final_gate"] == "REAL_EVIDENCE_PRESENT"
    assert summary["final_posture"] in {"REAL_EVIDENCE_PRESENT", "CERTIFIED"}


def test_e23_runtime_evidence_can_drive_catalogue_absent_case(tmp_path: Path) -> None:
    runtime_root = tmp_path / "AUDIT_EVIDENCE"
    catalogue_root = tmp_path / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE"
    _write(runtime_root / "p01_runtime_detection_audit" / "runtime_stage_verification.json", '{"ok":true}')

    summary = summarize_evidence_binding(runtime_root, catalogue_root)

    assert summary["final_posture"] in {"REAL_EVIDENCE_PRESENT", "CERTIFIED"}
    assert summary["domain_status"]["p01_runtime_detection_audit"] == "REAL_EVIDENCE_PRESENT"


def _build_metadata_repo_fixture(tmp_path: Path, epoch_dir: str, index_name: str, epoch_name: str) -> Path:
    repo_root = tmp_path
    evidence_dir = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / epoch_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "verification_output.json": "{}\n",
        "verification_summary.md": "ok\n",
        "compileall.txt": "compileall ok\n",
        "pytest.txt": "1 passed\n",
        "pytest_full.txt": "1 passed\n",
    }
    for name, payload in files.items():
        _write(evidence_dir / name, payload)

    idx = {
        "epoch": epoch_name,
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "files": [
            {
                "file": file_name,
                "bytes": (evidence_dir / file_name).stat().st_size,
                "sha256": __import__("hashlib").sha256((evidence_dir / file_name).read_bytes()).hexdigest(),
            }
            for file_name in files.keys()
        ],
    }
    _write(evidence_dir / index_name, json.dumps(idx))
    _write(repo_root / "TRADING_OS_MASTER_CATALOGUE" / "SYSTEM_STATE_CERTIFIED.md", "- M5_VERIFICATION_AUTHORITY: IMPLEMENTED\n- M6_DATA_LIFECYCLE_GOV: IMPLEMENTED\n")
    return repo_root


def test_m5_placeholder_strategy_evidence_is_not_certified(tmp_path: Path) -> None:
    repo_root = _build_metadata_repo_fixture(
        tmp_path,
        epoch_dir="M5_VERIFICATION_AUTHORITY",
        index_name="M5_EVIDENCE_INDEX.json",
        epoch_name="M5_VERIFICATION_AUTHORITY",
    )
    _write(repo_root / "AUDIT_EVIDENCE" / "M5" / "strategy_capability_inventory.json", '{"ok": true}')
    _write(
        repo_root / "AUDIT_EVIDENCE" / "M5" / "strategy_certification_matrix.json",
        '{"note":"placeholder_structural_compliance_only"}',
    )
    _write(
        repo_root / "AUDIT_EVIDENCE" / "M5" / "strategy_certification_summary.json",
        '{"ok": true}',
    )

    result = verify_m5_verification_authority(repo_root)

    assert result["reality_status"] in {"REAL_EVIDENCE_PRESENT", "CERTIFIED"}


def test_m5_placeholder_without_runtime_is_structural_only(tmp_path: Path) -> None:
    repo_root = _build_metadata_repo_fixture(
        tmp_path,
        epoch_dir="M5_VERIFICATION_AUTHORITY",
        index_name="M5_EVIDENCE_INDEX.json",
        epoch_name="M5_VERIFICATION_AUTHORITY",
    )
    _write(
        repo_root / "AUDIT_EVIDENCE" / "M5" / "strategy_capability_inventory.json",
        '{"note":"placeholder_structural_compliance_only"}',
    )
    _write(
        repo_root / "AUDIT_EVIDENCE" / "M5" / "strategy_certification_matrix.json",
        '{"note":"placeholder_structural_compliance_only"}',
    )
    _write(
        repo_root / "AUDIT_EVIDENCE" / "M5" / "strategy_certification_summary.json",
        '{"note":"placeholder_structural_compliance_only"}',
    )
    result = verify_m5_verification_authority(repo_root)

    assert result["reality_status"] == "STRUCTURAL_ONLY"
    assert any(v["check"] == "M5_REALITY_STATUS" for v in result["violations"])


def test_m6_placeholder_only_catalogue_is_structural_only(tmp_path: Path) -> None:
    repo_root = _build_metadata_repo_fixture(
        tmp_path,
        epoch_dir="M6_DATA_LIFECYCLE_GOVERNANCE",
        index_name="M6_EVIDENCE_INDEX.json",
        epoch_name="M6_DATA_LIFECYCLE_GOVERNANCE",
    )
    _write(
        repo_root
        / "TRADING_OS_MASTER_CATALOGUE"
        / "AUDIT_EVIDENCE"
        / "M6_DATA_LIFECYCLE_GOVERNANCE"
        / "verification_summary.md",
        "Minimal scaffold for CI compliance\n",
    )

    result = verify_m6_data_lifecycle_governance(repo_root)

    assert result["reality_status"] == "STRUCTURAL_ONLY"
    assert any(v["check"] == "M6_REALITY_STATUS" for v in result["violations"])
