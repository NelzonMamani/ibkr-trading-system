"""
Strategy runner skeleton responsible for converting pattern evaluations into trade intent.
"""

from typing import List

from models.data_models import PatternResult, TradeIntent


class StrategyRunner:
    """Skeleton strategy runner returning empty intents with instructional logs."""

    def __init__(self) -> None:
        print("[BOOT] StrategyRunner instantiated — skeleton only")

    def generate_trade_intent(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        """Generate trade intents placeholder from pattern results."""

        print("[STRATEGY] Skeleton strategy runner invoked — no logic implemented yet")
        return []
