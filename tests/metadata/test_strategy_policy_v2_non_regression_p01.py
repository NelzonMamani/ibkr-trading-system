from __future__ import annotations

from src.metadata.strategy_policy_v2_audit import run_audit


def test_p01_remains_certified_under_matrix_v2() -> None:
    results = run_audit()
    p01 = next(result for result in results if result.strategy_id == "P01")
    assert p01.verdict == "CERTIFIED"
