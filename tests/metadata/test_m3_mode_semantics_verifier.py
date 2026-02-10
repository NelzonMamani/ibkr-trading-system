from __future__ import annotations

from src.metadata.m3_mode_semantics_verifier import verify_mode_semantics


def test_m3_mode_semantics_verifier() -> None:
    result = verify_mode_semantics()
    assert result["violations"] == []
    assert result["valid"] is True
