# File: strategy_runner_base_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Skeleton based strictly on STEP_4_OUTCOME_ROSS_STRATEGY_MAP.md

"""
STRATEGY RUNNER BASE (ABSTRACT STRATEGY CONTRACT)
-------------------------------------------------

GLOBAL CONTEXT
--------------
This file defines the **base class for all trading strategies**.

A Strategy Runner:
- consumes scanner + pattern outputs
- decides *whether* a trade intent exists
- NEVER places orders
- NEVER bypasses risk

Concrete strategies (Ross, Quant, Algo) inherit from this class.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_4_OUTCOME_ROSS_STRATEGY_MAP.md

STANDALONE GUARANTEE
-------------------
This file contains no broker or data dependencies.
It can be imported safely anywhere.
"""

# ================================
# 1. Imports
# ================================

from abc import ABC, abstractmethod
from typing import Any, Dict, List

# ================================
# 2. Strategy Runner Base Class
# ================================

class StrategyRunnerBase(ABC):
    """
    StrategyRunnerBase
    ------------------
    Abstract base class for all strategy runners.

    Enforces a consistent interface across strategies.
    """

    def __init__(self, config: Dict | None = None):
        """
        Initialize strategy runner.

        Parameters
        ----------
        config : dict | None
            Strategy-specific configuration.
        """
        self.config = config or {}

    # ================================
    # 3. Strategy Lifecycle Hooks
    # ================================

    @abstractmethod
    def on_new_session(self, session_context: Dict[str, Any]):
        """
        Called at session start (PRE / REGULAR / AFTER).
        """
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, scanner_results: List[Dict], pattern_results: List[Dict]) -> Dict:
        """
        Evaluate scanner + pattern outputs.

        Returns
        -------
        Dict
            Trade intent or neutral decision.
        """
        raise NotImplementedError

    @abstractmethod
    def on_trade_closed(self, trade_result: Dict):
        """
        Called after a trade is fully closed.
        Used for learning or state updates.
        """
        raise NotImplementedError

# ================================
# TEACHING NOTE
# ================================
# This abstraction is what allows the system to support:
# - Ross Momentum
# - Quant factor models
# - Algo / scalping strategies
#
# All without changing the Core Orchestrator.

# ================================
# END OF FILE
# ================================
