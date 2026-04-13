from __future__ import annotations

from types import SimpleNamespace

from src.execution.dev_tools import flatten_positions


class _FakeTranslator:
    def __init__(self, order_translation_enabled: bool):
        self.order_translation_enabled = order_translation_enabled

    def translate(self, internal_order):
        contract = SimpleNamespace(symbol=internal_order.symbol)
        order = SimpleNamespace(
            action=internal_order.direction,
            totalQuantity=internal_order.quantity,
            orderType=internal_order.order_type,
            tif=internal_order.time_in_force,
            outsideRth=False,
        )
        return contract, order


class _FakeIbkrClient:
    def __init__(self, snapshots):
        self._snapshots = list(snapshots)
        self._idx = 0
        self.submissions = []

    def positions(self):
        idx = min(self._idx, len(self._snapshots) - 1)
        current = self._snapshots[idx]
        self._idx += 1
        return current

    def submit_order(self, contract, order):
        self.submissions.append((contract, order))
        return len(self.submissions)


def test_force_flatten_detects_positions_and_submits_opposites(monkeypatch):
    monkeypatch.setattr(flatten_positions, "IbkrOrderTranslator", _FakeTranslator)

    client = _FakeIbkrClient(
        snapshots=[
            [
                SimpleNamespace(symbol="AAPL", position=10, avgCost=180.0),
                SimpleNamespace(symbol="TSLA", position=-5, avgCost=200.0),
            ],
            [],
        ]
    )

    result = flatten_positions.force_flatten_all_positions(client, timeout_seconds=1)

    assert result["positions_detected"] == 2
    assert result["close_orders_submitted"] == 2
    assert result["positions_remaining"] == 0
    assert result["status"] == "SUCCESS"

    assert len(client.submissions) == 2
    first_contract, first_order = client.submissions[0]
    second_contract, second_order = client.submissions[1]

    assert first_contract.symbol == "AAPL"
    assert first_order.action == "SELL"
    assert first_order.totalQuantity == 10
    assert first_order.orderType == "MKT"
    assert first_order.tif == "DAY"
    assert first_order.outsideRth is True

    assert second_contract.symbol == "TSLA"
    assert second_order.action == "BUY"
    assert second_order.totalQuantity == 5
    assert second_order.outsideRth is True


def test_force_flatten_returns_success_when_no_positions(monkeypatch):
    monkeypatch.setattr(flatten_positions, "IbkrOrderTranslator", _FakeTranslator)
    client = _FakeIbkrClient(snapshots=[[]])

    result = flatten_positions.force_flatten_all_positions(client, timeout_seconds=1)

    assert result == {
        "positions_detected": 0,
        "close_orders_submitted": 0,
        "positions_remaining": 0,
        "status": "SUCCESS",
    }
    assert client.submissions == []


def test_force_flatten_partial_when_some_positions_remain(monkeypatch):
    monkeypatch.setattr(flatten_positions, "IbkrOrderTranslator", _FakeTranslator)
    client = _FakeIbkrClient(
        snapshots=[
            [
                SimpleNamespace(symbol="AAPL", position=10, avgCost=180.0),
                SimpleNamespace(symbol="MSFT", position=4, avgCost=320.0),
            ],
            [SimpleNamespace(symbol="MSFT", position=1, avgCost=320.0)],
            [SimpleNamespace(symbol="MSFT", position=1, avgCost=320.0)],
        ]
    )

    result = flatten_positions.force_flatten_all_positions(client, timeout_seconds=1)

    assert result["positions_detected"] == 2
    assert result["close_orders_submitted"] == 2
    assert result["positions_remaining"] == 1
    assert result["status"] == "PARTIAL"
