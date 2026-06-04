from __future__ import annotations

from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.engines.trade_lifecycle_engine import TradeLifecycleEngine
from src.core.event_collector import EventCollector
from src.core.orchestrator import CoreOrchestrator
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import OrderSnapshot, PositionSnapshot
from src.execution.startup_recovery_authority import RecoveryState, StartupRecoveryResult
from src.models.data_models import RiskDecision
from src.models.execution_result import ExecutionResult
from src.storage.sqlite_store import SCHEMA_VERSION, SQLiteStore


class _NoOpenLifecyclePersistence:
    def fetch_trade_lifecycle_trades(self, **_kwargs):
        return []


class _PriorRunLifecyclePersistence:
    def __init__(self) -> None:
        self.fetch_kwargs: dict = {}

    def fetch_trade_lifecycle_trades(self, **kwargs):
        self.fetch_kwargs = dict(kwargs)
        return [
            {
                "lifecycle_trade_id": "LIFE-1",
                "symbol": "AAPL",
                "side": "LONG",
                "strategy_name": "ross_momentum",
                "status": "TARGET_ACTIVE",
                "opened_at": "2026-06-01T13:30:00+00:00",
                "quantity_open": 5,
                "quantity_closed": 0,
                "entry_avg_price": 100.0,
                "stop_price": 99.0,
                "target_price": 105.0,
                "target_quantity": 2,
                "target_type": "FIXED_PRICE",
            }
        ]


class _P5Provider:
    def __init__(
        self,
        *,
        positions: list[object] | None = None,
        orders: list[object] | None = None,
        fail_positions: bool = False,
        fail_orders: bool = False,
    ) -> None:
        self.positions = list(positions or [])
        self.orders = list(orders or [])
        self.fail_positions = fail_positions
        self.fail_orders = fail_orders
        self.submitted_orders = 0

    def name(self) -> str:
        return "P5_TEST_PROVIDER"

    def is_live(self) -> bool:
        return True

    def get_positions(self) -> PositionSnapshot:
        if self.fail_positions:
            raise RuntimeError("positions unavailable")
        return PositionSnapshot(positions=list(self.positions), as_of="2026-06-03T12:00:00+00:00")

    def get_open_orders(self) -> list[object]:
        if self.fail_orders:
            raise RuntimeError("orders unavailable")
        return list(self.orders)

    def place_order(self, request):
        self.submitted_orders += 1
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=True,
            status="Filled",
            rationale="p5_test_fill",
            direction=request.direction,
            quantity=request.quantity,
            requested_quantity=request.quantity,
            filled_quantity=request.quantity,
            remaining_quantity=0,
            fill_status="FULL",
            client_order_id=request.client_order_id,
        )

    def cancel(self, order_id: str):
        return {"order_id": order_id, "status": "NOT_SUPPORTED", "rationale": "test"}

    def place_stop_order(self, **kwargs):
        return {"broker_order_id": "STOP-REPAIRED", "status": "Submitted", **kwargs}

    def place_target_order(self, **kwargs):
        return {"broker_order_id": "TGT-REPAIRED", "status": "Submitted", **kwargs}

    def modify_stop_order(self, **kwargs):
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Submitted"}

    def cancel_order(self, *, broker_order_id: str):
        return {"broker_order_id": broker_order_id, "status": "Cancelled"}


def _decision(symbol: str = "AAPL") -> RiskDecision:
    return RiskDecision(
        symbol=symbol,
        allowed=True,
        max_position_size=1,
        risk_level="LOW",
        rationale="p5 test",
        trader_type="RECOVERY_TEST",
        strategy_name="ross_momentum",
        direction="BUY",
        stop_loss_price=99.0,
        decision_id=f"decision-{symbol}",
        intent_id=f"intent-{symbol}",
    )


def _engine(provider: _P5Provider, lifecycle_engine: TradeLifecycleEngine | None = None) -> ExecutionEngine:
    return ExecutionEngine(
        provider=provider,
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        trade_lifecycle_engine=lifecycle_engine or TradeLifecycleEngine(
            persistence_adapter=_NoOpenLifecyclePersistence()
        ),
    )


def test_recovery_pending_blocks_entries_and_order_submission() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True, "IBKR_READONLY_ENABLED": False})
    try:
        provider = _P5Provider()
        engine = _engine(provider)
        engine.startup_recovery_state = RecoveryState.RECOVERY_PENDING
        engine.startup_recovery_result = StartupRecoveryResult(
            state=RecoveryState.RECOVERY_PENDING,
            reason="unit_test_pending",
        )

        result = engine.execute_trade(_decision())

        assert result.status == "BLOCKED"
        assert result.rationale == "STARTUP_RECOVERY_NOT_COMPLETE:unit_test_pending"
        assert provider.submitted_orders == 0
    finally:
        set_config_overrides(None)


def test_recovery_failure_blocks_trading() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True, "IBKR_READONLY_ENABLED": False})
    try:
        provider = _P5Provider(fail_positions=True)
        engine = _engine(provider)

        assert engine.startup_recovery_state == RecoveryState.RECOVERY_FAILED

        result = engine.execute_trade(_decision())

        assert result.status == "BLOCKED"
        assert result.rationale == "STARTUP_RECOVERY_NOT_COMPLETE:BROKER_POSITION_LOAD_FAILED"
        assert provider.submitted_orders == 0
    finally:
        set_config_overrides(None)


def test_broker_order_load_failure_enters_recovery_failed_and_blocks_trading() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True, "IBKR_READONLY_ENABLED": False})
    try:
        provider = _P5Provider(fail_orders=True)
        engine = _engine(provider)

        assert engine.startup_recovery_state == RecoveryState.RECOVERY_FAILED
        assert engine.startup_recovery_result is not None
        assert engine.startup_recovery_result.reason == "BROKER_ORDER_LOAD_FAILED"

        result = engine.execute_trade(_decision("MSFT"))

        assert result.status == "BLOCKED"
        assert result.rationale == "STARTUP_RECOVERY_NOT_COMPLETE:BROKER_ORDER_LOAD_FAILED"
        assert provider.submitted_orders == 0
    finally:
        set_config_overrides(None)


def test_prior_run_lifecycle_records_are_recovered_across_run_ids(tmp_path) -> None:
    store = SQLiteStore(str(tmp_path / "p5_lifecycle.db"))
    store.initialize_schema()
    old_run_id = "old-run"
    new_run_id = "new-run"
    for run_id in (old_run_id, new_run_id):
        store.insert_run(
            {
                "run_id": run_id,
                "started_at": "2026-06-03T00:00:00+00:00",
                "started_at_utc": "2026-06-03T00:00:00+00:00",
                "run_mode": "LIVE",
                "effective_run_mode": "LIVE",
                "event_replay_mode": "LIVE",
                "schema_version": SCHEMA_VERSION,
                "created_at": "2026-06-03T00:00:00+00:00",
            }
        )
    store.upsert_trade_lifecycle_trade(
        {
            "lifecycle_trade_id": "PRIOR-LIFE",
            "run_id": old_run_id,
            "symbol": "MSFT",
            "side": "LONG",
            "strategy_name": "ross_momentum",
            "status": "PROTECTED",
            "opened_at": "2026-06-02T13:30:00+00:00",
            "quantity_open": 4,
            "quantity_closed": 0,
            "entry_avg_price": 200.0,
            "stop_price": 198.0,
            "target_price": 204.0,
            "target_quantity": 2,
            "target_type": "FIXED_PRICE",
            "created_at": "2026-06-02T13:30:00+00:00",
            "updated_at": "2026-06-02T13:31:00+00:00",
        }
    )

    class _Adapter:
        def fetch_trade_lifecycle_trades(self, *, open_only: bool = False):
            assert open_only is True
            return store.fetch_open_trade_lifecycle_trades()

    engine = TradeLifecycleEngine(persistence_adapter=_Adapter())
    recovery = engine.recover_open_state()

    assert recovery["ok"] is True
    assert recovery["open_loaded"] == 1
    assert engine.find_open_trade_id_for_symbol("MSFT") == "PRIOR-LIFE"
    store.close()


def test_broker_position_stop_and_target_are_adopted_and_duplicate_target_blocked() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True, "IBKR_READONLY_ENABLED": False})
    try:
        lifecycle_persistence = _PriorRunLifecyclePersistence()
        lifecycle_engine = TradeLifecycleEngine(persistence_adapter=lifecycle_persistence)
        position = SimpleNamespace(symbol="AAPL", position=5, avgCost=100.0)
        orders = [
            OrderSnapshot(
                order_id="STOP-1",
                symbol="AAPL",
                status="Submitted",
                order_type="STP",
                parent_order_id="LIFE-1",
                metadata={"side": "SELL", "quantity": 5, "stop_price": 99.0, "trade_id": "LIFE-1"},
            ),
            OrderSnapshot(
                order_id="TGT-1",
                symbol="AAPL",
                status="Submitted",
                order_type="LMT",
                parent_order_id="LIFE-1",
                metadata={"side": "SELL", "quantity": 2, "limit_price": 105.0, "trade_id": "LIFE-1"},
            ),
        ]
        provider = _P5Provider(positions=[position], orders=orders)
        registry = ActiveTradeRegistry()
        engine = ExecutionEngine(
            provider=provider,
            trade_registry=registry,
            event_collector=EventCollector(),
            trade_lifecycle_engine=lifecycle_engine,
        )
        trade = engine.post_fill_lifecycle.get_trade("LIFE-1")

        assert engine.startup_recovery_complete() is True
        assert lifecycle_persistence.fetch_kwargs == {"open_only": True}
        assert registry.count_active() == 1
        assert trade is not None
        assert trade.stop is not None
        assert trade.stop.broker_order_id == "STOP-1"
        assert trade.target is not None
        assert trade.target.broker_order_id == "TGT-1"

        duplicate = engine.post_fill_lifecycle.take_profit_authority.create_fixed_price_target(
            trade_id="LIFE-1",
            symbol="AAPL",
            side="LONG",
            target_price=106.0,
            live_position_quantity=5,
            source_strategy="ross_momentum",
            target_stage="PARTIAL_1",
            quantity=2,
        )
        assert duplicate.accepted is False
        assert duplicate.reason_code == "DUPLICATE_TARGET_SLICE"
    finally:
        set_config_overrides(None)


def test_recovery_complete_enables_trading_and_orchestrator_gate_blocks_failures() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True, "IBKR_READONLY_ENABLED": False})
    try:
        provider = _P5Provider()
        engine = _engine(provider)
        assert engine.startup_recovery_complete() is True

        orchestrator_like = SimpleNamespace(
            execution_engine=SimpleNamespace(
                startup_recovery_complete=lambda: False,
                startup_recovery_state=RecoveryState.RECOVERY_FAILED,
                startup_recovery_block_reason=lambda: "unit_test_failed",
            )
        )
        assert CoreOrchestrator._startup_recovery_allows_strategy_execution(orchestrator_like) is False
    finally:
        set_config_overrides(None)
