from __future__ import annotations

from src.metadata.strategy_policy_v2_audit import run_audit


def test_global_minimums_enforced_and_default_only_detected() -> None:
    results = run_audit()

    assert len(results) == 20

    for result in results:
        domain_map = {domain.domain_id: domain for domain in result.domains}

        identity_control = next(c for c in domain_map["D0"].controls if c.control_id == "D0.C01")
        risk_control = next(c for c in domain_map["D7"].controls if c.control_id == "D7.C01")
        execution_control = next(c for c in domain_map["D12"].controls if c.control_id == "D12.C01")
        data_control = next(c for c in domain_map["D10"].controls if c.control_id == "D10.C01")

        assert identity_control.status == "PASS"
        assert risk_control.status == "PASS"
        assert execution_control.status == "PASS"
        assert data_control.status in {"PASS", "FAIL"}

        default_only_control = next(c for c in domain_map["D11"].controls if c.control_id == "D11.C02")
        if result.default_only:
            assert default_only_control.status == "FAIL"
            assert result.verdict == "FAIL"
