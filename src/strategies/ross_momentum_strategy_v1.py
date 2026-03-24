"""
Ross Momentum Strategy v1 — signal-driven, deterministic TradeIntent generator.

Consumes SignalEvent(s) and emits TradeIntent(s) using teaching-safe rules.
"""

from __future__ import annotations

import json
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
PATTERN_PRIORITY = {
    "P_ORB": 100,
    "P_PREMKT_BREAK": 95,
    "P_OPENING_DRIVE": 90,
    "P_HOD_BREAK": 85,
    "P_FIRST_PULLBACK": 80,
    "P_MICRO_PULLBACK": 75,
    "P_BULL_FLAG": 70,
    "P_CUP_HANDLE": 65,
    "P_MOMENTUM_RECLAIM": 60,
    "P_RANGE_BREAKOUT": 55,
    "P_ASCENDING_TRIANGLE_BREAKOUT": 50,
    "P_PENNANT_BREAK": 45,
    "P_EMA_PULLBACK": 40,
    "P_VWAP_PULLBACK": 35,
    "P_THREE_BAR_PULLBACK": 30,
    "P_SECOND_PULLBACK": 25,
}


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

    @staticmethod
    def _session_context_profile(session_label: str, session_phase: str) -> tuple[str, float, float]:
        session = str(session_phase or session_label or "PRE").upper()
        if session in {"POWER_HOUR", "RTH_LATE", "LATE"}:
            return "LOWER_MOMENTUM / HIGHER_VOLATILITY", 0.92, 0.60
        if session in {"MIDDAY", "RTH_MID"}:
            return "LOWER_MOMENTUM / NORMAL_VOLATILITY", 0.96, 0.58
        return "NORMAL_MOMENTUM / NORMAL_VOLATILITY", 1.00, 0.0

    @staticmethod
    def _pattern_input_validation(inputs) -> tuple[dict[str, object], list[str]]:
        candle_count = len(getattr(inputs, "candles", []) or [])
        has_recent_candles = candle_count >= 3
        levels = getattr(inputs, "levels", None)
        indicators = getattr(inputs, "indicators", None)
        liquidity = getattr(inputs, "liquidity_context", None)
        has_levels = bool(
            levels
            and any(
                getattr(levels, key, None) is not None
                for key in ("premarket_high", "premarket_low", "hod", "lod", "prior_close")
            )
        )
        has_trend = bool(
            indicators
            and any(getattr(indicators, key, None) is not None for key in ("ema9", "ema20", "ema50", "ema200"))
        )
        has_volume = any(float(getattr(candle, "volume", 0.0) or 0.0) > 0.0 for candle in (getattr(inputs, "candles", []) or []))
        has_rvol = bool(liquidity and getattr(liquidity, "rvol", None) is not None)
        has_float = bool(liquidity and getattr(liquidity, "float_millions", None) is not None)
        payload = {
            "candle_count": candle_count,
            "has_recent_candles": has_recent_candles,
            "has_levels": has_levels,
            "has_trend": has_trend,
            "has_volume": has_volume,
            "has_rvol": has_rvol,
            "has_float": has_float,
        }
        missing = [name for name, ok in payload.items() if name != "candle_count" and not bool(ok)]
        return payload, missing

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
        print(f"[ROSS][PROCESS_START] symbols={len(watchlist)}")
        symbol_traces: List[RossSymbolTrace] = []
        translated_intents: List[TradeIntent] = []
        synthetic_forced_intents = 0
        for row in watchlist:
            symbol = row.get("symbol") if isinstance(row, dict) else getattr(row, "symbol", None)
            if not symbol:
                continue
            print(f"[ROSS][SYMBOL_START] symbol={symbol}")
            expected_quality, confidence_multiplier, preferred_confidence_floor = self._session_context_profile(
                session_label=session_label,
                session_phase=session_phase,
            )
            session_context_label = str(session_phase or session_label or "PRE").upper()
            print("[ROSS][SESSION_CONTEXT]")
            print(f"symbol={symbol}")
            print(f"session={session_context_label}")
            print(f"expected_quality={expected_quality}")
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
            print("[PATTERN_PIPELINE] START")
            inputs, quality_flags = build_runtime_pattern_inputs(
                symbol=symbol,
                row=row,
                snapshot=snapshot if isinstance(snapshot, MarketSnapshot) else None,
                session_label=session_label,
                session_phase=session_phase,
            )
            print("[PATTERN_PIPELINE] DONE")
            if inputs is None:
                print(f"[PATTERN_INPUT][SKIP] symbol={symbol} reason=failed_to_build_inputs")
                symbol_trace.pre_registry_failure_reason = "failed_to_build_inputs"
                symbol_trace.final_outcome = "NO_SETUP:failed_to_build_inputs"
                print(f"[ROSS][NO_SETUP_SUMMARY] symbol={symbol} reason=failed_to_build_inputs")
                print(
                    "[ROSS][DECISION] "
                    f"symbol={symbol} outcome=NO_TRADE reason={symbol_trace.final_outcome}"
                )
                symbol_trace.pattern_traces = []
                symbol_traces.append(symbol_trace)
                self._failure_trace_collector.record_symbol(symbol_trace)
                continue

            input_summary = build_input_snapshot_summary(
                row=row,
                snapshot=snapshot if isinstance(snapshot, MarketSnapshot) else None,
                inputs=inputs,
                session_label=session_label,
                quality_flags=quality_flags,
            )
            symbol_trace.input_summary = input_summary.to_dict()
            print(
                "[ROSS][INPUT_SUMMARY] "
                f"symbol={symbol} candle_count={input_summary.candle_count} last={input_summary.last_price} "
                f"rvol={input_summary.rvol} float={input_summary.float_millions} "
                f"levels_present={input_summary.levels_present} indicators_present={input_summary.indicators_present}"
            )

            print("[ROSS][SETUP_PHASE][START]")
            setup_count = 1 if input_summary.candle_count > 0 else 0
            print(f"[ROSS][SETUP_PHASE][RESULT] symbol={symbol} setups_found={setup_count}")

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
                f"[PATTERN_INPUT_READY] symbol={symbol} candles={len(inputs.candles)} "
                f"session={inputs.session_context}"
            )
            final_payload = {
                "symbol": symbol,
                "has_indicators": input_summary.has_indicators,
                "has_levels": input_summary.has_levels,
                "pct_change": input_summary.pct_change,
                "rvol": input_summary.rvol,
                "float_millions": input_summary.float_millions,
                "missing_fields": input_summary.missing_fields,
            }
            print(f"[PATTERN_INPUT_READY_FINAL] {json.dumps(final_payload, sort_keys=True)}")
            print(
                "[ROSS][PATTERN_RESULTS] "
                f"symbol={symbol} registry=RossPatternRegistry audited_registry_match=true pattern_ids={registry_pattern_ids}"
            )
            pattern_inputs, missing_inputs = self._pattern_input_validation(inputs)
            print(
                "[PATTERN_TRACE][INPUTS] "
                f"symbol={symbol} payload={json.dumps(pattern_inputs, sort_keys=True)}"
            )
            if missing_inputs:
                print(
                    "[PATTERN_TRACE][INPUT_ERROR] "
                    f"symbol={symbol} missing={missing_inputs}"
                )
                symbol_trace.pre_registry_failure_reason = f"missing_inputs:{','.join(missing_inputs)}"
            results = self._pattern_registry.run(
                inputs,
                trace_context=registry_context,
                trace_collector=pattern_traces.append,
            )
            symbol_trace.pattern_traces = pattern_traces
            symbol_trace.detected_pattern_ids = [trace.pattern_id for trace in pattern_traces if trace.detected]
            confirmation_reasons = [trace.rejection_reason for trace in pattern_traces if trace.rejection_reason]
            confirmation_passed = bool(symbol_trace.detected_pattern_ids)
            print(
                "[ROSS][CONFIRMATION][RESULT] "
                f"symbol={symbol} passed={confirmation_passed} reasons={confirmation_reasons}"
            )
            for trace, result in zip(pattern_traces, results):
                trace.confidence = float(getattr(result, "confidence", 0.0) or 0.0)

            detected_patterns = [pattern for pattern in symbol_trace.pattern_traces if pattern.detected]
            preferred_patterns = [
                pattern for pattern in detected_patterns
                if float(getattr(pattern, "confidence", 0.0) or 0.0) >= preferred_confidence_floor
            ]
            if preferred_confidence_floor > 0.0:
                print(
                    "[ROSS][SESSION_FILTER] "
                    f"symbol={symbol} session={session_context_label} "
                    f"preferred_confidence_floor={preferred_confidence_floor:.2f} "
                    f"detected={len(detected_patterns)} preferred={len(preferred_patterns)}"
                )
            selection_pool = preferred_patterns or detected_patterns or symbol_trace.pattern_traces
            best_pattern = self._select_best_pattern(selection_pool)

            if not best_pattern:
                symbol_trace.final_outcome = "NO_SETUP:no_valid_pattern"
                print(
                    f"[ROSS][DECISION] symbol={symbol} outcome=NO_TRADE reason=no_valid_pattern"
                )
                print(f"[ROSS][TRIGGER][RESULT] symbol={symbol} triggered=False")
                print(
                    "[ROSS][NO_SETUP_SUMMARY] "
                    f"symbol={symbol} detected_patterns=0 rejections={[trace.rejection_reason for trace in pattern_traces if trace.rejection_reason]}"
                )
                symbol_traces.append(symbol_trace)
                self._failure_trace_collector.record_symbol(symbol_trace)
                continue

            trade = self._build_trade_from_pattern(best_pattern, inputs)
            if not trade:
                symbol_trace.final_outcome = "NO_SETUP:invalid_trade_structure"
                print(
                    f"[ROSS][DECISION] symbol={symbol} outcome=NO_TRADE reason=invalid_trade_structure"
                )
                print(f"[ROSS][TRIGGER][RESULT] symbol={symbol} triggered=False")
                symbol_traces.append(symbol_trace)
                self._failure_trace_collector.record_symbol(symbol_trace)
                continue

            entry, stop = trade

            base_confidence = float(getattr(best_pattern, "confidence", 0.0) or 0.0)
            adjusted_confidence = max(0.0, min(1.0, base_confidence * confidence_multiplier))
            if confidence_multiplier < 1.0:
                print(
                    "[ROSS][SESSION_ADJUSTMENT] "
                    f"symbol={symbol} session={session_context_label} "
                    f"confidence_before={base_confidence:.4f} confidence_after={adjusted_confidence:.4f} "
                    f"adjustment=market_condition_context_only"
                )
            intent = TradeIntent(
                symbol=symbol,
                direction="LONG",
                strategy_name=self.name,
                confidence=adjusted_confidence,
                rationale=(
                    f"pattern_detected={best_pattern.pattern_id} | entry={entry:.4f} | stop={stop:.4f}"
                ),
                trader_type=self.trader_type,
                stop_loss_price=stop,
                invalidation_level=stop,
                pattern_name=best_pattern.pattern_id,
            )

            translated_intents.append(intent)
            best_pattern.post_detect_disposition = "translated_to_trade_intent"
            best_pattern.final_outcome = "DETECTED_AND_EXECUTED"
            symbol_trace.final_outcome = "SETUP_DETECTED_AND_TRANSLATED"
            print(f"[ROSS][TRIGGER][RESULT] symbol={symbol} triggered=True")
            print(
                "[ROSS][FINAL_SELECTION] "
                f"symbol={symbol} selected_pattern={best_pattern.pattern_id} "
                f"entry={entry} stop={stop}"
            )
            print(
                "[ROSS][DECISION] "
                f"symbol={symbol} outcome=TRADE_READY reason=selected_pattern:{best_pattern.pattern_id}"
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

        print(f"[ROSS][INTENTS] generated={len(translated_intents)}")

        if not translated_intents:
            print("[ROSS][WARNING] NO TRADE INTENTS GENERATED")
        return translated_intents


    def _select_best_pattern(self, pattern_traces):
        detected = [pattern for pattern in pattern_traces if pattern.detected]

        if not detected:
            return None

        for pattern in detected:
            pattern.priority = PATTERN_PRIORITY.get(pattern.pattern_id, 0)
            pattern.confidence = float(getattr(pattern, "confidence", 0.0) or 0.0)

        detected.sort(
            key=lambda pattern: (pattern.priority, pattern.confidence),
            reverse=True,
        )
        return detected[0]

    @staticmethod
    def _build_trade_from_pattern(pattern, inputs):
        candles = list(getattr(inputs, "candles", []) or [])
        last_candle = candles[-1] if candles else None
        price = getattr(inputs, "last_price", None)
        if price is None and last_candle is not None:
            price = getattr(last_candle, "close", None)

        levels = getattr(inputs, "levels", None)
        indicators = getattr(inputs, "indicators", None)

        if pattern.pattern_id == "P_ORB":
            entry = getattr(levels, "hod", None)
            stop = getattr(levels, "lod", None)
        elif pattern.pattern_id in {"P_HOD_BREAK", "P_PREMKT_BREAK"}:
            entry = getattr(levels, "hod", None)
            stop = (entry * 0.97) if entry is not None else None
        elif pattern.pattern_id in {"P_MICRO_PULLBACK", "P_FIRST_PULLBACK"}:
            entry = price
            stop = getattr(indicators, "ema9", None)
        elif pattern.pattern_id == "P_EMA_PULLBACK":
            entry = price
            stop = getattr(indicators, "ema20", None)
        elif pattern.pattern_id == "P_VWAP_PULLBACK":
            entry = price
            stop = getattr(indicators, "vwap", None)
        else:
            entry = price
            stop = (price * 0.97) if price is not None else None

        if entry is None or stop is None:
            return None

        if stop >= entry:
            return None

        return float(entry), float(stop)

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
