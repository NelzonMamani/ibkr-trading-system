"""Decision mapping for statistical intraday momentum."""

from __future__ import annotations

from typing import Mapping

from src.strategy_portfolio.contracts import AllowState, DecisionIntent, SignalIntent
from src.strategy_portfolio.reason_codes import ReasonCode

from .features import build_feature_vector
from .regime import evaluate_regime
from .scoring import compute_score
from ..strategy_policy import StatisticalIntradayMomentumPolicy


REQUIRED_CONTEXT_FIELDS = {
    "last_price",
    "day_volume",
    "minutes_since_open",
    "bars_1m",
    "bars_5m",
}


def decide_intent(
    context: Mapping[str, object],
    policy: StatisticalIntradayMomentumPolicy,
    in_position: bool = False,
) -> DecisionIntent:
    if not REQUIRED_CONTEXT_FIELDS.issubset(context.keys()):
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=[ReasonCode.MISSING_FIELD_DEFAULT.value],
        )

    if not policy.activation.allow:
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=[ReasonCode.ACTIVATION_DISALLOW.value],
        )

    last_price = float(context["last_price"])
    day_volume = float(context["day_volume"])
    dollar_volume = last_price * day_volume
    if not (policy.universe.min_price <= last_price <= policy.universe.max_price):
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=[ReasonCode.UNIVERSE_REJECT.value],
        )
    if dollar_volume < policy.universe.min_dollar_volume:
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=[ReasonCode.UNIVERSE_REJECT.value],
        )

    allow_state, reasons, _ = evaluate_regime(
        context=context,
        activation=policy.activation,
        regime=policy.regime,
    )
    if allow_state == AllowState.DISALLOW:
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=reasons or [ReasonCode.DATA_QUALITY_FAIL.value],
        )

    minutes_since_open = int(context["minutes_since_open"])
    time_bucket = "open" if minutes_since_open < 60 else "midday" if minutes_since_open < 300 else "late"
    features = build_feature_vector(
        context["bars_1m"],
        context["bars_5m"],
        time_bucket,
    )
    score_state = compute_score(features, policy.signal)

    if in_position:
        if score_state.is_exit():
            return DecisionIntent(
                allow_state=AllowState.ALLOW,
                signal_intent=SignalIntent.EXIT_ONLY,
                reasons=[],
            )
        if score_state.is_hold():
            return DecisionIntent(
                allow_state=AllowState.ALLOW,
                signal_intent=SignalIntent.HOLD,
                reasons=[],
            )
        return DecisionIntent(
            allow_state=AllowState.ALLOW,
            signal_intent=SignalIntent.EXIT_ONLY,
            reasons=[],
        )

    if score_state.is_entry():
        return DecisionIntent(
            allow_state=AllowState.ALLOW,
            signal_intent=SignalIntent.ENTER_LONG,
            reasons=[],
        )

    return DecisionIntent(
        allow_state=AllowState.ALLOW,
        signal_intent=SignalIntent.NO_TRADE,
        reasons=[],
    )
