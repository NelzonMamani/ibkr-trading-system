"""Scanner policy for Mean Reversion stock selection."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.strategies.ross_momentum.strategy_policy import (
    StockSelectionSpec,
    UniverseSource,
    UniverseSpec,
)


def mean_reversion_stock_selection_spec() -> StockSelectionSpec:
    universe = UniverseSpec(
        source=UniverseSource.IBKR_TOP_GAINERS,
        ibkr_scan_code="TOP_PERC_GAIN",
        top_n=75,
    )
    return StockSelectionSpec(
        policy_name="MEAN_REVERSION",
        universe=universe,
        price_min=2.0,
        price_max=200.0,
        gap_min_pct=2.0,
        gap_max_pct=None,
        rvol_min=1.5,
        float_max_millions=200.0,
        liquidity_min_dollar_volume=20_000_000.0,
        min_volume=500_000,
        min_premarket_volume=0,
        spread_max_pct=None,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=True,
        data_quality_require_price=True,
        data_quality_require_bid_ask=True,
        watchlist_limit_k=20,
        focus_limit_m=5,
        top_gainers_n=75,
        max_symbols_per_cycle=75,
        session_allowlist=("REG",),
        ranking_intent="MEAN_REVERSION_STOCK_SELECTION",
    )


@dataclass(frozen=True)
class MeanReversionScannerPolicy:
    name: str = "mean_reversion"
    version: str = "1.0"
    stock_selection: StockSelectionSpec = field(
        default_factory=mean_reversion_stock_selection_spec
    )
