from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.learning.models import LearningDataset, LearningTrade
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


TUNABLE_FIELDS = {
    "price_min",
    "price_max",
    "gap_min_pct",
    "rvol_min",
    "float_max_millions",
    "min_volume",
    "min_premarket_volume",
    "spread_max_pct",
    "liquidity_min_dollar_volume",
    "require_catalyst",
}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        raise ValueError("No values available for percentile")
    sorted_vals = sorted(values)
    k = max(0, min(len(sorted_vals) - 1, int(round((pct / 100.0) * (len(sorted_vals) - 1)))))
    return float(sorted_vals[k])


def _collect_metric(trades: list[LearningTrade], key: str) -> list[float]:
    values: list[float] = []
    for trade in trades:
        value = trade.gate_context.get(key)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def propose_policy(
    *,
    baseline: RossMomentumPolicy,
    dataset: LearningDataset,
    min_trades: int,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    trades = dataset.trades
    if len(trades) < min_trades:
        return None, {}, {}
    baseline_dict = asdict(baseline)
    proposal = asdict(baseline)
    diff: dict[str, Any] = {}
    rationale: dict[str, Any] = {}

    winning = dataset.winning_trades()
    if not winning:
        return None, {}, {}

    stock_selection = proposal.get("stock_selection", {})
    base_stock = baseline_dict.get("stock_selection", {})

    field_map = {
        "price_min": ("last_price", 10.0, "min"),
        "price_max": ("last_price", 90.0, "max"),
        "gap_min_pct": ("gap_pct", 25.0, "min"),
        "rvol_min": ("rvol", 25.0, "min"),
        "float_max_millions": ("float_millions", 75.0, "max"),
        "min_volume": ("volume", 25.0, "min"),
        "min_premarket_volume": ("premarket_volume", 25.0, "min"),
        "spread_max_pct": ("spread_pct", 75.0, "max"),
        "liquidity_min_dollar_volume": ("dollar_volume", 25.0, "min"),
    }

    for field, (metric_key, pct, mode) in field_map.items():
        if field not in TUNABLE_FIELDS or field not in stock_selection:
            continue
        values = _collect_metric(winning, metric_key)
        if not values:
            continue
        proposed = _percentile(values, pct)
        if mode == "min":
            proposed = max(proposed, 0.0)
        current = base_stock.get(field)
        if current is None:
            continue
        delta = proposed - float(current)
        max_delta = abs(float(current) * 0.2)
        if abs(delta) > max_delta:
            proposed = float(current) + (max_delta if delta > 0 else -max_delta)
        if float(current) == float(proposed):
            continue
        stock_selection[field] = float(round(proposed, 4))
        diff[field] = {"old": current, "new": stock_selection[field]}
        rationale[field] = {
            "metric": metric_key,
            "percentile": pct,
            "sample": len(values),
        }

    proposal["stock_selection"] = stock_selection
    if diff:
        return proposal, diff, rationale
    return None, {}, {}


def validate_policy_schema(baseline: dict[str, Any], proposal: dict[str, Any]) -> bool:
    return set(baseline.keys()) == set(proposal.keys())
