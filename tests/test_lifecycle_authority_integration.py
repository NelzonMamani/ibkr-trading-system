from __future__ import annotations

from types import SimpleNamespace

import src.execution.order_router as order_router
from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator


class _DummyRegistry:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def snapshot(self):
        return list(self._rows)


def _orchestrator_stub(run_mode: RunMode = RunMode.PAPER) -> CoreOrchestrator:
    orchestrator = object.__new__(CoreOrchestrator)
    orchestrator.trade_registry = _DummyRegistry([])
    orchestrator.run_mode = run_mode
    orchestrator._latest_lifecycle_authority_verdict = {}
    return orchestrator


def test_orphan_working_order_blocks_new_entries(monkeypatch) -> None:
    orchestrator = _orchestrator_stub()
    monkeypatch.setattr(
        order_router,
        "_RUNTIME_ORDERS",
        {
            "1": SimpleNamespace(
                symbol="aapl",
                canonical_state="WORKING",
                remaining_qty=100,
                is_entry=True,
                is_exit=False,
            )
        },
        raising=False,
    )
    monkeypatch.setattr(
        order_router,
        "runtime_lifecycle_snapshot",
        lambda: {
            "open_position_count": 0,
            "working_no_fill_timeouts": 0,
        },
    )

    verdict = CoreOrchestrator._resolve_lifecycle_authority_cycle(orchestrator)

    assert "ORPHAN_WORKING_ORDER" in verdict["anomalies"]
    assert verdict["block_new_entries"] is True


def test_working_exit_with_broker_position_is_not_blocked() -> None:
    orchestrator = _orchestrator_stub()
    verdict = {
        "block_exit_progression": True,
        "critical_exit_anomaly": True,
        "open_position_count": 1,
        "working_exit_orders": 1,
    }

    blocked = CoreOrchestrator._resolve_lifecycle_exit_policy(orchestrator, verdict)

    assert blocked is False


def test_stalled_exit_anomaly_detected_but_not_frozen_when_exit_working(monkeypatch) -> None:
    orchestrator = _orchestrator_stub()
    monkeypatch.setattr(
        order_router,
        "_RUNTIME_ORDERS",
        {
            "2": SimpleNamespace(
                symbol="msft",
                canonical_state="WORKING",
                remaining_qty=50,
                is_entry=False,
                is_exit=True,
            )
        },
        raising=False,
    )
    monkeypatch.setattr(
        order_router,
        "runtime_lifecycle_snapshot",
        lambda: {
            "open_position_count": 1,
            "working_no_fill_timeouts": 3,
        },
    )

    verdict = CoreOrchestrator._resolve_lifecycle_authority_cycle(orchestrator)

    assert "EXIT_STALLED" in verdict["anomalies"]
    assert verdict["block_exit_progression"] is False
    assert CoreOrchestrator._resolve_lifecycle_exit_policy(orchestrator, verdict) is False
