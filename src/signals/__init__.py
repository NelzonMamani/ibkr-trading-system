"""Signals package for teaching-first momentum triggers."""

from signals.base import BaseSignal
from signals.engine import SignalEngine
from signals.registry import SignalRegistry, build_default_signal_registry
from signals.signal_engine_v1 import SignalEngineConfig, SignalEngineV1
from signals.signal_event import SignalEvent
from signals.signal_to_intent_adapter import SignalToIntentAdapter, SignalToIntentConfig
from signals.signal_types import SignalType
from signals.types import (
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
