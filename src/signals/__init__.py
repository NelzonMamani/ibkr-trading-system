"""Signals package for teaching-first momentum triggers."""

from src.signals.base import BaseSignal
from src.signals.engine import SignalEngine
from src.signals.registry import SignalRegistry, build_default_signal_registry
from src.signals.signal_engine_v1 import SignalEngineConfig, SignalEngineV1
from src.signals.signal_event import SignalEvent
from src.signals.signal_to_intent_adapter import SignalToIntentAdapter, SignalToIntentConfig
from src.signals.signal_types import SignalType
from src.signals.types import (
    Level,
    SignalContext,
    SignalDecision,
    SignalEvent as LegacySignalEvent,
    SignalType as LegacySignalType,
    validate_signal_event,
)

__all__ = [
    "BaseSignal",
    "SignalEngine",
    "SignalRegistry",
    "build_default_signal_registry",
    "SignalToIntentAdapter",
    "SignalToIntentConfig",
    "SignalEngineConfig",
    "SignalEngineV1",
    "Level",
    "SignalContext",
    "SignalDecision",
    "SignalEvent",
    "SignalType",
    "LegacySignalEvent",
    "LegacySignalType",
    "validate_signal_event",
]
