from __future__ import annotations

from src.core.time.trading_windows import TradingWindowDecision
from src.strategies.ross_momentum.time_policy import resolve_ross_time_policy


def test_ross_dead_regime_blocks_entries() -> None:
    decision = TradingWindowDecision(
        inside_window=True,
        allow_new_entries=True,
        allow_management=True,
        force_exit_mode=False,
        force_flat=False,
        reason="inside",
    )
    overlay = resolve_ross_time_policy(symbol="AAPL", window_decision=decision, regime="DEAD")
    assert overlay.entries_allowed is False
    assert overlay.management_allowed is True


def test_ross_late_window_blocks_new_entries() -> None:
    decision = TradingWindowDecision(
        inside_window=True,
        allow_new_entries=False,
        allow_management=True,
        force_exit_mode=False,
        force_flat=False,
        reason="entry_cutoff_reached",
    )
    overlay = resolve_ross_time_policy(symbol="AAPL", window_decision=decision, regime="NORMAL")
    assert overlay.entries_allowed is False
    assert overlay.management_allowed is True


def test_ross_force_flat_blocks_and_forces_exit() -> None:
    decision = TradingWindowDecision(
        inside_window=True,
        allow_new_entries=False,
        allow_management=False,
        force_exit_mode=True,
        force_flat=True,
        reason="hard_flat_enforced",
    )
    overlay = resolve_ross_time_policy(symbol="AAPL", window_decision=decision, regime="FAST")
    assert overlay.entries_allowed is False
    assert overlay.management_allowed is False
    assert overlay.force_exit is True
