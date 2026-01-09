"""Base interfaces for signal implementations."""

from abc import ABC, abstractmethod

from src.signals.types import SignalContext, SignalEvent, SignalType


class BaseSignal(ABC):
    @property
    @abstractmethod
    def signal_type(self) -> SignalType:
        """Unique type for the signal implementation."""

    @abstractmethod
    def evaluate(self, context: SignalContext, inputs: dict) -> SignalEvent:
        """Evaluate the signal given a context and raw inputs."""
