"""Teaching-first signal engine with deterministic Ross-style triggers."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional

from core.event_collector import EventCollector
from models.data_models import PatternResult, ScannerCandidate
from signals.types import SignalDecision, SignalEvent, SignalType


class SignalEngine:
    """Generate deterministic teaching signals without live data dependencies."""

    def __init__(self, registry=None, event_collector: Optional[EventCollector] = None):
        self._registry = registry
        self._event_collector = event_collector

    def evaluate(
        self,
        scanner_candidates: List[ScannerCandidate],
        pattern_results: List[PatternResult],
        tick: int,
        run_mode: str,
    ) -> Dict[str, List[SignalEvent]]:
        run_mode_normalized = (run_mode or "").upper()
        if run_mode_normalized == "LIVE":
            print("[SIGNAL] LIVE mode — signal generation disabled")
            self._emit_summary(tick, [], Counter())
            return {}

        patterns_by_symbol = self._group_patterns(pattern_results)
        results: Dict[str, List[SignalEvent]] = {}
        by_type: Counter[SignalType] = Counter()
        all_events: List[SignalEvent] = []

        for candidate in scanner_candidates:
            simulated_last_price = self._simulate_last_price(candidate.price, tick)
            symbol_events: List[SignalEvent] = []
            pattern = self._pick_pattern(patterns_by_symbol.get(candidate.symbol, []))
            metadata_base = {}
            if pattern is not None:
                metadata_base["pattern"] = pattern.pattern_name

            if candidate.gap_percent >= 4.0 and simulated_last_price > self._percent_above(
                candidate.price, Decimal("1.01")
            ):
                symbol_events.append(
                    self._build_signal(
                        candidate,
                        tick,
                        SignalType.PREMARKET_HIGH_BREAK,
                        confidence=0.65,
                        entry_level=simulated_last_price,
                        stop_level=simulated_last_price * Decimal("0.985"),
                        rationale=(
                            "Gap-driven momentum with a premarket high break "
                            "teaching trigger."
                        ),
                        metadata=metadata_base,
                    )
                )

            if simulated_last_price > self._percent_above(
                candidate.price, Decimal("1.02")
            ):
                symbol_events.append(
                    self._build_signal(
                        candidate,
                        tick,
                        SignalType.HOD_BREAK,
                        confidence=0.70,
                        entry_level=simulated_last_price,
                        stop_level=simulated_last_price * Decimal("0.99"),
                        rationale="HOD-style momentum continuation trigger.",
                        metadata=metadata_base,
                    )
                )

            if tick == 1 and simulated_last_price > self._percent_above(
                candidate.price, Decimal("1.005")
            ):
                symbol_events.append(
                    self._build_signal(
                        candidate,
                        tick,
                        SignalType.ORB_1M,
                        confidence=0.60,
                        entry_level=simulated_last_price,
                        stop_level=self._to_decimal(candidate.price),
                        rationale="Opening range concept (teaching approximation).",
                        metadata=metadata_base,
                    )
                )

            if tick >= 2 and simulated_last_price > self._percent_above(
                candidate.price, Decimal("1.015")
            ):
                symbol_events.append(
                    self._build_signal(
                        candidate,
                        tick,
                        SignalType.MICRO_PULLBACK,
                        confidence=0.55,
                        entry_level=simulated_last_price,
                        stop_level=simulated_last_price * Decimal("0.99"),
                        rationale="Pullback continuation teaching trigger.",
                        metadata=metadata_base,
                    )
                )

            if self._has_gap_pattern(patterns_by_symbol.get(candidate.symbol, [])) and (
                simulated_last_price > self._percent_above(candidate.price, Decimal("1.018"))
            ):
                symbol_events.append(
                    self._build_signal(
                        candidate,
                        tick,
                        SignalType.BULL_FLAG,
                        confidence=0.60,
                        entry_level=simulated_last_price,
                        stop_level=simulated_last_price * Decimal("0.985"),
                        rationale="Bull flag structure (teaching) continuation signal.",
                        metadata=metadata_base,
                    )
                )

            if symbol_events:
                results[candidate.symbol] = symbol_events
                for event in symbol_events:
                    self._log_signal(event)
                    self._emit_signal_detected(event)
                    by_type[event.signal_type] += 1
                    all_events.append(event)

        self._emit_summary(tick, all_events, by_type)
        return results

    def evaluate_all(
        self,
        context,
        inputs_by_symbol: Dict[str, dict],
    ) -> Dict[str, List[SignalEvent]]:
        scanner_candidates = self._coerce_candidates(inputs_by_symbol)
        return self.evaluate(
            scanner_candidates=scanner_candidates,
            pattern_results=[],
            tick=context.tick,
            run_mode=context.run_mode,
        )

    def _simulate_last_price(self, base_price: float, tick: int) -> Decimal:
        base = self._to_decimal(base_price)
        return self._quantize(base + Decimal(tick) * Decimal("0.01"))

    def _percent_above(self, base_price: float, multiplier: Decimal) -> Decimal:
        return self._quantize(self._to_decimal(base_price) * multiplier)

    def _to_decimal(self, value: float) -> Decimal:
        return Decimal(str(value))

    def _quantize(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _has_gap_pattern(self, patterns: Iterable[PatternResult]) -> bool:
        return any("Gap" in pattern.pattern_name for pattern in patterns)

    def _group_patterns(
        self, patterns: Iterable[PatternResult]
    ) -> Dict[str, List[PatternResult]]:
        grouped: Dict[str, List[PatternResult]] = {}
        for pattern in patterns:
            grouped.setdefault(pattern.symbol, []).append(pattern)
        return grouped

    def _pick_pattern(
        self, patterns: List[PatternResult]
    ) -> Optional[PatternResult]:
        if not patterns:
            return None
        return max(patterns, key=lambda item: item.confidence)

    def _build_signal(
        self,
        candidate: ScannerCandidate,
        tick: int,
        signal_type: SignalType,
        confidence: float,
        entry_level: Decimal,
        stop_level: Decimal,
        rationale: str,
        metadata: Dict[str, str],
    ) -> SignalEvent:
        entry = self._quantize(entry_level)
        stop = self._quantize(stop_level)
        meta = dict(metadata) if metadata else {}
        return SignalEvent(
            signal_type=signal_type,
            symbol=candidate.symbol,
            tick=tick,
            decision=SignalDecision.SIGNAL,
            confidence=confidence,
            rationale=rationale,
            entry_level=entry,
            stop_level=stop,
            target_level=None,
            invalidation_level=stop,
            source="SignalEngine",
            metadata=meta,
        )

    def _coerce_candidates(
        self, inputs_by_symbol: Dict[str, dict]
    ) -> List[ScannerCandidate]:
        candidates: List[ScannerCandidate] = []
        for symbol, inputs in inputs_by_symbol.items():
            base_price = inputs.get("last_price") or inputs.get("price") or 0.0
            candidates.append(
                ScannerCandidate(
                    symbol=symbol,
                    price=float(base_price),
                    gap_percent=float(inputs.get("gap_percent", 0.0)),
                    rvol=float(inputs.get("rvol", 0.0)),
                    float_millions=float(inputs.get("float_millions", 0.0)),
                    rationale="Derived from signal inputs for teaching evaluation.",
                )
            )
        return candidates

    def _log_signal(self, event: SignalEvent) -> None:
        entry = f"{event.entry_level:.2f}" if event.entry_level is not None else "n/a"
        stop = f"{event.stop_level:.2f}" if event.stop_level is not None else "n/a"
        print(
            "[SIGNAL] "
            f"{event.symbol} {event.signal_type.value} "
            f"conf={event.confidence:.2f} entry={entry} stop={stop}"
        )

    def _emit_signal_detected(self, event: SignalEvent) -> None:
        if not self._event_collector:
            return
        self._event_collector.emit(
            event_type="SIGNAL_DETECTED",
            source="SignalEngine",
            payload={
                "symbol": event.symbol,
                "signal_type": event.signal_type.value,
                "confidence": event.confidence,
                "tick": event.tick,
            },
        )

    def _emit_summary(
        self,
        tick: int,
        events: List[SignalEvent],
        by_type: Counter[SignalType],
    ) -> None:
        summary_payload = {
            "tick": tick,
            "total_signals": len(events),
            "by_type": {signal_type.value: count for signal_type, count in by_type.items()},
        }
        print(f"[SIGNAL] total={summary_payload['total_signals']} by_type={summary_payload['by_type']}")
        if not self._event_collector:
            return
        self._event_collector.emit(
            event_type="SIGNAL_SUMMARY",
            source="SignalEngine",
            payload=summary_payload,
        )
