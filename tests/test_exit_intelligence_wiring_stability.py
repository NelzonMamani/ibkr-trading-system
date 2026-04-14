from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from src.config.config_resolver import set_config_overrides
from src.execution.execution_engine import ExecutionEngine


def _build_engine() -> ExecutionEngine:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": False})
    return ExecutionEngine()


def _trade(**overrides):
    payload = {
        "trade_id": "T-1",
        "symbol": "AAPL",
        "avg_fill_price": 100.0,
        "high_water_mark": 100.0,
        "last_update_ts": (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(),
        "filled_qty": 2,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_exit_evaluation_runs_once_per_interval(monkeypatch):
    engine = _build_engine()
    try:
        trade = _trade()
        engine._exit_eval_interval_sec = 60.0
        engine._evaluate_exit_intelligence(trade, 99.0)
        first_ts = engine._last_exit_eval_ts.get("AAPL")
        assert first_ts is not None
        engine._evaluate_exit_intelligence(trade, 98.0)
        second_ts = engine._last_exit_eval_ts.get("AAPL")
        assert second_ts == first_ts
    finally:
        set_config_overrides({})


def test_duplicate_exit_execution_is_blocked(monkeypatch):
    engine = _build_engine()
    try:
        calls = {"pending": 0, "exited": 0}
        monkeypatch.setattr(engine.post_fill_lifecycle, "mark_exit_pending", lambda *args, **kwargs: calls.__setitem__("pending", calls["pending"] + 1))
        monkeypatch.setattr(engine.post_fill_lifecycle, "mark_exited", lambda *args, **kwargs: calls.__setitem__("exited", calls["exited"] + 1))
        trade = _trade(exit_triggered=True)
        engine._evaluate_exit_intelligence(trade, 95.0)
        assert calls["pending"] == 0
        assert calls["exited"] == 0
    finally:
        set_config_overrides({})


def test_scale_out_never_reduces_below_one_share():
    engine = _build_engine()
    try:
        trade = _trade(filled_qty=2)
        engine._evaluate_exit_intelligence(trade, 103.0)
        assert trade.filled_qty == 1
    finally:
        set_config_overrides({})


def test_exit_logic_is_disabled_by_environment_toggle(monkeypatch):
    monkeypatch.setenv("EXIT_INTELLIGENCE_ENABLED", "0")
    engine = _build_engine()
    try:
        trade = _trade()
        engine._evaluate_exit_intelligence(trade, 95.0)
        assert "AAPL" not in engine._last_exit_eval_ts
        assert not getattr(trade, "exit_triggered", False)
    finally:
        set_config_overrides({})
