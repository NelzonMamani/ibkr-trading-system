from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.config.config_resolver import get_config
from src.scanner.session_pct_change import normalize_session_label


@dataclass(frozen=True)
class TradeabilityGateDecision:
    accepted: bool
    reason: str
    liquidity_score: float


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _liquidity_score(*, volume: Optional[float], dollar_volume: Optional[float], spread_pct: Optional[float]) -> float:
    volume_component = min((volume or 0.0) / 1_000_000.0, 1.0)
    dollar_component = min((dollar_volume or 0.0) / 10_000_000.0, 1.0)
    spread_component = 1.0 - min(max(spread_pct or 0.0, 0.0), 1.0)
    return round((0.5 * volume_component) + (0.3 * dollar_component) + (0.2 * spread_component), 4)


def evaluate_tradeability(context: Mapping[str, Any]) -> TradeabilityGateDecision:
    session = normalize_session_label(str(context.get("session") or ""))
    enable_ovn_trading = bool(get_config("ENABLE_OVN_TRADING"))
    if session == "OVN" and not enable_ovn_trading:
        return TradeabilityGateDecision(False, "OVN_TRADING_DISABLED", 0.0)

    min_absolute_volume = int(get_config("MIN_ABSOLUTE_VOLUME"))
    max_spread_pct = _safe_float(get_config("MAX_SPREAD_PCT"))
    min_liquidity_score = float(get_config("MIN_LIQUIDITY_SCORE"))

    current_volume = _safe_float(context.get("volume"))
    dollar_volume = _safe_float(context.get("dollar_volume"))
    spread_pct = _safe_float(context.get("spread_pct"))
    bid = _safe_float(context.get("bid"))
    ask = _safe_float(context.get("ask"))

    if current_volume is None or current_volume < min_absolute_volume:
        return TradeabilityGateDecision(False, "LOW_ABSOLUTE_VOLUME", 0.0)
    if max_spread_pct is not None and (spread_pct is None or spread_pct > max_spread_pct):
        return TradeabilityGateDecision(False, "SPREAD_TOO_WIDE", 0.0)
    if bid is None or ask is None or ask <= bid:
        return TradeabilityGateDecision(False, "UNSTABLE_ORDERBOOK", 0.0)

    liquidity = _liquidity_score(volume=current_volume, dollar_volume=dollar_volume, spread_pct=spread_pct)
    if liquidity < min_liquidity_score:
        return TradeabilityGateDecision(False, "LOW_LIQUIDITY_SCORE", liquidity)
    return TradeabilityGateDecision(True, "PASS", liquidity)
