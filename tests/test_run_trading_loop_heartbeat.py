from __future__ import annotations

from types import SimpleNamespace

from src.cli import run_trading_loop


def test_loop_calls_manager_heartbeat_each_cycle(monkeypatch):
    calls = {"heartbeat": 0, "cycles": 0}

    class FakeManager:
        def heartbeat(self):
            calls["heartbeat"] += 1

    monkeypatch.setattr(
        run_trading_loop,
        "_parse_args",
        lambda: SimpleNamespace(
            mode="READ_ONLY",
            cadence_seconds=0.0,
            max_cycles=2,
            session_override=None,
            preflight=False,
        ),
    )
    monkeypatch.setattr(run_trading_loop, "bootstrap_runtime", lambda: None)
    monkeypatch.setattr(run_trading_loop.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        run_trading_loop,
        "get_shared_ibkr_connection_manager",
        lambda readonly_enabled=False: FakeManager(),
    )

    def _run_cycle(*, cycle_id, mode_value, forced_session_state):
        calls["cycles"] += 1

    monkeypatch.setattr(run_trading_loop.core_orchestrator, "run_cycle", _run_cycle)

    rc = run_trading_loop.main()

    assert rc == 0
    assert calls["cycles"] == 2
    assert calls["heartbeat"] == 2
