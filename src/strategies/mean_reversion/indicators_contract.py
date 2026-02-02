"""
Scanner → Strategy Contract (Strategy-Agnostic Facts Only)

This module exists to freeze the *boundary* between scanner and strategy.
The authoritative data types are re-exported from mean_reversion_strategy_policy.py for now.

Codex may later refactor so ScannerFacts lives here and policy imports it.
Until then, do NOT duplicate types.
"""

from .mean_reversion_strategy_policy import ScannerFacts
