"""Strategy runner dispatcher for pluggable, teaching-first strategy modules."""

from typing import List, Optional

from config.trading_config import ENABLED_STRATEGIES
from core.event_collector import EventCollector
from models.data_models import PatternResult, TradeIntent
from strategy.gap_and_go_strategy import GapAndGoStrategy
from strategy.momentum_continuation_strategy import MomentumContinuationStrategy
from strategy.exit_signal import ExitSignal
from core.active_trade_registry import ActiveTrade


class StrategyRunner:
    """Dispatches registered strategies to translate PatternResults into TradeIntents."""

    def __init__(self, event_collector: Optional[EventCollector] = None) -> None:
        configured_strategies = [
            ("GapAndGoStrategy", GapAndGoStrategy),
            ("MomentumContinuationStrategy", MomentumContinuationStrategy),
        ]
        self.strategies = []
        self.event_collector = event_collector

        for strategy_name, strategy_class in configured_strategies:
            enabled = ENABLED_STRATEGIES.get(strategy_name, False)
            if not enabled:
                reason = (
                    "explicitly disabled"
                    if strategy_name in ENABLED_STRATEGIES
                    else "missing from ENABLED_STRATEGIES; defaulting to DISABLED"
                )
                print(
                    f"[BOOT] Strategy '{strategy_name}' DISABLED via config "
                    f"({reason}); skipping."
                )
                continue

            strategy = strategy_class()
            self.strategies.append(strategy)
            print(f"[BOOT] Strategy '{strategy_name}' ENABLED via config and registered.")

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

    def run_from_intents(self, intents: List[TradeIntent]) -> List[TradeIntent]:
        """
        Teaching-first adapter entrypoint that preserves StrategyRunner ownership.
        """

        trade_intents = intents or []
        print(
            f"[STRATEGY] Received {len(trade_intents)} TradeIntent(s) from adapter."
        )
        if self.event_collector is not None:
            event = self.event_collector.emit(
                event_type="STRATEGY_COMPLETE",
                source="StrategyRunner",
                payload={"trade_intents": len(trade_intents)},
            )
            print(event)
        else:
            print("[STRATEGY] EventCollector unavailable; skipping STRATEGY_COMPLETE emit.")
        return trade_intents

    def generate_exit_signals(
        self, active_trades: List[ActiveTrade], current_tick: int
    ) -> List[ExitSignal]:
        """
        Call each registered strategy to request advisory exit signals for active trades.
        """

        print(f"[STRATEGY] Dispatching exit-signal review to {len(self.strategies)} strategy(ies)")
        all_exit_signals: List[ExitSignal] = []
        for strategy in self.strategies:
            print(
                f"[STRATEGY] Evaluating exit signals for strategy '{strategy.name}' "
                f"against {len(active_trades)} active trade(s)"
            )
            signals = strategy.evaluate_exit_signals(active_trades, current_tick)
            print(
                f"[STRATEGY] Strategy '{strategy.name}' requested {len(signals)} exit signal(s)"
            )
            all_exit_signals.extend(signals)
        print(
            f"[STRATEGY] Aggregated exit signals from all strategies: {len(all_exit_signals)} total"
        )
        return all_exit_signals
