from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class BrokerOrderRequest:
    """
    System-language order request (NOT broker-specific).

    direction: "LONG", "SHORT", or "SELL" (close-long semantic)
    order_type: e.g. "MKT" for now (teaching)
    """

    client_order_id: str
    symbol: str
    direction: str  # "LONG" | "SHORT" | "SELL" (system language)
    quantity: int
    order_type: str = "MKT"  # teaching default
    trader_type: Optional[str] = None
    strategy_name: Optional[str] = None
    attempt_number: int = 1
    created_tick: Optional[int] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    pattern_name: Optional[str] = None
    invalidation_level: Optional[float] = None
    next_retry_tick: Optional[int] = None


@runtime_checkable
class BaseBroker(Protocol):
    """
    Broker adapter contract.

    SIM and LIVE implementations must conform so ExecutionEngine remains unchanged.
    """

    def name(self) -> str:
        ...

    def is_live(self) -> bool:
        ...

    def place_order(self, request: BrokerOrderRequest):
        """
        Place an order and return an ExecutionResult-like object.
        We avoid importing ExecutionResult here to prevent circular imports.
        SIM broker will return the system ExecutionResult from execution domain.
        LIVE stub will return a system ExecutionResult marked as NOT_ATTEMPTED / STUBBED.
        """

        ...
