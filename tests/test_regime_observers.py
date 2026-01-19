from __future__ import annotations

from src.models.data_models import ScannerCandidate
from src.regime.observers import observe_features


def test_observers_compute_basic_features_and_flags():
    candidates = [
        ScannerCandidate(
            symbol="AAA",
            price=10.0,
            gap_percent=5.0,
            rvol=2.0,
            float_millions=1.0,
            rationale="test",
            session="REGULAR",
            bid=9.99,
            ask=10.01,
            spread=0.02,
            volume=1000.0,
            momentum_move_pct=3.0,
        ),
        ScannerCandidate(
            symbol="BBB",
            price=None,
            gap_percent=None,
            rvol=None,
            float_millions=2.0,
            rationale="test",
            session="REGULAR",
            bid=None,
            ask=None,
            spread=None,
            volume=None,
            momentum_move_pct=None,
        ),
    ]
    features, flags = observe_features(candidates=candidates, session="REGULAR")

    assert features.universe_count == 2
    assert features.median_spread_bps == 20.0
    assert features.pct_missing_prices == 0.5
    assert features.pct_missing_volume == 0.5
    assert features.median_rvol == 2.0
    assert features.median_gap_pct == 5.0
    assert features.top1_momentum_move_pct == 3.0
    assert features.liquidity_thin_flag is False

    flag_values = {flag.value for flag in flags}
    assert "MISSING_PRICE" in flag_values
    assert "MISSING_VOLUME" in flag_values
    assert "MISSING_NEWS" in flag_values
