from __future__ import annotations

import pytest

from src.config.config_resolver import set_config_overrides
from src.scanner.scanner_runner import (
    _evaluate_float_gate,
    _evaluate_focus_gates,
    _forced_premarket_focus_eligible,
    _gate_checks,
    _gate_thresholds,
    _resolve_runtime_thresholds,
)
from src.strategies.ross_momentum.policy import FloatQuality, PriceQuality, RossPolicy
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


@pytest.fixture(autouse=True)
def _reset_config_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


def _thresholds_for(session: str, *, mode: str = "LIVE"):
    set_config_overrides({"RUN_MODE": mode})
    policy = RossMomentumPolicy().stock_selection
    runtime = _resolve_runtime_thresholds(policy, session)
    return _gate_thresholds(policy, runtime)


def _focus_context(**overrides: object) -> dict[str, object]:
    context: dict[str, object] = {
        "symbol": "ROSSX",
        "session": "RTH_OPEN",
        "pct_change": 18.0,
        "scanner_rvol": 5.5,
        "rvol_phase": 5.5,
        "rvol_discovery": 5.5,
        "volume": 400_000,
        "premarket_volume": 400_000,
        "dollar_volume": 2_000_000,
        "last_price": 7.0,
        "float_shares": 8_000_000,
        "spread_pct": 0.01,
        "bid": 6.99,
        "ask": 7.01,
        "catalyst_present": True,
        "halted": False,
        "ssr": False,
    }
    context.update(overrides)
    return context


def test_ross_policy_exposes_pr2_selection_classifiers() -> None:
    policy = RossPolicy()

    assert policy.price.assess(7.0).quality == PriceQuality.PREFERRED_SWEET_SPOT
    assert policy.gap.discovery_threshold_for("RTH_OPEN") == 5.0
    assert policy.gap.focus_threshold_for("RTH_OPEN") == 10.0
    assert policy.gap.focus_threshold_for("PRE") == 5.0
    assert policy.rvol.focus_threshold_for("RTH_OPEN") == 2.5
    assert policy.rvol.focus_threshold_for("PRE") == 2.0
    assert policy.float.max_shares == 20_000_000


def test_live_runtime_ignores_legacy_relaxed_defaults() -> None:
    thresholds = _thresholds_for("RTH_OPEN", mode="LIVE")

    assert thresholds.min_pct_change == 5.0
    assert thresholds.focus_pct_change_min == 10.0
    assert thresholds.live_quality_pct_change_min == 10.0
    assert thresholds.focus_rvol_min == 2.5
    assert thresholds.max_float == 20_000_000
    assert thresholds.allow_unknown_float is False


def test_live_focus_rejects_rth_candidate_below_live_quality_pct() -> None:
    thresholds = _thresholds_for("RTH_OPEN", mode="LIVE")
    context = _focus_context(pct_change=7.0)

    assert _evaluate_focus_gates(context, thresholds) == "DROP_PCT_CHANGE_FOCUS"


def test_pre_focus_below_live_quality_is_labeled_session_adaptation() -> None:
    thresholds = _thresholds_for("PRE", mode="LIVE")
    context = _focus_context(
        session="PRE",
        pct_change=7.0,
        scanner_rvol=2.5,
        rvol_phase=2.5,
        rvol_discovery=2.5,
        volume=1_000_000,
        premarket_volume=1_000_000,
    )

    assert _evaluate_focus_gates(context, thresholds) is None
    assert context["pct_change_quality"] == "SESSION_ADAPTATION"
    assert context["selection_tier"] == "SESSION_ADAPTATION"
    assert context["execution_eligible"] is False


def test_unknown_float_blocks_live_but_explicit_validation_can_allow() -> None:
    live_thresholds = _thresholds_for("RTH_OPEN", mode="LIVE")
    live_context = _focus_context(float_shares=None)

    assert _evaluate_float_gate(live_context, live_thresholds) == "DROP_FLOAT_UNKNOWN"
    assert live_context["float_status"] == FloatQuality.UNKNOWN_FLOAT.value

    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "ROSS_VALIDATION_OVERRIDE_ENABLED": True,
            "ALLOW_UNKNOWN_FLOAT": True,
        }
    )
    policy = RossMomentumPolicy().stock_selection
    validation_thresholds = _gate_thresholds(
        policy,
        _resolve_runtime_thresholds(policy, "RTH_OPEN"),
    )
    validation_context = _focus_context(float_shares=None)

    assert _evaluate_float_gate(validation_context, validation_thresholds) is None
    assert validation_context["float_status"] == FloatQuality.UNKNOWN_FLOAT.value
    assert validation_context["float_tolerated"] is True


def test_focus_rvol_uses_session_policy_not_hardcoded_floor() -> None:
    thresholds = _thresholds_for("RTH_OPEN", mode="LIVE")
    context = _focus_context(scanner_rvol=2.0, rvol_phase=2.0, rvol_discovery=2.0)

    assert thresholds.focus_rvol_min == 2.5
    assert _evaluate_focus_gates(context, thresholds) == "DROP_RVOL_FOCUS"


def test_manual_focus_context_still_requires_final_live_gates() -> None:
    thresholds = _thresholds_for("RTH_OPEN", mode="LIVE")
    context = _focus_context(symbol_source="manual_focus", pct_change=7.0)

    assert _evaluate_focus_gates(context, thresholds) == "DROP_PCT_CHANGE_FOCUS"


def test_missing_live_catalyst_blocks_focus() -> None:
    thresholds = _thresholds_for("RTH_OPEN", mode="LIVE")
    context = _focus_context(catalyst_present=False, catalyst_status="DATA_UNAVAILABLE")

    assert _evaluate_focus_gates(context, thresholds) == "DROP_NO_CATALYST"


def test_selector_gate_checks_reject_price_range_drop() -> None:
    thresholds = _thresholds_for("RTH_OPEN", mode="LIVE")
    context = _focus_context(last_price=25.0)

    checks = _gate_checks(context, thresholds, catalyst_present=True)

    assert checks["watch_price"] is False


def test_forced_premarket_focus_rejects_missing_catalyst_drop() -> None:
    thresholds = _thresholds_for("PRE", mode="LIVE")
    context = _focus_context(
        session="PRE",
        pct_change=7.0,
        scanner_rvol=2.5,
        rvol_phase=2.5,
        rvol_discovery=2.5,
        volume=1_000_000,
        premarket_volume=1_000_000,
        catalyst_present=False,
        catalyst_status="DATA_UNAVAILABLE",
    )

    assert _evaluate_focus_gates(context, thresholds) == "DROP_NO_CATALYST"
    context["focus_drop_reason"] = "DROP_NO_CATALYST"

    assert _forced_premarket_focus_eligible(context, thresholds, session_label="PRE") is False


def test_forced_premarket_focus_rejects_price_range_drop() -> None:
    thresholds = _thresholds_for("PRE", mode="LIVE")
    context = _focus_context(
        session="PRE",
        pct_change=12.0,
        scanner_rvol=3.0,
        rvol_phase=3.0,
        rvol_discovery=3.0,
        volume=1_000_000,
        premarket_volume=1_000_000,
        last_price=25.0,
    )

    context["focus_drop_reason"] = "DROP_PRICE_RANGE"

    assert _forced_premarket_focus_eligible(context, thresholds, session_label="PRE") is False


def test_price_sweet_spot_improves_ranking_without_overriding_gates() -> None:
    strategy = RossMomentumStrategy()
    ranked = strategy.rank_candidates(
        [
            {"symbol": "WIDE", "pct_change": 15.0, "rvol": 4.0, "float_millions": 8.0, "last_price": 17.0},
            {"symbol": "SWEET", "pct_change": 15.0, "rvol": 4.0, "float_millions": 8.0, "last_price": 7.0},
        ]
    )

    assert ranked[0]["symbol"] == "SWEET"
