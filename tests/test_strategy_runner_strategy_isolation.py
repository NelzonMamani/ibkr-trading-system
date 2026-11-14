"""Dispatch isolation using real registered adapters, never prepared intents."""

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.strategy.strategy_runner import StrategyRunner


@pytest.fixture(autouse=True)
def config():
    set_config_overrides(None)
    yield
    set_config_overrides(None)


def configure(selected, **overrides):
    set_config_overrides({
        "SELECTED_STRATEGY": selected,
        "ROSS_MOMENTUM_STRATEGY_ENABLED": False,
        "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED": True,
        "MEAN_REVERSION_STRATEGY_ENABLED": True,
        "RUN_MODE": "SIM", "SCANNER_DATA_SOURCE": "IBKR",
        "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
        "LIVE_EXECUTION_PROBE_MODE": False,
        **overrides,
    })


def dispatch(runner, key, *, mode=RunMode.SIM, candidate=None):
    return runner.process(
        strategy_key=key, watchlist=[candidate or {"symbol": "TEST"}],
        snapshots={}, session_label="RTH", timestamp_utc="2026-11-13T16:30:00+00:00",
        mode=mode, session_phase="RTH_MID",
    )


def eligible_candidate(**changes):
    return {"symbol": "TEST", "last_price": 100., "gap_pct": 8., "rvol": 3.,
            "dollar_volume": 50_000_000., "bid": 99.99, "ask": 100.01,
            "float_millions": 50., "data_quality_flags": [], **changes}


@pytest.mark.parametrize("key", ["statistical_intraday_momentum", "mean_reversion"])
def test_non_ross_reaches_its_actual_adapter_with_ross_disabled(key, capsys):
    configure(key)
    runner = StrategyRunner()
    assert len(runner.strategies) == 1
    assert dispatch(runner, key) == []
    out = capsys.readouterr().out
    expected = "[SIMOM][EVAL]" if key.startswith("statistical") else "[MEAN_REVERSION][CYCLE]"
    assert expected in out
    assert "[STRATEGY_RUNNER] invoking RossMomentumStrategyV1" not in out


def test_selected_disabled_ross_still_fails_closed():
    configure("ross_momentum")
    runner = StrategyRunner()
    assert runner.strategies == []
    with pytest.raises(RuntimeError, match="ROSS STRATEGY DISABLED"):
        dispatch(runner, "ross_momentum")


def test_ross_disabled_after_registration_cannot_dispatch_in_mixed_batch(capsys):
    configure("ross_momentum", ROSS_MOMENTUM_STRATEGY_ENABLED=True)
    runner = StrategyRunner()
    assert runner.strategies[0].name == "RossMomentumStrategyV1"
    configure("statistical_intraday_momentum")
    # Stale/injected registry must not bypass the current per-owner enable flag.
    assert dispatch(runner, "statistical_intraday_momentum") == []
    assert "[STRATEGY_RUNNER] invoking RossMomentumStrategyV1" not in capsys.readouterr().out


def test_current_p02_sim_adapter_emits_own_intent_without_ross():
    configure("statistical_intraday_momentum")
    intents = dispatch(StrategyRunner(), "statistical_intraday_momentum", candidate=eligible_candidate())
    assert len(intents) == 1
    assert intents[0].strategy_name == "StatisticalIntradayMomentum"
    assert not intents[0].synthetic
    assert intents[0].stop_loss_price == 99.
    assert intents[0].take_profit_price == 102.
    # This is the existing gap/RVOL adapter contract, not the disconnected
    # bar-based statistical signal engine or a positive Core execution proof.


@pytest.mark.parametrize("ross_enabled", [False, True])
@pytest.mark.parametrize("changes", [{"rvol": 1.49}, {"gap_pct": 1.99},
    {"dollar_volume": 19_999_999.}, {"data_quality_flags": ["MD_TIMEOUT"]}])
def test_p02_adapter_rejections_do_not_inherit_ross_fallback(changes, ross_enabled, monkeypatch):
    configure("statistical_intraday_momentum", SCANNER_DATA_SOURCE="MOCK",
              ROSS_MOMENTUM_STRATEGY_ENABLED=ross_enabled,
              ROSS_VALIDATION_OVERRIDE_ENABLED=True)
    monkeypatch.setenv("FORCE_EXECUTION_WINDOW", "1")
    assert dispatch(StrategyRunner(), "statistical_intraday_momentum",
                    candidate=eligible_candidate(**changes)) == []


def test_p02_default_activation_veto_is_preserved_in_paper():
    configure("statistical_intraday_momentum", RUN_MODE="PAPER")
    assert dispatch(StrategyRunner(), "statistical_intraday_momentum", mode=RunMode.PAPER,
                    candidate=eligible_candidate()) == []


def test_real_p02_adapter_outputs_obey_existing_e22_budget():
    from src.e22.strategy_scalability_and_arbitration import E22PolicyConfig, apply_e22_arbitration_layer
    configure("statistical_intraday_momentum")
    runner = StrategyRunner()
    produced = runner.process(
        strategy_key="statistical_intraday_momentum",
        watchlist=[eligible_candidate(), eligible_candidate(symbol="PEER")], snapshots={},
        session_label="RTH", timestamp_utc="2026-11-13T16:30:00+00:00",
        mode=RunMode.SIM, session_phase="RTH_MID",
    )
    assert len(produced) == 2
    allowed, artifact = apply_e22_arbitration_layer(produced, E22PolicyConfig(
        enabled=True, strategy_max_intents={"StatisticalIntradayMomentum": 1},
    ))
    assert len(allowed) == 1
    assert any(allowed[0] is intent for intent in produced)
    assert artifact.suppression_counts_by_reason_code["BUDGET_DENY"] == 1
    assert all(intent.strategy_name == "StatisticalIntradayMomentum" for intent in produced)
