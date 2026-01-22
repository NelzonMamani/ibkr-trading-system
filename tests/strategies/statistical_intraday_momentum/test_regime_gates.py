from dataclasses import replace

from src.strategies.statistical_intraday_momentum.signal_engine.regime import evaluate_regime
from src.strategies.statistical_intraday_momentum.strategy_policy import default_policy
from src.strategy_portfolio.contracts import AllowState
from src.strategy_portfolio.reason_codes import ReasonCode


def _base_context():
    bars_1m = [{"close": 100.0 + i * 0.1, "volume": 1_000.0} for i in range(20)]
    bars_5m = [{"close": 100.0 + i * 0.5, "volume": 5_000.0} for i in range(4)]
    return {
        "last_price": 105.0,
        "day_volume": 500_000,
        "minutes_since_open": 500,
        "bars_1m": bars_1m,
        "bars_5m": bars_5m,
        "spread_pct": 0.0001,
    }


def test_time_window_gate_disallows():
    policy = default_policy()
    activation = replace(policy.activation, allow=True, start_minute_of_day=30, end_minute_of_day=300)
    allow_state, reasons, _ = evaluate_regime(_base_context(), activation, policy.regime)
    assert allow_state == AllowState.DISALLOW
    assert ReasonCode.ACTIVATION_DISALLOW.value in reasons


def test_volatility_gate_disallows():
    policy = default_policy()
    activation = replace(policy.activation, allow=True, start_minute_of_day=0, end_minute_of_day=600)
    flat_context = _base_context()
    flat_context["bars_1m"] = [{"close": 100.0, "volume": 1_000.0} for _ in range(20)]
    allow_state, reasons, _ = evaluate_regime(flat_context, activation, policy.regime)
    assert allow_state == AllowState.DISALLOW
    assert ReasonCode.DATA_QUALITY_FAIL.value in reasons
