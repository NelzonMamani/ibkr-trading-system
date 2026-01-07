"""Premarket high break teaching signal."""

from decimal import Decimal
from typing import Optional

from signals.base import BaseSignal
from signals.types import SignalContext, SignalDecision, SignalEvent, SignalType


def _coerce_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


class PremarketHighBreakSignal(BaseSignal):
    @property
    def signal_type(self) -> SignalType:
        return SignalType.PREMARKET_HIGH_BREAK

    def evaluate(self, context: SignalContext, inputs: dict) -> SignalEvent:
        last_price = _coerce_decimal(inputs.get("last_price"))
        pmh = _coerce_decimal(inputs.get("pmh"))
        if last_price is None or pmh is None:
            return SignalEvent(
                signal_type=self.signal_type,
                symbol=context.symbol,
                tick=context.tick,
                decision=SignalDecision.NO_SIGNAL,
                confidence=0.0,
                rationale="Missing last_price or pmh",
                entry_level=None,
                stop_level=None,
                target_level=None,
                invalidation_level=None,
                source=self.__class__.__name__,
            )

        if pmh > 0 and last_price >= pmh:
            invalidation_level = _coerce_decimal(inputs.get("pullback_low"))
            if invalidation_level is None:
                invalidation_level = pmh - Decimal("0.01")
            return SignalEvent(
                signal_type=self.signal_type,
                symbol=context.symbol,
                tick=context.tick,
                decision=SignalDecision.SIGNAL,
                confidence=0.70,
                rationale="Last price broke the premarket high",
                entry_level=pmh,
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
            rationale="Premarket high not reached",
            entry_level=None,
            stop_level=None,
            target_level=None,
            invalidation_level=None,
            source=self.__class__.__name__,
        )
