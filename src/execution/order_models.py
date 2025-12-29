from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class OrderRequest:
    client_order_id: str
    symbol: str
    trader_type: str
    strategy_name: str
    direction: str
    requested_quantity: int
    created_tick: int
    attempt_number: int
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    next_retry_tick: Optional[int] = None
    last_decision: Optional[str] = None


class PendingOrderBook:
    """In-memory pending order queue keyed by client_order_id."""

    def __init__(self) -> None:
        self._orders: Dict[str, OrderRequest] = {}

    def add(self, order: OrderRequest) -> None:
        self._orders[order.client_order_id] = order

    def due_orders(self, tick: int) -> List[OrderRequest]:
        return [order for order in self._orders.values() if order.next_retry_tick == tick]

    def remove(self, client_order_id: str) -> None:
        self._orders.pop(client_order_id, None)

    def count(self) -> int:
        return len(self._orders)

    def snapshot(self) -> Dict[str, OrderRequest]:
        return dict(self._orders)
