"""
Strategy-level configuration for enabling or disabling individual strategies.

These switches allow governance to turn strategies on or off without touching
strategy code. Strategies not explicitly listed here default to DISABLED.
"""

# Minimum number of ticks a trade must remain open before TradeExitEngine
# is allowed to close it. Keeps lifecycle visible across cycles.
MIN_HOLD_TICKS: int = 2

# Maximum number of ticks a trade may remain open before TradeExitEngine
# forces an exit. Ensures trades always resolve deterministically.
MAX_HOLD_TICKS: int = 10

# ==========================================================
# Strategy enable / disable governance
# True  = strategy allowed to run
# False = strategy skipped entirely
# ==========================================================

ROSS_MOMENTUM_STRATEGY_ENABLED: bool = False

ENABLED_STRATEGIES = {
    "GapAndGoStrategy": True,
    "MomentumContinuationStrategy": True,
}
