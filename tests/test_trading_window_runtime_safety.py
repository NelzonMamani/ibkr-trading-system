from datetime import datetime, timezone

from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from src.core.trading_window import (
    build_trading_window_policy,
    resolve_trading_window_decision,
)
from src.core.event_collector import EventCollector
from src.execution.execution_engine import ExecutionEngine


def _utc(y: int, m: int, d: int, hh: int, mm: int) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_trading_window_invariant_hard_flat_before_window_end() -> None:
    now = _utc(2026, 1, 5, 18, 0)  # 13:00 NY (EST)
    policy = build_trading_window_policy(now)
    assert policy.window_start < policy.entry_cutoff <= policy.manage_until < policy.hard_flat_time < policy.window_end


def test_runtime_rebuild_enforces_flat_after_close() -> None:
    before_close = _utc(2026, 1, 5, 20, 58)  # 15:58 NY (EST)
    after_close = _utc(2026, 1, 5, 21, 1)  # 16:01 NY (EST)

    pre_close_policy = build_trading_window_policy(before_close)
    pre_close_decision = resolve_trading_window_decision(pre_close_policy, before_close)
    assert pre_close_decision.force_flat is False

    post_close_policy = build_trading_window_policy(after_close)
    post_close_decision = resolve_trading_window_decision(post_close_policy, after_close)
    assert post_close_decision.force_flat is True
    assert post_close_decision.reason == "outside_window_force_flat"


def test_execution_engine_force_flatten_symbol_liquidates_open_trade(monkeypatch) -> None:
    monkeypatch.setenv("RUN_MODE", "PAPER")
    monkeypatch.setenv("EXECUTION_ENABLED", "True")
    registry = ActiveTradeRegistry()
    registry.register_trade(
        ActiveTrade(
            symbol="AAPL",
            trader_type="SYSTEM",
            entry_tick=1,
            entry_price=100.0,
            direction="LONG",
            quantity=10,
            strategy_name="ross_momentum",
            stop_loss_price=99.0,
        )
    )
    engine = ExecutionEngine(trade_registry=registry, event_collector=EventCollector())
    flattened = engine.force_flatten_symbol("AAPL", reason="outside_window_force_flat")
    assert flattened is True
    assert registry.get_trade("AAPL", "SYSTEM") is None
