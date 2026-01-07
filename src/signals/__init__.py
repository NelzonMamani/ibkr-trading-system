"""Signals package for teaching-first momentum triggers."""

from signals.base import BaseSignal
from signals.engine import SignalEngine
from signals.registry import SignalRegistry, build_default_signal_registry
from signals.types import (
    Level,
    SignalContext,
    SignalDecision,
    SignalEvent,
    SignalType,
    validate_signal_event,
)

__all__ = [
    "BaseSignal",
    "SignalEngine",
    "SignalRegistry",
    "build_default_signal_registry",
    "Level",
    "SignalContext",
    "SignalDecision",
    "SignalEvent",
    "SignalType",
    "validate_signal_event",
]
