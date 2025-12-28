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

# Event replay behavior
# OFF   → no replay
# CYCLE → replay most recent cycle events
# ALL   → replay all recorded events (teaching/debug only)
EVENT_REPLAY_MODE = "CYCLE"
