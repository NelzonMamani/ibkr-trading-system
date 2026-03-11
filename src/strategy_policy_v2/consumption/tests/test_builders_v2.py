from src.strategy_policy_v2.consumption.builders import FocusBuilderV2, WatchlistBuilderV2
from src.strategy_policy_v2.consumption.models import RankedCandidate
from src.strategies.ross_momentum.strategy_policy import POLICY_V2


def test_builders_respect_limits_and_tiebreakers() -> None:
    ranked = [
        RankedCandidate(candidate={"symbol": "BBB", "pct_change": 10.0, "dollar_volume": 100.0}, score=1.0, score_breakdown={}),
        RankedCandidate(candidate={"symbol": "AAA", "pct_change": 10.0, "dollar_volume": 100.0}, score=1.0, score_breakdown={}),
        RankedCandidate(candidate={"symbol": "CCC", "pct_change": 8.0, "dollar_volume": 99.0}, score=0.9, score_breakdown={}),
    ]
    watchlist = WatchlistBuilderV2().build(POLICY_V2, ranked).watchlist
    focus = FocusBuilderV2().build(POLICY_V2, ranked).focus
    assert watchlist[0]["symbol"] == "AAA"
    assert watchlist[1]["symbol"] == "BBB"
    assert len(watchlist) <= POLICY_V2.selection_plan.watchlist_limit_k
    assert len(focus) <= POLICY_V2.selection_plan.focus_limit_m
