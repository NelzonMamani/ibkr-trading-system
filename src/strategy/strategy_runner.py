"""Strategy runner dispatcher for pluggable, teaching-first strategy modules."""

from typing import List

from models.data_models import PatternResult, TradeIntent
from strategy.gap_and_go_strategy import GapAndGoStrategy


class StrategyRunner:
    """Dispatches registered strategies to translate PatternResults into TradeIntents."""

    def __init__(self) -> None:
        self.strategies = [GapAndGoStrategy()]
        registered = ", ".join(strategy.name for strategy in self.strategies)
        print(f"[BOOT] StrategyRunner instantiated with strategies: {registered}")

    def generate_trade_intents(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        """Call each registered strategy and aggregate their TradeIntent outputs."""

        print(f"[STRATEGY] Dispatching {len(self.strategies)} strategy(ies)")
        all_intents: List[TradeIntent] = []
        for strategy in self.strategies:
            print(
                f"[STRATEGY] Evaluating strategy '{strategy.name}' with "
                f"{len(pattern_results)} pattern result(s)"
            )
            intents = strategy.evaluate(pattern_results)
            print(
                f"[STRATEGY] Strategy '{strategy.name}' returned {len(intents)} TradeIntent(s)"
            )
            all_intents.extend(intents)
        print(f"[STRATEGY] Aggregated TradeIntents from all strategies: {len(all_intents)} total")
        return all_intents

    def generate_trade_intent(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        """
        Backwards-compatible wrapper that forwards to generate_trade_intents.
        """

        return self.generate_trade_intents(pattern_results)
