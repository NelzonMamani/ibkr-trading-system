"""Strategy runner dispatcher for pluggable, teaching-first strategy modules."""

from dataclasses import replace
from typing import List, Optional, Sequence

from src.config.trading_config import ENABLED_STRATEGIES, ROSS_MOMENTUM_STRATEGY_ENABLED
from src.core.event_collector import EventCollector
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.gap_and_go_strategy import GapAndGoStrategy
from src.strategy.momentum_continuation_strategy import MomentumContinuationStrategy
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategy.exit_signal import ExitSignal
from src.core.active_trade_registry import ActiveTrade
from src.signals.signal_event import SignalEvent
from src.regime.contracts import RegimePolicyDecision
from src.config.config_resolver import get_config


class StrategyRunner:
    """Dispatches registered strategies to translate PatternResults into TradeIntents."""

    def __init__(
        self,
        event_collector: Optional[EventCollector] = None,
        strategies: Optional[Sequence[object]] = None,
    ) -> None:
        configured_strategies = [
            ("GapAndGoStrategy", GapAndGoStrategy),
            ("MomentumContinuationStrategy", MomentumContinuationStrategy),
            ("RossMomentumStrategyV1", RossMomentumStrategyV1),
        ]
        self.strategies = []
        self.event_collector = event_collector

        if strategies is not None:
            self.strategies = list(strategies)
            registered = ", ".join(strategy.name for strategy in self.strategies)
            print(f"[BOOT] StrategyRunner instantiated with injected strategies: {registered}")
            return

        for strategy_name, strategy_class in configured_strategies:
            if strategy_name == "RossMomentumStrategyV1":
                enabled = ROSS_MOMENTUM_STRATEGY_ENABLED
                reason = (
                    f"ROSS_MOMENTUM_STRATEGY_ENABLED={ROSS_MOMENTUM_STRATEGY_ENABLED}"
                )
            else:
                enabled = ENABLED_STRATEGIES.get(strategy_name, False)
                reason = (
                    "explicitly disabled"
                    if strategy_name in ENABLED_STRATEGIES
                    else "missing from ENABLED_STRATEGIES; defaulting to DISABLED"
                )
            if not enabled:
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

    def generate_trade_intents(
        self,
        pattern_results: List[PatternResult],
        policy_decision: Optional[RegimePolicyDecision] = None,
        signals: Optional[Sequence[SignalEvent]] = None,
    ) -> List[TradeIntent]:
        """Call each registered strategy and aggregate their TradeIntent outputs."""

        strategies = self._apply_policy_filter(policy_decision)
        print(f"[STRATEGY] Dispatching {len(strategies)} strategy(ies)")
        all_intents: List[TradeIntent] = []
        for strategy in strategies:
            print(
                f"[STRATEGY] Evaluating strategy '{strategy.name}' with "
                f"{len(pattern_results)} pattern result(s)"
            )
            try:
                intents = strategy.evaluate(pattern_results, signals=signals)
            except TypeError:
                intents = strategy.evaluate(pattern_results)
            intents = self._apply_policy_weights(intents, policy_decision, strategy.name)
            print(
                f"[STRATEGY] Strategy '{strategy.name}' returned {len(intents)} TradeIntent(s)"
            )
            all_intents.extend(intents)
        print(f"[STRATEGY] Aggregated TradeIntents from all strategies: {len(all_intents)} total")
        return all_intents

    def generate_trade_intent(
        self,
        pattern_results: List[PatternResult],
        policy_decision: Optional[RegimePolicyDecision] = None,
        signals: Optional[Sequence[SignalEvent]] = None,
    ) -> List[TradeIntent]:
        """
        Backwards-compatible wrapper that forwards to generate_trade_intents.
        """

        return self.generate_trade_intents(
            pattern_results,
            policy_decision=policy_decision,
            signals=signals,
        )

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

    def _apply_policy_filter(
        self, policy_decision: Optional[RegimePolicyDecision]
    ) -> List[object]:
        if not policy_decision or not policy_decision.applied:
            return list(self.strategies)
        mode = str(get_config("ADAPTIVE_REGIME_STRATEGY_WEIGHTING_MODE") or "OFF").upper()
        if mode != "ENABLE_DISABLE":
            return list(self.strategies)
        eligible = set(policy_decision.eligible_strategies or [])
        filtered = [strategy for strategy in self.strategies if strategy.name in eligible]
        filtered_names = ", ".join(strategy.name for strategy in filtered) or "none"
        print(f"[STRATEGY][REGIME] Eligible strategies: {filtered_names}")
        return filtered

    def _apply_policy_weights(
        self,
        intents: List[TradeIntent],
        policy_decision: Optional[RegimePolicyDecision],
        strategy_name: str,
    ) -> List[TradeIntent]:
        if not policy_decision or not policy_decision.applied:
            return intents
        mode = str(get_config("ADAPTIVE_REGIME_STRATEGY_WEIGHTING_MODE") or "OFF").upper()
        if mode != "WEIGHT":
            return intents
        weight = float(policy_decision.strategy_weights.get(strategy_name, 0.0))
        if weight <= 0:
            print(f"[STRATEGY][REGIME] Dropping intents for {strategy_name} (weight=0)")
            return []
        adjusted: List[TradeIntent] = []
        for intent in intents:
            confidence = float(intent.confidence or 0.0) * weight
            adjusted.append(replace(intent, confidence=confidence))
        print(f"[STRATEGY][REGIME] Applied weight={weight:.2f} for {strategy_name}")
        return adjusted
