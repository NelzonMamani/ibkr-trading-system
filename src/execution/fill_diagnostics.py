from __future__ import annotations

from enum import Enum
from typing import Any


class NormalizedInactiveReason(str, Enum):
    OUTSIDE_RTH = "OUTSIDE_RTH"
    NON_MARKETABLE = "NON_MARKETABLE"
    NO_QUOTE = "NO_QUOTE"
    ROUTING = "ROUTING"
    HELD = "HELD"
    PERMISSION = "PERMISSION"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    UNKNOWN = "UNKNOWN"


class FillabilityClass(str, Enum):
    MARKETABLE_BUY = "MARKETABLE_BUY"
    MARKETABLE_SELL = "MARKETABLE_SELL"
    CROSSING_AGGRESSIVE = "CROSSING_AGGRESSIVE"
    INSIDE_SPREAD = "INSIDE_SPREAD"
    PASSIVE = "PASSIVE"
    AWAY_FROM_MARKET = "AWAY_FROM_MARKET"
    NO_QUOTE = "NO_QUOTE"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def classify_fillability(order: Any, quote_snapshot: dict[str, Any] | None) -> FillabilityClass:
    quote_snapshot = quote_snapshot or {}
    bid = _safe_float(quote_snapshot.get("bid"))
    ask = _safe_float(quote_snapshot.get("ask"))
    if bid is None or ask is None:
        return FillabilityClass.NO_QUOTE

    action = str(getattr(order, "action", "") or "").upper()
    order_type = str(getattr(order, "orderType", "") or "").upper()
    limit_price = _safe_float(getattr(order, "lmtPrice", None))

    if action == "BUY":
        if order_type == "MKT":
            return FillabilityClass.MARKETABLE_BUY
        if limit_price is None:
            return FillabilityClass.AWAY_FROM_MARKET
        if limit_price >= ask:
            return FillabilityClass.CROSSING_AGGRESSIVE
        if bid < limit_price < ask:
            return FillabilityClass.INSIDE_SPREAD
        if limit_price <= bid:
            return FillabilityClass.PASSIVE
        return FillabilityClass.AWAY_FROM_MARKET

    if action == "SELL":
        if order_type == "MKT":
            return FillabilityClass.MARKETABLE_SELL
        if limit_price is None:
            return FillabilityClass.AWAY_FROM_MARKET
        if limit_price <= bid:
            return FillabilityClass.CROSSING_AGGRESSIVE
        if bid < limit_price < ask:
            return FillabilityClass.INSIDE_SPREAD
        if limit_price >= ask:
            return FillabilityClass.PASSIVE
        return FillabilityClass.AWAY_FROM_MARKET

    return FillabilityClass.AWAY_FROM_MARKET


def normalize_inactive_reason(order: Any, broker_state: Any, quote_snapshot: dict[str, Any] | None) -> NormalizedInactiveReason:
    why_held = str(getattr(broker_state, "whyHeld", "") or "")
    why_upper = why_held.upper()
    if "RTH" in why_upper or "OUTSIDE" in why_upper:
        return NormalizedInactiveReason.OUTSIDE_RTH

    quote_snapshot = quote_snapshot or {}
    bid = _safe_float(quote_snapshot.get("bid"))
    ask = _safe_float(quote_snapshot.get("ask"))
    if bid is None or ask is None:
        return NormalizedInactiveReason.NO_QUOTE

    action = str(getattr(order, "action", "") or "").upper()
    limit_price = _safe_float(getattr(order, "lmtPrice", None))
    if action == "BUY" and limit_price is not None and limit_price < bid:
        return NormalizedInactiveReason.NON_MARKETABLE
    if action == "BUY" and limit_price is not None and limit_price >= ask:
        return NormalizedInactiveReason.ROUTING
    if action == "SELL" and limit_price is not None and limit_price > ask:
        return NormalizedInactiveReason.NON_MARKETABLE
    if action == "SELL" and limit_price is not None and limit_price <= bid:
        return NormalizedInactiveReason.ROUTING

    status = str(getattr(broker_state, "status", "") or "").upper()
    if status == "HELD":
        return NormalizedInactiveReason.HELD

    if any(token in why_upper for token in ("PERMISSION", "RESTRICT", "NOT ALLOWED", "DENIED")):
        return NormalizedInactiveReason.PERMISSION

    session_label = str(quote_snapshot.get("session_label", "") or "").upper()
    if any(token in why_upper for token in ("PRE", "AH", "AFTER")) and session_label == "RTH":
        return NormalizedInactiveReason.SESSION_MISMATCH

    return NormalizedInactiveReason.UNKNOWN


def diagnostic_verdict(fillability: FillabilityClass | str, inactive_reason: NormalizedInactiveReason | str) -> str:
    fillability_val = str(fillability)
    inactive_val = str(inactive_reason)
    if fillability_val in {FillabilityClass.MARKETABLE_BUY.value, FillabilityClass.CROSSING_AGGRESSIVE.value} and inactive_val in {
        NormalizedInactiveReason.UNKNOWN.value,
        NormalizedInactiveReason.ROUTING.value,
    }:
        return "BROKER_OR_ROUTING_ISSUE"
    if fillability_val == FillabilityClass.PASSIVE.value:
        return "EXPECTED_NO_FILL_PASSIVE"
    if fillability_val == FillabilityClass.NO_QUOTE.value:
        return "DATA_QUALITY_BLOCK"
    if inactive_val == NormalizedInactiveReason.OUTSIDE_RTH.value:
        return "SESSION_BLOCK"
    return "UNCLASSIFIED"


def marketable_expected(fillability: FillabilityClass | str) -> bool:
    return str(fillability) in {
        FillabilityClass.MARKETABLE_BUY.value,
        FillabilityClass.MARKETABLE_SELL.value,
        FillabilityClass.CROSSING_AGGRESSIVE.value,
    }
