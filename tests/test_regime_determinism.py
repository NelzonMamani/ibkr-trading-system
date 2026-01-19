from __future__ import annotations

from src.config.config_resolver import set_config_overrides
from src.models.data_models import ScannerCandidate
from src.regime.baselines import BaselineStore
from src.regime.layer import RegimeLayer


def test_regime_outputs_deterministic():
    overrides = {
        "ADAPTIVE_REGIME_LAYER_ENABLED": True,
        "ADAPTIVE_REGIME_POLICY_ENABLED": True,
        "ADAPTIVE_REGIME_STRATEGY_WEIGHTING_MODE": "WEIGHT",
        "ADAPTIVE_REGIME_MIN_CONFIDENCE_TO_APPLY": 0.2,
    }
    set_config_overrides(overrides)
    try:
        candidates = [
            ScannerCandidate(
                symbol="AAPL",
                price=10.0,
                gap_percent=1.0,
                rvol=1.5,
                float_millions=1.0,
                rationale="test",
                session="REGULAR",
                spread=0.01,
                volume=1000.0,
                momentum_move_pct=2.0,
            )
        ]
        layer_one = RegimeLayer(
            baseline_store=BaselineStore(window=5, alpha=0.2, persist_enabled=False)
        )
        layer_two = RegimeLayer(
            baseline_store=BaselineStore(window=5, alpha=0.2, persist_enabled=False)
        )
        snapshot_one, policy_one = layer_one.evaluate(candidates=candidates, session="REGULAR")
        snapshot_two, policy_two = layer_two.evaluate(candidates=candidates, session="REGULAR")
        payload_one = snapshot_one.to_payload()
        payload_two = snapshot_two.to_payload()
        payload_one["timestamp_utc"] = None
        payload_two["timestamp_utc"] = None
        policy_payload_one = policy_one.to_payload()
        policy_payload_two = policy_two.to_payload()
        policy_payload_one["timestamp_utc"] = None
        policy_payload_two["timestamp_utc"] = None
        assert payload_one == payload_two
        assert policy_payload_one == policy_payload_two
    finally:
        set_config_overrides(None)
