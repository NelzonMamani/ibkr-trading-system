from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from src.config.config_resolver import get_config
from src.regime.contracts import RegimeLabel, RegimePolicyDecision, RegimeSnapshot


@dataclass(frozen=True)
class RegimePolicy:
    def decide(self, snapshot: RegimeSnapshot, timestamp_utc: str | None) -> RegimePolicyDecision:
        policy_enabled = bool(get_config("ADAPTIVE_REGIME_POLICY_ENABLED"))
        min_confidence = float(get_config("ADAPTIVE_REGIME_MIN_CONFIDENCE_TO_APPLY"))
        weighting_mode = str(get_config("ADAPTIVE_REGIME_STRATEGY_WEIGHTING_MODE") or "OFF").upper()
        allowed_sessions = list(get_config("ADAPTIVE_REGIME_ALLOWED_SESSIONS") or [])
        risk_min = float(get_config("ADAPTIVE_REGIME_MIN_RISK_MULTIPLIER"))
        risk_max = float(get_config("ADAPTIVE_REGIME_MAX_RISK_MULTIPLIER"))
        allowed_risk = list(get_config("ADAPTIVE_REGIME_ALLOWED_RISK_MULTIPLIERS") or [])
        allowed_weights = list(get_config("ADAPTIVE_REGIME_ALLOWED_STRATEGY_WEIGHTS") or [])

        notes: List[str] = []
        if not policy_enabled:
            notes.append("Policy disabled by config.")
        if snapshot.confidence < min_confidence:
            notes.append(
                f"Confidence {snapshot.confidence:.2f} below threshold {min_confidence:.2f}."
            )
        if allowed_sessions and snapshot.session not in allowed_sessions:
            notes.append(f"Session {snapshot.session} not in allowed sessions.")

        applied = policy_enabled and snapshot.confidence >= min_confidence
        if allowed_sessions and snapshot.session not in allowed_sessions:
            applied = False

        eligible_strategies: List[str] = []
        strategy_weights: Dict[str, float] = {}
        risk_multiplier = _default_risk_multiplier(snapshot.label)

        if applied and weighting_mode == "ENABLE_DISABLE":
            eligible_strategies = _eligible_by_regime(snapshot.label)
            notes.append("ENABLE_DISABLE policy applied.")
        elif applied and weighting_mode == "WEIGHT":
            strategy_weights = _weights_by_regime(snapshot.label)
            notes.append("WEIGHT policy applied.")
        else:
            if weighting_mode != "OFF":
                notes.append(f"Weighting mode {weighting_mode} not applied.")
            if applied and weighting_mode == "OFF":
                notes.append("Weighting mode OFF; no strategy adjustments.")

        risk_multiplier = _clamp(risk_multiplier, risk_min, risk_max)
        if allowed_risk and risk_multiplier not in allowed_risk:
            risk_multiplier = _nearest_allowed(risk_multiplier, allowed_risk)
            notes.append("Risk multiplier snapped to allowed values.")

        if strategy_weights:
            strategy_weights = _normalize_weights(strategy_weights)
            if allowed_weights:
                strategy_weights = {
                    name: _nearest_allowed(weight, allowed_weights)
                    for name, weight in strategy_weights.items()
                }
                strategy_weights = _normalize_weights(strategy_weights)

        return RegimePolicyDecision(
            label=snapshot.label,
            confidence=snapshot.confidence,
            applied=applied,
            eligible_strategies=eligible_strategies,
            strategy_weights=strategy_weights,
            risk_multiplier=risk_multiplier,
            notes=notes,
            data_quality_flags=list(snapshot.data_quality_flags),
            timestamp_utc=timestamp_utc,
        )


def _eligible_by_regime(label: RegimeLabel) -> List[str]:
    if label == RegimeLabel.OPENING_MOMENTUM:
        return ["RossMomentumStrategyV1", "GapAndGoStrategy"]
    if label == RegimeLabel.TRENDING:
        return ["MomentumContinuationStrategy", "RossMomentumStrategyV1"]
    if label == RegimeLabel.CHOP_LOW_VOL:
        return ["RossMomentumStrategyV1"]
    if label == RegimeLabel.NEWS_DRIVEN:
        return ["GapAndGoStrategy", "RossMomentumStrategyV1"]
    if label in {RegimeLabel.HIGH_VOL_RISK_OFF, RegimeLabel.AFTER_HOURS_THIN}:
        return []
    return ["RossMomentumStrategyV1"]


def _weights_by_regime(label: RegimeLabel) -> Dict[str, float]:
    if label == RegimeLabel.OPENING_MOMENTUM:
        return {
            "RossMomentumStrategyV1": 0.6,
            "GapAndGoStrategy": 0.4,
            "MomentumContinuationStrategy": 0.0,
        }
    if label == RegimeLabel.TRENDING:
        return {
            "MomentumContinuationStrategy": 0.6,
            "RossMomentumStrategyV1": 0.4,
        }
    if label == RegimeLabel.CHOP_LOW_VOL:
        return {
            "RossMomentumStrategyV1": 0.5,
            "MomentumContinuationStrategy": 0.5,
        }
    if label == RegimeLabel.NEWS_DRIVEN:
        return {
            "RossMomentumStrategyV1": 0.5,
            "GapAndGoStrategy": 0.5,
        }
    return {
        "RossMomentumStrategyV1": 0.7,
        "MomentumContinuationStrategy": 0.3,
    }


def _default_risk_multiplier(label: RegimeLabel) -> float:
    if label in {RegimeLabel.HIGH_VOL_RISK_OFF, RegimeLabel.AFTER_HOURS_THIN}:
        return 0.25
    if label == RegimeLabel.CHOP_LOW_VOL:
        return 0.75
    if label == RegimeLabel.UNKNOWN:
        return 0.5
    if label == RegimeLabel.NEWS_DRIVEN:
        return 0.9
    return 1.0


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(value, 0.0) for value in weights.values())
    if total == 0:
        return {name: 0.0 for name in weights}
    return {name: round(max(value, 0.0) / total, 4) for name, value in weights.items()}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _nearest_allowed(value: float, allowed: Iterable[float]) -> float:
    allowed_list = sorted(float(item) for item in allowed)
    if not allowed_list:
        return value
    return min(allowed_list, key=lambda item: abs(item - value))
