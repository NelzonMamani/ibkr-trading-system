"""
Centralised stop controller for orchestrator and engines.

Provides a single source of truth for whether a stop has been requested
so every stage can make consistent decisions. The controller is small,
thread-safe enough for future multi-threaded usage, and designed to be
safe when called from exception blocks.
"""

from enum import Enum
from threading import Lock
from typing import Optional


class StopMode(str, Enum):
    GRACEFUL = "GRACEFUL"
    PANIC = "PANIC"


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
