"""Micro pullback teaching signal."""

from decimal import Decimal
from typing import Optional

from src.signals.base import BaseSignal
from src.signals.types import SignalContext, SignalDecision, SignalEvent, SignalType


def _coerce_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


class MicroPullbackSignal(BaseSignal):
    @property
    def signal_type(self) -> SignalType:
        return SignalType.MICRO_PULLBACK

    def evaluate(self, context: SignalContext, inputs: dict) -> SignalEvent:
        last_price = _coerce_decimal(inputs.get("last_price"))
        pullback_low = _coerce_decimal(inputs.get("pullback_low"))
        if last_price is None or pullback_low is None:
            return SignalEvent(
                signal_type=self.signal_type,
                symbol=context.symbol,
                tick=context.tick,
                decision=SignalDecision.NO_SIGNAL,
                confidence=0.0,
                rationale="Missing last_price or pullback_low",
                entry_level=None,
                stop_level=None,
                target_level=None,
                invalidation_level=None,
                source=self.__class__.__name__,
            )

        reclaim_level = pullback_low + (pullback_low * Decimal("0.02"))
        if pullback_low > 0 and last_price >= reclaim_level:
            invalidation_level = pullback_low
            return SignalEvent(
                signal_type=self.signal_type,
                symbol=context.symbol,
                tick=context.tick,
                decision=SignalDecision.SIGNAL,
                confidence=0.55,
                rationale="Price reclaimed 2% above pullback low",
                entry_level=reclaim_level,
                stop_level=invalidation_level,
                target_level=None,
                invalidation_level=invalidation_level,
                source=self.__class__.__name__,
            )

        return SignalEvent(
            signal_type=self.signal_type,
            symbol=context.symbol,
            tick=context.tick,
            decision=SignalDecision.NO_SIGNAL,
            confidence=0.0,
            rationale="Pullback reclaim not met",
            entry_level=None,
            stop_level=None,
            target_level=None,
            invalidation_level=None,
            source=self.__class__.__name__,
        )
