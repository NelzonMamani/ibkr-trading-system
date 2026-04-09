from __future__ import annotations

from src.metadata.m6_data_lifecycle_governance_verifier import (
    build_evidence_index,
    validate_evidence_index,
    verify_m6_data_lifecycle_governance,
)


def test_m6_data_lifecycle_governance_verifier() -> None:
    result = verify_m6_data_lifecycle_governance()

    evidence_related_checks = {
        "EVIDENCE_REQUIRED_FILES",
        "EVIDENCE_INDEX_EXISTS",
        "M6_REALITY_STATUS",
        "M6_RUNTIME_EVIDENCE_ROOT_EXISTS",
        "M6_RUNTIME_EVIDENCE_REAL_ARTIFACTS",
    }

    non_evidence_violations = [
        v for v in result["violations"]
        if v.get("check") not in evidence_related_checks
    ]

    assert not non_evidence_violations, (
        f"Non-evidence violations detected: {non_evidence_violations}"
    )


def test_m6_evidence_index_detects_tamper(tmp_path) -> None:
    evidence_file = tmp_path / "evidence.txt"
    evidence_file.write_text("original", encoding="utf-8")
    index = build_evidence_index([evidence_file])

    evidence_file.write_text("tampered", encoding="utf-8")
    violations = validate_evidence_index(tmp_path, index)

    assert any(
        violation["check"] == "EVIDENCE_INDEX_SHA256_MATCH" for violation in violations
    )
