"""Strategy registry for portfolio governance (not wired)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable

from .contracts import ExecutionMode, StrategyIdentity


class StrategyState(str, Enum):
    REGISTERED = "REGISTERED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    DEPRECATED = "DEPRECATED"


@dataclass(frozen=True)
class StrategyRegistryEntry:
    identity: StrategyIdentity
    state: StrategyState = StrategyState.DISABLED
    priority: int = 0
    supported_modes: Dict[str, bool] = field(default_factory=dict)
    description: str | None = None
    policy_provider: Callable[[], object] | str | None = None


class StrategyRegistry:
    def __init__(self) -> None:
        self._entries: Dict[str, StrategyRegistryEntry] = {}

    def register(self, entry: StrategyRegistryEntry) -> None:
        """Register (or replace) a strategy entry without executing it."""
        self._entries[entry.identity.strategy_id] = entry

    def enable(self, strategy_id: str) -> None:
        entry = self._get_entry(strategy_id)
        self._entries[strategy_id] = StrategyRegistryEntry(
            identity=entry.identity,
            state=StrategyState.ENABLED,
            priority=entry.priority,
            supported_modes=dict(entry.supported_modes),
            description=entry.description,
            policy_provider=entry.policy_provider,
        )

    def disable(self, strategy_id: str) -> None:
        entry = self._get_entry(strategy_id)
        self._entries[strategy_id] = StrategyRegistryEntry(
            identity=entry.identity,
            state=StrategyState.DISABLED,
            priority=entry.priority,
            supported_modes=dict(entry.supported_modes),
            description=entry.description,
            policy_provider=entry.policy_provider,
        )

    def set_priority(self, strategy_id: str, priority: int) -> None:
        entry = self._get_entry(strategy_id)
        self._entries[strategy_id] = StrategyRegistryEntry(
            identity=entry.identity,
            state=entry.state,
            priority=priority,
            supported_modes=dict(entry.supported_modes),
            description=entry.description,
            policy_provider=entry.policy_provider,
        )

    def list_enabled_ordered(self) -> Iterable[StrategyRegistryEntry]:
        enabled = [
            entry
            for entry in self._entries.values()
            if entry.state == StrategyState.ENABLED
        ]
        return sorted(
            enabled,
            key=lambda entry: (-entry.priority, entry.identity.strategy_id),
        )

    def list_enabled_for_mode(self, mode: ExecutionMode) -> Iterable[StrategyRegistryEntry]:
        enabled = [
            entry
            for entry in self._entries.values()
            if entry.state == StrategyState.ENABLED and self._supports_mode(entry, mode)
        ]
        return sorted(
            enabled,
            key=lambda entry: (-entry.priority, entry.identity.strategy_id),
        )

    def get(self, strategy_id: str) -> StrategyRegistryEntry:
        return self._get_entry(strategy_id)

    def _get_entry(self, strategy_id: str) -> StrategyRegistryEntry:
        if strategy_id not in self._entries:
            raise KeyError(f"Strategy '{strategy_id}' is not registered")
        return self._entries[strategy_id]

    @staticmethod
    def _supports_mode(entry: StrategyRegistryEntry, mode: ExecutionMode) -> bool:
        if not entry.supported_modes:
            return True
        return bool(
            entry.supported_modes.get(mode.value)
            or entry.supported_modes.get(mode)
        )
