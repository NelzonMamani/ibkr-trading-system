from __future__ import annotations

from _strategy_policy_verifier import (
    catalogue_strategy_entries,
    load_strategy_policy,
    stock_selection_of,
)


def _has_field(obj: object, field: str) -> bool:
    if isinstance(obj, dict):
        return field in obj
    return hasattr(obj, field)


def _missing_sections(policy: object) -> list[str]:
    missing: list[str] = []
    selection = stock_selection_of(policy)

    has_universe = any(
        _has_field(selection, field)
        for field in ("universe", "universe_source", "source")
    )
    has_caps = any(
        _has_field(selection, field)
        for field in ("top_gainers_n", "watchlist_limit_k", "focus_limit_m", "top_n")
    )
    if not (has_universe and has_caps):
        missing.append("stock_selection(universe+caps)")

    has_risk = hasattr(policy, "risk_policy") or hasattr(policy, "risk") or hasattr(
        policy, "max_consecutive_losses"
    )
    if not has_risk:
        missing.append("risk_policy")

    has_execution = hasattr(policy, "execution_policy") or hasattr(
        policy, "order_type_primary"
    ) or hasattr(policy, "allow_market_orders")
    if not has_execution:
        missing.append("execution_policy")

    has_setup = any(
        hasattr(policy, field)
        for field in (
            "setup_families",
            "allowed_setup_families",
            "detectors",
            "allowed_entry_triggers",
            "required_conditions",
        )
    )
    if not has_setup:
        missing.append("setup_families/detectors/triggers")

    return missing


def test_strategy_policy_completeness() -> None:
    failures: list[str] = []
    for strategy_id, slug in catalogue_strategy_entries():
        policy = load_strategy_policy(slug)
        missing = _missing_sections(policy)
        if missing:
            failures.append(f"{strategy_id}:{slug} missing={','.join(missing)}")

    assert not failures, "\n".join(failures)
