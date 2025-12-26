"""
Strategy runner skeleton showing how patterns could translate into trade intents.

Phase 3: Skeleton status only — this module is for teaching structure, not logic.
No real strategy evaluation, risk checks, or trade generation is implemented.
"""

from typing import List

from models.data_models import PatternResult, TradeIntent


class StrategyRunner:
    """Minimal strategy runner placeholder with instructional logging."""

    def __init__(self) -> None:
        print("[BOOT] StrategyRunner instantiated — phase 3 skeleton only")

    def generate_trade_intent(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        """
        Translate pattern results into teaching-only trade intents using deterministic rules.
        """

        print("[STRATEGY] Received pattern results — teaching-only translation starting")
        intents: List[TradeIntent] = []
        for pattern in pattern_results:
            direction = self._direction_from_pattern(pattern.pattern_name)
            rationale = (
                f"Teaching translation from pattern '{pattern.pattern_name}' with rationale: {pattern.rationale}"
            )
            print(
                f"[STRATEGY] Creating TradeIntent for {pattern.symbol}: "
                f"pattern='{pattern.pattern_name}' -> direction='{direction}'"
            )
            print(
                f"[STRATEGY] Assigning confidence={pattern.confidence} based on provided pattern confidence "
                "(teaching-only passthrough)"
            )
            intent = TradeIntent(
                symbol=pattern.symbol,
                direction=direction,
                strategy_name=pattern.pattern_name,
                confidence=pattern.confidence,
                rationale=rationale,
            )
            intents.append(intent)
        print("[STRATEGY] Completed TradeIntent generation — teaching visibility preserved")
        return intents

    @staticmethod
    def _direction_from_pattern(pattern_name: str) -> str:
        """Deterministically map teaching pattern names to directions."""

        direction_map = {
            "Gap and Go (Teaching)": "LONG",
            "Momentum Continuation (Teaching)": "LONG",
        }
        return direction_map.get(pattern_name, "NONE")
