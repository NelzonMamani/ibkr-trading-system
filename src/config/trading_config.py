"""
Strategy-level configuration for enabling or disabling individual strategies.

These switches allow governance to turn strategies on or off without touching
strategy code. Strategies not explicitly listed here default to DISABLED.
"""

from __future__ import annotations

from src.config.config_resolver import get_config

# Minimum number of ticks a trade must remain open before TradeExitEngine
# is allowed to close it. Keeps lifecycle visible across cycles.
MIN_HOLD_TICKS: int = int(get_config("MIN_HOLD_TICKS"))

# Maximum number of ticks a trade may remain open before TradeExitEngine
# forces an exit. Ensures trades always resolve deterministically.
MAX_HOLD_TICKS: int = int(get_config("MAX_HOLD_TICKS"))

# ==========================================================
# Strategy enable / disable governance
# True  = strategy allowed to run
# False = strategy skipped entirely
# ==========================================================

ROSS_MOMENTUM_STRATEGY_ENABLED: bool = bool(get_config("ROSS_MOMENTUM_STRATEGY_ENABLED"))
STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED: bool = bool(
    get_config("STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED")
)
LONG_HORIZON_VALUE_STRATEGY_ENABLED: bool = bool(
    get_config("LONG_HORIZON_VALUE_STRATEGY_ENABLED")
)

ENABLED_STRATEGIES = dict(get_config("ENABLED_STRATEGIES"))


def is_strategy_enabled(strategy_name: str) -> bool:
    if strategy_name == "RossMomentumStrategyV1":
        return ROSS_MOMENTUM_STRATEGY_ENABLED
    if strategy_name == "StatisticalIntradayMomentum":
        return STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED
    if strategy_name == "LongHorizonValue":
        return LONG_HORIZON_VALUE_STRATEGY_ENABLED
    return ENABLED_STRATEGIES.get(strategy_name or "", False)
