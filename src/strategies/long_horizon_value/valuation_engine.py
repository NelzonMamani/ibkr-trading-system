from __future__ import annotations

from dataclasses import dataclass

# Layer 4 interim bands until full policy band wiring (later layer).
STRONG_BUY_MOS_THRESHOLD = 0.30
BUY_MOS_THRESHOLD = 0.15
HOLD_MOS_THRESHOLD = 0.05


@dataclass(frozen=True)
class ValuationSnapshot:
    scenario_set: tuple[str, ...]
    intrinsic_value_by_scenario: dict[str, float]
    weighted_intrinsic_value: float
    price: float | None
    implied_margin_of_safety: float | None
    action_band: str


def compute_valuation_snapshot(
    *,
    symbol: str,
    context,
    default_scenarios: tuple[str, ...],
) -> tuple[ValuationSnapshot | None, list[str]]:
    price_payload = _context_value(context, "price_by_symbol")
    if not isinstance(price_payload, dict):
        price_payload = _context_value(context, "last_price_by_symbol")

    intrinsic_payload = _context_value(context, "intrinsic_value_by_symbol")

    missing: list[str] = []
    if not isinstance(intrinsic_payload, dict):
        missing.append("intrinsic_value_by_symbol")
        return None, missing

    symbol_intrinsic = intrinsic_payload.get(symbol)
    if not isinstance(symbol_intrinsic, dict):
        missing.append("intrinsic_value_by_symbol")
        return None, missing

    normalized_intrinsic = _normalize_float_map(symbol_intrinsic)
    if not normalized_intrinsic:
        missing.append("intrinsic_value_by_symbol")
        return None, missing

    scenario_set = tuple(s.upper() for s in default_scenarios) or tuple(sorted(normalized_intrinsic.keys()))
    if not scenario_set:
        scenario_set = tuple(sorted(normalized_intrinsic.keys()))

    filtered_intrinsic = {scenario: normalized_intrinsic[scenario] for scenario in scenario_set if scenario in normalized_intrinsic}
    if not filtered_intrinsic:
        filtered_intrinsic = {k: normalized_intrinsic[k] for k in sorted(normalized_intrinsic.keys())}
        scenario_set = tuple(filtered_intrinsic.keys())

    weights_payload = _context_value(context, "scenario_weights")
    weights = _resolve_weights(weights_payload=weights_payload, scenario_set=scenario_set)
    weighted_intrinsic = sum(filtered_intrinsic[scenario] * weights[scenario] for scenario in filtered_intrinsic)

    price = _safe_float(price_payload.get(symbol)) if isinstance(price_payload, dict) else None
    mos = None
    if price is not None and price > 0:
        mos = (weighted_intrinsic - price) / price

    return (
        ValuationSnapshot(
            scenario_set=scenario_set,
            intrinsic_value_by_scenario=filtered_intrinsic,
            weighted_intrinsic_value=float(weighted_intrinsic),
            price=price,
            implied_margin_of_safety=mos,
            action_band=classify_action_band(mos),
        ),
        missing,
    )


def classify_action_band(margin_of_safety: float | None) -> str:
    if margin_of_safety is None:
        return "UNKNOWN_PRICE"
    if margin_of_safety >= STRONG_BUY_MOS_THRESHOLD:
        return "STRONG_BUY_MOS"
    if margin_of_safety >= BUY_MOS_THRESHOLD:
        return "BUY_MOS"
    if margin_of_safety >= HOLD_MOS_THRESHOLD:
        return "HOLD_MOS"
    return "AVOID_MOS"


def _resolve_weights(*, weights_payload, scenario_set: tuple[str, ...]) -> dict[str, float]:
    normalized_weights = _normalize_float_map(weights_payload) if isinstance(weights_payload, dict) else {}
    selected = {scenario: normalized_weights[scenario] for scenario in scenario_set if scenario in normalized_weights and normalized_weights[scenario] > 0.0}
    if not selected:
        equal_weight = 1.0 / float(len(scenario_set))
        return {scenario: equal_weight for scenario in scenario_set}

    total = sum(selected.values())
    return {scenario: selected.get(scenario, 0.0) / total for scenario in scenario_set}


def _normalize_float_map(payload: dict) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, value in payload.items():
        numeric = _safe_float(value)
        if numeric is None:
            continue
        normalized[str(key).upper()] = numeric
    return normalized


def _context_value(context, key: str):
    if isinstance(context, dict):
        return context.get(key)
    return getattr(context, key, None)


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
