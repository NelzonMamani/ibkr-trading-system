from __future__ import annotations

from src.metadata.m6_data_lifecycle_governance_verifier import (
    build_evidence_index,
    validate_evidence_index,
    verify_m6_data_lifecycle_governance,
)


def test_m6_data_lifecycle_governance_verifier() -> None:
    result = verify_m6_data_lifecycle_governance()

    assert result["epoch"] == "M6_DATA_LIFECYCLE_GOVERNANCE"

    evidence_related_checks = {
        "EVIDENCE_REQUIRED_FILES",
        "EVIDENCE_INDEX_EXISTS",
        "M6_REALITY_STATUS",
    }

    non_evidence_violations = [
        v for v in result["violations"] if v.get("check") not in evidence_related_checks
    ]

    # HARD RULE: system violations must fail
    assert not non_evidence_violations, (
        f"Non-evidence violations detected: {non_evidence_violations}"
    )

    reality_status = result.get("reality_status")

    if reality_status is None:
        reality_status = (
            "STRUCTURAL_ONLY" if result["violations"] else "REAL_EVIDENCE_PRESENT"
        )

    assert reality_status in {
        "STRUCTURAL_ONLY",
        "REAL_EVIDENCE_PRESENT",
        "CERTIFIED",
    }

    if reality_status == "STRUCTURAL_ONLY":
        assert any(v["check"] in evidence_related_checks for v in result["violations"])


def test_m6_evidence_index_detects_tamper(tmp_path) -> None:
    evidence_file = tmp_path / "evidence.txt"
    evidence_file.write_text("original", encoding="utf-8")
    index = build_evidence_index([evidence_file])

    evidence_file.write_text("tampered", encoding="utf-8")
    violations = validate_evidence_index(tmp_path, index)

    assert any(
        violation["check"] == "EVIDENCE_INDEX_SHA256_MATCH" for violation in violations
    )
