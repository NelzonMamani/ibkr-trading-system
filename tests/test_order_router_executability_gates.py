from __future__ import annotations

import pytest

from src.core_engine.state import RunMode
from src.execution import order_router


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
        return 777

    def wait_for_order_status(self, _order_id, timeout_seconds=5):
        return {"status": "Submitted"}


def test_submit_blocks_when_quote_context_missing(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": None, "ask": None, "last": 5.0, "volume": 50_000})
    with pytest.raises(RuntimeError, match="NO_QUOTE_CONTEXT"):
        order_router._submit_ibkr_order(
            mode=RunMode.PAPER,
            client=client,
            symbol="MCRO",
            side="BUY",
            quantity=1,
            order_ref="TRADING_OS|ROSS_MOMENTUM|MCRO-1",
            entry_price=5.0,
            entry_price_source="IBKR_SNAPSHOT",
        )
    assert client.submissions == 0


def test_fillability_classifies_passive_limit_as_non_marketable() -> None:
    classification, _ = order_router.classify_submit_fillability(
        order_type="LMT",
        action="BUY",
        lmt_price=9.95,
        bid=10.0,
        ask=10.05,
    )
    assert classification == "PASSIVE_AWAY_FROM_MARKET"


def test_submit_allows_marketable_with_ibkr_authority(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": 10.0, "ask": 10.05, "last": 10.02, "volume": 100_000})
    order_id = order_router._submit_ibkr_order(
        mode=RunMode.PAPER,
        client=client,
        symbol="MCRO",
        side="BUY",
        quantity=1,
        order_ref="TRADING_OS|ROSS_MOMENTUM|MCRO-1",
        entry_price=10.02,
        entry_price_source="IBKR_SNAPSHOT",
    )
    assert order_id == 777
    assert client.submissions == 1


def test_submit_blocks_likely_restricted_low_price(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": 1.8, "ask": 1.85, "last": 1.82, "volume": 200_000})
    with pytest.raises(RuntimeError, match="LIKELY_IBKR_RESTRICTED"):
        order_router._submit_ibkr_order(
            mode=RunMode.PAPER,
            client=client,
            symbol="PENNY",
            side="BUY",
            quantity=1,
            order_ref="TRADING_OS|ROSS_MOMENTUM|PENNY-1",
            entry_price=1.82,
            entry_price_source="IBKR_SNAPSHOT",
        )
    assert client.submissions == 0
