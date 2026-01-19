from __future__ import annotations

from src.models.data_models import ScannerCandidate
from src.regime.classifier import RegimeClassifier
from src.regime.contracts import RegimeLabel
from src.regime.observers import observe_features


def test_live_readonly_missingness_after_hours_thin():
    candidates = [
        ScannerCandidate(
            symbol="TEST",
            price=None,
            gap_percent=None,
            rvol=None,
            float_millions=1.0,
            rationale="test",
            session="AFTER",
            bid=-1.0,
            ask=-1.0,
            spread=None,
            volume=None,
            momentum_move_pct=None,
        )
    ]
    features, flags = observe_features(candidates=candidates, session="AFTER")
    snapshot = RegimeClassifier().classify(
        features=features,
        baseline_stats={},
        data_quality_flags=flags,
        timestamp_utc=None,
    )
    assert snapshot.label == RegimeLabel.AFTER_HOURS_THIN
