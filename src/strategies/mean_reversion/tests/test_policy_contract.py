from src.strategies.mean_reversion.mean_reversion_strategy_policy import (
    MeanReversionPolicyConfig,
    MeanReversionStrategyPolicy,
    ScannerFacts,
    MarketRegimeFacts,
)

def test_policy_instantiates():
    policy = MeanReversionStrategyPolicy(cfg=MeanReversionPolicyConfig(), risk_engine=None)
    assert policy is not None

def test_policy_denies_invalid_price():
    policy = MeanReversionStrategyPolicy(cfg=MeanReversionPolicyConfig(), risk_engine=None)
    facts = ScannerFacts(symbol="X", last=0.0, vwap=1.0, ema9=1.0, ema20=1.0, atr=0.5)
    regime = MarketRegimeFacts()
    d = policy.evaluate_symbol(facts, regime)
    assert d.allowed is False
    assert d.reason == "INVALID_PRICE_OR_SYMBOL"
