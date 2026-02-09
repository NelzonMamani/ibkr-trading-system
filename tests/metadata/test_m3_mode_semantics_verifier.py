from __future__ import annotations

from pathlib import Path

from verification_scripts.verify_m3_mode_semantics import (
    CANONICAL_MODES,
    evaluate_mode_semantics,
)


def test_m3_canonical_modes_declared() -> None:
    assert CANONICAL_MODES == ["SIM", "PAPER", "READ_ONLY", "LIVE"]


def test_m3_mode_semantics_verification_passes() -> None:
    results = evaluate_mode_semantics(Path(__file__).resolve().parents[2])
    assert results["violations"] == [], f"Violations detected: {results['violations']}"
