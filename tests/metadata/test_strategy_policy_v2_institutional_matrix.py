from __future__ import annotations

from pathlib import Path

from src.metadata.strategy_policy_v2_audit import DOMAIN_LABELS, MATRIX_V2_PATH, REPORT_PATH, generate_audit_artifacts


def test_institutional_matrix_v2_generation_and_domain_coverage() -> None:
    results = generate_audit_artifacts()

    assert len(results) == 20
    for result in results:
        domain_ids = {domain.domain_id for domain in result.domains}
        assert domain_ids == {domain_id for domain_id, _ in DOMAIN_LABELS}

    matrix_text = MATRIX_V2_PATH.read_text(encoding="utf-8")
    report_text = REPORT_PATH.read_text(encoding="utf-8")
    for i in range(1, 21):
        strategy_id = f"P{i:02d}"
        assert strategy_id in matrix_text
        assert strategy_id in report_text


def test_institutional_matrix_v2_artifacts_exist() -> None:
    generate_audit_artifacts()

    assert MATRIX_V2_PATH.exists()
    assert REPORT_PATH.exists()
    assert Path(MATRIX_V2_PATH).name == "STRATEGY_AUDIT_MATRIX_V2.md"
