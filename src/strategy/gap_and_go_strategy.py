"""
Deterministic Gap and Go strategy plugin.

This strategy simply translates PatternResults labeled with "Gap and Go" into
TradeIntent objects without thresholds, sizing, or broker integration.
"""

from typing import List

from models.data_models import PatternResult, TradeIntent
from strategy.base_strategy import BaseStrategy


class GapAndGoStrategy(BaseStrategy):
    """Pure translation from Gap and Go pattern into a long SCALPER intent."""

    name = "GapAndGoStrategy"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        print(
            f"[STRATEGY:GapAndGo] Evaluation start — received {len(pattern_results)} pattern(s) for review"
        )
        trade_intents: List[TradeIntent] = []
        for pattern in pattern_results:
            if "Gap and Go" in pattern.pattern_name:
                rationale = (
                    f"{pattern.rationale} | Teaching note: translating 'Gap and Go' detection into a long SCALPER intent."
                )
                print(
                    "[STRATEGY:GapAndGo] Matched pattern — creating TradeIntent "
                    f"for symbol={pattern.symbol} with confidence={pattern.confidence}"
                )
                trade_intents.append(
                    TradeIntent(
                        symbol=pattern.symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=pattern.confidence,
                        rationale=rationale,
                        trader_type="SCALPER",
                    )
                )
            else:
                print(
                    "[STRATEGY:GapAndGo] Skipped pattern — not a Gap and Go label "
                    f"for symbol={pattern.symbol} (pattern='{pattern.pattern_name}')"
                )
        print(
            f"[STRATEGY:GapAndGo] Evaluation complete — generated {len(trade_intents)} TradeIntent(s)"
        )
        return trade_intents
