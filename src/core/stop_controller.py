"""
Centralised stop controller for orchestrator and engines.

Provides a single source of truth for whether a stop has been requested
so every stage can make consistent decisions. The controller is small,
thread-safe enough for future multi-threaded usage, and designed to be
safe when called from exception blocks.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Optional


class StopMode(str, Enum):
    GRACEFUL = "GRACEFUL"
    PANIC = "PANIC"


@dataclass(frozen=True)
class CircuitBreakerState:
    breaker_id: str
    reason: str
    source: str
    tripped_at: str
    details: dict


@dataclass(frozen=True)
class _StopState:
    mode: Optional[StopMode] = None
    reason: Optional[str] = None
    source: Optional[str] = None


class StopController:
    """
    Coordinate stop requests across the orchestrator and engines.

    Stop requests are idempotent: calling request_stop multiple times is safe.
    PANIC mode always overrides GRACEFUL to ensure the strongest intent wins.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._state = _StopState()
        self._circuit_breakers: dict[str, CircuitBreakerState] = {}

    def request_stop(self, mode: StopMode, reason: str, source: str) -> None:
        """
        Register a stop request.

        - Safe to call multiple times.
        - Escalates to PANIC mode if requested after a GRACEFUL request.
        """

        with self._lock:
            if self._state.mode is None or (
                self._state.mode == StopMode.GRACEFUL and mode == StopMode.PANIC
            ):
                # Publish one complete state; interruption cannot leave a
                # requested flag inconsistent with mode/reason/source.
                self._state = _StopState(mode, reason, source)

    def transition_keyboard_interrupt(self) -> StopMode:
        """Latch GRACEFUL on the first stop; any existing stop selects PANIC.

        The returned GRACEFUL means this was the first graceful interrupt.
        Decision and publication share the controller's reentrant lock.
        Callers must treat interruption before return as nested interruption
        and request PANIC directly, without making another first-stop query.
        """
        with self._lock:
            mode = StopMode.GRACEFUL if self._state.mode is None else StopMode.PANIC
            reason = "KeyboardInterrupt" if mode == StopMode.GRACEFUL else "KeyboardInterrupt (escalation)"
            self.request_stop(mode, reason=reason, source="Main")
            return self._state.mode

    def is_stop_requested(self) -> bool:
        return self._state.mode is not None

    def stop_mode(self) -> Optional[StopMode]:
        return self._state.mode

    def stop_reason(self) -> Optional[str]:
        return self._state.reason

    def stop_source(self) -> Optional[str]:
        return self._state.source

    def trip_breaker(
        self,
        breaker_id: str,
        reason: str,
        source: str,
        details: Optional[dict] = None,
    ) -> CircuitBreakerState:
        with self._lock:
            if breaker_id in self._circuit_breakers:
                return self._circuit_breakers[breaker_id]
            state = CircuitBreakerState(
                breaker_id=breaker_id,
                reason=reason,
                source=source,
                tripped_at=datetime.utcnow().isoformat(),
                details=details or {},
            )
            self._circuit_breakers[breaker_id] = state
            return state

    def is_breaker_tripped(self, breaker_id: Optional[str] = None) -> bool:
        with self._lock:
            if breaker_id is None:
                return bool(self._circuit_breakers)
            return breaker_id in self._circuit_breakers

    def breaker_snapshot(self) -> list[CircuitBreakerState]:
        with self._lock:
            return list(self._circuit_breakers.values())

    def reset_breakers(self, open_positions: int, reason: str, source: str) -> bool:
        with self._lock:
            if open_positions > 0:
                return False
            if not self._circuit_breakers:
                return True
            self._circuit_breakers.clear()
            self._state = _StopState(reason=reason, source=source)
            return True
