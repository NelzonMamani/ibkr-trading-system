"""Adapter to translate Ross Momentum outputs into interface-native intents."""

from __future__ import annotations

from typing import Iterable, Mapping

from src.models.data_models import TradeIntent
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy
from src.strategies.strategy_contracts import DecisionType, StrategyDecision
from src.strategy_portfolio.contracts import AllowState, DecisionIntent, SignalIntent, StrategyIdentity
from src.strategy_portfolio.reason_codes import ReasonCode


def ross_identity(policy: RossMomentumPolicy | None = None) -> StrategyIdentity:
    policy = policy or RossMomentumPolicy()
    return StrategyIdentity(
        strategy_id=policy.name,
        strategy_version=policy.version,
        strategy_family="ross_momentum",
    )


def ross_policy_to_interface(policy: RossMomentumPolicy | None = None) -> dict[str, object]:
    identity = ross_identity(policy)
    return {
        "strategy_id": identity.strategy_id,
        "strategy_version": identity.strategy_version,
        "strategy_family": identity.strategy_family,
    }


def _map_direction_to_intent(direction: str | None) -> SignalIntent | None:
    if direction is None:
        return None
    direction_upper = direction.upper()
    if direction_upper == "LONG":
        return SignalIntent.ENTER_LONG
    if direction_upper == "SHORT":
        return SignalIntent.ENTER_SHORT
    if direction_upper == "NEUTRAL":
        return SignalIntent.NO_TRADE
    return None


def ross_output_to_decision_intent(
    ross_output: TradeIntent | StrategyDecision | None,
    context: Mapping[str, object] | None = None,
) -> DecisionIntent:
    if ross_output is None:
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=[ReasonCode.MAPPING_UNSUPPORTED_OUTPUT.value],
        )

    if isinstance(ross_output, TradeIntent):
        mapped = _map_direction_to_intent(ross_output.direction)
        if mapped is None:
            return DecisionIntent(
                allow_state=AllowState.DISALLOW,
                signal_intent=SignalIntent.NO_TRADE,
                reasons=[ReasonCode.MAPPING_UNSUPPORTED_OUTPUT.value],
            )
        return DecisionIntent(
            allow_state=AllowState.ALLOW,
            signal_intent=mapped,
            reasons=[],
            metadata={"symbol": ross_output.symbol, "strategy": ross_output.strategy_name},
        )

    if isinstance(ross_output, StrategyDecision):
        if ross_output.decision_type == DecisionType.EMIT_INTENT and ross_output.intents:
            mapped = _map_direction_to_intent(ross_output.intents[0].direction)
            if mapped is None:
                return DecisionIntent(
                    allow_state=AllowState.DISALLOW,
                    signal_intent=SignalIntent.NO_TRADE,
                    reasons=[ReasonCode.MAPPING_UNSUPPORTED_OUTPUT.value],
                )
            return DecisionIntent(
                allow_state=AllowState.ALLOW,
                signal_intent=mapped,
                reasons=[],
                metadata={"symbol": ross_output.symbol, "strategy": ross_output.strategy_id},
            )
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=[],
            metadata={"symbol": ross_output.symbol, "strategy": ross_output.strategy_id},
        )

    return DecisionIntent(
        allow_state=AllowState.DISALLOW,
        signal_intent=SignalIntent.NO_TRADE,
        reasons=[ReasonCode.MAPPING_UNSUPPORTED_OUTPUT.value],
    )


def ross_trade_intents_to_decision_intents(
    intents: Iterable[TradeIntent],
) -> list[DecisionIntent]:
    return [ross_output_to_decision_intent(intent) for intent in intents]
