from dataclasses import replace

from src.scanner.contracts import StockSelectionPolicy
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def _to_scanner_policy(stock_policy) -> StockSelectionPolicy:
    return StockSelectionPolicy(
        policy_name="ROSS_MOMENTUM",
        price_min=stock_policy.price_min,
        price_max=stock_policy.price_max,
        gap_min_pct=stock_policy.gap_min_pct,
        gap_max_pct=stock_policy.gap_max_pct,
        rvol_min=stock_policy.rvol_min,
        float_max_millions=stock_policy.float_max_millions,
        liquidity_min_dollar_volume=stock_policy.liquidity_min_dollar_volume,
        min_volume=stock_policy.min_volume,
        min_premarket_volume=stock_policy.min_premarket_volume,
        spread_max=stock_policy.spread_max,
        require_catalyst=stock_policy.require_catalyst,
        allow_halts=stock_policy.allow_halts,
        allow_ssr=stock_policy.allow_ssr,
        data_quality_require_price=stock_policy.data_quality_require_price,
        data_quality_require_bid_ask=stock_policy.data_quality_require_bid_ask,
        watchlist_limit_k=stock_policy.watchlist_limit_k,
        focus_limit_m=stock_policy.focus_limit_m,
        top_gainers_n=stock_policy.top_gainers_n,
        max_symbols_per_cycle=stock_policy.max_symbols_per_cycle,
        session_allowlist=stock_policy.session_allowlist,
    )


def test_scanner_policy_limits_applied_in_teaching_mode():
    base_policy = RossMomentumPolicy()
    tuned_stock_policy = replace(
        base_policy.stock_selection,
        watchlist_limit_k=3,
        focus_limit_m=2,
        top_gainers_n=5,
    )
    tuned_policy = replace(base_policy, stock_selection=tuned_stock_policy)
    scanner_policy = _to_scanner_policy(tuned_policy.stock_selection)

    payload = run_scanner_cycle(mode="READONLY", policy=scanner_policy)

    assert len(payload.get("watchlist_k", [])) == 3
    assert len(payload.get("focus_m", [])) == 2
