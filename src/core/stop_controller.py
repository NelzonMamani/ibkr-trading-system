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
from threading import Lock
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


class StopController:
    """
    Coordinate stop requests across the orchestrator and engines.

    Stop requests are idempotent: calling request_stop multiple times is safe.
    PANIC mode always overrides GRACEFUL to ensure the strongest intent wins.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._stop_requested: bool = False
        self._mode: Optional[StopMode] = None
        self._reason: Optional[str] = None
        self._source: Optional[str] = None
        self._circuit_breakers: dict[str, CircuitBreakerState] = {}

    def request_stop(self, mode: StopMode, reason: str, source: str) -> None:
        """
        Register a stop request.

        - Safe to call multiple times.
        - Escalates to PANIC mode if requested after a GRACEFUL request.
        """

        with self._lock:
            if not self._stop_requested:
                self._stop_requested = True
                self._mode = mode
                self._reason = reason
                self._source = source
                return

            # If already stopping, keep the strongest mode and most recent reason.
            if self._mode == StopMode.GRACEFUL and mode == StopMode.PANIC:
                self._mode = mode
                self._reason = reason
                self._source = source

    def is_stop_requested(self) -> bool:
        return self._stop_requested

    def stop_mode(self) -> Optional[StopMode]:
        return self._mode

    def stop_reason(self) -> Optional[str]:
        return self._reason

    def stop_source(self) -> Optional[str]:
        return self._source

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
            self._stop_requested = False
            self._mode = None
            self._reason = reason
            self._source = source
            return True
