# File: pattern_base_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Skeleton based strictly on STEP_9_OUTCOME_PATTERN_ENGINE_RESPONSIBILITIES.md

"""
PATTERN BASE (ABSTRACT DETECTOR CONTRACT)
----------------------------------------

GLOBAL CONTEXT
--------------
This file defines the **abstract base class for all pattern detectors**.

Every concrete pattern detector MUST:
- inherit from this base
- follow the frozen Pattern Detection Contract
- return structured, explainable results

Patterns detect SETUPS — not trades.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_9_OUTCOME_PATTERN_ENGINE_RESPONSIBILITIES.md
- STEP_6_OUTCOME_PATTERN_DETECTION_CONTRACTS.md

STANDALONE GUARANTEE
-------------------
This file has no external dependencies and is safe to import anywhere.
"""

# ================================
# 1. Imports
# ================================

from abc import ABC, abstractmethod
from typing import Dict

# ================================
# 2. Pattern Base Class
# ================================

class PatternBase(ABC):
    """
    PatternBase
    -----------
    Abstract base class for all pattern detectors.
    """

    pattern_name: str
    pattern_family: str

    @abstractmethod
    def detect(self, market_context: Dict) -> Dict:
        """
        Detect a specific pattern.

        Parameters
        ----------
        market_context : dict
            Normalized market, indicator, and news context.

        Returns
        -------
        Dict
            PatternResult (structured, explainable).
        """
        raise NotImplementedError

# ================================
# TEACHING NOTE
# ================================
# Abstract base classes enforce discipline.
# If a detector cannot fit this interface, it does not belong in the system.

# ================================
# END OF FILE
# ================================
