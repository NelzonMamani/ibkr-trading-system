"""Lightweight invariants for trade lifecycle ordering."""

from typing import Iterable, Tuple

from src.core.events import SystemEvent


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
            self._validate_trade_opened(event)
            self._on_trade_opened(event)
        elif event.event_type == "TRADE_NOT_FILLED":
            self._validate_trade_not_filled(event)
        elif event.event_type == "TRADE_CLOSED":
            self._validate_trade_closed(event)
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

    def _validate_trade_opened(self, event: SystemEvent) -> None:
        payload = event.payload or {}
        filled_quantity = payload.get("filled_quantity", 0)
        requested_quantity = payload.get("requested_quantity", 0)
        remaining_quantity = payload.get("remaining_quantity", 0)
        reported_quantity = payload.get("quantity", 0)
        if filled_quantity <= 0 or reported_quantity <= 0:
            raise EventInvariantError(
                "TRADE_OPENED violation: trades must have positive filled quantity"
            )
        if reported_quantity != filled_quantity:
            raise EventInvariantError(
                "TRADE_OPENED violation: payload quantity must equal filled_quantity"
            )
        if requested_quantity < filled_quantity:
            raise EventInvariantError(
                "TRADE_OPENED violation: requested_quantity cannot be less than filled_quantity"
            )
        if remaining_quantity != requested_quantity - filled_quantity:
            raise EventInvariantError(
                "TRADE_OPENED violation: remaining_quantity must equal requested - filled"
            )
        fill_status = (payload.get("fill_status") or "").upper()
        if filled_quantity == requested_quantity:
            expected_status = "FULL"
        else:
            expected_status = "PARTIAL"
        if fill_status != expected_status:
            raise EventInvariantError(
                f"TRADE_OPENED violation: expected fill_status={expected_status}, got {fill_status or 'UNKNOWN'}"
            )

    def _validate_trade_not_filled(self, event: SystemEvent) -> None:
        payload = event.payload or {}
        requested_quantity = payload.get("requested_quantity", 0)
        filled_quantity = payload.get("filled_quantity", -1)
        remaining_quantity = payload.get("remaining_quantity", -1)
        fill_status = (payload.get("fill_status") or "").upper()
        reason = payload.get("reason")
        if filled_quantity != 0:
            raise EventInvariantError(
                "TRADE_NOT_FILLED violation: filled_quantity must be zero"
            )
        if remaining_quantity != requested_quantity:
            raise EventInvariantError(
                "TRADE_NOT_FILLED violation: remaining_quantity must equal requested_quantity"
            )
        if fill_status != "NONE":
            raise EventInvariantError(
                f"TRADE_NOT_FILLED violation: expected fill_status=NONE, got {fill_status or 'UNKNOWN'}"
            )
        if reason not in {"LIQUIDITY_ZERO", "LIQUIDITY_CAP"}:
            raise EventInvariantError(
                "TRADE_NOT_FILLED violation: reason must be LIQUIDITY_ZERO or LIQUIDITY_CAP"
            )

    def _validate_trade_closed(self, event: SystemEvent) -> None:
        payload = event.payload or {}
        quantity = payload.get("quantity", 0)
        if quantity <= 0:
            raise EventInvariantError(
                "TRADE_CLOSED violation: quantity must be positive"
            )


def check_invariants(events: Iterable[SystemEvent]) -> None:
    """
    Apply trade lifecycle invariants over the provided events in order.
    """

    checker = TradeLifecycleInvariantChecker()
    for event in events or []:
        checker.apply(event)
