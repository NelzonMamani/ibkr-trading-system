"""Compatibility shim for Ross Momentum canonical policy module.

Canonical definition lives in `strategy_policy.py`.
"""

from src.strategies.ross_momentum.strategy_policy import POLICY_V2

__all__ = ["POLICY_V2"]
