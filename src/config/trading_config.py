"""
Strategy-level configuration for enabling or disabling individual strategies.

These switches allow governance to turn strategies on or off without touching
strategy code. Strategies not explicitly listed here default to DISABLED.
"""

# ==========================================================
# Strategy enable / disable governance
# True  = strategy allowed to run
# False = strategy skipped entirely
# ==========================================================

ENABLED_STRATEGIES = {
    "GapAndGoStrategy": True,
    "MomentumContinuationStrategy": True,
}
