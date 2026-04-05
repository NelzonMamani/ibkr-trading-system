from __future__ import annotations

from dataclasses import asdict, dataclass

from src.core.time.trading_windows import TradingWindowDecision


@dataclass(frozen=True)
class RossTimePolicyDecision:
    symbol: str
    regime: str
    entries_allowed: bool
    management_allowed: bool
    force_exit: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_ross_time_policy(*, symbol: str, window_decision: TradingWindowDecision, regime: str) -> RossTimePolicyDecision:
    regime_value = str(regime or "NORMAL").upper()
    if window_decision.force_flat:
        return RossTimePolicyDecision(symbol, regime_value, False, False, True, "trading_window_force_flat")
    if window_decision.force_exit_mode:
        return RossTimePolicyDecision(symbol, regime_value, False, False, True, "trading_window_force_exit_mode")
    if regime_value == "DEAD":
        return RossTimePolicyDecision(symbol, regime_value, False, window_decision.allow_management, False, "regime_dead_entries_blocked")
    if not window_decision.allow_new_entries:
        return RossTimePolicyDecision(symbol, regime_value, False, window_decision.allow_management, False, "trading_window_entry_blocked")
    return RossTimePolicyDecision(symbol, regime_value, True, window_decision.allow_management, False, "entries_allowed")
