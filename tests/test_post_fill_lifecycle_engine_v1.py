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

    def place_stop_order(self, **kwargs):
        self.stop_calls.append(dict(kwargs))
        return {"broker_order_id": "STOP-1", "status": "Submitted"}

    def place_target_order(self, **kwargs):
        self.target_calls.append(dict(kwargs))
        return {"broker_order_id": "TGT-1", "status": "Submitted"}

    def modify_stop_order(self, **kwargs):
        self.modify_calls.append(dict(kwargs))
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Submitted"}


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
    trade = engine.get_trade("T-4")
    assert trade is not None
    assert trade.state == PositionLifecycleState.EXITED


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
