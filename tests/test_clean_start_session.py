from __future__ import annotations

from types import SimpleNamespace

from src.execution.clean_start_session import enforce_clean_start_session


class _FakeTranslator:
    def __init__(self, *args, **kwargs) -> None:
        self.internal_orders: list = []

    def translate(self, internal_order):
        self.internal_orders.append(internal_order)
        contract = SimpleNamespace(symbol=internal_order.symbol)
        order = SimpleNamespace(
            action=str(internal_order.direction).upper(),
            orderType=str(internal_order.order_type).upper(),
            totalQuantity=int(internal_order.quantity),
            outsideRth=False,
            orderRef="",
        )
        return contract, order


class _FakeIbkrClient:
    def __init__(self, *, open_orders=None, positions=None, clear_positions_on_submit: bool = True) -> None:
        self._open_orders = list(open_orders or [])
        self._positions = list(positions or [])
        self.clear_positions_on_submit = bool(clear_positions_on_submit)
        self.cancelled_order_ids: list[int] = []
        self.submitted_orders: list[tuple[object, object]] = []
        self.open_orders_calls = 0
        self.positions_calls = 0

    def openOrders(self):
        self.open_orders_calls += 1
        return list(self._open_orders)

    def positions(self):
        self.positions_calls += 1
        return list(self._positions)

    def cancelOrder(self, order_id: int):
        self.cancelled_order_ids.append(int(order_id))
        self._open_orders = [
            row for row in self._open_orders if int(getattr(row, "orderId", 0) or 0) != int(order_id)
        ]

    def submit_order(self, contract, order):
        self.submitted_orders.append((contract, order))
        if self.clear_positions_on_submit:
            self._positions = []
        return 101


def test_clean_start_disabled_no_behavior_change():
    client = _FakeIbkrClient()
    result = enforce_clean_start_session(enabled=False, ibkr_client=client)
    assert result.status == "DISABLED"
    assert result.ready_for_trading is True
    assert client.open_orders_calls == 0
    assert client.positions_calls == 0


def test_clean_start_cancels_broker_open_orders(monkeypatch):
    monkeypatch.setattr("src.execution.clean_start_session.IbkrOrderTranslator", _FakeTranslator)
    open_orders = [
        SimpleNamespace(orderId=11, contract=SimpleNamespace(symbol="AAPL")),
        SimpleNamespace(orderId=22, contract=SimpleNamespace(symbol="TSLA")),
    ]
    client = _FakeIbkrClient(open_orders=open_orders, positions=[])
    result = enforce_clean_start_session(enabled=True, ibkr_client=client, timeout_seconds=1, sleep_fn=lambda _: None)
    assert result.ready_for_trading is True
    assert client.cancelled_order_ids == [11, 22]


def test_clean_start_submits_opposite_market_orders_for_positions(monkeypatch):
    monkeypatch.setattr("src.execution.clean_start_session.IbkrOrderTranslator", _FakeTranslator)
    positions = [
        SimpleNamespace(symbol="AAPL", position=100),
        SimpleNamespace(symbol="TSLA", position=-50),
    ]
    client = _FakeIbkrClient(open_orders=[], positions=positions)
    result = enforce_clean_start_session(enabled=True, ibkr_client=client, timeout_seconds=1, sleep_fn=lambda _: None)
    assert result.ready_for_trading is True
    assert len(client.submitted_orders) == 2
    assert client.submitted_orders[0][1].action == "SELL"
    assert client.submitted_orders[0][1].orderType == "MKT"
    assert client.submitted_orders[0][1].totalQuantity == 100
    assert client.submitted_orders[1][1].action == "BUY"
    assert client.submitted_orders[1][1].totalQuantity == 50


def test_clean_start_waits_for_flat_confirmation(monkeypatch):
    monkeypatch.setattr("src.execution.clean_start_session.IbkrOrderTranslator", _FakeTranslator)
    waits: list[float] = []

    class _ProgressClient(_FakeIbkrClient):
        def __init__(self):
            super().__init__(
                open_orders=[],
                positions=[SimpleNamespace(symbol="AAPL", position=10)],
                clear_positions_on_submit=False,
            )

        def positions(self):
            self.positions_calls += 1
            if self.positions_calls >= 3:
                self._positions = []
            return list(self._positions)

    client = _ProgressClient()
    result = enforce_clean_start_session(
        enabled=True,
        ibkr_client=client,
        timeout_seconds=5,
        sleep_fn=lambda s: waits.append(s),
    )
    assert result.ready_for_trading is True
    assert waits


def test_clean_start_timeout_blocks_runtime(monkeypatch):
    monkeypatch.setattr("src.execution.clean_start_session.IbkrOrderTranslator", _FakeTranslator)
    client = _FakeIbkrClient(
        open_orders=[],
        positions=[SimpleNamespace(symbol="AAPL", position=10)],
        clear_positions_on_submit=False,
    )
    ticks = iter([0.0, 0.1, 0.2, 1.2])
    result = enforce_clean_start_session(
        enabled=True,
        ibkr_client=client,
        timeout_seconds=1,
        sleep_fn=lambda _: None,
        monotonic_fn=lambda: next(ticks),
    )
    assert result.ready_for_trading is False
    assert result.status == "FAILED"
    assert result.reason == "TIMEOUT"


def test_clean_start_orders_are_tagged_as_cleanup(monkeypatch):
    capture = _FakeTranslator()
    monkeypatch.setattr("src.execution.clean_start_session.IbkrOrderTranslator", lambda *a, **k: capture)
    client = _FakeIbkrClient(
        open_orders=[],
        positions=[SimpleNamespace(symbol="MSFT", position=5)],
    )
    result = enforce_clean_start_session(enabled=True, ibkr_client=client, timeout_seconds=1, sleep_fn=lambda _: None)
    assert result.ready_for_trading is True
    assert len(capture.internal_orders) == 1
    order = capture.internal_orders[0]
    assert order.strategy_name == "CLEAN_START"
    assert order.trader_type == "BROKER_CLEANUP"
    assert str(order.client_order_id).startswith("CLEAN_START_")
