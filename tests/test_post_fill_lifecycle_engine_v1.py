from types import SimpleNamespace

from src.execution.post_fill_lifecycle_engine import (
    ManagedTradeLifecycle,
    PostFillLifecycleEngine,
    PositionLifecycleState,
)


class _ProviderStub:
    def __init__(self) -> None:
        self.stop_calls: list[dict] = []
        self.target_calls: list[dict] = []
        self.modify_calls: list[dict] = []
        self.cancel_calls: list[dict] = []
        self.fail_stop_repairs = False
        self.fail_target_repairs = False

    def place_stop_order(self, **kwargs):
        self.stop_calls.append(dict(kwargs))
        if self.fail_stop_repairs and kwargs.get("trade_id") == "T-STOP-FAIL":
            raise RuntimeError("stop repair failure")
        return {"broker_order_id": "STOP-1", "status": "Submitted"}

    def place_target_order(self, **kwargs):
        self.target_calls.append(dict(kwargs))
        if self.fail_target_repairs and kwargs.get("trade_id") == "T-TARGET-FAIL":
            raise RuntimeError("target repair failure")
        return {"broker_order_id": "TGT-1", "status": "Submitted"}

    def modify_stop_order(self, **kwargs):
        self.modify_calls.append(dict(kwargs))
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Submitted"}

    def cancel_order(self, **kwargs):
        self.cancel_calls.append(dict(kwargs))
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Cancelled"}


def test_fill_installs_stop_and_target_in_paper_mode() -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    result = engine.activate_trade_management_after_fill(
        trade_id="T-1",
        symbol="AAPL",
        side="LONG",
        filled_qty=10,
        avg_fill_price=100.0,
        strategy_id="S1",
    )
    assert result["success"] is True
    assert result["installed_stop_metadata"]["trigger_price"] < 100.0
    assert result["installed_target_metadata"]["trigger_price"] > 100.0
    assert result["installed_stop_metadata"]["broker_order_id"] == "STOP-1"
    assert result["installed_target_metadata"]["broker_order_id"] == "TGT-1"
    assert len(provider.stop_calls) == 1
    assert len(provider.target_calls) == 1
    assert result["protection_state"] == PositionLifecycleState.TRAILING_ELIGIBLE.value


def test_read_only_does_not_mutate_and_flags_failure() -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="READ_ONLY", execution_provider=provider)
    result = engine.activate_trade_management_after_fill(
        trade_id="T-2",
        symbol="MSFT",
        side="LONG",
        filled_qty=5,
        avg_fill_price=200.0,
        strategy_id="S2",
    )
    assert result["success"] is False
    assert result["failure_reason"] == "READ_ONLY_MODE"
    trade = engine.get_trade("T-2")
    assert trade is not None
    assert trade.state == PositionLifecycleState.LIFECYCLE_FAILURE
    assert provider.stop_calls == []
    assert provider.target_calls == []


def test_trailing_only_activates_after_threshold_and_never_loosens() -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(
        trade_id="T-3",
        symbol="NVDA",
        side="LONG",
        filled_qty=2,
        avg_fill_price=100.0,
        strategy_id="S3",
    )
    first = engine.evaluate_trailing("T-3", current_price=101.0)
    assert first["updated"] is False
    activated = engine.evaluate_trailing("T-3", current_price=102.0)
    assert activated["updated"] is True
    stop_after = float(activated["stop_price"])
    assert len(provider.modify_calls) == 1
    rejected = engine.evaluate_trailing("T-3", current_price=100.5)
    assert rejected["updated"] is False
    assert float(rejected["stop_price"]) == stop_after
    assert len(provider.modify_calls) == 1


def test_exit_is_driven_from_broker_callback() -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(
        trade_id="T-4",
        symbol="AMD",
        side="LONG",
        filled_qty=1,
        avg_fill_price=100.0,
        strategy_id="S4",
    )
    callback_result = engine.handle_broker_callback(
        {"event_type": "execDetails", "order_id": "STOP-1", "price": 98.5, "shares": 1, "fill_time": "2026-04-15T00:00:00+00:00"}
    )
    assert callback_result["handled"] is True
    assert callback_result["exit_reason"] == "STOP_FILLED"
    assert callback_result["cancel_order_id"] == "TGT-1"
    assert provider.cancel_calls == [{"broker_order_id": "TGT-1"}]
    trade = engine.get_trade("T-4")
    assert trade is not None
    assert trade.state == PositionLifecycleState.EXITED
    assert trade.exit_fill_price == 98.5
    assert trade.realized_pnl == -1.5
    assert trade.target is not None
    assert trade.target.status == "CANCELLED"


def test_exit_submission_does_not_close_trade_immediately() -> None:
    engine = PostFillLifecycleEngine(run_mode="PAPER")
    engine.activate_trade_management_after_fill(
        trade_id="T-PENDING-1",
        symbol="AAPL",
        side="LONG",
        filled_qty=10,
        avg_fill_price=100.0,
        strategy_id="S-PENDING",
    )
    submit = engine.submit_exit_order_once(
        "T-PENDING-1",
        reason="STOP_LOSS",
        submitter=lambda trade: {"broker_order_id": "EXIT-100"},
    )
    trade = engine.get_trade("T-PENDING-1")
    assert submit["submitted"] is True
    assert trade is not None
    assert trade.state == PositionLifecycleState.EXIT_PENDING
    assert trade.exit_fill_price is None
    assert trade.realized_pnl is None
    assert trade.exit_fill_time is None


def test_exit_fill_closes_trade_and_computes_fill_based_pnl() -> None:
    engine = PostFillLifecycleEngine(run_mode="PAPER")
    engine.activate_trade_management_after_fill(
        trade_id="T-PENDING-2",
        symbol="MSFT",
        side="LONG",
        filled_qty=5,
        avg_fill_price=100.0,
        strategy_id="S-PNL",
    )
    engine.mark_exit_pending_with_order("T-PENDING-2", "TARGET_HIT", "EXIT-200")
    result = engine.record_exit_fill(
        "T-PENDING-2",
        fill_price=103.0,
        fill_qty=5,
        fill_time="2026-04-15T01:00:00+00:00",
        exit_order_id="EXIT-200",
    )
    trade = engine.get_trade("T-PENDING-2")
    assert result["ok"] is True
    assert trade is not None
    assert trade.state == PositionLifecycleState.EXITED
    assert trade.exit_fill_price == 103.0
    assert trade.realized_pnl == 15.0
    assert trade.exit_order_id == "EXIT-200"


def test_duplicate_exit_evaluation_does_not_submit_twice() -> None:
    engine = PostFillLifecycleEngine(run_mode="PAPER")
    engine.activate_trade_management_after_fill(
        trade_id="T-PENDING-3",
        symbol="NVDA",
        side="LONG",
        filled_qty=2,
        avg_fill_price=50.0,
        strategy_id="S-DEDUPE",
    )
    submissions: list[str] = []

    def _submit(_trade):
        submissions.append("called")
        return {"broker_order_id": "EXIT-300"}

    first = engine.submit_exit_order_once("T-PENDING-3", reason="STOP_LOSS", submitter=_submit)
    second = engine.submit_exit_order_once("T-PENDING-3", reason="STOP_LOSS", submitter=_submit)
    trade = engine.get_trade("T-PENDING-3")
    assert first["submitted"] is True
    assert second["submitted"] is False
    assert second["reason"] == "already_exit_pending"
    assert len(submissions) == 1
    assert trade is not None
    assert trade.state == PositionLifecycleState.EXIT_PENDING


def test_exit_submission_failure_leaves_trade_open() -> None:
    engine = PostFillLifecycleEngine(run_mode="PAPER")
    engine.activate_trade_management_after_fill(
        trade_id="T-PENDING-4",
        symbol="AMD",
        side="LONG",
        filled_qty=3,
        avg_fill_price=80.0,
        strategy_id="S-FAIL",
    )

    def _raise(_trade):
        raise RuntimeError("broker_down")

    submit = engine.submit_exit_order_once("T-PENDING-4", reason="STOP_LOSS", submitter=_raise)
    trade = engine.get_trade("T-PENDING-4")
    assert submit["submitted"] is False
    assert submit["reason"] == "submit_failed"
    assert trade is not None
    assert trade.state != PositionLifecycleState.EXIT_PENDING
    assert trade.state != PositionLifecycleState.EXITED
    assert trade.exit_fill_price is None
    assert trade.realized_pnl is None
    assert trade.exit_fill_time is None


def test_partial_safety_trade_closes_only_after_explicit_fill_confirmation() -> None:
    engine = PostFillLifecycleEngine(run_mode="PAPER")
    engine.activate_trade_management_after_fill(
        trade_id="T-PENDING-5",
        symbol="TSLA",
        side="LONG",
        filled_qty=10,
        avg_fill_price=200.0,
        strategy_id="S-PARTIAL",
    )
    engine.submit_exit_order_once(
        "T-PENDING-5",
        reason="RISK_EXIT",
        submitter=lambda trade: {"broker_order_id": "EXIT-500"},
    )
    pre_fill = engine.get_trade("T-PENDING-5")
    assert pre_fill is not None
    assert pre_fill.state == PositionLifecycleState.EXIT_PENDING
    assert pre_fill.realized_pnl is None

    result = engine.record_exit_fill(
        "T-PENDING-5",
        fill_price=198.0,
        fill_qty=5,
        fill_time="2026-04-15T02:00:00+00:00",
        exit_order_id="EXIT-500",
    )
    post_fill = engine.get_trade("T-PENDING-5")
    assert result["ok"] is True
    assert post_fill is not None
    assert post_fill.state == PositionLifecycleState.EXITED
    assert post_fill.exited_qty == 5


def test_startup_recovery_marks_protected_and_pending() -> None:
    engine = PostFillLifecycleEngine(run_mode="LIVE")
    positions = [
        SimpleNamespace(symbol="AMD", quantity=3, stop_loss_price=95.0, entry_price=100.0, direction="LONG"),
        SimpleNamespace(symbol="TSLA", quantity=4, stop_loss_price=None, entry_price=180.0, direction="LONG"),
    ]
    summary = engine.startup_safe_state(positions, broker_orders=[])
    assert summary["recovered"] == 1
    assert summary["recovery_pending"] == 1
    recovered = engine.get_trade("recovery:AMD")
    assert recovered is not None
    assert recovered.state == PositionLifecycleState.RECOVERED


def test_reconciliation_detects_missing_stop_and_repairs() -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(
        trade_id="T-5",
        symbol="AAPL",
        side="LONG",
        filled_qty=1,
        avg_fill_price=100.0,
        strategy_id="S5",
    )
    trade = engine.get_trade("T-5")
    assert trade is not None
    trade.stop.broker_order_id = "STOP-MISSING"
    trade.target.broker_order_id = "TGT-OPEN"
    summary = engine.reconcile_orders([{"orderId": "TGT-OPEN", "status": "Submitted"}], repair=True)
    assert any(f["issue"] == "MISSING_STOP" for f in summary["findings"])
    assert not any(f["issue"] == "STOP_REPAIR_FAILED" for f in summary["findings"])
    assert summary["repaired"] == 1
    assert summary["block_new_entries"] is False
    assert len(provider.stop_calls) == 2


def test_reconciliation_detects_missing_target_and_repairs() -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(
        trade_id="T-6",
        symbol="AAPL",
        side="LONG",
        filled_qty=1,
        avg_fill_price=100.0,
        strategy_id="S6",
    )
    trade = engine.get_trade("T-6")
    assert trade is not None
    trade.stop.broker_order_id = "STOP-OPEN"
    trade.target.broker_order_id = "TGT-MISSING"
    summary = engine.reconcile_orders([{"orderId": "STOP-OPEN", "status": "Submitted"}], repair=True)
    assert any(f["issue"] == "MISSING_TARGET" for f in summary["findings"])
    assert not any(f["issue"] == "TARGET_REPAIR_FAILED" for f in summary["findings"])
    assert summary["repaired"] == 1
    assert summary["block_new_entries"] is False
    assert len(provider.target_calls) == 2


def test_reconciliation_failed_stop_repair_triggers_hard_failsafe(capsys) -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(
        trade_id="T-STOP-FAIL",
        symbol="AAPL",
        side="LONG",
        filled_qty=1,
        avg_fill_price=100.0,
        strategy_id="S7",
    )
    trade = engine.get_trade("T-STOP-FAIL")
    assert trade is not None
    provider.fail_stop_repairs = True
    trade.stop.broker_order_id = "STOP-MISSING"
    summary = engine.reconcile_orders([], repair=True)
    assert any(f["issue"] == "MISSING_STOP" for f in summary["findings"])
    assert any(f["issue"] == "STOP_REPAIR_FAILED" for f in summary["findings"])
    assert summary["block_new_entries"] is True
    assert trade.state == PositionLifecycleState.LIFECYCLE_FAILURE
    assert "[LIFECYCLE][ILLEGAL_TRANSITION]" not in capsys.readouterr().out


def test_reconciliation_failed_target_repair_degrades_and_blocks_without_exit(capsys) -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(
        trade_id="T-TARGET-FAIL",
        symbol="AAPL",
        side="LONG",
        filled_qty=1,
        avg_fill_price=100.0,
        strategy_id="S8",
    )
    trade = engine.get_trade("T-TARGET-FAIL")
    assert trade is not None
    provider.fail_target_repairs = True
    trade.stop.broker_order_id = "STOP-OPEN"
    trade.target.broker_order_id = "TGT-MISSING"
    summary = engine.reconcile_orders([{"orderId": "STOP-OPEN", "status": "Submitted"}], repair=True)
    assert any(f["issue"] == "MISSING_TARGET" for f in summary["findings"])
    assert any(f["issue"] == "TARGET_REPAIR_FAILED" for f in summary["findings"])
    assert summary["block_new_entries"] is True
    assert trade.state == PositionLifecycleState.LIFECYCLE_FAILURE
    assert trade.stop is not None
    assert trade.stop.broker_order_id == "STOP-OPEN"
    assert "[LIFECYCLE][ILLEGAL_TRANSITION]" not in capsys.readouterr().out


def test_lifecycle_payload_is_serializable_for_audit() -> None:
    trade = ManagedTradeLifecycle(
        trade_id="T-9",
        symbol="QQQ",
        strategy_id="S9",
        side="LONG",
        run_mode="PAPER",
        session_label="unit",
        intended_qty=1,
        filled_qty=1,
        avg_fill_price=10.0,
    )
    payload = trade.to_dict()
    assert payload["trade_id"] == "T-9"
    assert payload["state"] == PositionLifecycleState.ENTRY_SUBMITTED.value
    assert "last_update_ts" in payload
