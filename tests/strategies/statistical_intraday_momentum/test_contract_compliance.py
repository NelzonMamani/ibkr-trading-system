from dataclasses import replace

from src.strategies.statistical_intraday_momentum.signal_engine.signal_decision import decide_intent
from src.strategies.statistical_intraday_momentum.strategy_policy import default_policy
from src.strategy_portfolio.contracts import AllowState, DecisionIntent, SignalIntent


def _context():
    bars_1m = [{"close": 100.0 + i * 0.1, "volume": 1_000.0} for i in range(20)]
    bars_5m = [{"close": 100.0 + i * 0.5, "volume": 5_000.0} for i in range(4)]
    return {
        "symbol": "AAPL",
        "now_ts": "2026-01-22T14:00:00Z",
        "last_price": 102.0,
        "day_volume": 500_000,
        "minutes_since_open": 120,
        "bars_1m": bars_1m,
        "bars_5m": bars_5m,
        "spread_pct": 0.0005,
    }


def test_contract_compliance_types():
    policy = default_policy()
    policy = replace(policy, activation=replace(policy.activation, allow=True))
    decision = decide_intent(_context(), policy)
    assert isinstance(decision, DecisionIntent)
    assert isinstance(decision.allow_state, AllowState)
    assert isinstance(decision.signal_intent, SignalIntent)
