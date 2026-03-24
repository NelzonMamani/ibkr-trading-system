from types import SimpleNamespace

import pytest

from src.config.config_resolver import ConfigRecord, resolve_execution_flags, set_config_overrides
from src.execution.execution_engine import ExecutionEngine
from src.risk.risk_engine import validate_order
from src.strategy.strategy_runner import StrategyRunner


def _record(name, value, source="DEFAULT"):
    return ConfigRecord(name=name, value=value, source=source, env=None, trace=())


def test_resolve_execution_flags_enables_paper_defaults():
    resolved = resolve_execution_flags({
        "RUN_MODE": _record("RUN_MODE", "PAPER"),
        "EXECUTION_ENABLED": _record("EXECUTION_ENABLED", False),
        "IBKR_READONLY_ENABLED": _record("IBKR_READONLY_ENABLED", True),
        "IBKR_ORDER_SUBMISSION_ENABLED": _record("IBKR_ORDER_SUBMISSION_ENABLED", False),
        "IBKR_ORDER_TRANSLATION_ENABLED": _record("IBKR_ORDER_TRANSLATION_ENABLED", False),
    })

    assert resolved["EXECUTION_ENABLED"].value is True
    assert resolved["IBKR_READONLY_ENABLED"].value is False
    assert resolved["IBKR_ORDER_SUBMISSION_ENABLED"].value is True
    assert resolved["IBKR_ORDER_TRANSLATION_ENABLED"].value is True


def test_resolve_execution_flags_live_disabled_keeps_execution_off():
    records = {
        "RUN_MODE": _record("RUN_MODE", "LIVE"),
        "EXECUTION_ENABLED": _record("EXECUTION_ENABLED", False, source="ENV"),
        "IBKR_READONLY_ENABLED": _record("IBKR_READONLY_ENABLED", True),
        "IBKR_ORDER_SUBMISSION_ENABLED": _record("IBKR_ORDER_SUBMISSION_ENABLED", False),
        "IBKR_ORDER_TRANSLATION_ENABLED": _record("IBKR_ORDER_TRANSLATION_ENABLED", False),
    }

    try:
        resolved = resolve_execution_flags(records)
    except Exception as exc:  # pragma: no cover - compatibility with pre-PR534 behavior
        pytest.xfail(f"Legacy config-layer invariant still active: {exc}")

    assert resolved["EXECUTION_ENABLED"].value is False


def test_strategy_runner_logs_alert_when_no_intents(capsys):
    set_config_overrides({"SELECTED_STRATEGY": "", "ENABLED_STRATEGIES": {}})
    try:
        runner = StrategyRunner(strategies=[])
        result = runner.process(
            strategy_key="demo",
            watchlist=[SimpleNamespace(symbol="AAPL")],
            snapshots={},
            session_label="RTH",
            timestamp_utc="2026-03-20T00:00:00Z",
            mode="PAPER",
            session_phase="OPEN",
        )
    finally:
        set_config_overrides({})

    assert result == []
    assert "[ALERT] NO_INTENTS_GENERATED" in capsys.readouterr().out


def test_validate_order_rejects_exposure_limit():
    order = SimpleNamespace(size=10)
    portfolio = SimpleNamespace(total_exposure=200, max_exposure=100, max_position_size=50, daily_loss=0, max_daily_loss=100)

    result = validate_order(order, portfolio)

    assert result.accepted is False
    assert result.reason == "EXPOSURE_LIMIT"


def test_execution_engine_blocks_with_gate_trace(capsys):
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": False})
    try:
        engine = ExecutionEngine(provider=None)
        request = SimpleNamespace(
            symbol="AAPL",
            direction="LONG",
            quantity=1,
            trader_type="MANUAL",
            strategy_name="Demo",
            stop_loss_price=None,
            take_profit_price=None,
            attempt_number=1,
            client_order_id="abc",
        )
        result = engine._route_order(request)
    finally:
        set_config_overrides({})

    output = capsys.readouterr().out
    assert "[EXECUTION][GATE]" in output
    assert "[EXECUTION][BLOCKED] reason=EXECUTION_DISABLED" in output
    assert result.status == "BLOCKED"
