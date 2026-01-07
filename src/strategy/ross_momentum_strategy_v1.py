"""
Ross Momentum Strategy v1 — deterministic, teaching-first intent generator.

This strategy consumes PatternResults (and optional SignalEvents) to produce
TradeIntents using Ross-style momentum heuristics. It is SIM-only and outputs
intents without any broker or execution logic.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from models.data_models import PatternResult, TradeIntent
from signals.signal_event import SignalEvent
from strategy.base_strategy import BaseStrategy
from strategy.exit_signal import ExitSignal


@dataclass
class RossMomentumStrategyConfig:
    enabled: bool = True
    min_confidence: float = 0.55
    allow_short: bool = False
    max_intents_per_cycle: int = 3
    require_signal_confirmation: bool = False


class RossMomentumStrategyV1(BaseStrategy):
    """Ross-style momentum strategy that emits teaching TradeIntents."""

    name = "RossMomentumStrategyV1"

    def __init__(self, config: Optional[RossMomentumStrategyConfig] = None) -> None:
        self.config = config or RossMomentumStrategyConfig()

    def evaluate(
        self,
        pattern_results: List[PatternResult],
        signals: Optional[Sequence[SignalEvent]] = None,
    ) -> List[TradeIntent]:
        print(
            "[STRATEGY:RossMomentum] Evaluation start — received "
            f"{len(pattern_results)} pattern(s) for review"
        )
        signals_by_symbol = self._group_signals(signals or [])
        trade_intents: List[TradeIntent] = []

        for pattern in pattern_results:
            base_confidence = self._base_confidence(pattern)
            bullish_signals = self._bullish_signals(signals_by_symbol.get(pattern.symbol))
            signal_confirmed = bool(bullish_signals)

            if self.config.require_signal_confirmation and not signal_confirmed:
                print(
                    "[STRATEGY:RossMomentum] Skipped pattern — "
                    f"signal confirmation required but missing (symbol={pattern.symbol})"
                )
                continue

            confidence = base_confidence
            if signal_confirmed:
                confidence = self._clamp_confidence(confidence + 0.07)

            if confidence < self.config.min_confidence:
                print(
                    "[STRATEGY:RossMomentum] Skipped pattern — confidence below threshold "
                    f"(symbol={pattern.symbol} confidence={confidence:.2f} min={self.config.min_confidence:.2f})"
                )
                continue

            trader_type = "MOMENTUM"
            if self._has_first_pullback_long(bullish_signals):
                trader_type = "SCALPER"

            rationale = (
                "RossMomentumStrategyV1 | "
                f"pattern='{pattern.pattern_name}' | "
                f"signal_confirmation={'yes' if signal_confirmed else 'no'} | "
                f"confidence={confidence:.2f}"
            )
            trade_intents.append(
                TradeIntent(
                    symbol=pattern.symbol,
                    direction="LONG",
                    strategy_name=self.name,
                    confidence=confidence,
                    rationale=rationale,
                    trader_type=trader_type,
                    stop_loss_price=None,
                    take_profit_price=None,
                )
            )
            print(
                "[STRATEGY:RossMomentum] Created TradeIntent "
                f"symbol={pattern.symbol} confidence={confidence:.2f} trader_type={trader_type}"
            )

        ranked = sorted(trade_intents, key=lambda intent: (-intent.confidence, intent.symbol))
        limited = ranked[: self.config.max_intents_per_cycle]
        print(
            "[STRATEGY:RossMomentum] Evaluation complete — generated "
            f"{len(limited)} TradeIntent(s) (limit={self.config.max_intents_per_cycle})"
        )
        return limited

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []

    def _base_confidence(self, pattern: PatternResult) -> float:
        base = getattr(pattern, "confidence", None)
        confidence = base if base is not None else 0.55
        name = pattern.pattern_name.lower()
        if "gap" in name:
            confidence += 0.05
        if "momentum" in name:
            confidence += 0.03
        return self._clamp_confidence(confidence)

    def _clamp_confidence(self, confidence: float) -> float:
        return max(0.30, min(0.90, confidence))

    def _group_signals(
        self, signals: Iterable[SignalEvent]
    ) -> Dict[str, List[SignalEvent]]:
        grouped: Dict[str, List[SignalEvent]] = {}
        for event in signals:
            decision = getattr(event, "decision", None)
            if decision is not None:
                decision_value = getattr(decision, "value", decision)
                if decision_value != "SIGNAL":
                    continue
            grouped.setdefault(event.symbol, []).append(event)
        return grouped

    def _bullish_signals(
        self, signals: Optional[Sequence[SignalEvent]]
    ) -> List[SignalEvent]:
        if not signals:
            return []
        bullish_types = {
            "MOMO_BREAKOUT",
            "HOD_BREAK",
            "ORB_BREAK",
            "ORB_1M",
            "VWAP_RECLAIM",
            "FIRST_PULLBACK_LONG",
        }
        return [
            event
            for event in signals
            if self._normalize_signal_name(event) in bullish_types
        ]

    def _has_first_pullback_long(self, signals: Sequence[SignalEvent]) -> bool:
        return any(
            self._normalize_signal_name(event) == "FIRST_PULLBACK_LONG"
            for event in signals
        )

    def _normalize_signal_name(self, event: SignalEvent) -> str:
        raw_name = getattr(event.signal_type, "value", str(event.signal_type))
        if raw_name == "ORB_1M":
            return "ORB_BREAK"
        return raw_name
