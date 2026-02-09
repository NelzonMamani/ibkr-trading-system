from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from config.config_resolver import set_config_overrides  # noqa: E402
from config.runtime_config import RunMode  # noqa: E402
from core.position_lifecycle_engine import (  # noqa: E402
    LifecycleIntent,
    PositionLifecycle,
    PositionLifecycleEngine,
    PositionState,
)
from storage.storage_engine import StorageEngine  # noqa: E402

def test_lifecycle_persistence_and_replay(tmp_path, monkeypatch):
    db_path = tmp_path / "lifecycle.db"
    monkeypatch.setenv("PERSISTENCE_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("PERSISTENCE_ENABLED", "1")
    monkeypatch.setenv("PERSISTENCE_BACKEND", "sqlite")
    set_config_overrides({})

    storage = StorageEngine()
    engine = PositionLifecycleEngine(storage_engine=storage)
    position = PositionLifecycle(symbol="ZZZ", trader_type="SIM")

    engine.apply_intent(
        position,
        LifecycleIntent.OPEN,
        requested_quantity=2,
        run_mode=RunMode.SIM,
        reason="Open for persistence",
    )
    engine.apply_intent(
        position,
        LifecycleIntent.FULL_EXIT,
        requested_quantity=2,
        run_mode=RunMode.SIM,
        reason="Exit for persistence",
    )

    transitions = storage.fetch_lifecycle_transitions(run_id=storage.run_id)
    assert transitions

    replayed = PositionLifecycleEngine.replay_transitions(transitions)
    restored = replayed[("ZZZ", "SIM")]
    assert restored.state == PositionState.CLOSED
    assert restored.quantity == 0

    storage.shutdown()
    set_config_overrides({})
