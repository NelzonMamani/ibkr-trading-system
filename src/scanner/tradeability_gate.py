from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.config.config_resolver import ConfigResolutionError, get_config
from src.scanner.session_pct_change import normalize_session_label


MIN_ABSOLUTE_VOLUME = 50_000
MAX_SPREAD_PCT = 0.10


@dataclass(frozen=True)
class TradeabilityDecision:
    accepted: bool
    reason: str
    liquidity_score: float


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_tradeability(context: Mapping[str, Any]) -> TradeabilityDecision:
    session = normalize_session_label(str(context.get("session") or ""))
    try:
        allow_ovn = bool(get_config("ALLOW_OVN_TRADING") or False)
    except ConfigResolutionError:
        allow_ovn = False
    if session == "OVN" and not allow_ovn:
        return TradeabilityDecision(False, "OVN_TRADING_DISABLED", 0.0)

    current_volume = _safe_float(context.get("volume"))
    try:
        min_absolute_volume = float(get_config("MIN_ABSOLUTE_VOLUME") or MIN_ABSOLUTE_VOLUME)
    except ConfigResolutionError:
        min_absolute_volume = float(MIN_ABSOLUTE_VOLUME)
    print(f"[TRADEABILITY][CHECK] volume={current_volume} threshold={min_absolute_volume}")
    if current_volume is None or current_volume < min_absolute_volume:
        return TradeabilityDecision(False, "INSUFFICIENT_VOLUME", 0.0)

    bid = _safe_float(context.get("bid"))
    ask = _safe_float(context.get("ask"))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return TradeabilityDecision(False, "INVALID_BID_ASK", 0.0)

    spread_pct = _safe_float(context.get("spread_pct"))
    if spread_pct is None:
        midpoint = (bid + ask) / 2.0
        spread_pct = ((ask - bid) / midpoint) if midpoint > 0 else None
    try:
        max_spread_pct = float(get_config("MAX_SPREAD_PCT") or MAX_SPREAD_PCT)
    except ConfigResolutionError:
        max_spread_pct = float(MAX_SPREAD_PCT)
    print(f"[TRADEABILITY][CHECK] spread={spread_pct} threshold={max_spread_pct}")
    if spread_pct is None or spread_pct > max_spread_pct:
        return TradeabilityDecision(False, "SPREAD_TOO_WIDE", 0.0)

    liquidity_score = min(1.0, (current_volume / min_absolute_volume) * 0.5 + (max(0.0, max_spread_pct - spread_pct) / max_spread_pct) * 0.5)
    return TradeabilityDecision(True, "TRADEABLE", liquidity_score)
