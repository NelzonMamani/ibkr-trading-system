"""Filtering rules for scanner watchlists."""
from __future__ import annotations

from typing import Any, Optional

from src.scanner.contracts import StockSelectionPolicy, policy_from_config


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _get_value(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _mechanical_stock_selection_gates(policy: StockSelectionPolicy | None = None) -> dict:
    resolved = policy or policy_from_config()
    return {
        "min_pct_change": float(resolved.gap_min_pct),
        "min_price": float(resolved.price_min),
        "max_price": float(resolved.price_max),
        "max_float": int(resolved.float_max_millions * 1_000_000),
        "min_rvol": float(resolved.rvol_min),
        "min_volume": int(resolved.min_volume),
        "min_premarket_volume": int(resolved.min_premarket_volume),
        "require_news": bool(resolved.require_catalyst),
    }


def evaluate_mechanical_stock_selection_gates(
    entry: Any,
    require_news_override: Optional[bool] = None,
    policy: StockSelectionPolicy | None = None,
) -> tuple[bool, list[str]]:
    pillars = _mechanical_stock_selection_gates(policy=policy)
    if require_news_override is not None:
        pillars["require_news"] = require_news_override
    pct = _safe_float(_get_value(entry, "current_percentage_change_from_prior_close"), None)
    px = _safe_float(_get_value(entry, "last_trade_price"), None)
    flt = _get_value(entry, "float_shares_raw")
    rvol = _safe_float(_get_value(entry, "relative_volume"), None)
    vol = _safe_float(_get_value(entry, "current_intraday_volume"), None)
    news_total = _safe_float(_get_value(entry, "news_total_headlines"), 0.0) or 0.0
    session_label = (_get_value(entry, "market_session_label") or "").upper()
    reasons: list[str] = []

    if pct is None or px is None or rvol is None or vol is None:
        reasons.append("missing_core_metrics")
        return False, reasons
    if pct < pillars["min_pct_change"]:
        reasons.append("pct_change_below_min")
    if not (pillars["min_price"] <= px <= pillars["max_price"]):
        reasons.append("price_out_of_range")
    if flt is None or flt <= 0:
        reasons.append("float_missing")
    elif flt > pillars["max_float"]:
        reasons.append("float_above_max")
    if rvol < pillars["min_rvol"]:
        reasons.append("rvol_below_min")
    if session_label in {"PRE", "OVN"}:
        if vol < pillars["min_premarket_volume"]:
            reasons.append("premarket_volume_below_min")
    elif vol < pillars["min_volume"]:
        reasons.append("volume_below_min")
    if pillars["require_news"] and news_total <= 0:
        reasons.append("news_required_missing")

    return (len(reasons) == 0), reasons


def passes_mechanical_stock_selection_gates(
    entry: Any,
    require_news_override: Optional[bool] = None,
    policy: StockSelectionPolicy | None = None,
) -> bool:
    passed, _ = evaluate_mechanical_stock_selection_gates(
        entry,
        require_news_override=require_news_override,
        policy=policy,
    )
    return passed


def evaluate_catalyst_eligibility(entry: Any, bypass: bool = False) -> tuple[bool, list[str]]:
    if bypass:
        return True, []
    total = _safe_float(_get_value(entry, "news_total_headlines"), 0.0) or 0.0

    if total <= 0:
        return False, ["news_total_missing"]
    return True, []


def passes_catalyst_eligibility(entry: Any, bypass: bool = False) -> bool:
    passed, _ = evaluate_catalyst_eligibility(entry, bypass=bypass)
    return passed


def evaluate_filters(
    entry: Any,
    require_news_override: Optional[bool] = None,
    bypass_news_gates: bool = False,
    policy: StockSelectionPolicy | None = None,
) -> tuple[bool, list[str]]:
    passed_pillars, pillar_reasons = evaluate_mechanical_stock_selection_gates(
        entry, require_news_override=require_news_override, policy=policy
    )
    if not passed_pillars:
        return False, pillar_reasons
    passed_catalyst, catalyst_reasons = evaluate_catalyst_eligibility(
        entry, bypass=bypass_news_gates
    )
    if not passed_catalyst:
        return False, catalyst_reasons
    return True, []
