"""
Strategy-level configuration for enabling or disabling individual strategies.

These switches allow governance to turn strategies on or off without touching
strategy code. Values default to True to preserve expected Phase 4 behaviour.
"""

# Strategy enable / disable switches
# True = strategy allowed to run
# False = strategy skipped entirely

ENABLED_STRATEGIES = {
    "GapAndGoStrategy": True,
    "MomentumContinuationStrategy": True,
}
