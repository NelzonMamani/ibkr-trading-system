from __future__ import annotations

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.strategies.ross_momentum import strategy_policy
from src.strategies.ross_momentum.policy import RossPolicy
from src.strategies.ross_momentum.policy.catalyst_policy import (
    CatalystStatus,
    assess_catalyst,
)
from src.strategy.strategy_runner import StrategyRunner


@pytest.fixture(autouse=True)
def _reset_config_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


class _NoOpRossStrategy:
    name = "RossMomentumStrategyV1"

    def process_watchlist(self, **_kwargs):
        return []


def _base_overrides(mode: str, validation: bool) -> dict[str, object]:
    return {
        "RUN_MODE": mode,
        "SELECTED_STRATEGY": "ross_momentum",
        "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
        "SCANNER_DATA_SOURCE": "MOCK",
        "ROSS_VALIDATION_OVERRIDE_ENABLED": validation,
        "LIVE_EXECUTION_PROBE_MODE": False,
    }


def test_ross_policy_facade_exposes_expected_sections() -> None:
    policy = RossPolicy()

    assert policy.stock_selection.policy_name == "ROSS_MOMENTUM"
    assert policy.rvol.focus_min == policy.stock_selection.focus_rvol_min
    assert policy.gap.min_pct == policy.stock_selection.gap_min_pct
    assert policy.float.max_millions == policy.stock_selection.float_max_millions
    assert policy.catalyst.require_catalyst is True
    assert policy.watchlist.watchlist_limit_k == policy.stock_selection.watchlist_limit_k
    assert "candles_10s_1m_5m" in policy.pattern_inputs.required_fields
    assert policy.execution_timing.opening.execution_tf == "10SEC"
    assert policy.exit.exit_model is policy.policy_v2.exit_model


def test_strategy_policy_compatibility_imports_still_work() -> None:
    assert strategy_policy.POLICY_V2.identity.strategy_id
    assert strategy_policy.CANONICAL_POLICY.name == "ROSS_MOMENTUM"
    assert strategy_policy.ROSS_POLICY.name == "ROSS_MOMENTUM"
    assert strategy_policy.RossStockSelectionPolicy is strategy_policy.StockSelectionSpec
    assert callable(strategy_policy.select_watchlist)
    assert callable(strategy_policy.timeframe_plan_for_session_phase)
    assert callable(strategy_policy.stock_selection_policy_for_session_phase)


def test_live_validation_override_is_blocked(capsys, monkeypatch) -> None:
    from src import main as main_module

    original_cls = strategy_policy.RossMomentumPolicy
    baseline = original_cls()
    monkeypatch.setattr(strategy_policy, "CANONICAL_POLICY", baseline)
    monkeypatch.setattr(strategy_policy, "ROSS_POLICY", baseline)
    monkeypatch.setattr(strategy_policy, "RossMomentumPolicy", original_cls)
    set_config_overrides(_base_overrides("LIVE", True))

    main_module._apply_temp_validation_override(RunMode.LIVE)

    captured = capsys.readouterr().out
    assert "[ROSS][VALIDATION_OVERRIDE][BLOCKED] mode=LIVE reason=not_live_safe" in captured
    assert strategy_policy.CANONICAL_POLICY.stock_selection.require_catalyst is True
    assert strategy_policy.CANONICAL_POLICY.stock_selection.focus_rvol_min == 2.0


def test_paper_validation_override_requires_explicit_flag(capsys, monkeypatch) -> None:
    from src import main as main_module

    original_cls = strategy_policy.RossMomentumPolicy
    baseline = original_cls()
    monkeypatch.setattr(strategy_policy, "CANONICAL_POLICY", baseline)
    monkeypatch.setattr(strategy_policy, "ROSS_POLICY", baseline)
    monkeypatch.setattr(strategy_policy, "RossMomentumPolicy", original_cls)
    set_config_overrides(_base_overrides("PAPER", True))

    try:
        main_module._apply_temp_validation_override(RunMode.PAPER)
        captured = capsys.readouterr().out
        assert "[ROSS][VALIDATION_OVERRIDE][ACTIVE] mode=PAPER" in captured
        assert strategy_policy.CANONICAL_POLICY.stock_selection.require_catalyst is False
        assert strategy_policy.CANONICAL_POLICY.stock_selection.focus_rvol_min == 0.2
    finally:
        monkeypatch.setattr(strategy_policy, "CANONICAL_POLICY", baseline)
        monkeypatch.setattr(strategy_policy, "ROSS_POLICY", baseline)
        monkeypatch.setattr(strategy_policy, "RossMomentumPolicy", original_cls)


def test_live_strategy_runner_blocks_synthetic_intent(capsys) -> None:
    set_config_overrides(_base_overrides("LIVE", False))
    runner = StrategyRunner(strategies=[_NoOpRossStrategy()])

    intents = runner.process(
        strategy_key="ross_momentum",
        watchlist=[{"symbol": "ROSSX"}],
        snapshots={},
        session_label="RTH",
        timestamp_utc="2026-06-12T12:00:00Z",
        mode=RunMode.LIVE,
        session_phase="RTH_OPEN",
    )

    captured = capsys.readouterr().out
    assert intents == []
    assert "[ROSS][NO_SETUP][NO_TRADE] symbol=ROSSX reason=NO_TRIGGER_PIPELINE" in captured
    assert "[ROSS][FALLBACK_INTENT][BLOCKED] mode=LIVE reason=real_setup_required" in captured


def test_paper_strategy_runner_allows_synthetic_intent_only_with_flag(capsys) -> None:
    set_config_overrides(_base_overrides("PAPER", True))
    runner = StrategyRunner(strategies=[_NoOpRossStrategy()])

    intents = runner.process(
        strategy_key="ross_momentum",
        watchlist=[{"symbol": "ROSSX"}],
        snapshots={},
        session_label="RTH",
        timestamp_utc="2026-06-12T12:00:00Z",
        mode=RunMode.PAPER,
        session_phase="RTH_OPEN",
    )

    captured = capsys.readouterr().out
    assert len(intents) == 1
    assert getattr(intents[0], "synthetic", False) is True
    assert "[ROSS][VALIDATION_OVERRIDE][ACTIVE] mode=PAPER reason=strategy_runner_synthetic_intent" in captured


def test_live_cannot_treat_news_unavailable_as_catalyst_true() -> None:
    live_decision = assess_catalyst(
        mode=RunMode.LIVE,
        news_enabled=False,
        news_available=False,
        confirmed=None,
        validation_bypass_requested=True,
    )
    paper_decision = assess_catalyst(
        mode=RunMode.PAPER,
        news_enabled=False,
        news_available=False,
        confirmed=None,
        validation_bypass_requested=True,
    )

    assert live_decision.status == CatalystStatus.DATA_UNAVAILABLE
    assert live_decision.satisfied is False
    assert paper_decision.status == CatalystStatus.DISABLED_FOR_VALIDATION
    assert paper_decision.satisfied is True
