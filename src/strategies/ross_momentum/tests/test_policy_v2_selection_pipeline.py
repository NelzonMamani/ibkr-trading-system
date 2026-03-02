from src.strategy_policy_v2.consumption import FocusBuilderV2, RankingEngineV2, SelectionEngineV2, WatchlistBuilderV2
from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2


def test_policy_v2_pipeline_watchlist_and_drop_reasons() -> None:
    candidates = [
        {"symbol": "AAA", "session_label": "PRE", "last_price": 4.0, "pct_change": 35.0, "volume": 3_000_000, "premarket_volume": 300_000, "rvol": 9.0, "dollar_volume": 15_000_000.0, "float_millions": 7.0, "spread_pct": 0.2, "halted": False, "ssr": False, "news_catalyst": True},
        {"symbol": "BBB", "session_label": "RTH", "last_price": 6.0, "pct_change": 15.0, "volume": 2_000_000, "premarket_volume": 200_000, "rvol": 6.0, "dollar_volume": 11_000_000.0, "float_millions": 8.0, "spread_pct": 0.4, "halted": False, "ssr": False, "news_catalyst": "MEDIUM"},
        {"symbol": "BAD", "session_label": "PRE", "last_price": 40.0, "pct_change": 12.0, "volume": 100_000, "premarket_volume": 10_000, "rvol": 1.0, "dollar_volume": 500_000.0, "float_millions": 90.0, "spread_pct": 10.0, "halted": True, "ssr": False, "news_catalyst": False},
    ]

    selection = SelectionEngineV2().evaluate(POLICY_V2, candidates)
    ranking = RankingEngineV2().rank(POLICY_V2, selection.eligible)
    watchlist = WatchlistBuilderV2().build(POLICY_V2, ranking.ranked).watchlist
    focus = FocusBuilderV2().build(POLICY_V2, ranking.ranked).focus

    assert [row["symbol"] for row in watchlist][:2] == ["AAA", "BBB"]
    assert [row["symbol"] for row in focus][:2] == ["AAA", "BBB"]
    bad = next(row for row in selection.dropped if row.candidate.get("symbol") == "BAD")
    assert "PRICE_OUT_OF_RANGE" in bad.reasons
    assert "RVOL_TOO_LOW" in bad.reasons
