from src.strategy_policy_v2.consumption.ranking_engine import RankingEngineV2
from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2


def test_ranking_engine_is_deterministic() -> None:
    candidates = [
        {"symbol": "AAA", "pct_change": 20.0, "rvol": 8.0, "float_millions": 10.0, "news_catalyst": True, "spread_pct": 0.2, "halted": False, "ssr": False},
        {"symbol": "BBB", "pct_change": 20.0, "rvol": 8.0, "float_millions": 10.0, "news_catalyst": True, "spread_pct": 0.2, "halted": False, "ssr": False},
    ]
    first = RankingEngineV2().rank(POLICY_V2, candidates)
    second = RankingEngineV2().rank(POLICY_V2, candidates)
    assert [row.score for row in first.ranked] == [row.score for row in second.ranked]
    assert [row.score_breakdown for row in first.ranked] == [row.score_breakdown for row in second.ranked]
