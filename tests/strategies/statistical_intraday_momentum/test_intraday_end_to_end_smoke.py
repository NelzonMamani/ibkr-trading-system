from dataclasses import replace

from src.strategies.statistical_intraday_momentum.signal_engine.signal_decision import decide_intent
from src.strategies.statistical_intraday_momentum.strategy_policy import default_policy
from src.strategy_portfolio.contracts import AllowState, SignalIntent


def test_end_to_end_smoke():
    policy = default_policy()
    policy = replace(
        policy,
        activation=replace(policy.activation, allow=True, start_minute_of_day=0, end_minute_of_day=600),
        signal=replace(policy.signal, entry_threshold=0.001, hold_threshold=0.0005, exit_threshold=-0.001),
        regime=replace(policy.regime, vol_floor=0.0, vol_ceiling=1.0),
    )
    bars_1m = [{"close": 100.0 + i * 0.2, "volume": 1_000.0} for i in range(20)]
    bars_5m = [{"close": 100.0 + i * 1.0, "volume": 5_000.0} for i in range(4)]
    context = {
        "symbol": "AAPL",
        "now_ts": "2026-01-22T14:00:00Z",
        "last_price": 103.8,
        "day_volume": 1_000_000,
        "minutes_since_open": 120,
        "bars_1m": bars_1m,
        "bars_5m": bars_5m,
        "spread_pct": 0.0001,
    }
    decision = decide_intent(context, policy)
    assert decision.allow_state == AllowState.ALLOW
    assert decision.signal_intent in {SignalIntent.ENTER_LONG, SignalIntent.NO_TRADE}
