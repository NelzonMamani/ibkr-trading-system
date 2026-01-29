from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ExecutionIntent:
    strategy_name: str
    mode: str
    session_phase: str
    scan_only: bool
    trade_enabled: bool
    ranking_intent: str
    enforcement: Dict[str, int]
    notes: str


def _mode_allows_trading(mode_value: str) -> bool:
    normalized = mode_value.strip().upper()
    if normalized in {"READONLY", "READ_ONLY", "LIVE_READ_ONLY", "LIVE_READONLY"}:
        return False
    return normalized in {
        "SIM",
        "PAPER",
        "LIVE",
        "LIVE_MICRO",
        "LIVE_ONE_SHARE",
        "LIVE_1SHARE",
    }


def build_execution_intent(
    *,
    strategy_name: str,
    mode: str,
    session_phase: str,
    policy: Any,
    execution_enabled: bool,
) -> ExecutionIntent:
    trade_allowed_by_mode = _mode_allows_trading(mode)
    trade_enabled = trade_allowed_by_mode and execution_enabled
    scan_only = not trade_allowed_by_mode
    ranking_intent = getattr(policy, "ranking_intent", "ROSS_MOMENTUM_STOCK_SELECTION")
    enforcement = {
        "watchlist_limit_k": int(getattr(policy, "watchlist_limit_k", 0)),
        "focus_limit_m": int(getattr(policy, "focus_limit_m", 0)),
        "top_gainers_n": int(getattr(policy, "top_gainers_n", 0)),
        "max_symbols_per_cycle": int(getattr(policy, "max_symbols_per_cycle", 0)),
    }
    notes = []
    if not trade_allowed_by_mode:
        notes.append("mode_blocks_trading")
    if not execution_enabled:
        notes.append("execution_disabled")
    return ExecutionIntent(
        strategy_name=strategy_name,
        mode=mode,
        session_phase=session_phase,
        scan_only=scan_only,
        trade_enabled=trade_enabled,
        ranking_intent=ranking_intent,
        enforcement=enforcement,
        notes=";".join(notes) if notes else "mode_allows_execution",
    )
