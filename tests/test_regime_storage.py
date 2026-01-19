from __future__ import annotations

import json

from src.config.config_resolver import set_config_overrides
from src.models.data_models import TradeRecord
from src.storage.storage_engine import StorageEngine


def test_regime_artifacts_persisted(tmp_path):
    db_path = tmp_path / "regime.db"
    set_config_overrides({"PERSISTENCE_SQLITE_PATH": str(db_path)})
    try:
        engine = StorageEngine()
        record = TradeRecord(
            scanner_output=[],
            pattern_output=[],
            strategy_output=[],
            risk_output=[],
            execution_output=[],
            trade_outcomes=[],
            performance_snapshot=None,
            regime_snapshot={"label": "OPENING_MOMENTUM"},
            regime_policy_decision={"applied": True, "risk_multiplier": 0.5},
        )
        result = engine.store_trade_record(record, cycle_context={"tick": 1}, events=[])
        assert result.ok
        rows = engine._store.fetch_trade_records(engine.run_id)
        assert rows
        payload = json.loads(rows[0]["regime_snapshot_json"])
        assert payload["label"] == "OPENING_MOMENTUM"
        engine._store.close()
    finally:
        set_config_overrides(None)
