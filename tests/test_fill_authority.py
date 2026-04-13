from __future__ import annotations

from src.core.orchestrator import CoreOrchestrator


def test_fill_authority_verdict_healthy(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.execution.order_router.runtime_lifecycle_snapshot",
        lambda: {
            "submitted_no_ack_timeouts": 0,
            "working_no_fill_timeouts": 0,
            "partial_fill_stalls": 0,
        },
    )
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    verdict = CoreOrchestrator._resolve_fill_authority_cycle(orchestrator)
    assert verdict["execution_stalled"] is False
    assert verdict["stalled_symbols"] == []


def test_fill_authority_verdict_stalled(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.execution.order_router.runtime_lifecycle_snapshot",
        lambda: {
            "submitted_no_ack_timeouts": 1,
            "working_no_fill_timeouts": 0,
            "partial_fill_stalls": 0,
        },
    )
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    verdict = CoreOrchestrator._resolve_fill_authority_cycle(orchestrator)
    assert verdict["execution_stalled"] is True
    assert verdict["stalled_symbols"] == []
