from __future__ import annotations

from src.core.orchestrator import CoreOrchestrator


def test_lifecycle_authority_owns_exit_progression_block(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.execution.order_router.runtime_lifecycle_snapshot",
        lambda: {
            "submitted_no_ack_timeouts": 0,
            "working_no_fill_timeouts": 0,
            "partial_fill_stalls": 0,
            "anomalies": ["EXIT_STALLED"],
            "open_position_count": 0,
            "working_exit_orders": 0,
        },
    )
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator._latest_fill_authority_verdict = {"execution_stalled": False, "stalled_symbols": []}
    orchestrator._latest_lifecycle_authority_verdict = {
        "block_exit_progression": False,
        "critical_exit_anomaly": False,
    }

    fill_verdict = CoreOrchestrator._resolve_fill_authority_cycle(orchestrator)
    lifecycle_verdict = CoreOrchestrator._resolve_lifecycle_authority_cycle(orchestrator)

    assert "critical_exit_anomaly" not in fill_verdict
    assert "block_exit_progression" not in fill_verdict
    assert lifecycle_verdict["critical_exit_anomaly"] is False
    assert lifecycle_verdict["block_exit_progression"] is False
