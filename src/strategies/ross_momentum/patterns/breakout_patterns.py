"""Compatibility exports for breakout setup families migrated to shared setup engine."""

from src.setup_engine.setup_families.breakouts import (
    ConsolidationBreakoutPattern,
    OpeningRangeBreakoutPattern,
    PremarketHighBreakPattern,
)

__all__ = [
    "ConsolidationBreakoutPattern",
    "OpeningRangeBreakoutPattern",
    "PremarketHighBreakPattern",
]
