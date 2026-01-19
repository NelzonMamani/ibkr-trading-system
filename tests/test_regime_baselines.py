from __future__ import annotations

from src.regime.baselines import BaselineStore
from src.regime.contracts import FeatureVector


def _feature(value: float) -> FeatureVector:
    return FeatureVector(
        session="REGULAR",
        universe_count=1,
        median_spread_bps=10.0,
        pct_missing_prices=0.0,
        pct_missing_volume=0.0,
        median_rvol=1.0,
        median_gap_pct=value,
        top1_momentum_move_pct=1.0,
        news_density_proxy=0.0,
        liquidity_thin_flag=False,
    )


def test_baseline_updates_and_quantiles():
    store = BaselineStore(window=3, alpha=0.2, persist_enabled=False)
    store.update(_feature(1.0))
    store.update(_feature(2.0))
    store.update(_feature(3.0))

    snapshot = store.snapshot()
    stats = snapshot["median_gap_pct"]
    assert stats.count == 3
    assert stats.rolling_mean == 2.0
    assert round(stats.rolling_std or 0.0, 6) == 0.816497
    assert stats.q25 == 1.5
    assert stats.q50 == 2.0
    assert stats.q75 == 2.5
    assert stats.ewma_mean == 1.56
