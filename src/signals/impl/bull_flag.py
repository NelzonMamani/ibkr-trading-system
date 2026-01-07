"""Bull flag teaching signal."""

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


class BullFlagSignal(BaseSignal):
    @property
    def signal_type(self) -> SignalType:
        return SignalType.BULL_FLAG

    def evaluate(self, context: SignalContext, inputs: dict) -> SignalEvent:
        last_price = _coerce_decimal(inputs.get("last_price"))
        vwap = _coerce_decimal(inputs.get("vwap"))
        if last_price is None or vwap is None:
            return SignalEvent(
                signal_type=self.signal_type,
                symbol=context.symbol,
                tick=context.tick,
                decision=SignalDecision.NO_SIGNAL,
                confidence=0.0,
                rationale="Missing last_price or vwap",
                entry_level=None,
                stop_level=None,
                target_level=None,
                invalidation_level=None,
                source=self.__class__.__name__,
            )

        if vwap > 0 and last_price >= vwap:
            invalidation_level = _coerce_decimal(inputs.get("pullback_low"))
            if invalidation_level is None:
                invalidation_level = vwap - Decimal("0.01")
            return SignalEvent(
                signal_type=self.signal_type,
                symbol=context.symbol,
                tick=context.tick,
                decision=SignalDecision.SIGNAL,
                confidence=0.55,
                rationale="Price holding above VWAP (teaching placeholder)",
                entry_level=vwap,
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
            rationale="VWAP not reclaimed",
            entry_level=None,
            stop_level=None,
            target_level=None,
            invalidation_level=None,
            source=self.__class__.__name__,
        )
