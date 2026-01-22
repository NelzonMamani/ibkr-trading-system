from dataclasses import replace

from src.strategies.statistical_intraday_momentum.signal_engine.features import build_feature_vector
from src.strategies.statistical_intraday_momentum.signal_engine.scoring import compute_score
from src.strategies.statistical_intraday_momentum.strategy_policy import default_policy


def test_scoring_determinism():
    bars_1m = [{"close": 100.0 + i * 0.1, "volume": 1_000.0} for i in range(20)]
    bars_5m = [{"close": 100.0 + i * 0.5, "volume": 5_000.0} for i in range(4)]
    features = build_feature_vector(bars_1m, bars_5m, "midday")
    policy = default_policy()
    policy = replace(policy, activation=replace(policy.activation, allow=True))
    score_a = compute_score(features, policy.signal)
    score_b = compute_score(features, policy.signal)
    assert score_a == score_b
