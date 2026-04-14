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


def test_paper_provider_open_orders_tracks_protective_truth() -> None:
    provider = PaperExecutionProvider(
        price_feed=DeterministicPriceFeed(),
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        run_mode=RunMode.PAPER,
    )
    stop = provider.place_stop_order(
        symbol="AAPL",
        side="SELL",
        quantity=10,
        stop_price=99.5,
        trade_id="T-1",
        parent_order_id="ENTRY-1",
    )
    target = provider.place_target_order(
        symbol="AAPL",
        side="SELL",
        quantity=10,
        limit_price=101.5,
        trade_id="T-1",
        parent_order_id="ENTRY-1",
    )
    snapshots = provider.get_open_orders()
    assert {order.order_id for order in snapshots} == {stop["broker_order_id"], target["broker_order_id"]}
    assert {order.order_type for order in snapshots} == {"STP", "LMT"}

    provider.cancel_order(broker_order_id=stop["broker_order_id"])
    snapshots_after_cancel = provider.get_open_orders()
    assert [order.order_id for order in snapshots_after_cancel] == [target["broker_order_id"]]


class _DummyIbkrBroker:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def open_orders(self):
        contract = SimpleNamespace(symbol="AAPL")
        order_state = SimpleNamespace(status="Submitted")
        return [SimpleNamespace(orderId=123, contract=contract, orderState=order_state)]

    def cancel_order(self, *, broker_order_id: str):
        self.cancelled.append(broker_order_id)
        return {"broker_order_id": broker_order_id, "status": "Cancelled"}


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
