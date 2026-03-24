"""Strategy runner dispatcher for pluggable, teaching-first strategy modules."""

from collections import defaultdict
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
from src.strategies.mean_reversion.runner import MeanReversionRunner
from src.strategies.long_horizon_value.strategy import LongHorizonValueStrategy
from src.strategies.ross_momentum.runner import RossMomentumRunner
from src.strategies.opening_drive.strategy import OpeningDriveStrategy
from src.strategies.vwap_reclaim.strategy import VwapReclaimStrategy
from src.strategies.power_hour.strategy import PowerHourStrategy
from src.strategies.volatility_expansion.strategy import VolatilityExpansionStrategy
from src.strategies.range_bound_fade.strategy import RangeBoundFadeStrategy
from src.strategies.support_resistance_channel.strategy import (
    SupportResistanceChannelStrategy,
)
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
from src.strategies.cross_sectional_relative_strength_rotation.strategy import (
    CrossSectionalRelativeStrengthRotationStrategy,
)
from src.strategies.time_based_seasonality.strategy import TimeBasedSeasonalityStrategy
from src.strategies.trend_following_classic.strategy import TrendFollowingClassicStrategy
from src.strategies.long_horizon_quality_compounder.strategy import (
    LongHorizonQualityCompounderStrategy,
)
from src.strategies.regime_adaptive_meta_allocator.strategy import (
    RegimeAdaptiveMetaAllocatorStrategy,
)
from src.strategies.statistical_intraday_momentum.runner import (
    StatisticalIntradayMomentumRunner,
)
from src.strategy.exit_signal import ExitSignal
from src.core.active_trade_registry import ActiveTrade
from src.signals.signal_event import SignalEvent
from src.regime.contracts import RegimePolicyDecision
from src.config.config_resolver import get_config
from src.scanner.session_pct_change import canonical_session_label


def safe_get_config(key, default=None, required=False):
    try:
        value = get_config(key)
        if value is None:
            raise ValueError(f"Config key '{key}' returned None")
        return value
    except Exception as e:
        if required:
            raise RuntimeError(
                f"[CONFIG][FATAL] Missing required config: {key}"
            ) from e
        print(
            f"[CONFIG][WARN] Missing optional config: {key} → using default={default}"
        )
        return default


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
                "OpeningDriveStrategy",
                OpeningDriveStrategy,
                "opening_drive",
            ),
            self.StrategyRegistration(
                "VwapReclaimStrategy",
                VwapReclaimStrategy,
                "vwap_reclaim",
            ),
            self.StrategyRegistration(
                "PowerHourStrategy",
                PowerHourStrategy,
                "power_hour",
            ),
            self.StrategyRegistration(
                "VolatilityExpansionStrategy",
                VolatilityExpansionStrategy,
                "volatility_expansion",
            ),
            self.StrategyRegistration(
                "RangeBoundFadeStrategy",
                RangeBoundFadeStrategy,
                "range_bound_fade",
            ),
            self.StrategyRegistration(
                "SupportResistanceChannelStrategy",
                SupportResistanceChannelStrategy,
                "support_resistance_channel",
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
            self.StrategyRegistration(
                "CrossSectionalRelativeStrengthRotationStrategy",
                CrossSectionalRelativeStrengthRotationStrategy,
                "cross_sectional_relative_strength_rotation",
            ),
            self.StrategyRegistration(
                "TimeBasedSeasonalityStrategy",
                TimeBasedSeasonalityStrategy,
                "time_based_seasonality",
            ),
            self.StrategyRegistration(
                "TrendFollowingClassicStrategy",
                TrendFollowingClassicStrategy,
                "trend_following_classic",
            ),
            self.StrategyRegistration(
                "LongHorizonQualityCompounderStrategy",
                LongHorizonQualityCompounderStrategy,
                "long_horizon_quality_compounder",
            ),
            self.StrategyRegistration(
                "RegimeAdaptiveMetaAllocatorStrategy",
                RegimeAdaptiveMetaAllocatorStrategy,
                "regime_adaptive_meta_allocator",
            ),
        ]
        self.strategies = []
        self.event_collector = event_collector
        self.last_watchlist_symbols: List[str] = []
        self.last_watchlist_snapshots: dict[str, MarketSnapshot] = {}

        selected_strategy_key = str(
            safe_get_config("SELECTED_STRATEGY", default="", required=False) or ""
        ).strip().lower()

        if strategies is not None:
            self.strategies = list(strategies)
            self._runner_registry = self._build_runner_registry(self.strategies)
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

        self._runner_registry = self._build_runner_registry(self.strategies)
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
        execution_allowed: bool | None = None,
        execution_ready: bool | None = None,
        prep_only: bool | None = None,
    ) -> List[TradeIntent]:
        strategies = list(self.strategies)
        session_norm = canonical_session_label(session_label or "")
        print("[STRATEGY_RUNNER] START")

        run_mode = safe_get_config("RUN_MODE", required=True)
        selected_strategy = safe_get_config("SELECTED_STRATEGY", default="", required=False)
        execution_enabled = safe_get_config(
            "EXECUTION_ENABLED", default=False, required=False
        )
        max_positions = safe_get_config("MAX_POSITIONS", default=1, required=False)
        enabled = safe_get_config(
            "ROSS_MOMENTUM_STRATEGY_ENABLED", default=True, required=False
        )

        if not enabled:
            raise RuntimeError("ROSS STRATEGY DISABLED — HARD FAILURE")

        print("[STRATEGY_RUNNER][CONFIG_SNAPSHOT]")
        print(
            {
                "RUN_MODE": run_mode,
                "EXECUTION_ENABLED": execution_enabled,
                "MAX_POSITIONS": max_positions,
                "ROSS_ENABLED": enabled,
                "SESSION": session_label,
                "SESSION_NORMALIZED": session_norm,
                "STRATEGY_KEY": safe_get_config(
                    "SELECTED_STRATEGY", default=strategy_key, required=False
                )
                or strategy_key,
            }
        )
        print(
            "[STRATEGY_RUNNER][CONFIG] "
            f"RUN_MODE={run_mode} "
            f"EXECUTION_ENABLED={execution_enabled} "
            f"STRATEGY_ENABLED={bool(strategies)} "
            f"SELECTED_STRATEGY={selected_strategy}"
        )
        resolved_execution_allowed = (
            execution_allowed if execution_allowed is not None else session_norm in {"PRE", "RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE"}
        )
        resolved_execution_ready = (
            execution_ready if execution_ready is not None else session_norm in {"PRE", "RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE"}
        )
        resolved_prep_only = (
            prep_only if prep_only is not None else session_norm in {"AH", "OVN", "CLOSED", "WEEKEND"}
        )
        print(
            "[EXECUTION_WINDOW] "
            f"session={session_norm or 'UNKNOWN'} "
            f"execution_allowed={resolved_execution_allowed} "
            f"execution_ready={resolved_execution_ready} "
            f"prep_only={resolved_prep_only}"
        )
        print(
            "[STRATEGY][PROCESS] "
            f"strategy_key={strategy_key} strategies={len(strategies)} "
            f"watchlist={len(watchlist)} session={session_norm} phase={session_phase}"
        )
        if not strategies:
            if len(watchlist) > 0:
                print("[ALERT] NO_INTENTS_GENERATED — CHECK STRATEGY LOGIC")
            print("[STRATEGY][PROCESS] No registered strategies; returning [].")
            return []
        results: List[TradeIntent] = []
        for strategy in strategies:
            runner = self._runner_registry.get(strategy.name)
            if runner:
                result = runner.run(
                    {
                        "watchlist": watchlist,
                        "snapshots": snapshots,
                        "session_label": session_label,
                        "timestamp_utc": timestamp_utc,
                        "mode": mode,
                        "session_phase": session_phase,
                    }
                )
                results.extend(list(result.get("trade_intents", [])))
                continue
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
        if len(watchlist) > 0 and len(results) == 0:
            print("[ALERT] NO_INTENTS_GENERATED — CHECK STRATEGY LOGIC")
        real_detected_setups = sum(1 for intent in results if not getattr(intent, "synthetic", False))
        synthetic_forced_intents = sum(1 for intent in results if getattr(intent, "synthetic", False))
        print(
            "[STRATEGY][PROCESS_SUMMARY] "
            f"real_detected_setups={real_detected_setups} synthetic_forced_intents={synthetic_forced_intents}"
        )
        for intent in results:
            symbol = getattr(intent, "symbol", "UNKNOWN")
            setup_name = getattr(intent, "strategy_name", getattr(intent, "setup_name", "UNKNOWN"))
            confidence = getattr(intent, "confidence", None)
            print("[INTENT]", f"symbol={symbol}", f"setup={setup_name}", f"confidence={confidence}")
        if len(watchlist) > 0 and len(results) == 0:
            patterns_called = 0
            patterns_detected = 0
            missing_inputs_count = 0
            dominant_failure_reason = "no_pattern_traces"
            for strategy in strategies:
                collector = getattr(strategy, "_failure_trace_collector", None)
                traces = getattr(collector, "_symbols", []) if collector is not None else []
                if not traces:
                    continue
                cycle_slice = traces[-len(watchlist) :]
                reasons: list[str] = []
                for trace in cycle_slice:
                    patterns_called += len(getattr(trace, "pattern_traces", []) or [])
                    patterns_detected += len(getattr(trace, "detected_pattern_ids", []) or [])
                    if getattr(trace, "pre_registry_failure_reason", None):
                        missing_inputs_count += 1
                    reasons.extend(
                        [
                            pattern_trace.rejection_reason
                            for pattern_trace in (getattr(trace, "pattern_traces", []) or [])
                            if getattr(pattern_trace, "rejection_reason", None)
                        ]
                    )
                    if getattr(trace, "pre_registry_failure_reason", None):
                        reasons.append(getattr(trace, "pre_registry_failure_reason"))
                if reasons:
                    reason_counts: dict[str, int] = defaultdict(int)
                    for reason in reasons:
                        reason_counts[str(reason)] += 1
                    dominant_failure_reason = max(reason_counts.items(), key=lambda item: item[1])[0]
                break
            print("[ROSS][GLOBAL_DIAG]")
            print(f"- symbols_evaluated={len(watchlist)}")
            print(f"- patterns_called={patterns_called}")
            print(f"- patterns_detected={patterns_detected}")
            print(f"- dominant_failure_reason={dominant_failure_reason}")
            print(f"- missing_inputs_count={missing_inputs_count}")
        results = self._apply_premarket_safety_filter(results, session_norm=session_norm, snapshots=snapshots)
        results = self._inject_live_probe_intents(results)
        return results

    @staticmethod
    def _apply_one_setup_per_symbol(intents: List[TradeIntent]) -> List[TradeIntent]:
        grouped: dict[str, List[TradeIntent]] = defaultdict(list)
        for intent in intents:
            grouped[getattr(intent, "symbol", "UNKNOWN")].append(intent)

        selected: List[TradeIntent] = []
        for symbol, symbol_intents in grouped.items():
            ranked = sorted(
                symbol_intents,
                key=lambda i: float(getattr(i, "confidence", 0.0) or 0.0),
                reverse=True,
            )
            winner = ranked[0]
            selected.append(winner)
            for dropped in ranked[1:]:
                dropped_setup = getattr(dropped, "strategy_name", getattr(dropped, "setup_name", "UNKNOWN"))
                print(
                    "[SETUP][DROP] "
                    f"symbol={symbol} setup={dropped_setup} reason=multi_setup_conflict"
                )
        return selected

    @staticmethod
    def _apply_premarket_safety_filter(
        intents: List[TradeIntent],
        *,
        session_norm: str,
        snapshots: dict[str, MarketSnapshot],
    ) -> List[TradeIntent]:
        if session_norm != "PRE":
            return intents

        filtered: List[TradeIntent] = []
        for intent in intents:
            symbol = getattr(intent, "symbol", "")
            snapshot = snapshots.get(symbol)
            volume = getattr(snapshot, "volume", None)
            rvol = getattr(intent, "rvol", None)
            if volume is None or float(volume) < 1000 or rvol is None:
                print(
                    "[PRE][BLOCK] "
                    f"symbol={symbol} volume={volume} rvol={rvol} reason=low_quality_data"
                )
                continue
            filtered.append(intent)
        return filtered

    @staticmethod
    def _inject_live_probe_intents(intents: List[TradeIntent]) -> List[TradeIntent]:
        if not bool(safe_get_config("LIVE_EXECUTION_PROBE_MODE", default=False, required=False)):
            return intents

        probe_symbols = list(safe_get_config("PROBE_SYMBOLS", default=["UGRO"], required=False) or ["UGRO"])
        merged = list(intents)
        existing_symbols = {getattr(intent, "symbol", "").upper() for intent in intents}
        for symbol in probe_symbols:
            normalized_symbol = str(symbol or "").strip().upper()
            if not normalized_symbol:
                continue
            if normalized_symbol in existing_symbols:
                continue
            print(f"[PROBE][BUY] symbol={normalized_symbol} source=forced_intent")
            merged.append(
                TradeIntent(
                    symbol=normalized_symbol,
                    direction="LONG",
                    strategy_name="LIVE_EXECUTION_PROBE",
                    confidence=1.0,
                    rationale="Forced probe-mode buy intent for broker-path validation.",
                    trader_type="MANUAL",
                    synthetic=True,
                )
            )
        return merged

    @staticmethod
    def _build_runner_registry(strategies: Sequence[object]) -> dict[str, object]:
        registry: dict[str, object] = {}
        for strategy in strategies:
            if isinstance(strategy, RossMomentumStrategyV1):
                runner = RossMomentumRunner()
                runner.strategy = strategy
                registry[strategy.name] = runner
            elif isinstance(strategy, StatisticalIntradayMomentum):
                runner = StatisticalIntradayMomentumRunner()
                runner.strategy = strategy
                registry[strategy.name] = runner
            elif isinstance(strategy, MeanReversionStrategy):
                runner = MeanReversionRunner()
                runner.strategy = strategy
                registry[strategy.name] = runner
        return registry

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
        mode = str(
            safe_get_config(
                "ADAPTIVE_REGIME_STRATEGY_WEIGHTING_MODE",
                default="OFF",
                required=False,
            )
            or "OFF"
        ).upper()
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
        mode = str(
            safe_get_config(
                "ADAPTIVE_REGIME_STRATEGY_WEIGHTING_MODE",
                default="OFF",
                required=False,
            )
            or "OFF"
        ).upper()
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
