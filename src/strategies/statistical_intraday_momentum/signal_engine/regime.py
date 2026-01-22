"""Regime gating helpers for statistical intraday momentum."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.strategy_portfolio.contracts import AllowState
from src.strategy_portfolio.reason_codes import ReasonCode

from .features import build_feature_vector
from ..strategy_policy import ActivationSpec, RegimeSpec


@dataclass(frozen=True)
class RegimeState:
    """Represents the evaluated regime conditions for gating."""

    volatility_ok: bool
    liquidity_ok: bool
    time_window_ok: bool
    spread_ok: bool

    @property
    def is_tradeable(self) -> bool:
        return self.volatility_ok and self.liquidity_ok and self.time_window_ok and self.spread_ok


def _minute_bucket(minutes_since_open: int) -> str:
    if minutes_since_open < 60:
        return "open"
    if minutes_since_open < 300:
        return "midday"
    return "late"


def evaluate_regime(
    context: Mapping[str, object],
    activation: ActivationSpec,
    regime: RegimeSpec,
) -> tuple[AllowState, list[str], RegimeState | None]:
    required = ["last_price", "day_volume", "minutes_since_open", "bars_1m", "bars_5m"]
    if not all(key in context for key in required):
        return (
            AllowState.DISALLOW,
            [ReasonCode.MISSING_FIELD_DEFAULT.value],
            None,
        )

    minutes_since_open = int(context["minutes_since_open"])
    time_window_ok = activation.start_minute_of_day <= minutes_since_open <= activation.end_minute_of_day

    last_price = float(context["last_price"])
    day_volume = float(context["day_volume"])
    dollar_volume = last_price * day_volume
    liquidity_ok = dollar_volume >= regime.min_liquidity_score * 1_000_000

    spread_ok = True
    if "spread_pct" in context and context["spread_pct"] is not None:
        spread_ok = float(context["spread_pct"]) * 10_000 <= regime.max_spread_bps

    time_bucket = _minute_bucket(minutes_since_open)
    features = build_feature_vector(
        context["bars_1m"],
        context["bars_5m"],
        time_bucket,
    )
    volatility_ok = regime.vol_floor <= features.volatility <= regime.vol_ceiling

    state = RegimeState(
        volatility_ok=volatility_ok,
        liquidity_ok=liquidity_ok,
        time_window_ok=time_window_ok,
        spread_ok=spread_ok,
    )

    if state.is_tradeable:
        return AllowState.ALLOW, [], state

    reasons = []
    if not time_window_ok:
        reasons.append(ReasonCode.ACTIVATION_DISALLOW.value)
    if not liquidity_ok:
        reasons.append(ReasonCode.UNIVERSE_REJECT.value)
    if not spread_ok:
        reasons.append(ReasonCode.DATA_QUALITY_FAIL.value)
    if not volatility_ok:
        reasons.append(ReasonCode.DATA_QUALITY_FAIL.value)

    return AllowState.DISALLOW, reasons, state
