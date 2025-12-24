# File: pattern_registry_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Skeleton based strictly on STEP_9_OUTCOME_PATTERN_ENGINE_RESPONSIBILITIES.md

"""
PATTERN REGISTRY (DETECTOR CATALOG)
----------------------------------

GLOBAL CONTEXT
--------------
This file defines the **Pattern Registry**.

The registry:
- maintains a catalog of available pattern detectors
- enables/disables patterns by name
- decouples PatternEngine from concrete implementations

This is the mechanism that allows:
- strategy-specific pattern sets
- easy experimentation
- safe extensibility

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_9_OUTCOME_PATTERN_ENGINE_RESPONSIBILITIES.md
- STEP_6_OUTCOME_PATTERN_DETECTION_CONTRACTS.md

STANDALONE GUARANTEE
-------------------
This file contains no broker, data, or execution dependencies.
"""

# ================================
# 1. Imports
# ================================

from typing import Dict, List, Type

from pattern_base_v01 import PatternBase

# ================================
# 2. Pattern Registry
# ================================

class PatternRegistry:
    """
    PatternRegistry
    ---------------
    Central catalog of pattern detectors.
    """

    def __init__(self):
        """
        Initialize empty registry.
        """
        self._registry: Dict[str, Type[PatternBase]] = {}

    # ================================
    # 3. Registry Management
    # ================================

    def register(self, detector_cls: Type[PatternBase]):
        """
        Register a pattern detector class.

        Parameters
        ----------
        detector_cls : Type[PatternBase]
            Concrete detector class.
        """
        name = getattr(detector_cls, "pattern_name", None)
        if not name:
            raise ValueError("Pattern detector must define pattern_name")

        self._registry[name] = detector_cls

    def unregister(self, pattern_name: str):
        """
        Remove a pattern detector from the registry.
        """
        self._registry.pop(pattern_name, None)

    # ================================
    # 4. Query Interface
    # ================================

    def get_detector(self, pattern_name: str) -> Type[PatternBase] | None:
        """Retrieve detector class by name."""
        return self._registry.get(pattern_name)

    def list_patterns(self) -> List[str]:
        """List all registered pattern names."""
        return list(self._registry.keys())

# ================================
# TEACHING NOTE
# ================================
# Registries are safer than hard-coded imports.
# They allow patterns to be composed, tested, and swapped dynamically.

# ================================
# END OF FILE
# ================================
