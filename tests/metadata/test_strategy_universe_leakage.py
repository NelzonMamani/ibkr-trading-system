from __future__ import annotations

from _strategy_policy_verifier import (
    catalogue_strategy_entries,
    load_strategy_policy,
    stock_selection_of,
    universe_marker,
)


def test_strategy_universe_leakage_controls() -> None:
    failures: list[str] = []

    for strategy_id, slug in catalogue_strategy_entries():
        policy = load_strategy_policy(slug)
        selection = stock_selection_of(policy)
        universe = universe_marker(policy)

        if not universe:
            failures.append(f"{strategy_id}:{slug} missing explicit universe source")
            continue

        if slug.startswith("long_horizon"):
            if isinstance(selection, dict):
                scan_code = selection.get("ibkr_scan_code")
            else:
                scan_code = getattr(getattr(selection, "universe", None), "ibkr_scan_code", None)
            if universe == "IBKR_TOP_GAINERS" or str(scan_code or "").upper() == "TOP_PERC_GAIN":
                failures.append(
                    f"{strategy_id}:{slug} long-horizon strategy must not use TOP_PERC_GAIN universe by default"
                )

        if slug == "mean_reversion":
            ranking_intent = str(selection.get("ranking_intent", "") if isinstance(selection, dict) else getattr(selection, "ranking_intent", "")).upper()
            if "MEAN_REVERSION" not in ranking_intent:
                failures.append(
                    f"{strategy_id}:{slug} must explicitly declare mean-reversion ranking intent"
                )

        ross_gate_fields = ["gap_min_pct", "rvol_min", "float_max_millions"]
        has_ross_like_gates = any((field in selection) if isinstance(selection, dict) else hasattr(selection, field) for field in ross_gate_fields)
        has_policy_name = ("policy_name" in selection) if isinstance(selection, dict) else hasattr(selection, "policy_name")
        if has_ross_like_gates and not has_policy_name:
            failures.append(
                f"{strategy_id}:{slug} uses Ross-like scanner gates without explicit policy_name declaration"
            )

    assert not failures, "\n".join(failures)
