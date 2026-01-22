"""Risk request policy for Statistical Intraday Momentum (interface-only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from src.strategy_portfolio.reason_codes import ReasonCode

from .strategy_policy import RiskSpec, StatisticalIntradayMomentumPolicy


@dataclass(frozen=True)
class StopModelSpec:
    """Stop model specification (placeholder for risk engine)."""

    model_name: str
    atr_multiple: float | None = None  # Conservative default if ATR-based.


@dataclass(frozen=True)
class RiskRequest:
    """Risk request intent sent to risk governance (non-binding)."""

    enabled: bool
    per_trade_risk_usd: float | None
    max_concurrent_positions: int
    stop_model: StopModelSpec
    daily_loss_limit_usd: float | None = None
    reasons: list[str] = field(default_factory=list)


def _build_stop_model(risk_spec: RiskSpec) -> StopModelSpec:
    return StopModelSpec(model_name=risk_spec.stop_model, atr_multiple=1.5)


def build_risk_request(
    policy: StatisticalIntradayMomentumPolicy,
    context: Mapping[str, object],
    symbol: str,
) -> RiskRequest:
    if "last_price" not in context:
        return RiskRequest(
            enabled=False,
            per_trade_risk_usd=None,
            max_concurrent_positions=policy.risk.max_concurrent_positions,
            stop_model=_build_stop_model(policy.risk),
            reasons=[ReasonCode.MISSING_FIELD_DEFAULT.value],
        )

    return RiskRequest(
        enabled=True,
        per_trade_risk_usd=policy.risk.per_trade_risk_usd,
        max_concurrent_positions=policy.risk.max_concurrent_positions,
        stop_model=_build_stop_model(policy.risk),
        daily_loss_limit_usd=None,
        reasons=[],
    )
