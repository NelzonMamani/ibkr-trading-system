"""
Ross Momentum Strategy v1 — signal-driven, deterministic TradeIntent generator.

Consumes SignalEvent(s) and emits TradeIntent(s) using teaching-safe rules.
"""

from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.config.config_resolver import get_config
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
        self._session_allowlist_by_pattern: Dict[str, set[str]] = {
            "P_ORB": {"REGULAR"},
            "P_OPENING_DRIVE": {"REGULAR"},
            "P_FAILED_ORB_FAKEOUT": {"REGULAR"},
        }
        self._blocking_reasons: set[str] = {
            "no continuation close",
            "missing initial impulse",
            "no 1-3 bar pullback",
            "not regular session",
            "missing required levels",
            "missing required indicators",
            "no key level break",
            "structure invalid",
            "no breakout above opening range",
            "no breakout above cup rim",
            "price below premarket high",
            "no prior shakeout under reclaim level",
            "no fakeout probe above opening range",
            "entry_or_stop_missing",
            "entry_stop_structure_invalid",
        }
        self._pre_volume_min = float(get_config("PREMARKET_MIN_VOLUME"))
        self._rth_volume_min = float(get_config("RTH_MIN_VOLUME"))
        self._pre_rvol_min = 0.8
        self._rth_rvol_min = 1.5

    def _session_thresholds(self, session_label: str | None) -> tuple[float, float]:
        session = str(session_label or "").upper()
        if session == "PRE":
            return self._pre_volume_min, self._pre_rvol_min
        return self._rth_volume_min, self._rth_rvol_min

    @staticmethod
    def _is_rth_session(session_label: str | None) -> bool:
        session = str(session_label or "").upper()
        return session in {"RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE", "REG", "REGULAR", "POWER_HOUR", "LATE"}

    def _data_contract_block_reasons(self, *, symbol: str, input_summary, inputs) -> list[str]:
        reasons: list[str] = []
        volume_min, rvol_min = self._session_thresholds(input_summary.session_context)
        session = str(input_summary.session_context or "UNKNOWN").upper()
        print(
            "[DATA][THRESHOLD] "
            f"symbol={symbol} session={session} min_volume={int(volume_min)}"
        )
        volume = input_summary.volume
        rvol = input_summary.rvol
        spread = input_summary.spread
        if "INVALID_VOLUME" in set(input_summary.quality_flags):
            reasons.append("INVALID_VOLUME")
        if volume is None or volume <= volume_min:
            reasons.append(f"VOLUME_BELOW_THRESHOLD({volume_min})")
        if rvol is None:
            reasons.append("RVOL_MISSING")
        elif rvol < 0.5:
            print(f"[ROSS][MOMENTUM_CONTEXT] symbol={symbol} momentum_context=WEAK rvol={rvol}")
            reasons.append("RVOL_WEAK")
        elif rvol < rvol_min:
            reasons.append(f"RVOL_BELOW_THRESHOLD({rvol_min})")
        if self._is_rth_session(input_summary.session_context) and spread is None:
            reasons.append("SPREAD_UNKNOWN")
        if input_summary.last_price is None:
            reasons.append("PRICE_MISSING")
        if not input_summary.has_levels:
            reasons.append("LEVELS_MISSING")
        if not getattr(inputs, "candles", None):
            reasons.append("CANDLES_MISSING")
        return reasons

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
        classification_counts = {
            "DATA_BLOCKED": 0,
            "PATTERN_NO_SETUP": 0,
            "TRIGGER_REJECTED": 0,
            "READY_FOR_EXECUTION": 0,
        }
        for row in watchlist:
            symbol = row.get("symbol") if isinstance(row, dict) else getattr(row, "symbol", None)
            if not symbol:
                continue
            print(f"[ROSS][SYMBOL_START] symbol={symbol}")
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
            symbol_source_tag = "MANUAL_OVERRIDE" if symbol_trace.manual_focus else "WATCHLIST"
            print(
                "[ROSS][SYMBOL_EVAL][START] "
                f"symbol={symbol} source={symbol_source_tag} manual_focus={symbol_trace.manual_focus} "
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
                print(f"[DATA_CONTRACT_BLOCK] symbol={symbol} reason=MISSING_DATA")
                print(f"[CLASSIFICATION] symbol={symbol} category=DATA_BLOCKED")
                classification_counts["DATA_BLOCKED"] += 1
                print(f"[ROSS][NO_SETUP_SUMMARY] symbol={symbol} reason=failed_to_build_inputs")
                self._log_decision_blocked(
                    symbol=symbol,
                    final_stage="pattern",
                    reason=symbol_trace.final_outcome,
                )
                self._log_pipeline_no_decision(symbol)
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
            if symbol_trace.manual_focus:
                manual_warnings: list[str] = []
                if input_summary.volume is None or input_summary.volume <= self._session_thresholds(input_summary.session_context)[0]:
                    manual_warnings.append("LOW_VOLUME")
                if input_summary.pct_change is not None and input_summary.pct_change < 0:
                    manual_warnings.append("NEGATIVE_PCT_CHANGE")
                if input_summary.rvol is None:
                    manual_warnings.append("RVOL_UNAVAILABLE")
                if manual_warnings:
                    print(f"[MANUAL_FOCUS][WARNING] symbol={symbol} reason={','.join(manual_warnings)}")
            block_reasons = self._data_contract_block_reasons(
                symbol=symbol,
                input_summary=input_summary,
                inputs=inputs,
            )
            if block_reasons:
                reason_text = ",".join(block_reasons)
                print(f"[ROSS][DATA_BLOCK] symbol={symbol} reason={reason_text}")
                print(f"[DATA_CONTRACT_BLOCK] symbol={symbol} reason={reason_text}")
                print(f"[CLASSIFICATION] symbol={symbol} category=DATA_BLOCKED")
                classification_counts["DATA_BLOCKED"] += 1
                symbol_trace.pre_registry_failure_reason = f"data_contract_blocked:{reason_text}"
                symbol_trace.final_outcome = f"NO_SETUP:data_contract_blocked:{reason_text}"
                self._log_decision_blocked(
                    symbol=symbol,
                    final_stage="pattern",
                    reason=f"data_contract_blocked:{reason_text}",
                )
                self._log_pipeline_no_decision(symbol)
                symbol_trace.pattern_traces = []
                symbol_traces.append(symbol_trace)
                self._failure_trace_collector.record_symbol(symbol_trace)
                continue

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
            symbol_trace.detected_pattern_ids = [
                trace.pattern_id for trace in pattern_traces if trace.detected and not self._is_inactive_pattern(trace.pattern_id)
            ]
            for trace, result in zip(pattern_traces, results):
                trace.confidence = float(getattr(result, "confidence", 0.0) or 0.0)
            for trace in pattern_traces:
                if self._is_inactive_pattern(trace.pattern_id):
                    print(
                        "[ROSS][PATTERN][INACTIVE] "
                        f"symbol={symbol} pattern_id={trace.pattern_id}"
                    )

            best_pattern = self._select_best_pattern(
                symbol=symbol,
                pattern_traces=symbol_trace.pattern_traces,
            )

            if not best_pattern:
                symbol_trace.final_outcome = "NO_SETUP:no_valid_pattern"
                print(f"[PATTERN_NO_SETUP] symbol={symbol} dominant_reason=no_valid_pattern")
                print(f"[CLASSIFICATION] symbol={symbol} category=PATTERN_NO_SETUP")
                classification_counts["PATTERN_NO_SETUP"] += 1
                self._log_no_trade_root_cause(
                    symbol=symbol,
                    pattern=None,
                    primary_reason="no_valid_pattern",
                    details=["no_detected_tradeable_patterns_after_arbitration"],
                )
                self._log_decision_blocked(
                    symbol=symbol,
                    final_stage="pattern",
                    reason="no_valid_pattern",
                )
                self._log_pipeline_no_decision(symbol)
                print(
                    "[ROSS][NO_SETUP_SUMMARY] "
                    f"symbol={symbol} detected_patterns=0 rejections={[trace.rejection_reason for trace in pattern_traces if trace.rejection_reason]}"
                )
                symbol_traces.append(symbol_trace)
                self._failure_trace_collector.record_symbol(symbol_trace)
                continue

            confirmation_passed, blocking_reasons, warnings = self._evaluate_confirmation(
                symbol=symbol,
                selected_pattern=best_pattern,
                pattern_traces=pattern_traces,
                session_label=session_label,
            )
            if not confirmation_passed:
                self._evaluate_trigger(
                    symbol=symbol,
                    selected_pattern=best_pattern,
                    confirmation_passed=False,
                    trigger_name="confirmation_gate",
                    entry_price=None,
                )
                symbol_trace.dropped_detected_pattern_ids = [best_pattern.pattern_id]
                symbol_trace.final_outcome = "NO_SETUP:confirmation_blocked"
                print(
                    f"[CLASSIFICATION] symbol={symbol} category=TRIGGER_REJECTED"
                )
                classification_counts["TRIGGER_REJECTED"] += 1
                self._log_no_trade_root_cause(
                    symbol=symbol,
                    pattern=best_pattern.pattern_id,
                    primary_reason="confirmation_blocked",
                    details=blocking_reasons or ["unspecified_blocker"],
                )
                self._log_decision_blocked(
                    symbol=symbol,
                    final_stage="confirmation",
                    reason=f"confirmation_blocked:{best_pattern.pattern_id}",
                )
                self._log_pipeline_no_decision(symbol)
                symbol_traces.append(symbol_trace)
                self._failure_trace_collector.record_symbol(symbol_trace)
                continue

            trade = self._build_trade_from_pattern(best_pattern, inputs)
            if not trade:
                symbol_trace.final_outcome = "NO_SETUP:invalid_trade_structure"
                print(
                    f"[CLASSIFICATION] symbol={symbol} category=TRIGGER_REJECTED"
                )
                classification_counts["TRIGGER_REJECTED"] += 1
                self._log_no_trade_root_cause(
                    symbol=symbol,
                    pattern=best_pattern.pattern_id,
                    primary_reason="invalid_trade_structure",
                    details=["entry_or_stop_missing_or_invalid"],
                )
                self._log_decision_blocked(
                    symbol=symbol,
                    final_stage="trigger",
                    reason="invalid_trade_structure",
                )
                self._log_pipeline_no_decision(symbol)
                symbol_traces.append(symbol_trace)
                self._failure_trace_collector.record_symbol(symbol_trace)
                continue

            entry, stop = trade
            print(f"[ROSS][ENTRY_MODEL] symbol={symbol} pattern={best_pattern.pattern_id} entry={entry}")
            print(f"[ROSS][STOP_MODEL] symbol={symbol} pattern={best_pattern.pattern_id} stop={stop}")
            trigger_ready, _trigger_reason = self._evaluate_trigger(
                symbol=symbol,
                selected_pattern=best_pattern,
                confirmation_passed=True,
                trigger_name="confirmation_gate",
                entry_price=entry,
            )

            intent = TradeIntent(
                symbol=symbol,
                direction="LONG",
                strategy_name=self.name,
                confidence=float(getattr(best_pattern, "confidence", 0.0) or 0.0),
                rationale=(
                    f"pattern_detected={best_pattern.pattern_id} | entry={entry:.4f} | stop={stop:.4f}"
                ),
                trader_type=self.trader_type,
                stop_loss_price=stop,
                invalidation_level=stop,
                pattern_name=best_pattern.pattern_id,
            )
            intent.entry_price = entry
            intent.has_valid_pattern = True
            intent.confirmation_passed = confirmation_passed
            intent.trigger_ready = trigger_ready
            intent.decision = "TRADE_READY"

            translated_intents.append(intent)
            best_pattern.post_detect_disposition = "translated_to_trade_intent"
            best_pattern.final_outcome = "DETECTED_AND_EXECUTED"
            symbol_trace.final_outcome = "SETUP_DETECTED_AND_TRANSLATED"
            print(f"[CLASSIFICATION] symbol={symbol} category=READY_FOR_EXECUTION")
            classification_counts["READY_FOR_EXECUTION"] += 1
            print(
                "[ROSS][INTENT][EMIT] "
                f"symbol={symbol} pattern={best_pattern.pattern_id} entry={entry} stop={stop} "
                f"has_valid_pattern={intent.has_valid_pattern} confirmation_passed={intent.confirmation_passed} trigger_ready={intent.trigger_ready}"
            )
            print(
                "[ROSS][FINAL_SELECTION] "
                f"symbol={symbol} selected_pattern={best_pattern.pattern_id} "
                f"entry={entry} stop={stop}"
            )
            print(
                "[ROSS][DECISION] "
                f"symbol={symbol} outcome=TRADE_READY pattern={best_pattern.pattern_id}"
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
        print(
            "[ROSS][PIPELINE_SUMMARY] "
            "dominant_no_trade_reasons="
            f"{{'DATA_BLOCKED': {classification_counts['DATA_BLOCKED']}, "
            f"'PATTERN_NO_SETUP': {classification_counts['PATTERN_NO_SETUP']}, "
            f"'TRIGGER_REJECTED': {classification_counts['TRIGGER_REJECTED']}}}"
        )

        print(f"[ROSS][INTENTS] generated={len(translated_intents)}")

        if not translated_intents:
            print("[ROSS][WARNING] NO TRADE INTENTS GENERATED")
        return translated_intents


    def _select_best_pattern(self, *, symbol: str, pattern_traces):
        all_detected = [pattern for pattern in pattern_traces if pattern.detected]
        tradeable_detected = [pattern for pattern in all_detected if not self._is_inactive_pattern(pattern.pattern_id)]
        rejected_patterns = []
        for pattern in all_detected:
            if self._is_inactive_pattern(pattern.pattern_id):
                rejected_patterns.append(f"{pattern.pattern_id}:inactive")
        detected = []
        for pattern in tradeable_detected:
            pattern.priority = PATTERN_PRIORITY.get(pattern.pattern_id, 0)
            pattern.confidence = float(getattr(pattern, "confidence", 0.0) or 0.0)
            if pattern.priority <= 0:
                rejected_patterns.append(f"{pattern.pattern_id}:unknown_priority")
                continue
            detected.append(pattern)

        if not detected:
            print(
                "[ROSS][ARBITRATION] "
                f"symbol={symbol} detected_patterns={[pattern.pattern_id for pattern in tradeable_detected]} selected_pattern=None rejected_patterns={rejected_patterns}"
            )
            return None

        detected.sort(
            key=lambda pattern: (pattern.priority, pattern.confidence),
            reverse=True,
        )
        selected = detected[0]
        print(
            "[ROSS][ARBITRATION] "
            f"symbol={symbol} detected_patterns={[pattern.pattern_id for pattern in detected]} "
            f"selected_pattern={selected.pattern_id} rejected_patterns={rejected_patterns}"
        )
        return selected

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

    def _is_inactive_pattern(self, pattern_id: str) -> bool:
        return pattern_id in self._pattern_registry.inactive_pattern_ids

    def _evaluate_confirmation(
        self,
        *,
        symbol: str,
        selected_pattern,
        pattern_traces,
        session_label: str,
    ) -> tuple[bool, list[str], list[str]]:
        print(
            "[ROSS][CONFIRMATION][START] "
            f"symbol={symbol} pattern={selected_pattern.pattern_id}"
        )
        selected_trace = next((trace for trace in pattern_traces if trace.pattern_id == selected_pattern.pattern_id), None)
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        if selected_trace and selected_trace.rejection_reason:
            if self._is_blocking_reason(selected_trace.rejection_reason):
                blocking_reasons.append(selected_trace.rejection_reason)
            else:
                warnings.append(selected_trace.rejection_reason)
        for trace in pattern_traces:
            if trace.pattern_id == selected_pattern.pattern_id:
                continue
            if self._is_inactive_pattern(trace.pattern_id) and trace.rejection_reason:
                warnings.append(f"{trace.pattern_id}:{trace.rejection_reason}")
        if not self._session_guard_passed(
            symbol=symbol,
            pattern=selected_pattern.pattern_id,
            session_label=session_label,
        ):
            blocking_reasons.append("not regular session")
        if blocking_reasons:
            first_failed = blocking_reasons[0]
            print(
                "[ROSS][CONFIRMATION][FAIL] "
                f"symbol={symbol} failed_check={first_failed} value=failed expected=pass"
            )
        if warnings:
            print(
                "[ROSS][CONFIRMATION][WARNINGS] "
                f"symbol={symbol} pattern={selected_pattern.pattern_id} reasons={warnings}"
            )
        passed = not blocking_reasons and bool(selected_pattern.detected)
        if passed:
            check_list = ["pattern_detected", "session_guard"]
            print(
                "[ROSS][CONFIRMATION][PASS] "
                f"symbol={symbol} checks={check_list}"
            )
        print(
            "[ROSS][CONFIRMATION][RESULT] "
            f"symbol={symbol} pattern={selected_pattern.pattern_id} passed={passed} "
            f"blocking_reasons={blocking_reasons} warnings={warnings}"
        )
        return passed, blocking_reasons, warnings

    def _session_guard_passed(self, *, symbol: str, pattern: str, session_label: str) -> bool:
        allowed_sessions = self._session_allowlist_by_pattern.get(pattern)
        actual_session = "REGULAR" if session_label in {"REG", "RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE", "REGULAR"} else session_label
        if not allowed_sessions:
            passed = True
        else:
            passed = actual_session in allowed_sessions
        print(
            "[ROSS][SESSION_GUARD] "
            f"symbol={symbol} pattern={pattern} allowed_session={sorted(allowed_sessions) if allowed_sessions else ['ANY']} "
            f"actual_session={actual_session} passed={passed}"
        )
        return passed

    def _is_blocking_reason(self, reason: str) -> bool:
        return reason in self._blocking_reasons

    @staticmethod
    def _log_decision_blocked(*, symbol: str, final_stage: str, reason: str) -> None:
        print(
            "[ROSS][DECISION][BLOCKED] "
            f"symbol={symbol} final_stage={final_stage} reason={reason}"
        )

    @staticmethod
    def _log_pipeline_no_decision(symbol: str) -> None:
        print(
            "[ROSS][PIPELINE][NO_DECISION] "
            f"symbol={symbol} reason=no_valid_pattern_or_trigger"
        )

    def _evaluate_trigger(
        self,
        *,
        symbol: str,
        selected_pattern,
        confirmation_passed: bool,
        trigger_name: str,
        entry_price: float | None,
    ) -> tuple[bool, str]:
        print(
            "[ROSS][TRIGGER][START] "
            f"symbol={symbol} pattern={selected_pattern.pattern_id}"
        )
        if not confirmation_passed:
            reason = "confirmation_not_passed"
            print(f"[ROSS][TRIGGER][FAIL] symbol={symbol} reason={reason}")
            return False, reason
        if entry_price is None:
            reason = "entry_price_missing"
            print(f"[ROSS][TRIGGER][FAIL] symbol={symbol} reason={reason}")
            return False, reason
        print(
            "[ROSS][TRIGGER][PASS] "
            f"symbol={symbol} trigger={trigger_name} entry={entry_price}"
        )
        return True, "trigger_fired"

    @staticmethod
    def _log_no_trade_root_cause(*, symbol: str, pattern: str | None, primary_reason: str, details: list[str]) -> None:
        print(
            "[ROSS][NO_TRADE_ROOT_CAUSE] "
            f"symbol={symbol} pattern={pattern} primary_reason={primary_reason} details={details}"
        )

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
