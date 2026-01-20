"""Filtering rules for scanner watchlists."""
from __future__ import annotations

from typing import Any, Optional

from src.config.config_resolver import get_config
from src.scanner.contracts import StockSelectionPolicy


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


def _mechanical_stock_selection_gates(
    policy: StockSelectionPolicy | None = None,
) -> dict:
    if policy is not None:
        return {
            "min_pct_change": float(policy.gap_min_pct),
            "min_price": float(policy.price_min),
            "max_price": float(policy.price_max),
            "max_float": int(policy.float_max_millions * 1_000_000),
            "min_rvol": float(policy.rvol_min),
            "min_volume": int(policy.min_volume),
            "min_premarket_volume": int(policy.min_premarket_volume),
            "require_catalyst": bool(policy.require_catalyst),
        }
    return {
        "min_pct_change": float(get_config("ROSS_MIN_PCT_CHANGE")),
        "min_price": float(get_config("ROSS_MIN_PRICE")),
        "max_price": float(get_config("ROSS_MAX_PRICE")),
        "max_float": int(get_config("ROSS_MAX_FLOAT")),
        "min_rvol": float(get_config("ROSS_MIN_RVOL")),
        "min_volume": int(get_config("ROSS_MIN_VOLUME")),
        "min_premarket_volume": int(get_config("ROSS_MIN_PREMARKET_VOLUME")),
        "require_catalyst": bool(get_config("ROSS_REQUIRE_NEWS")),
    }


def _news_gates() -> dict:
    return {
        "max_age_seconds": int(get_config("NEWS_MAX_AGE_SECONDS")),
        "min_velocity_10m": int(get_config("NEWS_MIN_VELOCITY_10M")),
        "min_regions": int(get_config("NEWS_MIN_REGIONS")),
    }


def evaluate_stock_selection_gates(
    entry: Any,
    require_catalyst_override: Optional[bool] = None,
    policy: StockSelectionPolicy | None = None,
) -> tuple[bool, list[str]]:
    gates = _mechanical_stock_selection_gates(policy=policy)
    if require_catalyst_override is not None:
        gates["require_catalyst"] = require_catalyst_override
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
    if pct < gates["min_pct_change"]:
        reasons.append("pct_change_below_min")
    if not (gates["min_price"] <= px <= gates["max_price"]):
        reasons.append("price_out_of_range")
    if flt is None or flt <= 0:
        reasons.append("float_missing")
    elif flt > gates["max_float"]:
        reasons.append("float_above_max")
    if rvol < gates["min_rvol"]:
        reasons.append("rvol_below_min")
    if session_label in {"PRE", "OVN"}:
        if vol < gates["min_premarket_volume"]:
            reasons.append("premarket_volume_below_min")
    elif vol < gates["min_volume"]:
        reasons.append("volume_below_min")
    if gates["require_catalyst"] and news_total <= 0:
        reasons.append("news_required_missing")

    return (len(reasons) == 0), reasons


def passes_stock_selection_gates(
    entry: Any,
    require_catalyst_override: Optional[bool] = None,
    policy: StockSelectionPolicy | None = None,
) -> bool:
    passed, _ = evaluate_stock_selection_gates(
        entry,
        require_catalyst_override=require_catalyst_override,
        policy=policy,
    )
    return passed


def evaluate_catalyst_eligibility(entry: Any, bypass: bool = False) -> tuple[bool, list[str]]:
    if bypass:
        return True, []
    gates = _news_gates()
    total = _safe_float(_get_value(entry, "news_total_headlines"), 0.0) or 0.0
    vel10 = _safe_float(_get_value(entry, "news_velocity_10m"), 0.0) or 0.0
    freshest = _safe_float(_get_value(entry, "news_freshest_age_minutes"), None)
    spike = _get_value(entry, "news_spike_indicator") is True
    region_count = _safe_float(_get_value(entry, "news_region_count"), 0.0) or 0.0

    if total <= 0:
        return False, ["news_total_missing"]
    if vel10 < gates["min_velocity_10m"]:
        return False, ["news_velocity_below_min"]
    if freshest is None or freshest * 60 > gates["max_age_seconds"]:
        return False, ["news_too_old"]
    if not (spike or vel10 >= 2):
        return False, ["news_spike_missing"]
    if region_count < gates["min_regions"]:
        return False, ["news_regions_below_min"]
    return True, []


def passes_catalyst_eligibility(entry: Any, bypass: bool = False) -> bool:
    passed, _ = evaluate_catalyst_eligibility(entry, bypass=bypass)
    return passed


def evaluate_filters(
    entry: Any,
    require_catalyst_override: Optional[bool] = None,
    bypass_news_gates: bool = False,
    policy: StockSelectionPolicy | None = None,
) -> tuple[bool, list[str]]:
    passed_gates, gate_reasons = evaluate_stock_selection_gates(
        entry, require_catalyst_override=require_catalyst_override, policy=policy
    )
    if not passed_gates:
        return False, gate_reasons
    passed_catalyst, catalyst_reasons = evaluate_catalyst_eligibility(
        entry, bypass=bypass_news_gates
    )
    if not passed_catalyst:
        return False, catalyst_reasons
    return True, []
