"""Ross Momentum stock selection application."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, List, Tuple

from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec


def _get(candidate: Any, key: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _evaluate_candidate(
    policy: StockSelectionSpec,
    candidate: Any,
    session_context: str,
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    pct = _safe_float(_get(candidate, "pct_change"))
    price = _safe_float(_get(candidate, "last_price"))
    rvol = _safe_float(_get(candidate, "rvol"))
    volume = _safe_float(_get(candidate, "volume"))
    float_shares = _safe_int(_get(candidate, "float_shares"))
    dollar_volume = _safe_float(_get(candidate, "dollar_volume"))
    spread_pct = _safe_float(_get(candidate, "spread_pct"))
    halted = _get(candidate, "halted")
    ssr = _get(candidate, "ssr")
    catalyst = bool(_get(candidate, "catalyst_present"))

    if pct is None:
        reasons.append("missing_pct_change")
    elif pct < policy.gap_min_pct:
        reasons.append("pct_change_below_min")
    if policy.gap_max_pct is not None and pct is not None and pct > policy.gap_max_pct:
        reasons.append("pct_change_above_max")

    if price is None:
        reasons.append("missing_price")
    elif not (policy.price_min <= price <= policy.price_max):
        reasons.append("price_out_of_range")

    if float_shares is None or float_shares <= 0:
        reasons.append("float_missing")
    elif float_shares > int(policy.float_max_millions * 1_000_000):
        reasons.append("float_above_max")

    if rvol is None:
        reasons.append("missing_rvol")
    elif rvol < policy.rvol_min:
        reasons.append("rvol_below_min")

    if volume is None:
        reasons.append("missing_volume")
    else:
        if session_context in {"PRE", "PREMARKET"}:
            if volume < policy.min_premarket_volume:
                reasons.append("premarket_volume_below_min")
        elif volume < policy.min_volume:
            reasons.append("volume_below_min")

    if policy.liquidity_min_dollar_volume is not None:
        if dollar_volume is None:
            reasons.append("missing_dollar_volume")
        elif dollar_volume < policy.liquidity_min_dollar_volume:
            reasons.append("dollar_volume_below_min")

    if policy.spread_max_pct is not None:
        if spread_pct is None:
            reasons.append("missing_spread")
        elif spread_pct > policy.spread_max_pct:
            reasons.append("spread_above_max")

    if policy.require_catalyst and not catalyst:
        reasons.append("catalyst_missing")

    if halted is True and not policy.allow_halts:
        reasons.append("halted")
    if ssr is True and not policy.allow_ssr:
        reasons.append("ssr")

    return (len(reasons) == 0), reasons


def _sort_key(candidate: Any) -> tuple:
    pct = _safe_float(_get(candidate, "pct_change")) or -10**9
    rvol = _safe_float(_get(candidate, "rvol")) or -10**9
    float_shares = _safe_int(_get(candidate, "float_shares"))
    float_sort = float_shares if float_shares is not None else 10**9
    symbol = _get(candidate, "symbol", "")
    return (-pct, -rvol, float_sort, symbol)


def apply_ross_stock_selection(
    policy: StockSelectionSpec,
    candidates: Iterable[Any],
    session_context: str,
) -> dict[str, Any]:
    eligible: List[Any] = []
    drop_ledger: dict[str, str] = {}
    for candidate in candidates:
        symbol = _get(candidate, "symbol")
        passed, reasons = _evaluate_candidate(policy, candidate, session_context)
        if not passed:
            if symbol:
                drop_ledger[symbol] = reasons[0]
            continue
        eligible.append(candidate)

    ranked = sorted(eligible, key=_sort_key)
    watchlist_limit = max(int(policy.watchlist_limit_k), 0)
    focus_limit = max(int(policy.focus_limit_m), 0)
    if watchlist_limit and focus_limit > watchlist_limit:
        focus_limit = watchlist_limit

    watchlist = ranked[:watchlist_limit] if watchlist_limit else ranked
    focus = watchlist[:focus_limit] if focus_limit else []

    for candidate in ranked[watchlist_limit:]:
        symbol = _get(candidate, "symbol")
        if symbol and symbol not in drop_ledger:
            drop_ledger[symbol] = "rank_below_watchlist"

    drop_summary = dict(Counter(drop_ledger.values()))
    return {
        "watchlist_k": watchlist,
        "focus_m": focus,
        "drop_ledger": drop_ledger,
        "drop_summary": drop_summary,
    }
