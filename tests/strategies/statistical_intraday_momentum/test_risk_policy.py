from src.strategies.statistical_intraday_momentum.risk_policy import build_risk_request
from src.strategies.statistical_intraday_momentum.strategy_policy import default_policy
from src.strategy_portfolio.reason_codes import ReasonCode


def test_risk_request_missing_context_disabled():
    policy = default_policy()
    request = build_risk_request(policy, context={}, symbol="AAPL")
    assert request.enabled is False
    assert request.reasons == [ReasonCode.MISSING_FIELD_DEFAULT.value]


def test_risk_request_deterministic():
    policy = default_policy()
    request = build_risk_request(policy, context={"last_price": 100.0}, symbol="AAPL")
    assert request.enabled is True
    assert request.per_trade_risk_usd == policy.risk.per_trade_risk_usd
