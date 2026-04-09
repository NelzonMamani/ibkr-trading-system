from __future__ import annotations

from src.metadata.m5_verification_authority_verifier import (
    build_evidence_index,
    validate_evidence_index,
    verify_m5_verification_authority,
)


def test_m5_verification_authority_verifier() -> None:
    result = verify_m5_verification_authority()

    evidence_related_checks = {
        "EVIDENCE_REQUIRED_FILES",
        "EVIDENCE_INDEX_EXISTS",
        "M5_STRATEGY_EVIDENCE_EXISTS",
        "M5_REALITY_STATUS",
    }

    non_evidence_violations = [
        v for v in result["violations"] if v.get("check") not in evidence_related_checks
    ]

    # HARD RULE
    assert not non_evidence_violations, (
        f"Non-evidence violations detected: {non_evidence_violations}"
    )

    reality_status = result.get("reality_status")

    assert reality_status in {
        "STRUCTURAL_ONLY",
        "REAL_EVIDENCE_PRESENT",
        "CERTIFIED",
        "MISSING",
    }

    if reality_status == "STRUCTURAL_ONLY":
        assert len(result["violations"]) > 0


def test_m5_evidence_index_detects_tamper(tmp_path) -> None:
    evidence_file = tmp_path / "evidence.txt"
    evidence_file.write_text("original", encoding="utf-8")
    index = build_evidence_index([evidence_file])

    evidence_file.write_text("tampered", encoding="utf-8")
    violations = validate_evidence_index(tmp_path, index)

    assert any(
        violation["check"] == "EVIDENCE_INDEX_SHA256_MATCH" for violation in violations
    )
