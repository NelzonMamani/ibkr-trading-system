"""Scanner policy adapter for Statistical Intraday Momentum."""

from __future__ import annotations

from dataclasses import replace

from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec
from src.strategies.statistical_intraday_momentum.strategy_policy import (
    StatisticalIntradayMomentumPolicy,
)


def statistical_stock_selection_policy(
    policy: StatisticalIntradayMomentumPolicy,
) -> StockSelectionSpec:
    base = StockSelectionSpec()
    return replace(
        base,
        policy_name=policy.name,
        price_min=policy.universe.min_price,
        price_max=policy.universe.max_price,
        gap_min_pct=0.0,
        rvol_min=0.0,
        float_max_millions=500.0,
        liquidity_min_dollar_volume=policy.universe.min_dollar_volume,
        min_volume=100_000,
        min_premarket_volume=0,
        require_catalyst=False,
        watchlist_limit_k=50,
        focus_limit_m=20,
        top_gainers_n=100,
        session_allowlist=policy.universe.allowed_sessions,
    )
