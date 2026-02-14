"""
Ross Momentum Strategy v1 — signal-driven, deterministic TradeIntent generator.

Consumes SignalEvent(s) and emits TradeIntent(s) using teaching-safe rules.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.config.runtime_config import RunMode
from src.models.data_models import PatternResult, TradeIntent
from src.signals.signal_event import SignalEvent
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal


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
        )
        print(
            "[STRATEGY:RossMomentumV1] Fallback intent emitted "
            f"symbol={symbol} mode={mode.value} session={session_label} phase={session_phase}"
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
