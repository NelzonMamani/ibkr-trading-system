"""Registry for signal implementations."""

from signals.base import BaseSignal
from signals.types import SignalType
from signals.impl.hod_break import HodBreakSignal
from signals.impl.premarket_high_break import PremarketHighBreakSignal
from signals.impl.micro_pullback import MicroPullbackSignal
from signals.impl.bull_flag import BullFlagSignal
from signals.impl.orb_1m import Orb1mSignal


class SignalRegistry:
    def __init__(self) -> None:
        self._signals: dict[SignalType, BaseSignal] = {}

    def register(self, signal: BaseSignal) -> None:
        signal_type = signal.signal_type
        if signal_type in self._signals:
            raise ValueError(f"Signal already registered: {signal_type}")
        self._signals[signal_type] = signal

    def list_signals(self) -> list[BaseSignal]:
        return list(self._signals.values())

    def get_by_type(self, signal_type: SignalType) -> BaseSignal:
        if signal_type not in self._signals:
            raise KeyError(f"Signal not found: {signal_type}")
        return self._signals[signal_type]


def build_default_signal_registry() -> SignalRegistry:
    registry = SignalRegistry()
    registry.register(HodBreakSignal())
    registry.register(PremarketHighBreakSignal())
    registry.register(MicroPullbackSignal())
    registry.register(BullFlagSignal())
    registry.register(Orb1mSignal())
    return registry
