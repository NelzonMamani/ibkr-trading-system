from src.config.runtime_config import RunMode
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.execution.execution_providers import IbkrExecutionProvider, PaperExecutionProvider
from src.sim.price_feed import DeterministicPriceFeed
from types import SimpleNamespace


def test_paper_provider_cancel_order_logs_and_returns_cancelled() -> None:
    provider = PaperExecutionProvider(
        price_feed=DeterministicPriceFeed(),
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        run_mode=RunMode.PAPER,
    )
    result = provider.cancel_order(broker_order_id="PAPER-STP-1")
    assert result["broker_order_id"] == "PAPER-STP-1"
    assert result["status"] == "Cancelled"


class _DummyIbkrBroker:
    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.placed_orders: list[object] = []

    def open_orders(self):
        contract = SimpleNamespace(symbol="AAPL")
        order_state = SimpleNamespace(status="Submitted")
        return [SimpleNamespace(orderId=123, contract=contract, orderState=order_state)]

    def cancel_order(self, *, broker_order_id: str):
        self.cancelled.append(broker_order_id)
        return {"broker_order_id": broker_order_id, "status": "Cancelled"}

    def place_order(self, request):
        self.placed_orders.append(request)
        return SimpleNamespace(status="Submitted", broker_order_id="FLAT-1")


def test_ibkr_provider_open_orders_and_cancel_order() -> None:
    broker = _DummyIbkrBroker()
    provider = IbkrExecutionProvider(
        broker=broker,  # type: ignore[arg-type]
        trade_registry=ActiveTradeRegistry(),
        run_mode=RunMode.LIVE,
    )
    snapshots = provider.get_open_orders()
    assert len(snapshots) == 1
    assert snapshots[0].order_id == "123"
    assert snapshots[0].symbol == "AAPL"
    cancel = provider.cancel_order(broker_order_id="123")
    assert cancel["status"] == "Cancelled"
    assert broker.cancelled == ["123"]
    flatten = provider.flatten_position(symbol="AAPL", quantity=10)
    assert flatten["status"] == "Submitted"
    assert len(broker.placed_orders) == 1
    assert broker.placed_orders[0].order_type == "MKT"
    assert broker.placed_orders[0].direction == "SELL"
