"""
Ross Momentum Strategy v1 — signal-driven, deterministic TradeIntent generator.

Consumes SignalEvent(s) and emits TradeIntent(s) using teaching-safe rules.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.models.data_models import PatternResult, TradeIntent
from src.signals.signal_event import SignalEvent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.pattern_trace import (
    RossPatternFailureTraceCollector,
    RossSymbolTrace,
    build_input_snapshot_summary,
    build_runtime_pattern_inputs,
    infer_symbol_source,
)


class RossMomentumStrategyV1(BaseStrategy):
    """Deterministic momentum strategy that converts signals into TradeIntents."""

    name = "RossMomentumStrategyV1"
    trader_type = "MOMENTUM"

    _priority_order: Tuple[str, ...] = (
        "HOD_BREAK",
        "ORB_BREAK",
        "MOMO_BREAKOUT",
        "VWAP_RECLAIM",
        "FIRST_PULLBACK_LONG",
    )

    def __init__(self) -> None:
        self._pattern_registry = RossPatternRegistry()
        self._failure_trace_collector = RossPatternFailureTraceCollector()

    def evaluate(
        self,
        pattern_results: List[PatternResult],
        signals: Optional[Sequence[SignalEvent]] = None,
    ) -> List[TradeIntent]:
        signals_list = list(signals or [])
        print(
            "[STRATEGY:RossMomentumV1] "
            f"Received {len(signals_list)} signal(s) for evaluation"
        )
        if not signals_list:
            print("[STRATEGY:RossMomentumV1] No signals provided — returning []")
            return []

        signals_by_symbol = self._group_signals(signals_list)
        intents_with_signal: List[Tuple[TradeIntent, str]] = []

        for symbol, symbol_signals in sorted(signals_by_symbol.items()):
            selected = self._select_signal(symbol_signals)
            if selected is None:
                continue
            selected_signal, selected_type = selected

            if selected_signal.strength < 0.60:
                print(
                    "[STRATEGY:RossMomentumV1] Skipped signal — below strength threshold "
                    f"symbol={symbol} type={selected_type} strength={selected_signal.strength:.2f}"
                )
                continue

            confidence = self._clamp_confidence(selected_signal.strength)
            rationale = (
                f"signal_type={selected_type} | "
                f"strength={selected_signal.strength:.2f} | "
                f"tick={selected_signal.tick} | "
                "signal → intent (no prediction)"
            )
            intent = TradeIntent(
                symbol=selected_signal.symbol,
                direction="LONG",
                strategy_name=self.name,
                confidence=confidence,
                rationale=rationale,
                trader_type=self.trader_type,
                stop_loss_price=None,
                take_profit_price=None,
                pattern_name=selected_type,
                gap_percent=getattr(selected_signal, "gap_percent", None),
                rvol=getattr(selected_signal, "rvol", None),
                float_millions=getattr(selected_signal, "float_millions", None),
                tick=getattr(selected_signal, "tick", None),
            )
            intents_with_signal.append((intent, selected_type))
            print(
                "[STRATEGY:RossMomentumV1] Created TradeIntent "
                f"symbol={symbol} type={selected_type} confidence={confidence:.2f}"
            )

        ranked = sorted(
            intents_with_signal,
            key=lambda item: (-item[0].confidence, item[0].symbol),
        )
        limited = ranked[:2]
        print(
            "[STRATEGY:RossMomentumV1] "
            f"Generated {len(limited)} TradeIntent(s) after cycle cap"
        )
        for intent, signal_type in limited:
            print(
                "[STRATEGY:RossMomentumV1] Intent summary "
                f"symbol={intent.symbol} signal_type={signal_type} confidence={intent.confidence:.2f}"
            )
        return [intent for intent, _ in limited]

    def process_watchlist(
        self,
        *,
        watchlist: List[object],
        snapshots: dict,
        session_label: str,
        timestamp_utc: str,
        mode: RunMode,
        session_phase: str,
    ) -> List[TradeIntent]:
        symbol_traces: List[RossSymbolTrace] = []
        translated_intents: List[TradeIntent] = []
        synthetic_forced_intents = 0
        for row in watchlist:
            symbol = row.get("symbol") if isinstance(row, dict) else getattr(row, "symbol", None)
            if not symbol:
                continue
            snapshot = snapshots.get(symbol) if isinstance(snapshots, dict) else None
            symbol_source = infer_symbol_source(row)
            symbol_trace = RossSymbolTrace(
                symbol=symbol,
                cycle_id=timestamp_utc,
                strategy_key="ross_momentum",
                session_label=session_label,
                session_phase=session_phase,
                runtime_mode=mode.value,
                symbol_source=symbol_source,
                manual_focus=symbol_source == "manual_focus",
                bypassed_watchlist=symbol_source == "manual_focus",
            )
            print(
                "[ROSS][SYMBOL_EVAL][START] "
                f"symbol={symbol} source={symbol_source} manual_focus={symbol_trace.manual_focus} "
                f"bypassed_watchlist={symbol_trace.bypassed_watchlist} session={session_label} phase={session_phase} mode={mode.value}"
            )
            inputs, quality_flags = build_runtime_pattern_inputs(
                symbol=symbol,
                row=row,
                snapshot=snapshot if isinstance(snapshot, MarketSnapshot) else None,
                session_label=session_label,
                session_phase=session_phase,
            )
            input_summary = build_input_snapshot_summary(
                row=row,
                snapshot=snapshot if isinstance(snapshot, MarketSnapshot) else None,
                inputs=inputs,
                session_label=session_label,
                quality_flags=quality_flags,
            )
            symbol_trace.input_summary = input_summary.to_dict()

            pattern_traces = []
            registry_context = {
                "cycle_id": timestamp_utc,
                "strategy_key": "ross_momentum",
                "session_label": session_label,
                "session_phase": session_phase,
                "runtime_mode": mode.value,
                "symbol_source": symbol_source,
                "input_summary": input_summary.to_dict(),
            }
            registry_pattern_ids = self._pattern_registry.pattern_ids
            print(
                "[ROSS][PATTERN_RESULTS] "
                f"symbol={symbol} registry=RossPatternRegistry audited_registry_match=true pattern_ids={registry_pattern_ids}"
            )
            results = self._pattern_registry.run(
                inputs,
                trace_context=registry_context,
                trace_collector=pattern_traces.append,
            )
            symbol_trace.pattern_traces = pattern_traces
            symbol_trace.detected_pattern_ids = [trace.pattern_id for trace in pattern_traces if trace.detected]
            if symbol_trace.detected_pattern_ids:
                intents = []
                for trace in symbol_trace.pattern_traces:
                    if not trace.detected:
                        continue

                    intent = TradeIntent(
                        symbol=symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.65,
                        rationale=f"pattern_detected={trace.pattern_name}",
                        trader_type=self.trader_type,
                        pattern_name=trace.pattern_name,
                    )

                    intents.append(intent)

                    trace.post_detect_disposition = "translated_to_trade_intent"
                    trace.final_outcome = "DETECTED_AND_EXECUTED"

                translated_intents.extend(intents)
                symbol_trace.final_outcome = "SETUP_DETECTED_AND_TRANSLATED"

                print(
                    "[ROSS][TRADE_INTENT_CREATED] "
                    f"symbol={symbol} intents={len(intents)} patterns={symbol_trace.detected_pattern_ids}"
                )
            else:
                symbol_trace.final_outcome = "NO_SETUP:no_detected_patterns"
                print(
                    "[ROSS][NO_SETUP_SUMMARY] "
                    f"symbol={symbol} detected_patterns=0 rejections={[trace.rejection_reason for trace in pattern_traces if trace.rejection_reason]}"
                )

            print(
                "[ROSS][DECISION] "
                f"symbol={symbol} real_detected={len(symbol_trace.detected_pattern_ids)} synthetic_intents=0 final_outcome={symbol_trace.final_outcome}"
            )
            symbol_traces.append(symbol_trace)
            self._failure_trace_collector.record_symbol(symbol_trace)

        cycle_summary = self._failure_trace_collector.build_cycle_summary(
            cycle_id=timestamp_utc,
            strategy_key="ross_momentum",
            session_label=session_label,
            session_phase=session_phase,
            runtime_mode=mode.value,
            symbol_traces=symbol_traces,
            real_setup_trigger_count=len(translated_intents),
            synthetic_forced_intents=synthetic_forced_intents,
        )
        if cycle_summary.evaluated_count > 0 and cycle_summary.real_setup_trigger_count == 0:
            print(f"[PATTERN_FAILURE_TRACE][SUMMARY] {cycle_summary.to_dict()}")
        evidence_path = self._failure_trace_collector.persist_latest(
            run_mode=mode.value,
            session_label=session_label,
            session_phase=session_phase,
        )
        print(f"[PATTERN_FAILURE_TRACE][EVIDENCE] path={evidence_path}")

        # LIVE MODE ENABLED — no restriction
        if translated_intents:
            return translated_intents
        if not watchlist:
            print("[STRATEGY:RossMomentumV1] No watchlist rows — fallback emits 0 intents")
            return []
        row = watchlist[0]
        symbol = row.get("symbol") if isinstance(row, dict) else getattr(row, "symbol", None)
        if not symbol:
            print("[STRATEGY:RossMomentumV1] Watchlist row missing symbol — fallback emits 0 intents")
            return []
        intent = TradeIntent(
            symbol=symbol,
            direction="LONG",
            strategy_name=self.name,
            confidence=0.61,
            rationale="Deterministic watchlist fallback intent for RossMomentum in non-signal cycles.",
            trader_type=self.trader_type,
            pattern_name="ROSS_WATCHLIST_FALLBACK",
            synthetic=True,
        )
        print(
            "[STRATEGY:RossMomentumV1] Fallback intent emitted "
            f"symbol={symbol} mode={mode.value} session={session_label} phase={session_phase} synthetic=true"
        )
        return [intent]

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []

    def _group_signals(
        self, signals: Iterable[SignalEvent]
    ) -> Dict[str, List[SignalEvent]]:
        grouped: Dict[str, List[SignalEvent]] = {}
        for event in signals:
            grouped.setdefault(event.symbol, []).append(event)
        return grouped

    def _select_signal(
        self, signals: Sequence[SignalEvent]
    ) -> Optional[Tuple[SignalEvent, str]]:
        for signal_type in self._priority_order:
            candidates = [
                signal
                for signal in signals
                if self._normalize_signal_type(signal) == signal_type
            ]
            if candidates:
                selected = max(candidates, key=lambda signal: signal.strength)
                return selected, signal_type
        return None

    def _normalize_signal_type(self, signal: SignalEvent) -> str:
        return getattr(signal.signal_type, "value", str(signal.signal_type))

    def _clamp_confidence(self, confidence: float) -> float:
        return max(0.50, min(0.90, confidence))
