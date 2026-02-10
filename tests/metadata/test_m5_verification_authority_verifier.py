from __future__ import annotations

from src.metadata.m5_verification_authority_verifier import (
    build_evidence_index,
    validate_evidence_index,
    verify_m5_verification_authority,
)


def test_m5_verification_authority_verifier() -> None:
    result = verify_m5_verification_authority()
    assert result["violations"] == []
    assert result["valid"] is True


def test_m5_evidence_index_detects_tamper(tmp_path) -> None:
    evidence_file = tmp_path / "evidence.txt"
    evidence_file.write_text("original", encoding="utf-8")
    index = build_evidence_index([evidence_file])

    evidence_file.write_text("tampered", encoding="utf-8")
    violations = validate_evidence_index(tmp_path, index)

    assert any(
        violation["check"] == "EVIDENCE_INDEX_SHA256_MATCH" for violation in violations
    )
