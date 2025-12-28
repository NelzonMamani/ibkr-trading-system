"""Lightweight invariants for trade lifecycle ordering."""

from typing import Iterable, Tuple

from core.events import SystemEvent


class EventInvariantError(Exception):
    """Raised when an invariant is violated."""


class TradeLifecycleInvariantChecker:
    """
    Tracks open trades and enforces a simple open/close sequence.
    """

    def __init__(self) -> None:
        self._open_positions: set[Tuple[str, str]] = set()

    def apply(self, event: SystemEvent) -> None:
        if event.event_type == "TRADE_OPENED":
            self._on_trade_opened(event)
        elif event.event_type == "TRADE_CLOSED":
            self._on_trade_closed(event)

    def _on_trade_opened(self, event: SystemEvent) -> None:
        payload = event.payload or {}
        symbol = payload.get("symbol")
        trader_type = payload.get("trader_type")
        key = (symbol, trader_type)
        if key in self._open_positions:
            raise EventInvariantError(
                f"TRADE_OPENED violation: {symbol}/{trader_type} already open"
            )
        self._open_positions.add(key)

    def _on_trade_closed(self, event: SystemEvent) -> None:
        payload = event.payload or {}
        symbol = payload.get("symbol")
        trader_type = payload.get("trader_type")
        key = (symbol, trader_type)
        if key not in self._open_positions:
            raise EventInvariantError(
                f"TRADE_CLOSED violation: {symbol}/{trader_type} was not open"
            )
        self._open_positions.remove(key)


def check_invariants(events: Iterable[SystemEvent]) -> None:
    """
    Apply trade lifecycle invariants over the provided events in order.
    """

    checker = TradeLifecycleInvariantChecker()
    for event in events or []:
        checker.apply(event)
