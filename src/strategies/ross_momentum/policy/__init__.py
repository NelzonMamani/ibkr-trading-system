"""Authoritative Ross policy package.

Legacy imports continue to work from strategy_policy.py. New code should import
the PR1 facade from this package.
"""

from .catalyst_policy import (
    CatalystDecision,
    CatalystPolicy,
    CatalystStatus,
    assess_catalyst,
    log_catalyst_live_not_satisfied,
    log_catalyst_unavailable,
    log_catalyst_validation_bypass,
)
from .ross_policy import ROSS_POLICY_AUTHORITY, RossPolicy
from .runtime_safety import (
    is_live_like_mode,
    is_live_mode,
    is_read_only_mode,
    is_validation_mode,
    log_fallback_intent_blocked,
    log_no_setup_no_trade,
    log_validation_override_active,
    log_validation_override_blocked,
    normalize_run_mode,
    synthetic_intent_allowed,
    validation_override_allowed,
)

__all__ = [
    "CatalystDecision",
    "CatalystPolicy",
    "CatalystStatus",
    "ROSS_POLICY_AUTHORITY",
    "RossPolicy",
    "assess_catalyst",
    "is_live_like_mode",
    "is_live_mode",
    "is_read_only_mode",
    "is_validation_mode",
    "log_catalyst_live_not_satisfied",
    "log_catalyst_unavailable",
    "log_catalyst_validation_bypass",
    "log_fallback_intent_blocked",
    "log_no_setup_no_trade",
    "log_validation_override_active",
    "log_validation_override_blocked",
    "normalize_run_mode",
    "synthetic_intent_allowed",
    "validation_override_allowed",
]
