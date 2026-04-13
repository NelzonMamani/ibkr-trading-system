from __future__ import annotations

from types import SimpleNamespace

from src.core.orchestrator import CoreOrchestrator


def test_critical_exit_anomaly_blocks_exit_progression(monkeypatch) -> None:
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

    verdict = CoreOrchestrator._resolve_lifecycle_authority_cycle(orchestrator)

    assert verdict["critical_exit_anomaly"] is True
    assert verdict["block_exit_progression"] is True
    assert verdict["block_new_entries"] is True


def test_lifecycle_entry_guard_uses_block_new_entries() -> None:
    intents = [SimpleNamespace(symbol="AAPL")]
    guarded = CoreOrchestrator._apply_lifecycle_entry_guard(intents, {"block_new_entries": False})
    assert guarded == intents

    blocked = CoreOrchestrator._apply_lifecycle_entry_guard(intents, {"block_new_entries": True})
    assert blocked == []
