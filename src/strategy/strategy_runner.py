"""Strategy runner dispatcher for pluggable, teaching-first strategy modules."""

from dataclasses import dataclass, replace
from typing import List, Optional, Sequence

from src.config.trading_config import (
    is_strategy_enabled,
)
from src.core.event_collector import EventCollector
from src.domain.market_snapshot import MarketSnapshot
from src.models.data_models import PatternResult, TradeIntent
from src.strategy.gap_and_go_strategy import GapAndGoStrategy
from src.strategy.momentum_continuation_strategy import MomentumContinuationStrategy
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
from src.strategies.statistical_intraday_momentum.strategy import (
    StatisticalIntradayMomentum,
)
from src.strategies.mean_reversion.strategy import MeanReversionStrategy
from src.strategies.long_horizon_value.strategy import LongHorizonValueStrategy
from src.strategies.event_earnings_reaction.strategy import EventEarningsReactionStrategy
from src.strategies.event_news_shock_continuation.strategy import (
    EventNewsShockContinuationStrategy,
)
from src.strategies.volatility_contraction_breakout.strategy import (
    VolatilityContractionBreakoutStrategy,
)
from src.strategies.volatility_carry_risk_premium.strategy import (
    VolatilityCarryRiskPremiumStrategy,
)
from src.strategies.pairs_divergence_reversion.strategy import (
    PairsDivergenceReversionStrategy,
)
from src.strategy.exit_signal import ExitSignal
from src.core.active_trade_registry import ActiveTrade
from src.signals.signal_event import SignalEvent
from src.regime.contracts import RegimePolicyDecision
from src.config.config_resolver import get_config


class StrategyRunner:
    """Dispatches registered strategies to translate PatternResults into TradeIntents."""

    @dataclass(frozen=True)
    class StrategyRegistration:
        strategy_name: str
        strategy_class: type
        selected_key: str

    def __init__(
        self,
        event_collector: Optional[EventCollector] = None,
        strategies: Optional[Sequence[object]] = None,
    ) -> None:
        configured_strategies = [
            self.StrategyRegistration("GapAndGoStrategy", GapAndGoStrategy, "gap_and_go"),
            self.StrategyRegistration(
                "MomentumContinuationStrategy",
                MomentumContinuationStrategy,
                "momentum_continuation",
            ),
            self.StrategyRegistration(
                "RossMomentumStrategyV1", RossMomentumStrategyV1, "ross_momentum"
            ),
            self.StrategyRegistration(
                "StatisticalIntradayMomentum",
                StatisticalIntradayMomentum,
                "statistical_intraday_momentum",
            ),
            self.StrategyRegistration(
                "MeanReversionStrategy", MeanReversionStrategy, "mean_reversion"
            ),
            self.StrategyRegistration(
                "LongHorizonValueStrategy",
                LongHorizonValueStrategy,
                "long_horizon_value",
            ),
            self.StrategyRegistration(
                "EventEarningsReactionStrategy",
                EventEarningsReactionStrategy,
                "event_earnings_reaction",
            ),
            self.StrategyRegistration(
                "EventNewsShockContinuationStrategy",
                EventNewsShockContinuationStrategy,
                "event_news_shock_continuation",
            ),
            self.StrategyRegistration(
                "VolatilityContractionBreakoutStrategy",
                VolatilityContractionBreakoutStrategy,
                "volatility_contraction_breakout",
            ),
            self.StrategyRegistration(
                "VolatilityCarryRiskPremiumStrategy",
                VolatilityCarryRiskPremiumStrategy,
                "volatility_carry_risk_premium",
            ),
            self.StrategyRegistration(
                "PairsDivergenceReversionStrategy",
                PairsDivergenceReversionStrategy,
                "pairs_divergence_reversion",
            ),
        ]
        self.strategies = []
        self.event_collector = event_collector
        self.last_watchlist_symbols: List[str] = []
        self.last_watchlist_snapshots: dict[str, MarketSnapshot] = {}

        selected_strategy_key = str(get_config("SELECTED_STRATEGY") or "").strip().lower()

        if strategies is not None:
            self.strategies = list(strategies)
            registered = ", ".join(strategy.name for strategy in self.strategies)
            print(f"[BOOT] StrategyRunner instantiated with injected strategies: {registered}")
            return

        for registration in configured_strategies:
            strategy_name = registration.strategy_name
            if selected_strategy_key and selected_strategy_key != registration.selected_key:
                print(
                    f"[BOOT] Strategy '{strategy_name}' skipped due to selection "
                    f"(selected={selected_strategy_key})."
                )
                continue
            enabled = is_strategy_enabled(strategy_name)
            reason = f"is_strategy_enabled({strategy_name})={enabled}"
            if not enabled:
                print(
                    f"[BOOT] Strategy '{strategy_name}' DISABLED via config "
                    f"({reason}); skipping."
                )
                continue

            strategy = registration.strategy_class()
            self.strategies.append(strategy)
            print(f"[BOOT] Strategy '{strategy_name}' ENABLED via config and registered.")

        registered = ", ".join(strategy.name for strategy in self.strategies)
        print(f"[BOOT] StrategyRunner instantiated with strategies: {registered}")

    def receive_watchlist_snapshot(
        self,
        *,
        watchlist_symbols: Sequence[str],
        snapshots: Optional[dict[str, MarketSnapshot]] = None,
        session_label: str,
        timestamp_utc: str,
    ) -> None:
        self.last_watchlist_symbols = list(watchlist_symbols)
        self.last_watchlist_snapshots = dict(snapshots or {})
        print(
            "STRATEGY_RUNNER_RECEIVED "
            f"K={len(self.last_watchlist_symbols)} session={session_label} "
            f"timestamp_utc={timestamp_utc}"
        )

    def process(
        self,
        *,
        strategy_key: str,
        watchlist: Sequence[object],
        snapshots: dict[str, MarketSnapshot],
        session_label: str,
        timestamp_utc: str,
        mode,
        session_phase: str,
    ) -> List[TradeIntent]:
        strategies = list(self.strategies)
        print(
            "[STRATEGY][PROCESS] "
            f"strategy_key={strategy_key} strategies={len(strategies)} "
            f"watchlist={len(watchlist)} session={session_label} phase={session_phase}"
        )
        if not strategies:
            print("[STRATEGY][PROCESS] No registered strategies; returning [].")
            return []
        results: List[TradeIntent] = []
        for strategy in strategies:
            handler = getattr(strategy, "process_watchlist", None)
            if callable(handler):
                results.extend(
                    handler(
                        watchlist=watchlist,
                        snapshots=snapshots,
                        session_label=session_label,
                        timestamp_utc=timestamp_utc,
                        mode=mode,
                        session_phase=session_phase,
                    )
                )
                continue
            print(
                "[STRATEGY][PROCESS] "
                f"Strategy '{strategy.name}' has no watchlist handler; skipping."
            )
        return results

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

    def filter_pattern_results(
        self,
        pattern_results: List[PatternResult],
        focus_symbols: Optional[Sequence[object]] = None,
    ) -> List[PatternResult]:
        focus_list = self._symbols_from_focus(focus_symbols)
        if not focus_list:
            symbols_for_eval = sorted({result.symbol for result in pattern_results})
            print(
                "[RUNNER] symbols_for_evaluation="
                f"{symbols_for_eval} source=ALL_CANDIDATES"
            )
            return pattern_results
        focus_set = set(focus_list)
        filtered = [result for result in pattern_results if result.symbol in focus_set]
        print(
            "[RUNNER] symbols_for_evaluation="
            f"{focus_list} source=FOCUS_M"
        )
        return filtered

    @staticmethod
    def _symbols_from_focus(focus_symbols: Optional[Sequence[object]]) -> List[str]:
        symbols: List[str] = []
        for entry in focus_symbols or []:
            symbol = None
            if isinstance(entry, str):
                symbol = entry
            elif isinstance(entry, dict):
                symbol = entry.get("symbol")
            else:
                symbol = getattr(entry, "symbol", None)
            if symbol:
                symbols.append(symbol)
        return symbols

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
