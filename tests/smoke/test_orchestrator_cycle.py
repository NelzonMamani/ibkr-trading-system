from __future__ import annotations

from src.core_engine.orchestrator import run_cycles


def test_orchestrator_readonly_cycle() -> None:
    summaries = run_cycles(mode="READONLY", cycles=1)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.mode == "READONLY"
    assert summary.scanner.watchlist is not None
