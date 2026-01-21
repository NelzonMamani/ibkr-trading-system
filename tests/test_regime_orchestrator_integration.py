from __future__ import annotations

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator


def test_orchestrator_emits_regime_snapshot(tmp_path):
    overrides = {
        "ADAPTIVE_REGIME_LAYER_ENABLED": True,
        "ADAPTIVE_REGIME_POLICY_ENABLED": False,
        "EVENT_REPLAY_MODE": "CYCLE",
        "RUN_MODE": "SIM",
        "PERSISTENCE_SQLITE_PATH": str(tmp_path / "regime_orch.db"),
    }
    set_config_overrides(overrides)
    try:
        orchestrator = CoreOrchestrator()
        assert orchestrator.run_once() is True
        events = orchestrator.event_collector.snapshot_cycle()
        assert any(event.event_type == "REGIME_SNAPSHOT" for event in events)
        replay_events = orchestrator.event_collector.get_events_for_replay("CYCLE")
        assert any(event.event_type == "REGIME_SNAPSHOT" for event in replay_events)
        if orchestrator.storage_engine._store is not None:
            orchestrator.storage_engine._store.close()
    finally:
        set_config_overrides(None)
