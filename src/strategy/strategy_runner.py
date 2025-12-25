"""
Strategy runner skeleton showing how patterns could translate into trade intents.

Phase 3: Skeleton status only — this module is for teaching structure, not logic.
No real strategy evaluation, risk checks, or trade generation is implemented.
"""

from typing import List


class StrategyRunner:
    """Minimal strategy runner placeholder with instructional logging."""

    def __init__(self) -> None:
        print("[BOOT] StrategyRunner instantiated — phase 3 skeleton only")

    def generate_trade_intent(self, pattern_results: List[str]) -> List[str]:
        """
        Demonstrate how trade intents would be generated from pattern outputs.

        Returns an empty list to highlight the absence of strategy logic while
        emitting teaching-first log statements.
        """

        print("[STRATEGY] Received pattern results — teaching-only pass-through")
        print("[STRATEGY] No strategy logic executed — returning empty list")
        return []
