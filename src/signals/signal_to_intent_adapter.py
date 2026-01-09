"""Adapter that converts SignalEvents into TradeIntents (teaching-first)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from src.core.event_collector import EventCollector
from src.models.data_models import TradeIntent
from src.signals.types import SignalDecision, SignalEvent


@dataclass(frozen=True)
class SignalToIntentConfig:
    """Configuration thresholds for deterministic confidence mapping."""

    base_confidence: float = 0.55
    rvol_threshold: float = 2.0
    rvol_bonus: float = 0.10
    gap_threshold: float = 4.0
    gap_bonus: float = 0.10
    float_threshold: float = 50.0
    float_bonus: float = 0.05
    min_confidence: float = 0.30
    max_confidence: float = 0.90


class SignalToIntentAdapter:
    """Deterministic adapter to map SignalEvents into TradeIntents."""

    _long_bias = {
        "MOMO_BREAKOUT",
        "HOD_BREAK",
        "VWAP_RECLAIM",
        "ORB_BREAK",
        "FIRST_PULLBACK_LONG",
    }
    _short_bias = {
        "FAIL_HOD",
        "VWAP_REJECT",
        "ORB_BREAKDOWN",
        "FIRST_PULLBACK_SHORT",
    }
    _scalper_signals = {"FIRST_PULLBACK_LONG", "FIRST_PULLBACK_SHORT"}
    _momentum_signals = {
        "MOMO_BREAKOUT",
        "HOD_BREAK",
        "VWAP_RECLAIM",
        "VWAP_REJECT",
        "ORB_BREAK",
        "ORB_BREAKDOWN",
    }

    def __init__(
        self,
        config: Optional[SignalToIntentConfig] = None,
        event_collector: Optional[EventCollector] = None,
    ) -> None:
        self._config = config or SignalToIntentConfig()
        self._event_collector = event_collector

    def convert(
        self, signals: List[SignalEvent], tick: int | None = None
    ) -> List[TradeIntent]:
        """Convert SignalEvents into TradeIntents using Ross-style heuristics."""

        intents: List[TradeIntent] = []
        for event in self._sorted_signals(signals):
            if event.decision != SignalDecision.SIGNAL:
                continue
            signal_name = self._signal_name(event)
            direction = self._direction_for_signal(signal_name)
            if direction is None:
                continue
            trader_type = self._trader_type_for_signal(signal_name)
            payload = self._payload_fields(event)
            confidence = self._calculate_confidence(payload)
            rationale = self._build_rationale(
                event=event,
                signal_name=signal_name,
                direction=direction,
                trader_type=trader_type,
                confidence=confidence,
                payload=payload,
                tick=tick,
            )
            intents.append(
                TradeIntent(
                    symbol=event.symbol,
                    direction=direction,
                    strategy_name="SignalAdapter",
                    confidence=confidence,
                    rationale=rationale,
                    trader_type=trader_type,
                    stop_loss_price=None,
                    take_profit_price=None,
                )
            )

        if self._event_collector is not None:
            event = self._event_collector.emit(
                event_type="SIGNAL_INTENTS_CREATED",
                source="SignalToIntentAdapter",
                payload={"count": len(intents), "signals_in": len(signals)},
            )
            print(event)

        return intents

    def _sorted_signals(self, signals: Iterable[SignalEvent]) -> List[SignalEvent]:
        return sorted(
            signals,
            key=lambda event: (
                event.symbol,
                self._signal_name(event),
                event.tick,
            ),
        )

    def _signal_name(self, event: SignalEvent) -> str:
        raw = getattr(event.signal_type, "value", event.signal_type)
        return str(raw).upper()

    def _direction_for_signal(self, signal_name: str) -> Optional[str]:
        if signal_name in self._long_bias:
            return "LONG"
        if signal_name in self._short_bias:
            return "SHORT"
        return None

    def _trader_type_for_signal(self, signal_name: str) -> str:
        if signal_name in self._scalper_signals:
            return "SCALPER"
        if signal_name in self._momentum_signals:
            return "MOMENTUM"
        return "MOMENTUM"

    def _payload_fields(self, event: SignalEvent) -> dict:
        metadata = event.metadata or {}
        return {
            "rvol": metadata.get("rvol"),
            "gap_percent": metadata.get("gap_percent"),
            "float_millions": metadata.get("float_millions"),
            "pattern": metadata.get("pattern"),
        }

    def _calculate_confidence(self, payload: dict) -> float:
        confidence = self._config.base_confidence
        rvol = payload.get("rvol")
        gap_percent = payload.get("gap_percent")
        float_millions = payload.get("float_millions")
        if rvol is not None and rvol >= self._config.rvol_threshold:
            confidence += self._config.rvol_bonus
        if gap_percent is not None and gap_percent >= self._config.gap_threshold:
            confidence += self._config.gap_bonus
        if float_millions is not None and float_millions <= self._config.float_threshold:
            confidence += self._config.float_bonus
        return min(max(confidence, self._config.min_confidence), self._config.max_confidence)

    def _build_rationale(
        self,
        event: SignalEvent,
        signal_name: str,
        direction: str,
        trader_type: str,
        confidence: float,
        payload: dict,
        tick: int | None,
    ) -> str:
        pieces = []
        if event.rationale:
            pieces.append(event.rationale)
        pieces.append(
            f"Signal={signal_name} direction={direction} trader_type={trader_type} "
            f"confidence={confidence:.2f}"
        )
        key_parts = []
        for key in ("rvol", "gap_percent", "float_millions"):
            if payload.get(key) is not None:
                key_parts.append(f"{key}={payload.get(key)}")
        if key_parts:
            pieces.append("payload:" + ", ".join(key_parts))
        if payload.get("pattern"):
            pieces.append(f"pattern={payload.get('pattern')}")
        if tick is not None:
            pieces.append(f"tick={tick}")
        pieces.append("Risk/exit handled in later phases.")
        return " | ".join(pieces)
