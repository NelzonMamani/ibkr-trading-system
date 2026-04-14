from __future__ import annotations

from types import SimpleNamespace

from src.core_engine.state import RunMode
from src.execution import order_router


def _reset_router_state() -> None:
    order_router._RUNTIME_ORDERS.clear()
    order_router._RUNTIME_POSITIONS.clear()
    order_router._IBKR_POSITIONS_BY_SYMBOL.clear()
    order_router._POSITION_OWNERSHIP_BY_SYMBOL.clear()
    order_router._OPEN_ORDER_OWNERSHIP_BY_ID.clear()
    order_router._BROKER_POSITION_LAST_QTY_BY_SYMBOL.clear()
    order_router._TRADING_CONTROL_MODE_LOCKED = False
    order_router._TRADING_CONTROL_MODE = "LEGACY"
    order_router._CIRCUIT_BREAKER_ACTIVE = False


def _decision(symbol: str, intent_id: str = "ABCD-1", *, side: str = "LONG", action: str = "ENTER"):
    return SimpleNamespace(
        symbol=symbol,
        intent_id=intent_id,
        side=side,
        action=action,
        decision="ALLOW",
        approved_quantity=1,
        available_funds=1000.0,
        order_value=10.0,
        risk_allowed=True,
        max_position_size=1,
        constraints=[],
        block_reason="",
        entry_price=10.0,
    )


def test_control_mode_selected_and_runtime_switch_is_blocked(capsys) -> None:
    _reset_router_state()
    assert order_router.set_trading_control_mode("ISOLATED_TRADING", lock=True) is True
    assert order_router.set_trading_control_mode("CLEAN_START", lock=True) is False
    out = capsys.readouterr().out
    assert "[CONTROL_MODE][SELECTED] mode=ISOLATED_TRADING" in out
    assert "[CONTROL_MODE][VIOLATION] attempted_runtime_mode_switch=true" in out


def test_isolated_unknown_positions_default_to_external(monkeypatch, capsys) -> None:
    _reset_router_state()
    order_router.set_trading_control_mode("ISOLATED_TRADING", lock=True)
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    monkeypatch.setattr(
        order_router,
        "_fetch_ibkr_truth",
        lambda _mode: ([], [], [SimpleNamespace(symbol="EXT", position=5, avgCost=10.0)]),
    )
    order_router.execute_intents(mode=RunMode.PAPER, decisions=[])
    out = capsys.readouterr().out
    assert "[POSITION][EXTERNAL] symbol=EXT qty=5" in out
    assert "external_positions=1" in out


def test_external_positions_do_not_count_toward_max_open_positions(monkeypatch, capsys) -> None:
    _reset_router_state()
    order_router.set_trading_control_mode("ISOLATED_TRADING", lock=True)
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    monkeypatch.setattr(order_router, "_config_int", lambda n, d: 1 if n == "MAX_OPEN_POSITIONS" else d)
    monkeypatch.setattr(order_router, "_config_bool", lambda *_a, **_k: True)
    monkeypatch.setattr(
        order_router,
        "_fetch_ibkr_truth",
        lambda _mode: (
            [],
            [],
            [
                SimpleNamespace(symbol="EXT1", position=10, avgCost=10.0),
                SimpleNamespace(symbol="EXT2", position=7, avgCost=20.0),
            ],
        ),
    )
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision("NEWSYM")])
    out = capsys.readouterr().out
    assert events[0].action == "SUBMITTED"
    assert "[RISK][SYSTEM_PORTFOLIO] system_open_positions=0 external_open_positions=2" in out
    assert "reason=MAX_OPEN_POSITIONS" not in out


def test_external_symbol_blocks_new_system_entry(monkeypatch, capsys) -> None:
    _reset_router_state()
    order_router.set_trading_control_mode("ISOLATED_TRADING", lock=True)
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    monkeypatch.setattr(order_router, "_config_int", lambda *_a, **_k: 5)
    monkeypatch.setattr(order_router, "_config_bool", lambda *_a, **_k: True)
    monkeypatch.setattr(
        order_router,
        "_fetch_ibkr_truth",
        lambda _mode: ([], [], [SimpleNamespace(symbol="RMSG", position=10, avgCost=10.0)]),
    )
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision("RMSG")])
    out = capsys.readouterr().out
    assert events[0].action == "BLOCKED"
    assert "[EXECUTION][SYMBOL_OWNERSHIP_BLOCK] symbol=RMSG reason=EXTERNAL_POSITION_PRESENT" in out


def test_external_positions_are_non_fatal_reconciliation(monkeypatch, capsys) -> None:
    _reset_router_state()
    order_router.set_trading_control_mode("ISOLATED_TRADING", lock=True)
    order_router._POSITION_OWNERSHIP_BY_SYMBOL["BBB"] = order_router.OWNERSHIP_EXTERNAL
    order_router._run_passive_position_reconciliation(
        positions=[SimpleNamespace(symbol="BBB", position=5, avgCost=10.0)]
    )
    out = capsys.readouterr().out
    assert "[RECON][EXTERNAL_INVENTORY] symbol=BBB reason=unowned_broker_state" in out
    assert order_router._RECONCILED_POSITIONS_MISMATCH == 0


def test_system_mismatch_remains_strict(monkeypatch, capsys) -> None:
    _reset_router_state()
    order_router.set_trading_control_mode("ISOLATED_TRADING", lock=True)
    order_router._POSITION_OWNERSHIP_BY_SYMBOL["SYS"] = order_router.OWNERSHIP_SYSTEM
    order_router._run_passive_position_reconciliation(
        positions=[SimpleNamespace(symbol="SYS", position=5, avgCost=10.0)]
    )
    out = capsys.readouterr().out
    assert "[RECON][SYSTEM_MISMATCH] symbol=SYS verdict=BROKER_POSITION_WITHOUT_FILL" in out
    assert order_router._RECONCILED_POSITIONS_MISMATCH >= 1


def test_external_open_order_classified_and_excluded_from_duplicate_check(monkeypatch, capsys) -> None:
    _reset_router_state()
    order_router.set_trading_control_mode("ISOLATED_TRADING", lock=True)
    monkeypatch.setattr(order_router, "_is_explicit_test_mode", lambda: True)
    monkeypatch.setattr(order_router, "_config_int", lambda *_a, **_k: 5)
    monkeypatch.setattr(order_router, "_config_bool", lambda *_a, **_k: True)
    monkeypatch.setattr(
        order_router,
        "_fetch_ibkr_truth",
        lambda _mode: (
            [SimpleNamespace(symbol="ABCD", orderId=99, status="Submitted", order=SimpleNamespace(action="BUY", orderRef="MANUAL|OTHER|X"))],
            [],
            [],
        ),
    )
    events = order_router.execute_intents(mode=RunMode.PAPER, decisions=[_decision("ABCD")])
    out = capsys.readouterr().out
    assert events[0].action == "SUBMITTED"
    assert "[ORDER][EXTERNAL] order_id=99 symbol=ABCD" in out
    assert "DUPLICATE_WORKING_ORDER" not in out
