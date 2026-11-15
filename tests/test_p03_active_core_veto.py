"""Actual Core retains P03 policy vetoes; this is no positive admission proof."""
from test_pr1082_rth_watchlist_continuity import (
    _install_runtime_harness, _row, _payload, _reset_config,
)
from test_flat_top_production_handoff import forbid_collection_and_execution, forbid_io
from src.strategy.strategy_runner import StrategyRunner


def test_actual_core_preserves_p03_all_veto_without_fallback(monkeypatch, capsys):
    row = _row("TEST")
    # Measurements alone do not establish the required regime/entry contract.
    row.last_price = 100.
    row.bid, row.ask, row.spread = 99.99, 100.01, .02
    row.atr, row.vwap, row.ema9, row.ema20 = 1., 102., 102., 102.
    core, scanner_calls, _ = _install_runtime_harness(
        monkeypatch, [_payload([row], focus=[row])], run_mode="SIM",
        config_overrides={
            "SELECTED_STRATEGY": "mean_reversion",
            "ROSS_MOMENTUM_STRATEGY_ENABLED": False,
            "MEAN_REVERSION_STRATEGY_ENABLED": True,
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
        proposed = list(intents)
        result = real_integrity(proposed)
        received.append((proposed, list(result)))
        return result

    monkeypatch.setattr(core, "_enforce_ross_execution_integrity", observed_integrity)
    assert core.run_once()
    out = capsys.readouterr().out
    assert len(scanner_calls) == len(received) == 1
    assert received == [([], [])]
    assert "[MEAN_REVERSION][EVAL] symbol=TEST decision=SKIP" in out
    assert "[MEAN_REVERSION][FALLBACK]" not in out
    assert "[MEAN_REVERSION][SIGNAL]" not in out
    assert core.trade_registry.count_active() == 0
    assert core.execution_engine._native_orders == {}
