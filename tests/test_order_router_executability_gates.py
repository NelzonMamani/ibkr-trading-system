from __future__ import annotations

import pytest

from src.core_engine.state import RunMode
from src.execution import order_router


class _Client:
    def __init__(self) -> None:
        self.submissions = 0
        self.last_order = None
        self._test_order_id_seq = 100000

    def qualifyContracts(self, contract):
        contract.conId = 123
        contract.exchange = "SMART"
        contract.currency = "USD"
        contract.primaryExchange = "NASDAQ"
        contract.secType = "STK"
        return [contract]

    def submit_order(self, _contract, _order):
        self.submissions += 1
        self.last_order = _order
        self._test_order_id_seq += 1
        reserved_order_id = self._test_order_id_seq
        broker_order_id = 777
        print("[EXECUTION][NON_IBKR_CLIENT] deterministic_id_emulated")
        print(
            "[EXECUTION][ORDER_SUBMIT_WARNING] "
            f"submit_order_order_id_mismatch reserved_order_id={reserved_order_id} broker_order_id={broker_order_id}"
        )
        return reserved_order_id

    def wait_for_order_status(self, _order_id, timeout_seconds=5):
        return {"status": "Submitted"}


def test_submit_blocks_paper_with_last_price_only_quote_context(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "RTH")
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": None, "ask": None, "last": 5.0, "volume": 50_000})
    with pytest.raises(RuntimeError, match="NO_QUOTE_PRE_SUBMIT"):
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


def test_submit_blocks_live_when_quote_context_missing(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "RTH")
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": None, "ask": None, "last": 5.0, "volume": 50_000})
    with pytest.raises(RuntimeError, match="NO_QUOTE_PRE_SUBMIT"):
        order_router._submit_ibkr_order(
            mode=RunMode.LIVE,
            client=client,
            symbol="MCRO",
            side="BUY",
            quantity=1,
            order_ref="TRADING_OS|ROSS_MOMENTUM|MCRO-1",
            entry_price=5.0,
            entry_price_source="IBKR_SNAPSHOT",
        )
    assert client.submissions == 0


def test_submit_live_premarket_uses_quote_aware_limit(monkeypatch, capsys) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "PRE")
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": 10.0, "ask": 10.05, "last": 10.02, "volume": 100_000})
    order_id = order_router._submit_ibkr_order(
        mode=RunMode.LIVE,
        client=client,
        symbol="MCRO",
        side="BUY",
        quantity=1,
        order_ref="TRADING_OS|ROSS_MOMENTUM|MCRO-1",
        entry_price=10.02,
        entry_price_source="IBKR_BID_ASK",
    )
    out = capsys.readouterr().out
    assert order_id == 100001
    assert client.submissions == 1
    assert "[EXECUTION][NON_IBKR_CLIENT] deterministic_id_emulated" in out
    assert "submit_order_order_id_mismatch" in out
    assert getattr(client.last_order, "orderType", None) == "LMT"
    assert getattr(client.last_order, "lmtPrice", None) == 10.07
    assert "enforced=PREMARKET_LIMIT orderType=LMT lmtPrice=10.07 source=BID_ASK_BUFFERED" in out


def test_submit_live_premarket_sell_uses_bid_limit(monkeypatch, capsys) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "PRE")
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": 10.0, "ask": 10.05, "last": 10.02, "volume": 100_000})
    order_id = order_router._submit_ibkr_order(
        mode=RunMode.LIVE,
        client=client,
        symbol="MCRO",
        side="SELL",
        quantity=1,
        order_ref="TRADING_OS|ROSS_MOMENTUM|MCRO-9",
        entry_price=10.02,
        entry_price_source="IBKR_BID_ASK",
    )
    out = capsys.readouterr().out
    assert order_id == 100001
    assert client.submissions == 1
    assert "[EXECUTION][NON_IBKR_CLIENT] deterministic_id_emulated" in out
    assert "submit_order_order_id_mismatch" in out
    assert getattr(client.last_order, "orderType", None) == "LMT"
    assert getattr(client.last_order, "lmtPrice", None) == 9.98
    assert "enforced=PREMARKET_LIMIT orderType=LMT lmtPrice=9.98 source=BID_ASK_BUFFERED" in out


def test_submit_exit_order_forces_market_and_outside_rth(monkeypatch, capsys) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "PRE")
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": 10.0, "ask": 10.05, "last": 10.02, "volume": 100_000})
    order_id = order_router._submit_ibkr_order(
        mode=RunMode.LIVE,
        client=client,
        symbol="MCRO",
        side="SELL",
        quantity=1,
        order_ref="TRADING_OS|ROSS_MOMENTUM|MCRO-EXIT",
        entry_price=10.02,
        entry_price_source="IBKR_BID_ASK",
        is_exit_order=True,
    )
    out = capsys.readouterr().out
    assert order_id == 100001
    assert getattr(client.last_order, "orderType", None) == "MKT"
    assert getattr(client.last_order, "outsideRth", None) is True
    assert "[EXECUTION][EXIT_FORCE_ALLOW] symbol=MCRO action=FORCE_EXECUTABLE orderType=MKT outsideRth=True" in out
    assert "enforced=EXIT_FORCE_MKT orderType=MKT outsideRth=True" in out


def test_fillability_classifies_passive_limit_as_non_marketable() -> None:
    classification, _ = order_router.classify_submit_fillability(
        order_type="LMT",
        action="BUY",
        lmt_price=9.95,
        bid=10.0,
        ask=10.05,
    )
    assert classification == "PASSIVE_AWAY_FROM_MARKET"


def test_aggressive_limit_helper_rounds_in_favor() -> None:
    buy_limit, _cap_buy, _ = order_router._compute_aggressive_limit_price(
        side="BUY", bid=10.0, ask=10.05, tick_size=0.01, aggression_level=1
    )
    sell_limit, _cap_sell, _ = order_router._compute_aggressive_limit_price(
        side="SELL", bid=10.0, ask=10.05, tick_size=0.01, aggression_level=1
    )
    assert buy_limit > 10.05
    assert round((buy_limit / 0.01) % 1, 8) == 0
    assert sell_limit < 10.0
    assert round((sell_limit / 0.01) % 1, 8) == 0


def test_fillability_distinguishes_passive_vs_crossing() -> None:
    passive, _ = order_router.classify_submit_fillability(
        order_type="LMT",
        action="BUY",
        lmt_price=10.05,
        bid=10.0,
        ask=10.05,
    )
    aggressive, _ = order_router.classify_submit_fillability(
        order_type="LMT",
        action="BUY",
        lmt_price=10.07,
        bid=10.0,
        ask=10.05,
    )
    assert passive == "PASSIVE_AT_ASK"
    assert aggressive == "CROSSING_ASK_AGGRESSIVE"


def test_submit_allows_marketable_with_ibkr_authority(monkeypatch, capsys) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "RTH")
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
    out = capsys.readouterr().out
    assert order_id == 100001
    assert client.submissions == 1
    assert "[EXECUTION][NON_IBKR_CLIENT] deterministic_id_emulated" in out
    assert "submit_order_order_id_mismatch" in out


def test_submit_allows_marketable_with_ibkr_stream_authority(monkeypatch, capsys) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "RTH")
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": 10.0, "ask": 10.05, "last": 10.02, "volume": 100_000})
    order_id = order_router._submit_ibkr_order(
        mode=RunMode.PAPER,
        client=client,
        symbol="MCRO",
        side="BUY",
        quantity=1,
        order_ref="TRADING_OS|ROSS_MOMENTUM|MCRO-2",
        entry_price=10.02,
        entry_price_source="IBKR_STREAM",
    )
    out = capsys.readouterr().out
    assert order_id == 100001
    assert client.submissions == 1
    assert "[EXECUTION][NON_IBKR_CLIENT] deterministic_id_emulated" in out
    assert "submit_order_order_id_mismatch" in out


def test_submit_blocks_non_ibkr_price_authority(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "RTH")
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": 10.0, "ask": 10.05, "last": 10.02, "volume": 100_000})
    with pytest.raises(RuntimeError, match="NO_IBKR_PRICE_AUTHORITY"):
        order_router._submit_ibkr_order(
            mode=RunMode.PAPER,
            client=client,
            symbol="MCRO",
            side="BUY",
            quantity=1,
            order_ref="TRADING_OS|ROSS_MOMENTUM|MCRO-3",
            entry_price=10.02,
            entry_price_source="SCANNER_LAST_PRICE",
        )
    assert client.submissions == 0


def test_submit_allows_low_price_when_broker_is_authority(monkeypatch, capsys) -> None:
    client = _Client()
    monkeypatch.setattr(order_router, "_session_label_now", lambda: "RTH")
    monkeypatch.setattr(order_router, "_wait_for_ibkr_snapshot_for_symbol", lambda *_args, **_kwargs: {"bid": 1.8, "ask": 1.85, "last": 1.82, "volume": 200_000})
    order_id = order_router._submit_ibkr_order(
        mode=RunMode.PAPER,
        client=client,
        symbol="PENNY",
        side="BUY",
        quantity=1,
        order_ref="TRADING_OS|ROSS_MOMENTUM|PENNY-1",
        entry_price=1.82,
        entry_price_source="IBKR_SNAPSHOT",
    )
    out = capsys.readouterr().out
    assert order_id == 100001
    assert client.submissions == 1
    assert "[EXECUTION][NON_IBKR_CLIENT] deterministic_id_emulated" in out
    assert "submit_order_order_id_mismatch" in out
