from dataclasses import fields

from src.scanner.contracts import StockSelectionPolicy


def test_stock_selection_policy_fields_unique_and_ordered():
    names = [field.name for field in fields(StockSelectionPolicy)]
    expected = [
        "policy_name",
        "universe_source",
        "exchange_allowlist",
        "top_gainers_n",
        "watchlist_limit_k",
        "focus_limit_m",
        "price_min",
        "price_max",
        "gap_min_pct",
        "rvol_min",
        "float_max_millions",
        "min_volume",
        "min_premarket_volume",
        "spread_max_pct",
        "require_catalyst",
        "allow_halts",
        "allow_ssr",
        "data_quality_require_price",
        "data_quality_require_bid_ask",
        "max_symbols_per_cycle",
        "session_allowlist",
    ]
    assert names == expected
    assert len(names) == len(set(names))
