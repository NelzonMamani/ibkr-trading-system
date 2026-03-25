from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.execution.execution_engine import ExecutionEngine
from src.models.data_models import RiskDecision, TradeIntent
from src.strategy.strategy_runner import StrategyRunner
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


class _FakeRunner:
    def __init__(self, payload: dict):
        self.payload = payload

    def run(self, _context):
        return self.payload


class _Mode:
    value = "PAPER"


def test_trade_ready_without_concrete_intent_raises() -> None:
    runner = StrategyRunner(strategies=[SimpleNamespace(name="RossMomentumStrategyV1")])
    runner._runner_registry = {
        "RossMomentumStrategyV1": _FakeRunner({"trade_intents": [], "trade_ready_count": 1})
    }

    with pytest.raises(RuntimeError, match="Ross emitted TRADE_READY"):
        runner.process(
            strategy_key="ross_momentum",
            watchlist=["AAPL"],
            snapshots={},
            session_label="PRE",
            timestamp_utc="2026-03-25T00:00:00Z",
            mode=_Mode(),
            session_phase="PREMARKET",
        )


def test_trade_ready_forward_log_is_emitted(capsys: pytest.CaptureFixture[str]) -> None:
    intent = TradeIntent(
        symbol="AAPL",
        direction="LONG",
        strategy_name="RossMomentumStrategyV1",
        confidence=0.9,
        rationale="test",
        pattern_name="P_ORB",
    )
    intent.decision = "TRADE_READY"

    runner = StrategyRunner(strategies=[SimpleNamespace(name="RossMomentumStrategyV1")])
    runner._runner_registry = {
        "RossMomentumStrategyV1": _FakeRunner({"trade_intents": [intent], "trade_ready_count": 1})
    }

    result = runner.process(
        strategy_key="ross_momentum",
        watchlist=["AAPL"],
        snapshots={},
        session_label="PRE",
        timestamp_utc="2026-03-25T00:00:00Z",
        mode=_Mode(),
        session_phase="PREMARKET",
    )

    assert len(result) == 1
    assert "[INTENT][FORWARD] symbol=AAPL strategy=ross_momentum pattern=P_ORB decision=TRADE_READY forwarded=True" in capsys.readouterr().out


def test_terminal_path_guard_raises_on_missing_terminal_path() -> None:
    with pytest.raises(RuntimeError, match="CRITICAL: TRADE_READY reached terminal handling"):
        CoreOrchestrator._assert_trade_ready_terminal_paths(
            execution_enabled=True,
            trade_ready_terminal={"AAPL": {"blocked": False, "submitted": False}},
        )


def test_session_aware_volume_thresholds() -> None:
    set_config_overrides({"PREMARKET_MIN_VOLUME": 2_000, "RTH_MIN_VOLUME": 10_000})
    try:
        strategy = RossMomentumStrategyV1()
    finally:
        set_config_overrides(None)

    pre_vol, _ = strategy._session_thresholds("PRE")
    rth_vol, _ = strategy._session_thresholds("RTH_OPEN")
    assert pre_vol == 2000
    assert rth_vol == 10000


def test_execution_engine_logs_receipt_build_and_submit(capsys: pytest.CaptureFixture[str]) -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        engine = ExecutionEngine()
        engine.current_tick = 7
        decision = RiskDecision(
            symbol="AAPL",
            allowed=True,
            max_position_size=1,
            risk_level="LOW",
            rationale="ok",
            trader_type="MANUAL",
            strategy_name="ross_momentum",
            direction="LONG",
            stop_loss_price=99.0,
            decision_id="decision-1",
        )
        decision.entry_price = 100.0

        _ = engine.execute_trade(decision)
        out = capsys.readouterr().out
        assert "[EXECUTION][RECEIVED] symbol=AAPL" in out
        assert "[ORDER][BUILD] symbol=AAPL" in out
        assert "[ORDER][SUBMIT]" in out
    finally:
        set_config_overrides(None)


def test_ibkr_callbacks_emit_order_observability_logs(capsys: pytest.CaptureFixture[str]) -> None:
    ibapi = pytest.importorskip("ibapi")
    _ = ibapi
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient

    client = IbkrClient.__new__(IbkrClient)
    client.NON_REJECTING_ORDER_WARNING_CODES = {2109}
    client._errors = {}
    client._order_status = {}
    client._order_errors = {}
    client._order_warnings = {}
    client._order_status_events = {123: threading.Event()}
    client._exec_details_by_order = {}
    client._contract_events = {}
    client._market_events = {}
    client._historical_events = {}
    client._account_summary_events = {}
    client._scanner_events = {}
    client._market_update_event = threading.Event()
    client._connection_event = threading.Event()

    contract = SimpleNamespace(symbol="AAPL")
    execution = SimpleNamespace(orderId=123, execId="e-1", time="now", price=101.5, shares=5)

    client.orderStatus(123, "Submitted", 0, 5, 0.0, 0, 0, 0.0, 0, "", 0.0)
    client.openOrder(123, contract, SimpleNamespace(), SimpleNamespace())
    client.execDetails(0, contract, execution)
    client.error(123, 201, "rejected")

    out = capsys.readouterr().out
    assert "[ORDER][STATUS] order_id=123 status=Submitted filled=0 remaining=5" in out
    assert "[ORDER][OPEN] order_id=123 symbol=AAPL" in out
    assert "[ORDER][FILL] symbol=AAPL order_id=123 shares=5 avg_price=101.5" in out
    assert "[ORDER][ERROR] order_id=123 code=201 message=rejected" in out
