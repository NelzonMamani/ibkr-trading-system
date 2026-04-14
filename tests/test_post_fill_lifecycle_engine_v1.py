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

    def place_stop_order(self, **kwargs):
        self.stop_calls.append(dict(kwargs))
        return {"broker_order_id": "STOP-1", "status": "Submitted"}

    def place_target_order(self, **kwargs):
        self.target_calls.append(dict(kwargs))
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
    callback_result = engine.handle_broker_callback({"event_type": "execDetails", "order_id": "STOP-1"})
    assert callback_result["handled"] is True
    assert callback_result["exit_reason"] == "STOP_FILLED"
    assert callback_result["cancel_order_id"] == "TGT-1"
    assert provider.cancel_calls == [{"broker_order_id": "TGT-1"}]
    trade = engine.get_trade("T-4")
    assert trade is not None
    assert trade.state == PositionLifecycleState.EXITED
    assert trade.target is not None
    assert trade.target.status == "CANCELLED"


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
    assert summary["repaired"] == 1
    assert summary["block_new_entries"] is False
    assert len(provider.stop_calls) == 2


def test_reconciliation_failed_stop_repair_blocks_new_entries_and_triggers_live_hard_failsafe() -> None:
    provider = _ProviderStub()
    hard_failsafe_calls: list[dict[str, str]] = []
    engine = PostFillLifecycleEngine(
        run_mode="LIVE",
        execution_provider=provider,
        hard_failsafe_handler=lambda **kwargs: hard_failsafe_calls.append(kwargs),
    )
    engine.activate_trade_management_after_fill(
        trade_id="T-6",
        symbol="META",
        side="LONG",
        filled_qty=1,
        avg_fill_price=100.0,
        strategy_id="S6",
    )
    trade = engine.get_trade("T-6")
    assert trade is not None
    trade.stop.broker_order_id = "STOP-MISSING"
    trade.target.broker_order_id = "TGT-OPEN"
    provider.place_stop_order = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("stop repair down"))
    summary = engine.reconcile_orders([{"orderId": "TGT-OPEN", "status": "Submitted"}], repair=True)
    assert any(f["issue"] == "STOP_REPAIR_FAILED" for f in summary["findings"])
    assert summary["block_new_entries"] is True
    assert summary["hard_failsafe_actions"][0]["action"] == "LIVE_FLATTEN_REQUESTED"
    assert hard_failsafe_calls == [{"symbol": "META", "reason": "STOP_REPAIR_FAILED"}]


def test_reconciliation_failed_stop_repair_in_paper_halts_new_entries_without_flatten() -> None:
    provider = _ProviderStub()
    hard_failsafe_calls: list[dict[str, str]] = []
    engine = PostFillLifecycleEngine(
        run_mode="PAPER",
        execution_provider=provider,
        hard_failsafe_handler=lambda **kwargs: hard_failsafe_calls.append(kwargs),
    )
    engine.activate_trade_management_after_fill(
        trade_id="T-7",
        symbol="AMD",
        side="LONG",
        filled_qty=1,
        avg_fill_price=100.0,
        strategy_id="S7",
    )
    trade = engine.get_trade("T-7")
    assert trade is not None
    trade.stop.broker_order_id = "STOP-MISSING"
    trade.target.broker_order_id = "TGT-OPEN"
    provider.place_stop_order = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("stop repair down"))
    summary = engine.reconcile_orders([{"orderId": "TGT-OPEN", "status": "Submitted"}], repair=True)
    assert any(f["issue"] == "STOP_REPAIR_FAILED" for f in summary["findings"])
    assert summary["block_new_entries"] is True
    assert summary["hard_failsafe_actions"][0]["action"] == "PAPER_HALT_NEW_ENTRIES"
    assert hard_failsafe_calls == []


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
