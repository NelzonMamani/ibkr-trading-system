"""
Momentum Continuation strategy plugin.

This module translates detected "Momentum Continuation" patterns into
TradeIntent objects without applying thresholds, sizing, or risk logic. It
keeps the system deterministic and SIM-only while demonstrating coexistence
with other strategy modules like GapAndGoStrategy.
"""

from typing import List

from models.data_models import PatternResult, TradeIntent
from strategy.base_strategy import BaseStrategy


class MomentumContinuationStrategy(BaseStrategy):
    """Pure translation from Momentum Continuation pattern into a long MOMENTUM intent."""

    name = "MomentumContinuationStrategy"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        print(
            f"[STRATEGY:Momentum] Evaluation start — received {len(pattern_results)} pattern(s) for review"
        )
        trade_intents: List[TradeIntent] = []
        for pattern in pattern_results:
            if "Momentum Continuation" in pattern.pattern_name:
                rationale = (
                    f"{pattern.rationale} | Teaching note: translating 'Momentum Continuation' detection into a long MOMENTUM intent."
                )
                print(
                    "[STRATEGY:Momentum] Matched pattern — creating TradeIntent "
                    f"for symbol={pattern.symbol} with confidence={pattern.confidence}"
                )
                trade_intents.append(
                    TradeIntent(
                        symbol=pattern.symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=pattern.confidence,
                        rationale=rationale,
                        trader_type="MOMENTUM",
                    )
                )
            else:
                print(
                    "[STRATEGY:Momentum] Skipped pattern — not a Momentum Continuation label "
                    f"for symbol={pattern.symbol} (pattern='{pattern.pattern_name}')"
                )
        print(
            f"[STRATEGY:Momentum] Evaluation complete — generated {len(trade_intents)} TradeIntent(s)"
        )
        return trade_intents
