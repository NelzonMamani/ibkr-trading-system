# File: risk_config_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Risk configuration and session rules skeleton

"""
RISK CONFIGURATION & SESSION RULES
---------------------------------

GLOBAL CONTEXT
--------------
This file defines the **configuration schema** and **session rules** consumed by the Risk Engine.

It externalizes:
- risk limits
- phase-based constraints
- session timing rules

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_21_OUTCOME_RISK_CONFIGURATION_AND_SESSION_RULES.md

STANDALONE GUARANTEE
-------------------
This file contains no trading logic.

TRADING MODE
------------
Configuration only.
"""

# ================================
# 1. Imports
# ================================

from dataclasses import dataclass, field
from datetime import time
from typing import Dict

# ================================
# 2. Session Rules Model
# ================================

@dataclass(frozen=True)
class SessionRule:
    """
    SessionRule
    -----------
    Defines trading permissions for a session window.
    """

    name: str
    start: time
    end: time
    trading_allowed: bool
    max_position_size: int

# ================================
# 3. Risk Configuration Model
# ================================

@dataclass(frozen=True)
class RiskConfig:
    """
    RiskConfig
    ----------
    Canonical risk configuration container.
    """

    phase_mode: str  # TEST / LIVE
    max_daily_loss_pct: float
    max_consecutive_losses: int
    max_trades_per_day: int

    session_rules: Dict[str, SessionRule]

# ================================
# TEACHING NOTE
# ================================
# Risk should be configurable, not hard-coded.
# This file allows behaviour changes without rewriting logic.

# ================================
# END OF FILE
# ================================
