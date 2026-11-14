"""Actual active Core preserves its contract veto for incomplete P02 adapter output.

This is a demonstrated veto, not positive statistical strategy integration. The
inherited harness supplies synthetic scanner facts and isolates housekeeping;
real StrategyRunner/adapter and actual Core integrity owner remain exercised.
"""
from test_pr1082_rth_watchlist_continuity import (
    _install_runtime_harness, _row, _payload, _reset_config,
)
from test_flat_top_production_handoff import forbid_collection_and_execution, forbid_io
from src.strategy.strategy_runner import StrategyRunner


def test_actual_core_retains_incomplete_p02_contract_veto(monkeypatch, capsys):
    row = _row("TEST")
    row.last_price = 100.
    row.bid, row.ask, row.spread = 99.99, 100.01, .02
    row.dollar_volume, row.gap_pct, row.data_quality_flags = 50_000_000., 8., []
    core, scanner_calls, _ = _install_runtime_harness(
        monkeypatch, [_payload([row], focus=[row])], run_mode="SIM",
        config_overrides={
            "SELECTED_STRATEGY": "statistical_intraday_momentum",
            "ROSS_MOMENTUM_STRATEGY_ENABLED": False,
            "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED": True,
            "SCANNER_DATA_SOURCE": "IBKR",
            "LIVE_EXECUTION_PROBE_MODE": False,
            "FORCE_EXECUTION_ON_TRADE_READY": False,
            "FORCE_RISK_APPROVAL_FOR_TRADE_READY": False,
        },
    )
    core.strategy_runner.process = StrategyRunner.process.__get__(core.strategy_runner)
    received = []
    real_integrity = core._enforce_ross_execution_integrity

    def observed_integrity(intents):
        result = real_integrity(intents)
        received.append((list(intents), list(result)))
        return result

    monkeypatch.setattr(core, "_enforce_ross_execution_integrity", observed_integrity)
    assert core.run_once()
    out = capsys.readouterr().out
    assert len(scanner_calls) == len(received) == 1
    proposals, retained = received[0]
    assert len(proposals) == 1 and retained == []
    intent = proposals[0]
    assert intent.strategy_name == "StatisticalIntradayMomentum" and not intent.synthetic
    assert intent.setup_family_id is None and intent.trigger_id is None
    assert intent.invalidation_level is None
    assert not getattr(intent, "has_valid_pattern", False)
    assert "[SIMOM][SIGNAL]" in out
    assert "[ROSS][EXECUTION][REJECT] reason=PATTERN_INVALID symbol=TEST" in out
    assert core.trade_registry.count_active() == 0
    assert core.execution_engine._native_orders == {}
    # Safety/transport guards forbid dispatch; no mocked risk ALLOW, forced
    # native contract or conversion of this veto into an execution success.
