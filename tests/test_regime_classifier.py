from __future__ import annotations

from src.regime.baselines import BaselineStats
from src.regime.classifier import RegimeClassifier
from src.regime.contracts import FeatureVector, RegimeDataQualityFlag, RegimeLabel


def _baseline(mean: float, std: float) -> BaselineStats:
    return BaselineStats(
        count=10,
        rolling_mean=mean,
        rolling_std=std,
        ewma_mean=mean,
        q25=mean - std,
        q50=mean,
        q75=mean + std,
    )


def test_classifier_opening_momentum_label():
    features = FeatureVector(
        session="REGULAR",
        universe_count=5,
        median_spread_bps=20.0,
        pct_missing_prices=0.0,
        pct_missing_volume=0.0,
        median_rvol=3.0,
        median_gap_pct=4.0,
        top1_momentum_move_pct=5.0,
        news_density_proxy=0.0,
        liquidity_thin_flag=False,
        range_expansion_proxy=3.5,
    )
    baselines = {
        "median_rvol": _baseline(1.0, 0.5),
        "median_gap_pct": _baseline(1.0, 0.5),
        "range_expansion_proxy": _baseline(1.0, 0.5),
    }
    snapshot = RegimeClassifier().classify(
        features=features,
        baseline_stats=baselines,
        data_quality_flags=[],
        timestamp_utc=None,
    )
    assert snapshot.label == RegimeLabel.OPENING_MOMENTUM
    assert snapshot.confidence >= 0.5


def test_classifier_unknown_on_missing_prices():
    features = FeatureVector(
        session="REGULAR",
        universe_count=2,
        median_spread_bps=None,
        pct_missing_prices=0.6,
        pct_missing_volume=0.0,
        median_rvol=None,
        median_gap_pct=None,
        top1_momentum_move_pct=None,
        news_density_proxy=0.0,
        liquidity_thin_flag=False,
    )
    snapshot = RegimeClassifier().classify(
        features=features,
        baseline_stats={},
        data_quality_flags=[RegimeDataQualityFlag.MISSING_PRICE],
        timestamp_utc=None,
    )
    assert snapshot.label == RegimeLabel.UNKNOWN
