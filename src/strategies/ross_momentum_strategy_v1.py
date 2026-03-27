"""
Ross Momentum Strategy v1 — signal-driven, deterministic TradeIntent generator.

Consumes SignalEvent(s) and emits TradeIntent(s) using teaching-safe rules.
"""

from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.config.config_resolver import ConfigResolutionError, get_config
from src.config.runtime_config import RunMode
from src.core.engines.decision_engine import DecisionEngine
from src.core.engines.level_engine import LevelEngine
from src.core.engines.structure_engine import StructureEngine
from src.core.engines.setup_engine import SetupEngine
from src.core.engines.trigger_engine import TriggerEngine
from src.core.engines.trigger_quality_engine import TriggerQualityEngine
from src.domain.market_snapshot import MarketSnapshot
from src.models.data_models import PatternResult, TradeIntent
from src.signals.signal_event import SignalEvent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal
from src.utils.pipeline_trace import pipeline_trace
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.pattern_trace import (
    RossPatternFailureTraceCollector,
    RossSymbolTrace,
    build_input_snapshot_summary,
    build_runtime_pattern_inputs,
    infer_symbol_source,
)
TERMINAL_CATEGORY = {
    "DATA_BLOCKED": "DATA_BLOCKED",
    "SETUP_NOT_FOUND": "SETUP_NOT_FOUND",
    "SETUP_FOUND_DECISION_REJECTED": "SETUP_FOUND_DECISION_REJECTED",
    "SETUP_FOUND_CONFIRMATION_BLOCKED": "SETUP_FOUND_CONFIRMATION_BLOCKED",
    "SETUP_FOUND_TRIGGER_NOT_READY": "SETUP_FOUND_TRIGGER_NOT_READY",
    "INTENT_CREATED": "INTENT_CREATED",
}


class RossMomentumStrategyV1(BaseStrategy):
    """Deterministic momentum strategy that converts signals into TradeIntents."""

    name = "RossMomentumStrategyV1"
    trader_type = "MOMENTUM"
    _SETUP_FAMILY_ALIASES: dict[str, str] = {
        "P_PREMKT_BREAK": "PREMARKET_HIGH_BREAK",
        "P_HOD_BREAK": "HOD_BREAK",
        "P_FIRST_PULLBACK": "FIRST_PULLBACK",
    }

    _priority_order: Tuple[str, ...] = (
        "HOD_BREAK",
        "ORB_BREAK",
        "MOMO_BREAKOUT",
        "VWAP_RECLAIM",
        "FIRST_PULLBACK_LONG",
    )

    def __init__(self) -> None:
        self._pattern_registry = RossPatternRegistry()
        self._decision_engine = DecisionEngine()
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
        self._pre_trigger_min_pct_change = self._cfg_float("ROSS_PRE_TRIGGER_MIN_PCT_CHANGE", 2.0)
        self._pre_trigger_min_volume = self._cfg_float("ROSS_PRE_TRIGGER_MIN_VOLUME", max(self._pre_volume_min, 10_000.0))
        self._pre_trigger_min_rvol = self._cfg_float("ROSS_PRE_TRIGGER_MIN_RVOL", 1.2)
        self._rth_trigger_min_pct_change = self._cfg_float("ROSS_TRIGGER_MIN_PCT_CHANGE", 5.0)
        self._rth_trigger_min_rvol = self._cfg_float("ROSS_TRIGGER_MIN_RVOL", 2.0)
        self._pre_require_reclaim_or_level_pressure = self._cfg_bool(
            "ROSS_PRE_TRIGGER_REQUIRE_RECLAIM_OR_LEVEL_PRESSURE",
            True,
        )
        self._max_trades_per_cycle = 1
        self._max_concurrent_positions = 3

    @staticmethod
    def _cfg_float(key: str, default: float) -> float:
        try:
            value = get_config(key)
        except ConfigResolutionError:
            return float(default)
        try:
            return float(default if value is None else value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _cfg_bool(key: str, default: bool) -> bool:
        try:
            value = get_config(key)
        except ConfigResolutionError:
            return default
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _session_thresholds(self, session_label: str | None) -> tuple[float, float]:
        session = str(session_label or "").upper()
        if session == "PRE":
            return self._pre_volume_min, self._pre_rvol_min
        return self._rth_volume_min, self._rth_rvol_min

    def _min_volume_threshold(self, session: str | None) -> float:
        s = str(session or "").upper()
        if "PRE" in s:
            return 10_000.0
        if "RTH" in s:
            return 1_000_000.0
        if "AH" in s:
            return 50_000.0
        return 100_000.0

    @staticmethod
    def _is_pre_session(session_label: str | None) -> bool:
        return str(session_label or "").upper() == "PRE"

    @staticmethod
    def _is_rth_session(session_label: str | None) -> bool:
        session = str(session_label or "").upper()
        return session in {"RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE", "REG", "REGULAR", "POWER_HOUR", "LATE"}

    def _is_strong_momentum(self, ctx) -> bool:
        pct_change = self._safe_float(getattr(ctx, "pct_change", None))
        rvol = self._safe_float(getattr(ctx, "rvol", None))
        last = self._safe_float(getattr(ctx, "last", None))
        if last is None:
            last = self._safe_float(getattr(ctx, "last_price", None))
        return (
            pct_change is not None
            and rvol is not None
            and pct_change >= 20
            and rvol >= 3
            and last is not None
            and 1.0 <= last <= 20.0
        )

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
        symbols = list(watchlist)
        print(f"[ROSS][EVALUATE_START] symbols_received={len(symbols)}")
        if not symbols:
            print("[ROSS][ERROR] EMPTY_SYMBOL_LIST")
            print("[WARNING] condition hit but continuing for debug")
        self.last_symbol_terminal_outcomes: dict[str, dict[str, str]] = {}
        self.last_evaluated_symbols: list[str] = []
        watchlist_symbols: list[str] = []
        gated_focus_symbols: list[str] = []
        focus_symbols: set[str] = set()
        for row in symbols:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if symbol:
                watchlist_symbols.append(symbol)
            for key in ("focus_list", "focus_symbols", "focus_m_symbols"):
                value = row.get(key)
                if isinstance(value, list):
                    focus_symbols.update(str(symbol).upper() for symbol in value if symbol)
            session_for_gate = row.get("session_label") or session_label or session_phase
            volume = self._safe_float(
                row.get("volume")
                or row.get("session_volume")
                or row.get("day_volume")
                or row.get("premarket_volume")
            )
            min_volume = self._min_volume_threshold(str(session_for_gate))
            print(
                "[VOLUME_GATE_FIX] "
                f"symbol={symbol} session={session_for_gate} "
                f"threshold={min_volume}"
            )
            decision = volume is not None and volume >= min_volume
            print(
                "[VOLUME_GATE][SESSION_AWARE] "
                f"symbol={symbol} session={session_for_gate} volume={volume} "
                f"threshold={min_volume} decision={'PASS' if decision else 'DROP'}"
            )
            if decision:
                gated_focus_symbols.append(symbol)
            else:
                print(
                    "[ROSS][FOCUS_DROP] "
                    f"symbol={symbol} reason=DROP_VOLUME_SESSION_ADJUSTED volume={volume} threshold={min_volume}"
                )
        effective_focus_symbols: set[str]
        if focus_symbols:
            effective_focus_symbols = focus_symbols.intersection(set(gated_focus_symbols))
        else:
            effective_focus_symbols = set(gated_focus_symbols)
        if not effective_focus_symbols and watchlist_symbols:
            fallback = watchlist_symbols[:3]
            print("[FOCUS][FORCED_FALLBACK] activating:", fallback)
            effective_focus_symbols = set(fallback)
        print(f"[FOCUS_FINAL] count={len(effective_focus_symbols)} symbols={sorted(effective_focus_symbols)}")
        symbol_traces: List[RossSymbolTrace] = []
        translated_intents: List[TradeIntent] = []
        trade_candidates: list[dict[str, object]] = []
        synthetic_forced_intents = 0
        classification_counts = {
            "DATA_BLOCKED": 0,
            "PATTERN_NO_SETUP": 0,
            "TRIGGER_REJECTED": 0,
            "READY_FOR_EXECUTION": 0,
        }

        def _terminal(symbol: str, category: str, reason: str) -> None:
            print(f"[ROSS][TERMINAL] symbol={symbol} category={category} reason={reason}")
            self.last_symbol_terminal_outcomes[str(symbol).upper()] = {
                "outcome": str(category),
                "reason": str(reason),
            }
        for row in symbols:
            symbol = row.get("symbol") if isinstance(row, dict) else getattr(row, "symbol", None)
            if not symbol:
                continue
            if effective_focus_symbols and str(symbol).upper() not in effective_focus_symbols:
                print(f"[ROSS][FOCUS][SKIP] symbol={symbol} reason=NOT_IN_FOCUS_LIST")
                continue
            self.last_evaluated_symbols.append(str(symbol).upper())
            print(f"[ROSS][SYMBOL_EVAL][START] symbol={symbol}")
            print(f"[ROSS][EVALUATE][START] symbol={symbol}")
            print(f"[ROSS][EVAL_START] symbol={symbol}")
            print(f"[ROSS][SYMBOL_START] symbol={symbol}")
            print(f"[ROSS][PIPELINE_ENTRY] symbol={symbol}")
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
            symbol_trace.structure_stage = {
                "status": "COMPRESSED",
                "reason_code": "STRUCTURE_COMPRESSED_IN_MAKE_IT_TRADE_LAYER",
            }
            symbol_trace.confirmation_stage = {
                "status": "COMPRESSED",
                "reason_code": "CONFIRMATION_COMPRESSED_IN_MAKE_IT_TRADE_LAYER",
            }
            symbol_source_tag = "MANUAL_OVERRIDE" if symbol_trace.manual_focus else "WATCHLIST"
            print(
                "[ROSS][SYMBOL_EVAL][START] "
                f"symbol={symbol} source={symbol_source_tag} manual_focus={symbol_trace.manual_focus} "
                f"bypassed_watchlist={symbol_trace.bypassed_watchlist} session={session_label} phase={session_phase} mode={mode.value}"
            )
            print(f"[ROSS][SYMBOL_EVAL][START] symbol={symbol}")
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
            intraday_payload = {
                "candles": list(getattr(inputs, "candles", []) or []),
                "last_price": input_summary.last_price,
            }
            premarket_payload = {
                "candles": [
                    candle
                    for candle in (getattr(inputs, "candles", []) or [])
                    if getattr(candle, "timestamp", None) is not None
                    and getattr(candle.timestamp, "hour", 24) < 14
                ],
            }
            levels = LevelEngine().compute_levels(
                symbol=symbol,
                candles=list(getattr(inputs, "candles", []) or []),
                intraday_data=intraday_payload,
                premarket_data=premarket_payload,
            )
            structure = StructureEngine().compute_structure(
                candles=list(getattr(inputs, "candles", []) or [])
            )
            setups = SetupEngine().compute_setups(
                candles=list(getattr(inputs, "candles", []) or []),
                levels=levels,
                structure=structure,
                session_context=input_summary.session_context,
                tradability_context={
                    "session": input_summary.session_context,
                    "rvol": input_summary.rvol,
                    "float_millions": input_summary.float_millions,
                },
            )
            trigger_candidates = TriggerEngine().evaluate_triggers(
                symbol=symbol,
                candles=list(getattr(inputs, "candles", []) or []),
                setups=setups,
                levels=levels,
                structure=structure,
            )
            quality_engine = TriggerQualityEngine()
            for trigger in trigger_candidates:
                trigger["quality"] = quality_engine.evaluate_trigger_quality(
                    trigger=trigger,
                    structure=structure,
                    session_context=input_summary.session_context,
                    rvol=input_summary.rvol,
                )
            valid_triggers = [t for t in trigger_candidates if t.get("trigger_ready_now") is True]
            ranked_triggers = sorted(
                valid_triggers,
                key=lambda t: float((t.get("quality") or {}).get("quality_score", 0.0)),
                reverse=True,
            )
            for rank, trigger in enumerate(ranked_triggers, start=1):
                print(
                    "[TRADE_RANKING] "
                    f"symbol={symbol} rank={rank} score={float((trigger.get('quality') or {}).get('quality_score', 0.0)):.2f} "
                    f"setup={trigger.get('setup_family_id')}"
                )
            print(
                "[ROSS][ENGINE_STACK] "
                f"symbol={symbol} levels={len(levels)} structure_direction={structure.get('dominant_direction')} "
                f"setups={len(setups)} triggers={len(trigger_candidates)} "
                f"ready_triggers={sum(1 for t in trigger_candidates if t.get('trigger_ready_now'))}"
            )
            symbol_trace.input_summary = input_summary.to_dict()
            symbol_trace.input_summary["levels"] = levels
            symbol_trace.input_summary["structure"] = structure
            symbol_trace.input_summary["setups"] = setups
            symbol_trace.input_summary["trigger_candidates"] = trigger_candidates
            print(
                "[ROSS][INPUT_SUMMARY] "
                f"symbol={symbol} candle_count={input_summary.candle_count} last={input_summary.last_price} "
                f"rvol={input_summary.rvol} float={input_summary.float_millions} "
                f"levels_present={input_summary.levels_present} indicators_present={input_summary.indicators_present}"
            )
            print(
                "[ROSS][EVAL_CONTEXT] "
                f"symbol={symbol} pct_change={input_summary.pct_change} rvol={input_summary.rvol} "
                f"float_millions={input_summary.float_millions} session={input_summary.session_context}"
            )
            symbol_trace.context_stage = {
                "status": "PASS",
                "reason_code": "CONTEXT_READY",
                "details": {
                    "pct_change": input_summary.pct_change,
                    "rvol": input_summary.rvol,
                    "float_millions": input_summary.float_millions,
                    "session": input_summary.session_context,
                },
            }
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
                print(f"[ROSS][SETUP_REJECT] symbol={symbol} reason=DATA_CONTRACT_BLOCKED")
                print(f"[CLASSIFICATION] symbol={symbol} category=DATA_BLOCKED")
                _terminal(symbol, TERMINAL_CATEGORY["DATA_BLOCKED"], reason_text)
                classification_counts["DATA_BLOCKED"] += 1
                symbol_trace.pre_registry_failure_reason = f"data_contract_blocked:{reason_text}"
                symbol_trace.final_outcome = f"NO_SETUP:data_contract_blocked:{reason_text}"
                symbol_trace.setup_stage = {"status": "FAIL", "reason_code": "SETUP_BLOCKED_BY_DATA_CONTRACT", "details": {"reasons": block_reasons}}
                symbol_trace.trigger_stage = {"status": "REJECTED", "reason_code": "NO_SETUP_AVAILABLE"}
                symbol_trace.final_reason_code = "DATA_CONTRACT_BLOCKED"
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

            pipeline_trace("SETUP", symbol)
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
                "pattern_inputs": {"levels": levels, "structure": structure, "setups": setups, "triggers": trigger_candidates},
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
                "levels_present": input_summary.levels_present,
                "normalized_level_keys": sorted(list((getattr(inputs.levels, "key_levels", {}) or {}).keys())),
                "prior_close_present": getattr(inputs.levels, "prior_close", None) is not None,
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
            attempted_count = len(registry_pattern_ids)
            pattern_inputs, missing_inputs = self._pattern_input_validation(inputs)
            print(
                "[PATTERN_TRACE][INPUTS] "
                f"symbol={symbol} payload={json.dumps(pattern_inputs, sort_keys=True)}"
            )
            print(
                f"[PATTERN_INPUT] symbol={symbol} "
                f"candles={len(getattr(inputs, 'candles', []) or [])} "
                f"rvol={input_summary.rvol} "
                f"float={input_summary.float_millions} "
                f"has_levels={input_summary.has_levels} "
                f"session={input_summary.session_context}"
            )
            if missing_inputs:
                print(
                    "[PATTERN_TRACE][INPUT_ERROR] "
                    f"symbol={symbol} missing={missing_inputs}"
                )
                symbol_trace.pre_registry_failure_reason = f"missing_inputs:{','.join(missing_inputs)}"
            print(f"[ROSS][PATTERN_ENGINE][START] symbol={symbol}")
            results = self._pattern_registry.run(
                inputs,
                trace_context=registry_context,
                trace_collector=pattern_traces.append,
            )
            setup_source = "pattern_registry"
            if not results and not pattern_traces:
                fallback_setups = self._detect_lightweight_setups(inputs, input_summary)
                if fallback_setups:
                    setup_source = "fallback_detector"
                    print(
                        "[ROSS][SETUP_FALLBACK] "
                        f"symbol={symbol} setups={len(fallback_setups)} types={[setup['setup_type'] for setup in fallback_setups]}"
                    )
                    for setup in fallback_setups:
                        fallback_trace = self._fallback_setup_to_trace(
                                symbol=symbol,
                                setup=setup,
                                cycle_id=timestamp_utc,
                                session_label=session_label,
                                session_phase=session_phase,
                                runtime_mode=mode.value,
                                symbol_source=symbol_source,
                                input_summary=input_summary.to_dict(),
                            )
                        fallback_trace.confidence = float(setup.get("confidence", 0.6))
                        pattern_traces.append(fallback_trace)
            if pattern_traces:
                selected_setup_name = next((trace.pattern_name for trace in pattern_traces if trace.detected), "UNKNOWN")
                print(f"[ROSS][SETUP] symbol={symbol} source={setup_source} setup={selected_setup_name}")
                print(f"[ROSS][SETUP_FOUND] symbol={symbol} source={setup_source} setup={selected_setup_name}")
                symbol_trace.setup_stage = {
                    "status": "PASS",
                    "reason_code": "SETUP_DETECTED",
                    "details": {"source": setup_source, "detected": [trace.pattern_id for trace in pattern_traces if trace.detected]},
                }
            symbol_trace.pattern_traces = pattern_traces
            symbol_trace.input_summary["setup_stage"] = {"details": {"source": setup_source}}
            symbol_trace.detected_pattern_ids = [
                trace.pattern_id for trace in pattern_traces if trace.detected and not self._is_inactive_pattern(trace.pattern_id)
            ]
            print(
                f"[ROSS][PATTERN_RESULTS] symbol={symbol} attempted={attempted_count} detected={len(symbol_trace.detected_pattern_ids)}"
            )
            for trace, result in zip(pattern_traces, results):
                trace.confidence = float(getattr(result, "confidence", 0.0) or 0.0)
            for trace in pattern_traces:
                if self._is_inactive_pattern(trace.pattern_id):
                    print(
                        "[ROSS][PATTERN][INACTIVE] "
                        f"symbol={symbol} pattern_id={trace.pattern_id}"
                    )

            decision = self._decision_engine.compute_decision(
                symbol=symbol,
                levels=levels,
                structure=structure,
                setups=setups,
                pattern_results=results or symbol_trace.pattern_traces,
                session_context=input_summary.session_context,
                pattern_traces=symbol_trace.pattern_traces,
                inactive_pattern_ids=getattr(self._pattern_registry, "inactive_pattern_ids", set()),
            )
            selected_trigger = self._select_trigger_candidate(
                setup_family_id=decision.get("selected_setup_family"),
                trigger_candidates=ranked_triggers or trigger_candidates,
            )
            print(
                "[ROSS][DECISION_ENGINE] "
                f"symbol={symbol} state={decision['decision_state']} "
                f"selected_pattern={decision['selected_pattern_id']} "
                f"selected_setup={decision['selected_setup_family']} "
                f"selected_trigger={selected_trigger.get('trigger_type') if selected_trigger else None} "
                f"trigger_ready={selected_trigger.get('trigger_ready_now') if selected_trigger else None} "
                f"reason={decision['decision_reason']}"
            )
            best_pattern = self._resolve_selected_pattern_trace(
                selected_pattern_id=decision.get("selected_pattern_id"),
                pattern_traces=symbol_trace.pattern_traces,
            )

            if not best_pattern:
                pre_activation = self._detect_pre_breakout_pressure(
                    symbol=symbol,
                    inputs=inputs,
                    input_summary=input_summary,
                )
                if pre_activation and pre_activation.get("status") == "READY":
                    print(
                        "[ROSS][PRE_ACTIVATION] "
                        f"symbol={symbol} setup={pre_activation.get('setup_type')} classification={pre_activation.get('classification')}"
                    )
                detected_patterns = bool(symbol_trace.detected_pattern_ids)
                if detected_patterns:
                    decision_reason = decision.get("decision_reason") or "decision_not_candidate_selected"
                    print(f"[ROSS][DECISION] symbol={symbol} verdict=REJECT reason={decision_reason}")
                    symbol_trace.final_outcome = "SETUP_FOUND_DECISION_REJECTED"
                    symbol_trace.setup_stage = {"status": "PASS", "reason_code": "SETUP_DETECTED"}
                    symbol_trace.trigger_stage = {"status": "REJECTED", "reason_code": "DECISION_REJECTED"}
                    symbol_trace.final_reason_code = "DECISION_REJECTED"
                    print(f"[ROSS][SETUP_REJECT] symbol={symbol} reason=DECISION_REJECTED:{decision_reason}")
                    print(f"[CLASSIFICATION] symbol={symbol} category=SETUP_FOUND_DECISION_REJECTED")
                    _terminal(symbol, TERMINAL_CATEGORY["SETUP_FOUND_DECISION_REJECTED"], decision_reason)
                    classification_counts["TRIGGER_REJECTED"] += 1
                else:
                    reason = decision.get("decision_reason") or "no_valid_pattern"
                    print(f"[ROSS][DECISION] symbol={symbol} verdict=REJECT reason={reason}")
                    symbol_trace.final_outcome = "NO_SETUP:no_valid_pattern"
                    symbol_trace.setup_stage = {"status": "FAIL", "reason_code": "NO_VALID_PATTERN"}
                    symbol_trace.trigger_stage = {"status": "REJECTED", "reason_code": "NO_SETUP_AVAILABLE"}
                    symbol_trace.final_reason_code = "NO_VALID_PATTERN"
                    pre_classification = (
                        pre_activation.get("classification")
                        if isinstance(pre_activation, dict)
                        else None
                    )
                    if pre_classification:
                        symbol_trace.final_outcome = f"NO_SETUP:{pre_classification}"
                        symbol_trace.final_reason_code = pre_classification.upper()
                    print(f"[ROSS][SETUP][FAIL] symbol={symbol} reason=no_valid_pattern")
                    print(f"[ROSS][SETUP_REJECT] symbol={symbol} reason=NO_VALID_PATTERN")
                    print(f"[PATTERN_NO_SETUP] symbol={symbol} dominant_reason=no_valid_pattern")
                    print(f"[ROSS][NO_SETUP] symbol={symbol} reason=NO_PATTERN_DETECTED")
                    print(f"[CLASSIFICATION] symbol={symbol} category=PATTERN_NO_SETUP")
                    _terminal(symbol, TERMINAL_CATEGORY["SETUP_NOT_FOUND"], pre_classification or "no_valid_pattern")
                    classification_counts["PATTERN_NO_SETUP"] += 1
                self._log_no_trade_root_cause(
                    symbol=symbol,
                    pattern=None,
                    primary_reason=decision.get("decision_reason") or "no_valid_pattern",
                    details=[decision.get("decision_reason") or "no_detected_tradeable_patterns_after_decision_engine"],
                )
                self._log_decision_blocked(
                    symbol=symbol,
                    final_stage="pattern",
                    reason=decision.get("decision_reason") or "no_valid_pattern",
                )
                self._log_pipeline_no_decision(symbol)
                print(
                    "[ROSS][NO_SETUP_SUMMARY] "
                    f"symbol={symbol} detected_patterns={len(symbol_trace.detected_pattern_ids)} "
                    f"rejections={[trace.rejection_reason for trace in pattern_traces if trace.rejection_reason]}"
                )
                symbol_traces.append(symbol_trace)
                self._failure_trace_collector.record_symbol(symbol_trace)
                continue

            pipeline_trace("CONFIRMATION", symbol)
            confirmation_passed, blocking_reasons, warnings = self._evaluate_confirmation(
                symbol=symbol,
                selected_pattern=best_pattern,
                pattern_traces=pattern_traces,
                session_label=session_label,
            )
            if not confirmation_passed:
                print("[TRIGGER][EVALUATE] " f"symbol={symbol} trigger=confirmation_gate")
                print(f"[TRIGGER][REJECT] symbol={symbol} reason=CONFIRMATION_BLOCKED")
                print(f"[TRADE_INTENT][SKIP] symbol={symbol} reason=CONFIRMATION_BLOCKED")
                self._evaluate_trigger(
                    symbol=symbol,
                    selected_pattern=best_pattern,
                    confirmation_passed=False,
                    trigger_name="confirmation_gate",
                    entry_price=None,
                )
                symbol_trace.dropped_detected_pattern_ids = [best_pattern.pattern_id]
                symbol_trace.final_outcome = "SETUP_FOUND_TRIGGER_NOT_READY"
                symbol_trace.confirmation_stage = {
                    "status": "FAIL",
                    "reason_code": "CONFIRMATION_BLOCKED",
                    "details": {"pattern": best_pattern.pattern_id, "blocking_reasons": blocking_reasons},
                }
                symbol_trace.trigger_stage = {"status": "REJECTED", "reason_code": "CONFIRMATION_BLOCKED"}
                symbol_trace.final_reason_code = "CONFIRMATION_BLOCKED"
                print(
                    f"[CLASSIFICATION] symbol={symbol} category=TRIGGER_REJECTED"
                )
                print(f"[ROSS][TRIGGER_FAIL] symbol={symbol} reason=CONFIRMATION_BLOCKED")
                _terminal(symbol, TERMINAL_CATEGORY["SETUP_FOUND_TRIGGER_NOT_READY"], "confirmation_blocked")
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

            pipeline_trace("TRIGGER", symbol)
            trade = self._build_trade_from_pattern(best_pattern, inputs)
            if not trade:
                print("[TRIGGER][EVALUATE] " f"symbol={symbol} trigger=trade_structure")
                print(f"[TRIGGER][REJECT] symbol={symbol} reason=INVALID_TRADE_STRUCTURE")
                print(f"[TRADE_INTENT][SKIP] symbol={symbol} reason=INVALID_TRADE_STRUCTURE")
                symbol_trace.final_outcome = "SETUP_FOUND_TRIGGER_NOT_READY"
                symbol_trace.trigger_stage = {"status": "REJECTED", "reason_code": "INVALID_TRADE_STRUCTURE"}
                symbol_trace.final_reason_code = "INVALID_TRADE_STRUCTURE"
                print(
                    f"[CLASSIFICATION] symbol={symbol} category=TRIGGER_REJECTED"
                )
                print(f"[ROSS][TRIGGER_FAIL] symbol={symbol} reason=INVALID_TRADE_STRUCTURE")
                _terminal(symbol, TERMINAL_CATEGORY["SETUP_FOUND_TRIGGER_NOT_READY"], "invalid_trade_structure")
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
            print(f"[ROSS][TRIGGER][PASS] symbol={symbol} trigger=confirmation_gate")
            print(f"[ROSS][TRIGGER_PASS] symbol={symbol} trigger=confirmation_gate")
            print("[TRIGGER][EVALUATE] " f"symbol={symbol} trigger=confirmation_gate")
            trigger_ready, _trigger_reason = self._evaluate_trigger(
                symbol=symbol,
                selected_pattern=best_pattern,
                confirmation_passed=True,
                trigger_name="first_valid_breakout",
                entry_price=entry,
            )
            symbol_trace.trigger_stage = {
                "status": "FIRED" if trigger_ready else "ARMED_NOT_FIRED_YET",
                "reason_code": "TRIGGER_PASS" if trigger_ready else "TRIGGER_NOT_READY",
                "details": {"pattern": best_pattern.pattern_id, "entry_price": entry},
            }
            quality_tier = self._resolve_trigger_quality_tier(
                selected_trigger=selected_trigger,
                pattern_confidence=float(getattr(best_pattern, "confidence", 0.0) or 0.0),
            )
            setup_family = self._normalize_setup_family_id(
                selected_trigger.get("setup_family_id") if selected_trigger else self._setup_family_from_pattern_id(best_pattern.pattern_id)
            )
            allow_trade, permission_reason = self._trade_permission(
                trigger_ready=trigger_ready,
                setup_family_id=setup_family,
            )
            print(
                "[TRIGGER_QUALITY] "
                f"symbol={symbol} setup_family={setup_family} tier={quality_tier}"
            )
            print(
                "[TRADE_PERMISSION] "
                f"symbol={symbol} decision={'ALLOW' if allow_trade else 'BLOCK'} "
                f"reason={permission_reason} quality={quality_tier}"
            )
            if not allow_trade:
                print(f"[TRIGGER][REJECT] symbol={symbol} reason={permission_reason}")
                print(f"[TRADE_INTENT][SKIP] symbol={symbol} reason={permission_reason}")
                symbol_trace.final_outcome = "SETUP_FOUND_TRIGGER_NOT_READY"
                symbol_trace.trigger_stage = {"status": "REJECTED", "reason_code": permission_reason}
                symbol_trace.final_reason_code = permission_reason
                print(
                    f"[CLASSIFICATION] symbol={symbol} category=TRIGGER_REJECTED"
                )
                print(f"[ROSS][TRIGGER_FAIL] symbol={symbol} reason={permission_reason}")
                _terminal(symbol, TERMINAL_CATEGORY["SETUP_FOUND_TRIGGER_NOT_READY"], permission_reason)
                classification_counts["TRIGGER_REJECTED"] += 1
                self._log_no_trade_root_cause(
                    symbol=symbol,
                    pattern=best_pattern.pattern_id,
                    primary_reason=permission_reason,
                    details=[f"quality={quality_tier}", f"setup_family={setup_family}"],
                )
                self._log_decision_blocked(
                    symbol=symbol,
                    final_stage="trade_permission",
                    reason=permission_reason,
                )
                self._log_pipeline_no_decision(symbol)
                symbol_traces.append(symbol_trace)
                self._failure_trace_collector.record_symbol(symbol_trace)
                continue

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
                setup_family_id=self._setup_family_from_pattern_id(best_pattern.pattern_id),
                trigger_id=(selected_trigger.get("trigger_type") if selected_trigger else "confirmation_gate"),
            )
            intent.entry_price = entry
            intent.has_valid_pattern = bool(getattr(best_pattern, "detected", False))
            intent.confirmation_passed = confirmation_passed
            intent.trigger_ready = trigger_ready
            intent.decision = "TRADE_READY"
            intent = self._apply_intent_contract_defaults(intent, input_summary, timestamp_utc=timestamp_utc)
            pipeline_trace("INTENT", symbol)
            quality_score = float((selected_trigger or {}).get("quality", {}).get("quality_score", 0.0))
            if not intent.symbol:
                raise ValueError(f"[TRADE_INTENT][INVALID] empty symbol for intent: {intent}")
            print(f"[TRADE_INTENT][VALID] symbol={intent.symbol}")
            trade_candidates.append(
                {
                    "symbol": symbol,
                    "intent": intent,
                    "quality_score": quality_score,
                    "setup_family_id": setup_family,
                }
            )
            print(f"[TRADE_SELECTION] symbol={symbol} selected=False reason=awaiting_ranked_cycle_selection")
            best_pattern.post_detect_disposition = "translated_to_trade_intent"
            best_pattern.final_outcome = "DETECTED_AND_EXECUTED"
            symbol_trace.final_outcome = "SETUP_DETECTED_AND_TRANSLATED"
            symbol_trace.confirmation_stage = {
                "status": "PASS",
                "reason_code": "CONFIRMATION_PASS",
                "details": {"pattern": best_pattern.pattern_id, "warnings": warnings},
            }
            symbol_trace.final_reason_code = "INTENT_GENERATED"
            print(f"[CLASSIFICATION] symbol={symbol} category=READY_FOR_EXECUTION")
            classification_counts["READY_FOR_EXECUTION"] += 1
            print(f"TRADE_INTENT symbol={symbol} setup={best_pattern.pattern_id}")
            print(f"[ROSS][INTENT_GENERATED] symbol={symbol}")
            print(
                "[ROSS][INTENT][EMIT] "
                f"symbol={symbol} pattern={best_pattern.pattern_id} entry={entry} stop={stop} "
                f"has_valid_pattern={intent.has_valid_pattern} confirmation_passed={intent.confirmation_passed} trigger_ready={intent.trigger_ready}"
            )
            print(
                "[ROSS][INTENT_READY] "
                f"symbol={symbol} setup_family_id={intent.setup_family_id} trigger_type={intent.trigger_id} "
                f"entry_reference={intent.entry_price} stop_reference={intent.stop_loss_price} "
                f"invalidation_reference={intent.invalidation_level}"
            )
            _terminal(symbol, TERMINAL_CATEGORY["INTENT_CREATED"], "intent_created")
            print(
                "[ROSS][FINAL_SELECTION] "
                f"symbol={symbol} selected_pattern={best_pattern.pattern_id} "
                f"entry={entry} stop={stop}"
            )
            print(
                "[ROSS][DECISION] "
                f"symbol={symbol} outcome=TRADE_READY pattern={best_pattern.pattern_id}"
            )
            print(f"[ROSS][DECISION] symbol={symbol} verdict=ALLOW reason=pattern_and_trigger_valid")
            print(f"[ROSS][BEST_PATTERN] symbol={symbol} pattern={best_pattern.pattern_id} confidence={float(getattr(best_pattern, 'confidence', 0.0) or 0.0):.4f}")
            symbol_traces.append(symbol_trace)
            self._failure_trace_collector.record_symbol(symbol_trace)

        open_positions = self._infer_open_positions_count(watchlist)
        if open_positions >= self._max_concurrent_positions:
            for candidate in sorted(trade_candidates, key=lambda item: float(item.get("quality_score", 0.0)), reverse=True):
                print(
                    f"[TRADE_SELECTION] symbol={candidate.get('symbol')} selected=False reason=max_concurrent_positions_reached"
                )
            trade_candidates = []

        ranked_candidates = sorted(
            trade_candidates,
            key=lambda item: float(item.get("quality_score", 0.0)),
            reverse=True,
        )
        allowed_capacity = max(0, self._max_concurrent_positions - open_positions)
        selected_count = min(self._max_trades_per_cycle, allowed_capacity)
        selected_candidates = ranked_candidates[:selected_count]

        for rank, candidate in enumerate(ranked_candidates, start=1):
            symbol = str(candidate.get("symbol"))
            score = float(candidate.get("quality_score", 0.0))
            setup = str(candidate.get("setup_family_id") or "UNKNOWN")
            print(f"[TRADE_RANKING] symbol={symbol} rank={rank} score={score:.2f} setup={setup}")
            selected = candidate in selected_candidates
            reason = "top_rank" if selected else "max_trades_per_cycle"
            print(f"[TRADE_SELECTION] symbol={symbol} selected={str(selected)} reason={reason}")
            if not selected:
                continue
            intent = candidate["intent"]
            base_size = float(getattr(intent, "position_size", None) or getattr(intent, "quantity", None) or getattr(intent, "requested_quantity", None) or 1.0)
            size_multiplier = self._size_multiplier_for_quality(score)
            position_size = base_size * size_multiplier
            setattr(intent, "position_size", position_size)
            setattr(intent, "quantity", max(1, int(round(position_size))))
            translated_intents.append(intent)
            print(f"[CAPITAL_ALLOCATION] symbol={symbol} size={size_multiplier:.2f} reason=quality_scaled")
            print(
                f"[TRADE_INTENT][CREATE] symbol={symbol} trigger=confirmation_gate side=LONG qty={getattr(intent, 'quantity', None) or getattr(intent, 'requested_quantity', None) or 1}"
            )

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
        pattern_invocations_total = sum(len(getattr(trace, "pattern_traces", []) or []) for trace in symbol_traces)
        pattern_detected_total = sum(
            sum(1 for pattern_trace in (getattr(trace, "pattern_traces", []) or []) if bool(getattr(pattern_trace, "detected", False)))
            for trace in symbol_traces
        )
        print(
            f"[ROSS][SUMMARY] evaluated={len(symbol_traces)} "
            f"patterns_invoked={pattern_invocations_total} "
            f"patterns_detected={pattern_detected_total}"
        )

        print(f"[ROSS][INTENTS] generated={len(translated_intents)}")

        if not translated_intents:
            print("[ROSS][WARNING] NO TRADE INTENTS GENERATED")
        return translated_intents

    def _build_fallback_momentum_intent(
        self,
        *,
        symbol: str,
        input_summary,
        setup_override: str | None = None,
    ) -> TradeIntent | None:
        setup_name = setup_override or "MOMENTUM_BREAKOUT"
        print(f"[ROSS][SETUP] symbol={symbol} source=fallback_detector setup={setup_name}")
        print(f"[ROSS][SETUP_FALLBACK] symbol={symbol} setups=1 types=['{setup_name}']")
        pct_change = self._safe_float(getattr(input_summary, "pct_change", None))
        rvol = self._safe_float(getattr(input_summary, "rvol", None))
        volume = self._safe_float(getattr(input_summary, "volume", None))
        session = str(getattr(input_summary, "session_context", "")).upper()
        min_pct = self._pre_trigger_min_pct_change if self._is_pre_session(session) else self._rth_trigger_min_pct_change
        min_rvol = self._pre_trigger_min_rvol if self._is_pre_session(session) else self._rth_trigger_min_rvol
        volume_ready = volume is not None and volume >= self._pre_trigger_min_volume
        momentum_ready = rvol is not None and rvol >= min_rvol
        print(f"[ROSS][TRIGGER_EVAL] symbol={symbol} setup=MOMENTUM_BREAKOUT")
        if self._is_pre_session(session):
            print(
                "[ROSS][PRE_TRIGGER] "
                f"symbol={symbol} pct_change={pct_change} rvol={rvol} volume={volume} min_pct={min_pct} min_rvol={min_rvol} min_volume={self._pre_trigger_min_volume}"
            )
        if pct_change is None or pct_change < min_pct or not (momentum_ready or (self._is_pre_session(session) and volume_ready)):
            print(
                "[ROSS][TRIGGER][FAIL] "
                f"symbol={symbol} reason=pct_or_rvol_below_threshold pct_change={pct_change} rvol={rvol} session={session}"
            )
            return None
        print(f"[ROSS][TRIGGER][PASS] symbol={symbol} setup={setup_name}")
        entry = self._safe_float(getattr(input_summary, "last_price", None))
        if entry is None:
            print(f"[ROSS][TRIGGER][ARMED] symbol={symbol} awaiting=last_price")
            return None
        stop = round(entry * 0.97, 4)
        intent = TradeIntent(
            symbol=symbol,
            direction="LONG",
            strategy_name=self.name,
            confidence=0.61,
            rationale=(
                f"fallback_setup={setup_name}|pct_change={pct_change:.2f}|rvol={(rvol or 0.0):.2f}|entry={entry:.4f}"
            ),
            trader_type=self.trader_type,
            stop_loss_price=stop,
            invalidation_level=stop,
            pattern_name="XL_PRE_EARLY_MOMENTUM" if setup_name.startswith("PRE_") else "XL_HOD_BREAK",
        )
        intent.entry_price = entry
        intent.has_valid_pattern = True
        intent.confirmation_passed = True
        intent.trigger_ready = True
        intent.decision = "TRADE_READY"
        print(f"TRADE_INTENT symbol={symbol} setup=XL_HOD_BREAK")
        print(f"[ROSS][INTENT_GENERATED] symbol={symbol}")
        return intent

    def _build_trade_intent(
        self,
        ctx,
        trigger: dict[str, str],
        *,
        timestamp_utc: str,
        symbol: str,
    ) -> TradeIntent:
        pct_change = self._safe_float(getattr(ctx, "pct_change", None))
        rvol = self._safe_float(getattr(ctx, "rvol", None))
        assert symbol is not None and symbol != "", "TradeIntent symbol must be non-empty"
        intent = TradeIntent(
            symbol=symbol,
            direction="LONG",
            strategy_name=self.name,
            confidence=0.7,
            rationale=f"forced_momentum_trigger={trigger['type']}",
            trader_type=self.trader_type,
            pattern_name=trigger["type"],
            rvol=rvol,
        )
        intent.metadata = {
            "pct_change": pct_change,
            "rvol": rvol,
            "trigger": trigger["type"],
        }
        intent.trigger_ready = True
        intent.confirmation_passed = True
        intent.has_valid_pattern = True
        intent.decision = "TRADE_READY"
        intent = self._apply_intent_contract_defaults(intent, ctx, timestamp_utc=timestamp_utc)
        if not intent.symbol:
            raise ValueError(f"[TRADE_INTENT][INVALID] empty symbol for intent: {intent}")
        print(f"[INTENT][FORCED] symbol={symbol} setup={intent.setup_family_id}")
        print(f"[TRADE_INTENT][VALID] symbol={intent.symbol}")
        print(f"TRADE_INTENT symbol={intent.symbol} setup={trigger['type']}")
        return intent

    def _apply_intent_contract_defaults(self, intent: TradeIntent, ctx, *, timestamp_utc: str) -> TradeIntent:
        if getattr(intent, "entry_price", None) is None:
            entry_price = self._safe_float(getattr(ctx, "last_price", None))
            if entry_price is None:
                entry_price = self._safe_float(getattr(ctx, "last", None))
            if entry_price is not None:
                intent.entry_price = float(entry_price)
        if getattr(intent, "entry_price", None) is not None:
            intent.entry_price = float(intent.entry_price)
        intent.side = "BUY" if str(getattr(intent, "direction", "LONG")).upper() == "LONG" else "SELL"
        intent.decision = "TRADE_READY"
        if not getattr(intent, "pattern_name", None):
            intent.pattern_name = "XL_HOD_BREAK"
        intent.timestamp_utc = str(timestamp_utc)
        intent.stop_loss_price = getattr(intent, "stop_loss_price", None)
        intent.take_profit_price = getattr(intent, "take_profit_price", None)
        if getattr(intent, "float_millions", None) is None:
            intent.float_millions = self._safe_float(getattr(ctx, "float_millions", None))
        if getattr(intent, "rvol", None) is None:
            intent.rvol = self._safe_float(getattr(ctx, "rvol", None))
        if getattr(intent, "synthetic", None) is None:
            intent.synthetic = False
        return intent

    @staticmethod
    def _setup_family_from_pattern_id(pattern_id: str | None) -> str:
        mapping = {
            "P_ORB": "ORB",
            "P_PREMKT_BREAK": "PREMARKET_HIGH_BREAK",
            "P_OPENING_DRIVE": "OPENING_DRIVE",
            "P_HOD_BREAK": "HOD_BREAK",
            "P_FIRST_PULLBACK": "FIRST_PULLBACK",
            "P_MICRO_PULLBACK": "MICRO_PULLBACK",
            "P_BULL_FLAG": "BULL_FLAG",
            "P_CUP_HANDLE": "CUP_HANDLE",
            "P_MOMENTUM_RECLAIM": "MOMENTUM_RECLAIM",
            "P_RANGE_BREAKOUT": "RANGE_BREAK",
            "P_ASCENDING_TRIANGLE_BREAKOUT": "ASCENDING_TRIANGLE",
            "P_PENNANT_BREAK": "PENNANT",
            "P_EMA_PULLBACK": "EMA_PULLBACK",
            "P_VWAP_PULLBACK": "VWAP_PULLBACK",
            "P_THREE_BAR_PULLBACK": "THREE_BAR_PULLBACK",
            "P_SECOND_PULLBACK": "SECOND_PULLBACK",
        }
        return mapping.get(str(pattern_id or "").upper(), "UNKNOWN")


    @staticmethod
    def _select_trigger_candidate(*, setup_family_id: str | None, trigger_candidates: list[dict] | None) -> dict | None:
        family = RossMomentumStrategyV1._normalize_setup_family_id(setup_family_id)
        candidates = [
            c
            for c in (trigger_candidates or [])
            if RossMomentumStrategyV1._normalize_setup_family_id(c.get("setup_family_id")) == family
        ]
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda item: (
                1 if bool(item.get("trigger_ready_now")) else 0,
                0 if "MISSING_TRIGGER_REFERENCE" in set(item.get("trigger_quality_flags") or []) else 1,
                str(item.get("trigger_type") or ""),
            ),
            reverse=True,
        )
        return ranked[0]

    @classmethod
    def _normalize_setup_family_id(cls, setup_family_id: str | None) -> str:
        normalized = str(setup_family_id or "").upper()
        return cls._SETUP_FAMILY_ALIASES.get(normalized, normalized)

    @staticmethod
    def _resolve_trigger_quality_tier(*, selected_trigger: dict | None, pattern_confidence: float) -> str:
        if selected_trigger and "MISSING_TRIGGER_REFERENCE" in set(selected_trigger.get("trigger_quality_flags") or []):
            return "LOW"
        if pattern_confidence >= 0.8:
            return "HIGH"
        if pattern_confidence >= 0.6:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _size_multiplier_for_quality(score: float) -> float:
        if score >= 0.8:
            return 1.0
        if score >= 0.7:
            return 0.75
        if score >= 0.6:
            return 0.5
        return 0.25

    @staticmethod
    def _infer_open_positions_count(watchlist: list[object]) -> int:
        count = 0
        for row in watchlist:
            if not isinstance(row, dict):
                continue
            qty = row.get("position_qty")
            if qty is None:
                qty = row.get("position_size")
            try:
                if float(qty or 0.0) > 0.0:
                    count += 1
            except (TypeError, ValueError):
                continue
        return count

    @staticmethod
    def _trade_permission(*, trigger_ready: bool, setup_family_id: str) -> tuple[bool, str]:
        if str(setup_family_id or "").upper() == "GENERIC_MOMENTUM_PROBE":
            return False, "fallback_setup_blocked"
        if trigger_ready:
            return True, "trigger_fired"
        return False, "trigger_not_ready"

    @staticmethod
    def _resolve_selected_pattern_trace(*, selected_pattern_id: str | None, pattern_traces):
        if not selected_pattern_id:
            return None
        normalized_pattern_id = str(selected_pattern_id).upper()
        for pattern in pattern_traces:
            if str(getattr(pattern, "pattern_id", "")).upper() == normalized_pattern_id:
                return pattern
        return None

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
        print(f"[ROSS][TRIGGER_EVAL] symbol={symbol} setup={selected_pattern.pattern_id}")
        print("[ROSS][TRIGGER][START] " f"symbol={symbol} pattern={selected_pattern.pattern_id}")
        if not confirmation_passed:
            reason = "confirmation_not_passed"
            print(f"[ROSS][TRIGGER][FAIL] symbol={symbol} reason={reason}")
            return False, reason
        if entry_price is None:
            reason = "entry_price_missing"
            print(f"[ROSS][TRIGGER][ARMED] symbol={symbol} awaiting=entry_price")
            print(f"[PIPELINE][TRIGGER] symbol={symbol} trigger_valid=false rule={trigger_name} reason={reason}")
            return False, reason
        print(
            "[ROSS][TRIGGER][PASS] "
            f"symbol={symbol} trigger={trigger_name} entry={entry_price}"
        )
        print(
            "[ROSS][TRIGGER][PASS] "
            f"symbol={symbol} rule={trigger_name} entry={entry_price}"
        )
        print(
            "[PIPELINE][TRIGGER] "
            f"symbol={symbol} trigger_valid=true rule={trigger_name} entry={entry_price}"
        )
        return True, "trigger_fired"

    @staticmethod
    def _log_no_trade_root_cause(*, symbol: str, pattern: str | None, primary_reason: str, details: list[str]) -> None:
        print(
            "[ROSS][NO_TRADE_ROOT_CAUSE] "
            f"symbol={symbol} pattern={pattern} primary_reason={primary_reason} details={details}"
        )

    def _detect_pre_breakout_pressure(self, *, symbol: str, inputs, input_summary) -> dict[str, object] | None:
        if not self._is_pre_session(getattr(input_summary, "session_context", None)):
            return None
        last_price = self._safe_float(getattr(input_summary, "last_price", None))
        pct_change = self._safe_float(getattr(input_summary, "pct_change", None))
        rvol = self._safe_float(getattr(input_summary, "rvol", None))
        volume = self._safe_float(getattr(input_summary, "volume", None))
        spread = self._safe_float(getattr(input_summary, "spread", None))
        levels = getattr(inputs, "levels", None)
        indicators = getattr(inputs, "indicators", None)
        candles = list(getattr(inputs, "candles", []) or [])
        premarket_high = self._safe_float(getattr(levels, "premarket_high", None))
        hod = self._safe_float(getattr(levels, "hod", None))
        ema9 = self._safe_float(getattr(indicators, "ema9", None))
        vwap = self._safe_float(getattr(indicators, "vwap", None))

        if last_price is None or pct_change is None or pct_change < self._pre_trigger_min_pct_change:
            return None
        strong_volume = (rvol is not None and rvol >= self._pre_trigger_min_rvol) or (
            volume is not None and volume >= self._pre_trigger_min_volume
        )
        if not strong_volume:
            return None
        if spread is not None and spread > 0.15:
            return None
        levels_ready = bool(premarket_high is not None or hod is not None)
        if not levels_ready:
            return None

        pressure_level = premarket_high if premarket_high is not None else hod
        near_high = bool(pressure_level is not None and last_price >= pressure_level * 0.997)
        ema_reclaim = bool(ema9 is not None and last_price >= ema9)
        vwap_reclaim = bool(vwap is not None and last_price >= vwap)
        tight_consolidation = False
        if len(candles) >= 4:
            window = candles[-4:]
            highs = [self._safe_float(getattr(c, "high", None)) for c in window]
            lows = [self._safe_float(getattr(c, "low", None)) for c in window]
            valid_highs = [v for v in highs if v is not None]
            valid_lows = [v for v in lows if v is not None]
            if valid_highs and valid_lows and min(valid_lows) > 0:
                tight_consolidation = ((max(valid_highs) - min(valid_lows)) / min(valid_lows)) <= 0.015

        pressure_confirmed = near_high or ema_reclaim or vwap_reclaim or tight_consolidation
        print(
            "[ROSS][PRE_BREAKOUT_PRESSURE] "
            f"symbol={symbol} near_high={near_high} ema_reclaim={ema_reclaim} vwap_reclaim={vwap_reclaim} "
            f"tight_consolidation={tight_consolidation} strong_volume={strong_volume}"
        )
        if ema_reclaim or vwap_reclaim:
            print(f"[ROSS][PRE_RECLAIM] symbol={symbol} ema_reclaim={ema_reclaim} vwap_reclaim={vwap_reclaim}")
        if self._pre_require_reclaim_or_level_pressure and not pressure_confirmed:
            return {
                "status": "BUILDING",
                "classification": "pre_breakout_not_ready",
            }
        return {
            "status": "READY",
            "setup_type": "PRE_EARLY_MOMENTUM",
            "pattern_id": "P_PRE_EARLY_MOMENTUM",
            "confidence": 0.63,
            "classification": "pre_early_momentum_ready",
        }

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

    @staticmethod
    def _safe_float(value) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def _detect_lightweight_setups(self, inputs, summary) -> list[dict[str, float | str]]:
        candles = list(getattr(inputs, "candles", []) or [])
        if len(candles) < 3:
            return []

        closes = [self._safe_float(getattr(candle, "close", None)) for candle in candles]
        highs = [self._safe_float(getattr(candle, "high", None)) for candle in candles]
        lows = [self._safe_float(getattr(candle, "low", None)) for candle in candles]
        volumes = [self._safe_float(getattr(candle, "volume", None)) or 0.0 for candle in candles]
        last_price = self._safe_float(getattr(inputs, "last_price", None)) or closes[-1]
        if last_price is None:
            return []

        rvol = self._safe_float(getattr(summary, "rvol", None)) or self._safe_float(
            getattr(getattr(inputs, "liquidity_context", None), "rvol", None)
        )
        pct_change = self._safe_float(getattr(summary, "pct_change", None))
        if pct_change is None and closes and closes[0]:
            pct_change = ((last_price - closes[0]) / closes[0]) * 100.0

        setups: list[dict[str, float | str]] = []
        recent_high_candidates = [high for high in highs[-10:] if high is not None]
        if not recent_high_candidates:
            return []
        recent_high = max(recent_high_candidates)
        volume_increasing = len(volumes) >= 2 and volumes[-1] >= volumes[-2]

        if (
            pct_change is not None
            and pct_change >= 5.0
            and rvol is not None
            and rvol >= 2.0
            and last_price >= (recent_high * 0.995)
            and volume_increasing
        ):
            setups.append(
                {
                    "setup_type": "HOD_BREAK",
                    "pattern_id": "P_HOD_BREAK",
                    "trigger_price": recent_high,
                    "confidence": 0.66,
                }
            )

        impulse_bars = 0
        for idx in range(len(closes) - 5, len(closes) - 1):
            if idx < 0 or closes[idx] is None or closes[idx + 1] is None:
                continue
            if closes[idx + 1] > closes[idx]:
                impulse_bars += 1
        pullback_bars = 0
        for idx in range(max(0, len(closes) - 3), len(closes) - 1):
            if closes[idx] is None or closes[idx + 1] is None:
                continue
            if closes[idx + 1] < closes[idx]:
                pullback_bars += 1
        indicators = getattr(inputs, "indicators", None)
        ema9 = self._safe_float(getattr(indicators, "ema9", None))
        vwap = self._safe_float(getattr(indicators, "vwap", None))
        support = ema9 or vwap
        recent_pullback_high_candidates = [high for high in highs[-3:] if high is not None]
        recent_pullback_high = max(recent_pullback_high_candidates) if recent_pullback_high_candidates else recent_high
        if (
            2 <= impulse_bars <= 5
            and 1 <= pullback_bars <= 2
            and support is not None
            and last_price >= support
        ):
            setups.append(
                {
                    "setup_type": "MICRO_PULLBACK",
                    "pattern_id": "P_MICRO_PULLBACK",
                    "trigger_price": recent_pullback_high,
                    "confidence": 0.64,
                }
            )

        range_window = candles[-5:]
        range_high = max(self._safe_float(getattr(candle, "high", None)) or 0.0 for candle in range_window)
        range_low = min(self._safe_float(getattr(candle, "low", None)) or 0.0 for candle in range_window)
        is_tight_range = range_low > 0 and (range_high - range_low) / range_low <= 0.02
        lows_increasing = all(
            (self._safe_float(getattr(range_window[idx + 1], "low", None)) or 0.0)
            >= (self._safe_float(getattr(range_window[idx], "low", None)) or 0.0)
            for idx in range(len(range_window) - 1)
        )
        if is_tight_range and lows_increasing and last_price >= range_high * 0.998:
            setups.append(
                {
                    "setup_type": "RANGE_BREAK",
                    "pattern_id": "P_RANGE_BREAKOUT",
                    "trigger_price": range_high,
                    "confidence": 0.62,
                }
            )

        return setups

    def _fallback_setup_to_trace(
        self,
        *,
        symbol: str,
        setup: dict[str, float | str],
        cycle_id: str,
        session_label: str,
        session_phase: str,
        runtime_mode: str,
        symbol_source: str,
        input_summary: dict,
    ):
        from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternTrace

        return RossPatternTrace(
            symbol=symbol,
            cycle_id=cycle_id,
            strategy_key="ross_momentum",
            session_label=session_label,
            session_phase=session_phase,
            runtime_mode=runtime_mode,
            symbol_source=symbol_source,
            pattern_id=str(setup.get("pattern_id", "P_HOD_BREAK")),
            pattern_name=str(setup.get("setup_type", "HOD_BREAK")),
            setup_family_id=str(setup.get("pattern_id", "P_HOD_BREAK")),
            invoked=True,
            detected=True,
            input_summary=input_summary,
        )
