"""Adapter that converts SignalEvents into TradeIntents for teaching-only flows."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from src.models.data_models import PatternResult, ScannerCandidate, TradeIntent
from src.signals.types import SignalDecision, SignalEvent, SignalType


@dataclass(frozen=True)
class _SignalSelection:
    event: SignalEvent
    strategy_name: str
    trader_type: str
    priority: int


class SignalToIntentAdapter:
    """Deterministic adapter to map SignalEvents into TradeIntents."""

    _priority_order: Tuple[SignalType, ...] = (
        SignalType.HOD_BREAK,
        SignalType.PREMARKET_HIGH_BREAK,
        SignalType.ORB_1M,
        SignalType.MICRO_PULLBACK,
        SignalType.BULL_FLAG,
    )
    _signal_map: Dict[SignalType, Tuple[str, str]] = {
        SignalType.HOD_BREAK: ("GapAndGoStrategy", "SCALPER"),
        SignalType.PREMARKET_HIGH_BREAK: ("GapAndGoStrategy", "SCALPER"),
        SignalType.ORB_1M: ("GapAndGoStrategy", "SCALPER"),
        SignalType.MICRO_PULLBACK: ("MomentumContinuationStrategy", "MOMENTUM"),
        SignalType.BULL_FLAG: ("MomentumContinuationStrategy", "MOMENTUM"),
    }

    def __init__(self, logger=None) -> None:
        self._logger = logger
        self._priority_map = {
            signal_type: index for index, signal_type in enumerate(self._priority_order)
        }

    def to_trade_intents(
        self,
        signal_events_by_symbol: Dict[str, List[SignalEvent]],
        pattern_results: List[PatternResult],
        scanner_candidates: List[ScannerCandidate],
        tick: int,
    ) -> List[TradeIntent]:
        """Convert SignalEvents into TradeIntents with teaching-first defaults."""

        del scanner_candidates, tick
        patterns_by_symbol = self._group_patterns(pattern_results)
        selected_signals: List[_SignalSelection] = []

        for symbol in sorted(signal_events_by_symbol.keys()):
            events = signal_events_by_symbol.get(symbol, [])
            best_by_trader: Dict[str, _SignalSelection] = {}
            for event in events:
                if event.decision != SignalDecision.SIGNAL:
                    continue
                mapping = self._signal_map.get(event.signal_type)
                if not mapping:
                    continue
                strategy_name, trader_type = mapping
                priority = self._priority_map[event.signal_type]
                candidate = _SignalSelection(
                    event=event,
                    strategy_name=strategy_name,
                    trader_type=trader_type,
                    priority=priority,
                )
                current = best_by_trader.get(trader_type)
                if current is None or self._is_better(candidate, current):
                    best_by_trader[trader_type] = candidate

            for trader_type in sorted(best_by_trader.keys()):
                selected_signals.append(best_by_trader[trader_type])

        intents_with_meta = []
        for selection in selected_signals:
            event = selection.event
            pattern = self._pick_pattern(patterns_by_symbol.get(event.symbol, []))
            confidence = self._merge_confidence(event.confidence, pattern)
            rationale = self._build_rationale(event, pattern)
            stop_loss_price = (
                float(event.stop_level) if event.stop_level is not None else None
            )
            intent = TradeIntent(
                symbol=event.symbol,
                direction="LONG",
                strategy_name=selection.strategy_name,
                confidence=confidence,
                rationale=rationale,
                trader_type=selection.trader_type,
                stop_loss_price=stop_loss_price,
                take_profit_price=None,
                pattern_name=event.signal_type.value,
                invalidation_level=(
                    float(event.invalidation_level)
                    if event.invalidation_level is not None
                    else None
                ),
                data_quality_flags=(
                    pattern.data_quality_flags if pattern is not None else []
                ),
            )
            intents_with_meta.append((intent, selection.priority))

        capped = self._apply_global_cap(intents_with_meta, cap=3)
        return [intent for intent, _priority in capped]

    def _log(self, message: str) -> None:
        if self._logger is None:
            print(message)
            return
        if hasattr(self._logger, "info"):
            self._logger.info(message)
            return
        self._logger(message)

    def _group_patterns(
        self, pattern_results: Iterable[PatternResult]
    ) -> Dict[str, List[PatternResult]]:
        grouped: Dict[str, List[PatternResult]] = {}
        for pattern in pattern_results:
            grouped.setdefault(pattern.symbol, []).append(pattern)
        return grouped

    def _pick_pattern(self, patterns: List[PatternResult]) -> Optional[PatternResult]:
        if not patterns:
            return None
        return max(patterns, key=lambda item: item.confidence)

    def _merge_confidence(
        self, signal_confidence: float, pattern: Optional[PatternResult]
    ) -> float:
        if pattern is None:
            return signal_confidence
        return min(max(signal_confidence, pattern.confidence), 0.95)

    def _build_rationale(
        self, event: SignalEvent, pattern: Optional[PatternResult]
    ) -> str:
        entry = self._format_level(event.entry_level)
        invalid = self._format_level(event.invalidation_level)
        signal_fragment = (
            f"Signal={event.signal_type.value} conf={event.confidence:.2f} "
            f"entry={entry} invalid={invalid}"
        )
        parts = []
        if event.rationale:
            parts.append(event.rationale)
        parts.append(signal_fragment)
        if pattern is not None:
            parts.append(
                f"Pattern={pattern.pattern_name} conf={pattern.confidence:.2f}"
            )
        parts.append("Teaching: signals→intent adapter.")
        return " | ".join(parts)

    def _format_level(self, level: Optional[Decimal]) -> str:
        if level is None:
            return "n/a"
        return f"{level:.2f}"

    def _is_better(self, candidate: _SignalSelection, current: _SignalSelection) -> bool:
        if candidate.priority != current.priority:
            return candidate.priority < current.priority
        return candidate.event.confidence > current.event.confidence

    def _apply_global_cap(
        self, intents_with_meta: List[Tuple[TradeIntent, int]], cap: int
    ) -> List[Tuple[TradeIntent, int]]:
        if len(intents_with_meta) <= cap:
            return intents_with_meta
        sorted_intents = sorted(
            intents_with_meta,
            key=lambda item: (
                -item[0].confidence,
                item[1],
                item[0].symbol,
                item[0].trader_type,
            ),
        )
        return sorted_intents[:cap]
