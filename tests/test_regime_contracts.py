from __future__ import annotations

from datetime import datetime, timezone

from src.regime.contracts import (
    FeatureVector,
    RegimeEvidenceItem,
    RegimeLabel,
    RegimePolicyDecision,
    RegimeSnapshot,
)
from src.storage.serialization import canonical_json


def test_regime_labels_present():
    expected = {
        "OPENING_MOMENTUM",
        "CHOP_LOW_VOL",
        "TRENDING",
        "HIGH_VOL_RISK_OFF",
        "NEWS_DRIVEN",
        "AFTER_HOURS_THIN",
        "UNKNOWN",
    }
    assert expected.issubset({label.value for label in RegimeLabel})


def test_regime_snapshot_payload_deterministic():
    features = FeatureVector(
        session="REGULAR",
        universe_count=3,
        median_spread_bps=12.5,
        pct_missing_prices=0.0,
        pct_missing_volume=0.0,
        median_rvol=2.1,
        median_gap_pct=3.2,
        top1_momentum_move_pct=4.5,
        news_density_proxy=0.0,
        liquidity_thin_flag=False,
    )
    evidence = [
        RegimeEvidenceItem(
            feature_name="median_gap_pct",
            value=3.2,
            baseline=1.0,
            contribution=0.5,
            note="z-score vs baseline",
        )
    ]
    snapshot = RegimeSnapshot(
        label=RegimeLabel.OPENING_MOMENTUM,
        confidence=0.8,
        session="REGULAR",
        features=features,
        evidence=evidence,
        timestamp_utc=datetime(2026, 1, 19, tzinfo=timezone.utc).isoformat(),
    )
    payload = snapshot.to_payload()
    assert canonical_json(payload) == canonical_json(snapshot.to_payload())


def test_regime_policy_payload_serializable():
    decision = RegimePolicyDecision(
        label=RegimeLabel.TRENDING,
        confidence=0.72,
        applied=True,
        eligible_strategies=["RossMomentumStrategyV1"],
        strategy_weights={"RossMomentumStrategyV1": 1.0},
        risk_multiplier=0.75,
        notes=["Policy applied."],
    )
    payload = decision.to_payload()
    assert payload["label"] == "TRENDING"
    assert payload["risk_multiplier"] == 0.75
