"""Standalone policy normaliser (not wired to orchestrator)."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import AllowState, DecisionIntent, SignalIntent
from .reason_codes import ReasonCode


def _get_value(obj: Any, *keys: str) -> Any:
    if isinstance(obj, Mapping):
        for key in keys:
            if key in obj:
                return obj[key]
        return None
    for key in keys:
        if hasattr(obj, key):
            return getattr(obj, key)
    return None


def _parse_signal_intent(raw_intent: Any) -> SignalIntent | None:
    if isinstance(raw_intent, SignalIntent):
        return raw_intent
    if isinstance(raw_intent, str):
        for intent in SignalIntent:
            if intent.value == raw_intent:
                return intent
    return None


def normalise_strategy_policy(policy_obj: Any) -> dict[str, Any]:
    return {
        "strategy_id": _get_value(policy_obj, "strategy_id", "name"),
        "strategy_version": _get_value(policy_obj, "strategy_version", "version"),
    }


def evaluate_activation(policy_obj: Any, context: Any) -> AllowState:
    activation = _get_value(policy_obj, "activation")
    if activation is None:
        return AllowState.DISALLOW
    allow_flag = _get_value(activation, "allow", "enabled")
    if allow_flag is True:
        return AllowState.ALLOW
    return AllowState.DISALLOW


def derive_decision_intent(policy_obj: Any, context: Any) -> DecisionIntent:
    if policy_obj is None:
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=[ReasonCode.MISSING_POLICY_FIELDS.value],
        )
    if context is None:
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=[ReasonCode.MISSING_FIELD_DEFAULT.value],
        )
    allow_state = evaluate_activation(policy_obj, context)
    if allow_state == AllowState.DISALLOW:
        return DecisionIntent(
            allow_state=AllowState.DISALLOW,
            signal_intent=SignalIntent.NO_TRADE,
            reasons=[ReasonCode.MISSING_POLICY_FIELDS.value],
        )

    explicit_intent = _parse_signal_intent(
        _get_value(policy_obj, "signal_intent", "intent")
    )
    return DecisionIntent(
        allow_state=AllowState.ALLOW,
        signal_intent=explicit_intent or SignalIntent.HOLD,
        reasons=[],
    )
