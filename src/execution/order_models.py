from typing import Dict, List

from brokers.base_broker import BrokerOrderRequest

# Backwards compatibility alias for prior imports.
OrderRequest = BrokerOrderRequest


class PendingOrderBook:
    """In-memory pending order queue keyed by client_order_id."""

    def __init__(self) -> None:
        self._orders: Dict[str, BrokerOrderRequest] = {}

    def add(self, order: BrokerOrderRequest) -> None:
        self._orders[order.client_order_id] = order

    def due_orders(self, tick: int) -> List[BrokerOrderRequest]:
        return [order for order in self._orders.values() if order.next_retry_tick == tick]

    def remove(self, client_order_id: str) -> None:
        self._orders.pop(client_order_id, None)

    def count(self) -> int:
        return len(self._orders)

    def snapshot(self) -> Dict[str, BrokerOrderRequest]:
        return dict(self._orders)
