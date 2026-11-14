"""Signal component controls; these deliberately do not claim Core integration.

The active watchlist adapter does not consume this bar-based decision owner.
"""
from copy import deepcopy
from dataclasses import replace

import pytest

from src.strategies.statistical_intraday_momentum.signal_engine.signal_decision import decide_intent
from src.strategies.statistical_intraday_momentum.strategy_policy import default_policy
from src.strategy_portfolio.contracts import AllowState, SignalIntent


def signal_context():
    closes = [100.]
    for i in range(19):
        closes.append(closes[-1] * (0.99 if i % 5 == 4 else 1.02))
    bars_1m = [{"close": price, "volume": 7_000. if i >= 15 else 1_000.}
               for i, price in enumerate(closes)]
    return {
        "symbol": "TEST", "now_ts": "2026-11-13T16:30:00Z",
        "last_price": closes[-1], "day_volume": 1_000_000,
        "minutes_since_open": 120, "bars_1m": bars_1m,
        "bars_5m": [{"close": closes[i], "volume": sum(b["volume"] for b in bars_1m[i-4:i+1])}
                    for i in (4, 9, 14, 19)],
        "spread_pct": .0001,
    }


def activated_policy():
    # Explicit component-test enrollment only; all production defaults and
    # universe, timing, volatility and scoring thresholds stay unchanged.
    policy = default_policy()
    return replace(policy, activation=replace(policy.activation, allow=True))


def test_native_signal_has_a_concrete_eligible_decision_at_unchanged_thresholds():
    decision = decide_intent(signal_context(), activated_policy())
    assert decision.allow_state == AllowState.ALLOW
    assert decision.signal_intent == SignalIntent.ENTER_LONG
    assert not decision.reasons


@pytest.mark.parametrize("fault", ["default_off", "missing", "outside_window", "illiquid", "wide", "flat", "weak"])
def test_native_signal_rejection_controls(fault):
    policy = activated_policy()
    context = deepcopy(signal_context())
    if fault == "default_off": policy = default_policy()
    if fault == "missing": del context["bars_1m"]
    if fault == "outside_window": context["minutes_since_open"] = 29
    if fault == "illiquid": context["day_volume"] = 100
    if fault == "wide": context["spread_pct"] = .003
    if fault == "flat":
        for bar in context["bars_1m"]: bar["close"] = 100.
    if fault == "weak":
        for bar in context["bars_1m"]: bar["volume"] = 1_000.
    decision = decide_intent(context, policy)
    assert decision.signal_intent == SignalIntent.NO_TRADE
    if fault != "weak": assert decision.allow_state == AllowState.DISALLOW
