# File: trade_and_risk_models_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Canonical trade and risk data models

"""
TRADE & RISK DATA MODELS (CANONICAL STRUCTURES)
----------------------------------------------

GLOBAL CONTEXT
--------------
This file defines the **canonical data models** for trade lifecycle tracking.

These models are shared across:
- Strategy
- Risk
- Execution
- Storage
- Analytics / Learning

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_20_OUTCOME_TRADE_AND_RISK_MODELS.md

STANDALONE GUARANTEE
-------------------
This file contains no business logic and can be imported anywhere.

TRADING MODE
------------
None — structure only.
"""

# ================================
# 1. Imports
# ================================

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

# ================================
# 2. Trade Intent Model
# ================================

@dataclass(frozen=True)
class TradeIntent:
    """
    TradeIntent
    -----------
    Represents a proposed trade before risk approval.
    """

    trade_id: str
    symbol: str
    side: str  # LONG / SHORT
    strategy_name: str
    pattern_name: str
    entry_reason: str

    proposed_entry_price: Optional[float]
    proposed_stop_price: Optional[float]

    created_at: datetime = field(default_factory=datetime.utcnow)

# ================================
# 3. Risk Decision Model
# ================================

@dataclass(frozen=True)
class RiskDecision:
    """
    RiskDecision
    ------------
    Result of risk evaluation.
    """

    trade_id: str
    decision: str  # ALLOW / BLOCK / ALLOW_WITH_CONSTRAINTS
    max_position_size: int
    risk_flags: List[str]
    risk_rationale: str

    evaluated_at: datetime = field(default_factory=datetime.utcnow)

# ================================
# 4. Execution Record Model
# ================================

@dataclass(frozen=True)
class ExecutionRecord:
    """
    ExecutionRecord
    ---------------
    Broker-side execution details.
    """

    trade_id: str
    order_id: Optional[str]
    order_status: str
    filled_quantity: int
    avg_fill_price: Optional[float]
    execution_errors: List[str]

    recorded_at: datetime = field(default_factory=datetime.utcnow)

# ================================
# 5. Trade Outcome Model
# ================================

@dataclass(frozen=True)
class TradeOutcome:
    """
    TradeOutcome
    ------------
    Final trade result used for learning.
    """

    trade_id: str
    realized_pnl: float
    mae: Optional[float]
    mfe: Optional[float]
    duration_seconds: Optional[int]
    exit_reason: str

    closed_at: datetime = field(default_factory=datetime.utcnow)

# ================================
# TEACHING NOTE
# ================================
# These models enable accountability.
# If you cannot reconstruct a trade, the system is lying.

# ================================
# END OF FILE
# ================================
