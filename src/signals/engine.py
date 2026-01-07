"""Signal engine for evaluating signal implementations."""

from typing import Dict, List, Optional

from core.event_collector import EventCollector
from signals.registry import SignalRegistry
from signals.types import SignalContext, SignalDecision, SignalEvent, SignalType, validate_signal_event


class SignalEngine:
    def __init__(self, registry: SignalRegistry, event_collector: Optional[EventCollector] = None):
        self._registry = registry
        self._event_collector = event_collector

    def evaluate_all(
        self,
        context: SignalContext,
        inputs_by_symbol: Dict[str, dict],
    ) -> Dict[str, List[SignalEvent]]:
        results: Dict[str, List[SignalEvent]] = {}
        for symbol, inputs in inputs_by_symbol.items():
            symbol_context = SignalContext(
                symbol=symbol,
                tick=context.tick,
                run_mode=context.run_mode,
                session=context.session,
            )
            symbol_events: List[SignalEvent] = []
            for signal in self._registry.list_signals():
                event = signal.evaluate(symbol_context, inputs)
                ok, reason = validate_signal_event(event)
                if not ok:
                    invalid_event = SignalEvent(
                        signal_type=event.signal_type,
                        symbol=event.symbol,
                        tick=event.tick,
                        decision=SignalDecision.INVALID,
                        confidence=0.0,
                        rationale=f"Validation failed: {reason}",
                        entry_level=None,
                        stop_level=None,
                        target_level=None,
                        invalidation_level=None,
                        source=event.source,
                    )
                    symbol_events.append(invalid_event)
                    self._emit_system_event("SIGNAL_INVALID", invalid_event)
                    continue

                if event.decision == SignalDecision.SIGNAL:
                    symbol_events.append(event)
                    self._emit_system_event("SIGNAL_EMITTED", event)
                elif event.decision == SignalDecision.INVALID:
                    symbol_events.append(event)
                    self._emit_system_event("SIGNAL_INVALID", event)

            if symbol_events:
                results[symbol] = symbol_events
        return results

    def _emit_system_event(self, event_type: str, event: SignalEvent) -> None:
        if not self._event_collector:
            return
        payload = {
            "symbol": event.symbol,
            "signal_type": event.signal_type.value,
            "decision": event.decision.value,
            "confidence": event.confidence,
        }
        self._event_collector.emit(
            event_type=event_type,
            source=event.source,
            payload=payload,
        )
