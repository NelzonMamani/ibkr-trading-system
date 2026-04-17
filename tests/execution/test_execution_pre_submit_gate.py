from __future__ import annotations

import pytest

from src.core_engine.state import RunMode
from src.execution import order_router
from src.execution.fill_diagnostics import FillabilityClass


class _Client:
    def __init__(self) -> None:
        self.submissions = 0

    def qualifyContracts(self, contract):
        contract.conId = 123
        contract.exchange = "SMART"
        contract.currency = "USD"
        contract.primaryExchange = "NASDAQ"
        contract.secType = "STK"
        return [contract]

    def submit_order(self, _contract, _order):
        self.submissions += 1
        return 9001

    def wait_for_order_status(self, _order_id, timeout_seconds=5):
        return {"status": "Submitted"}


def test_no_quote_blocks_submission(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "RTH")
    monkeypatch.setattr(
        order_router,
        "_wait_for_ibkr_snapshot_for_symbol",
        lambda *_args, **_kwargs: {"bid": None, "ask": None, "last": None, "volume": 1_000},
    )

    with pytest.raises(RuntimeError, match="NO_QUOTE_PRE_SUBMIT"):
        order_router._submit_ibkr_order(
            mode=RunMode.PAPER,
            client=client,
            symbol="TST",
            side="BUY",
            quantity=1,
            order_ref="TRADING_OS|ROSS_MOMENTUM|TST-1",
            entry_price=10.0,
            entry_price_source="IBKR_SNAPSHOT",
        )

    assert client.submissions == 0


def test_passive_blocks_when_enabled(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setenv("EXECUTION_BLOCK_LOW_QUALITY_PRE_SUBMIT", "1")
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "RTH")
    monkeypatch.setattr(
        order_router,
        "_wait_for_ibkr_snapshot_for_symbol",
        lambda *_args, **_kwargs: {"bid": 10.0, "ask": 10.1, "last": 10.05, "volume": 1_000},
    )
    monkeypatch.setattr(order_router, "classify_fillability", lambda **_kwargs: FillabilityClass.PASSIVE)

    with pytest.raises(RuntimeError, match="LOW_QUALITY_PASSIVE"):
        order_router._submit_ibkr_order(
            mode=RunMode.PAPER,
            client=client,
            symbol="TST",
            side="BUY",
            quantity=1,
            order_ref="TRADING_OS|ROSS_MOMENTUM|TST-2",
            entry_price=10.05,
            entry_price_source="IBKR_SNAPSHOT",
        )

    assert client.submissions == 0


def test_paper_ignores_synthetic_backfill_exec_id(monkeypatch) -> None:
    order_router._RUNTIME_ORDERS.clear()
    order_router._SEEN_EXEC_IDS.clear()
    monkeypatch.setenv("RUN_MODE", "PAPER")

    order_router._on_ibkr_callback(
        {
            "event_type": "execDetails",
            "order_id": 4242,
            "symbol": "TST",
            "shares": 10,
            "price": 10.0,
            "execId": "BACKFILL-4242",
        }
    )

    assert 4242 not in order_router._RUNTIME_ORDERS
