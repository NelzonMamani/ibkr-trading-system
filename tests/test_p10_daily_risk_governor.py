from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.daily_risk_governor import (
    DailyRiskDecisionStatus,
    DailyRiskExistingPositionPolicy,
    DailyRiskGovernor,
)
from src.core.event_collector import EventCollector
from src.core.events import SystemEvent
from src.core.orchestrator import CoreOrchestrator
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import OrderSnapshot, PositionSnapshot
from src.execution.startup_recovery_authority import RecoveryState, StartupRecoveryResult
from src.models.data_models import RiskDecision
from src.models.execution_result import ExecutionResult
from src.sim.price_feed import DeterministicPriceFeed
from src.config.runtime_config import RunMode


NOW = datetime(2026, 6, 5, 14, 0, tzinfo=timezone.utc)


BASE_CONFIG = {
    "RUN_MODE": "PAPER",
    "EXECUTION_ENABLED": True,
    "IBKR_READONLY_ENABLED": False,
    "IBKR_ORDER_SUBMISSION_ENABLED": True,
    "DAILY_RISK_GOVERNOR_ENABLED": True,
    "DAILY_RISK_TIMEZONE": "UTC",
    "DAILY_RISK_MAX_LOSS_AMOUNT": 10_000.0,
    "DAILY_RISK_MAX_LOSS_PCT": 0.0,
    "DAILY_RISK_MAX_DRAWDOWN_AMOUNT": 0.0,
    "DAILY_RISK_MAX_DRAWDOWN_PCT": 0.0,
    "DAILY_RISK_INCLUDE_UNREALIZED": False,
    "DAILY_RISK_MAX_TRADES": 0,
    "DAILY_RISK_MAX_LOSING_TRADES": 0,
    "DAILY_RISK_MAX_CONSECUTIVE_LOSSES": 0,
    "DAILY_RISK_EXISTING_POSITION_POLICY": "MANAGED_ONLY",
    "DAILY_RISK_LIVE_FAIL_CLOSED": True,
    "DAILY_RISK_MANUAL_HALT": False,
    "DAILY_RISK_RESET_TIME_LOCAL": "00:00",
    "RISK_ACCOUNT_EQUITY": 10_000.0,
    "RISK_MAX_OPEN_POSITIONS": 5,
    "LIFECYCLE_MAX_POSITIONS": 5,
    "LIFECYCLE_MAX_POSITION_EXPOSURE": 10_000.0,
    "LIFECYCLE_MAX_PORTFOLIO_EXPOSURE": 50_000.0,
    "RISK_MAX_TOTAL_EXPOSURE_PCT": 100.0,
    "STRATEGY_CAPITAL_DEFAULT_ALLOCATION_PCT": 1.0,
}


@pytest.fixture(autouse=True)
def _reset_config() -> None:
    set_config_overrides(dict(BASE_CONFIG))
    yield
    set_config_overrides(None)


def _set_config(**overrides: object) -> None:
    config = dict(BASE_CONFIG)
    config.update(overrides)
    set_config_overrides(config)


def _record_closed_trade(
    events: EventCollector,
    pnl: float,
    *,
    timestamp: datetime = NOW,
    trade_id: str | None = None,
) -> None:
    payload = {
        "symbol": "AAPL",
        "trader_type": "P10_TEST",
        "strategy_name": "unit_strategy",
        "net_realised_pnl": pnl,
        "realised_pnl": pnl,
    }
    if trade_id is not None:
        payload["trade_id"] = trade_id
    events.record_event(
        SystemEvent(
            event_type="TRADE_CLOSED",
            source="unit_test",
            timestamp=timestamp,
            payload=payload,
        )
    )


def _decision(
    *,
    symbol: str = "AAPL",
    direction: str = "BUY",
    quantity: int = 1,
    force_execute: bool = False,
) -> RiskDecision:
    risk_decision = RiskDecision(
        symbol=symbol,
        allowed=True,
        max_position_size=quantity,
        risk_level="LOW",
        rationale="p10 daily risk gate",
        trader_type="P10_TEST",
        strategy_name="unit_strategy",
        direction=direction,
        stop_loss_price=99.0 if direction.upper() != "SELL" else 101.0,
        decision_id=f"risk-p10-{symbol}-{direction}-{quantity}",
        intent_id=f"intent-p10-{symbol}-{direction}-{quantity}",
    )
    risk_decision.force_execute = force_execute
    return risk_decision


class _P10Provider:
    def __init__(self) -> None:
        self.submitted_orders: list[object] = []

    def name(self) -> str:
        return "P10_TEST_PROVIDER"

    def is_live(self) -> bool:
        return True

    def get_account_summary(self) -> dict[str, float]:
        return {
            "NetLiquidation": 10_000.0,
            "AvailableFunds": 10_000.0,
            "BuyingPower": 10_000.0,
        }

    def get_positions(self) -> PositionSnapshot:
        return PositionSnapshot(positions=[], as_of=NOW.isoformat())

    def get_open_orders(self) -> list[OrderSnapshot]:
        return []

    def place_order(self, request):
        self.submitted_orders.append(request)
        return ExecutionResult(
            symbol=request.symbol,
            trader_type=request.trader_type or "UNKNOWN",
            attempted=True,
            status="Filled",
            rationale="p10_test_fill",
            direction=request.direction,
            quantity=request.quantity,
            requested_quantity=request.quantity,
            filled_quantity=request.quantity,
            remaining_quantity=0,
            fill_status="FULL",
            average_fill_price=Decimal("100.00"),
            client_order_id=request.client_order_id,
            ibkr_order_id=1001,
            attempt_number=request.attempt_number,
        )

    def cancel(self, order_id: str):
        return {"order_id": order_id, "status": "NOT_SUPPORTED", "rationale": "test"}

    def place_stop_order(self, **kwargs):
        return {"broker_order_id": "STOP-1", "status": "Submitted", "order_type": "STP"}

    def place_target_order(self, **kwargs):
        return {"broker_order_id": "TGT-1", "status": "Submitted", "order_type": "LMT"}

    def modify_stop_order(self, **kwargs):
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Submitted"}

    def cancel_order(self, *, broker_order_id: str):
        return {"broker_order_id": broker_order_id, "status": "Cancelled"}


@dataclass
class _Lifecycle:
    realized: float = 0.0
    unrealized: float = 0.0

    def build_portfolio_state(self):
        return SimpleNamespace(
            total_realized_pnl=self.realized,
            total_unrealized_pnl=self.unrealized,
        )


def _governor(events: EventCollector | None = None, lifecycle: object | None = None) -> DailyRiskGovernor:
    return DailyRiskGovernor(
        event_collector=events or EventCollector(),
        trade_lifecycle_engine=lifecycle,
    )


def test_max_daily_loss_amount_blocks_new_entries() -> None:
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=10.0)
    events = EventCollector()
    _record_closed_trade(events, -11.0)

    decision = _governor(events).evaluate(run_mode="PAPER", now=NOW)

    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert decision.reason == "MAX_DAILY_LOSS_AMOUNT"
    assert decision.blocks_new_entries is True


def test_max_daily_loss_pct_blocks_new_entries() -> None:
    _set_config(RISK_ACCOUNT_EQUITY=1_000.0, DAILY_RISK_MAX_LOSS_PCT=1.0)
    events = EventCollector()
    _record_closed_trade(events, -11.0)

    decision = _governor(events).evaluate(run_mode="PAPER", now=NOW)

    assert decision.reason == "MAX_DAILY_LOSS_PCT"


def test_realized_pnl_tracking_uses_trade_closed_events() -> None:
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=50.0)
    events = EventCollector()
    _record_closed_trade(events, 5.0)
    _record_closed_trade(events, -7.5)

    decision = _governor(events).evaluate(run_mode="PAPER", now=NOW)

    assert decision.status == DailyRiskDecisionStatus.ALLOW
    assert decision.realized_pnl == -2.5
    assert decision.daily_trade_count == 2


def test_unrealized_losses_are_optional() -> None:
    lifecycle = _Lifecycle(unrealized=-25.0)
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=10.0, DAILY_RISK_INCLUDE_UNREALIZED=False)
    ignored = _governor(lifecycle=lifecycle).evaluate(run_mode="PAPER", now=NOW)
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=10.0, DAILY_RISK_INCLUDE_UNREALIZED=True)
    included = _governor(lifecycle=lifecycle).evaluate(run_mode="PAPER", now=NOW)

    assert ignored.status == DailyRiskDecisionStatus.ALLOW
    assert included.reason == "MAX_DAILY_LOSS_AMOUNT"


def test_daily_drawdown_amount_and_pct_block_entries() -> None:
    events = EventCollector()
    _record_closed_trade(events, -12.0)
    _set_config(DAILY_RISK_MAX_DRAWDOWN_AMOUNT=10.0)
    amount_decision = _governor(events).evaluate(run_mode="PAPER", now=NOW)
    _set_config(RISK_ACCOUNT_EQUITY=1_000.0, DAILY_RISK_MAX_DRAWDOWN_PCT=1.0)
    pct_decision = _governor(events).evaluate(run_mode="PAPER", now=NOW)

    assert amount_decision.reason == "MAX_DAILY_DRAWDOWN_AMOUNT"
    assert pct_decision.reason == "MAX_DAILY_DRAWDOWN_PCT"


def test_daily_trade_losing_trade_and_consecutive_loss_limits() -> None:
    events = EventCollector()
    _record_closed_trade(events, -1.0)
    _record_closed_trade(events, -2.0)
    _set_config(DAILY_RISK_MAX_TRADES=2)
    trade_limit = _governor(events).evaluate(run_mode="PAPER", now=NOW)
    _set_config(DAILY_RISK_MAX_LOSING_TRADES=2)
    losing_limit = _governor(events).evaluate(run_mode="PAPER", now=NOW)
    _set_config(DAILY_RISK_MAX_CONSECUTIVE_LOSSES=2)
    consecutive_limit = _governor(events).evaluate(run_mode="PAPER", now=NOW)

    assert trade_limit.reason == "MAX_DAILY_TRADES"
    assert losing_limit.reason == "MAX_LOSING_TRADES"
    assert consecutive_limit.reason == "MAX_CONSECUTIVE_LOSSES"


def test_manual_halt_and_recovery_incomplete_fail_closed() -> None:
    _set_config(DAILY_RISK_MANUAL_HALT=True)
    manual = _governor().evaluate(run_mode="LIVE", recovery_complete=True, now=NOW)
    _set_config(DAILY_RISK_MANUAL_HALT=False)
    recovery = _governor().evaluate(run_mode="LIVE", recovery_complete=False, now=NOW)

    assert manual.status == DailyRiskDecisionStatus.MANUAL_HALT
    assert recovery.status == DailyRiskDecisionStatus.RECOVERY_NOT_COMPLETE


def test_existing_position_policies_are_explicit_and_do_not_force_liquidation() -> None:
    events = EventCollector()
    _record_closed_trade(events, -11.0)
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=10.0, DAILY_RISK_EXISTING_POSITION_POLICY="MANAGED_ONLY")
    managed = _governor(events).evaluate(run_mode="PAPER", now=NOW, is_new_entry=True)
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=10.0, DAILY_RISK_EXISTING_POSITION_POLICY="HOLD")
    hold = _governor(events).evaluate(run_mode="PAPER", now=NOW, is_new_entry=True)
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=10.0, DAILY_RISK_EXISTING_POSITION_POLICY="FLATTEN")
    flatten = _governor(events).evaluate(run_mode="PAPER", now=NOW, is_new_entry=True)

    assert managed.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert managed.allows_existing_position_management is True
    assert hold.existing_position_policy == DailyRiskExistingPositionPolicy.HOLD
    assert hold.recommended_existing_position_action == "HOLD_EXISTING_POSITIONS"
    assert flatten.existing_position_policy == DailyRiskExistingPositionPolicy.FLATTEN
    assert flatten.recommended_existing_position_action == "FLATTEN_MANUAL_REVIEW"


def test_live_fail_closed_when_state_has_no_recovery_source() -> None:
    governor = DailyRiskGovernor()

    decision = governor.evaluate(run_mode="LIVE", recovery_complete=True, now=NOW)

    assert decision.status == DailyRiskDecisionStatus.DATA_UNAVAILABLE
    assert decision.reason == "DAILY_RISK_STATE_UNRECONSTRUCTED"


def test_recovery_complete_with_reconstructed_empty_state_enables_trading() -> None:
    governor = _governor(EventCollector())

    decision = governor.evaluate(run_mode="LIVE", recovery_complete=True, now=NOW)

    assert decision.status == DailyRiskDecisionStatus.ALLOW
    assert decision.blocks_new_entries is False


def test_live_fail_closed_when_provider_read_fails() -> None:
    class _Provider:
        def get_daily_fills(self):
            raise RuntimeError("broker fill API unavailable")

    governor = DailyRiskGovernor(event_collector=EventCollector(), provider=_Provider())

    decision = governor.evaluate(run_mode="LIVE", recovery_complete=True, now=NOW)

    assert decision.status == DailyRiskDecisionStatus.DATA_UNAVAILABLE
    assert decision.reason.startswith("DATA_UNAVAILABLE:broker_fills:BROKER_FILLS_READ_FAILED")
    assert decision.blocks_new_entries is True


def test_live_fail_closed_when_storage_read_fails() -> None:
    class _Store:
        def fetch_trade_outcomes(self, run_id: str):
            raise RuntimeError("database unavailable")

    storage = SimpleNamespace(_store=_Store(), run_id="run-p10")
    governor = DailyRiskGovernor(event_collector=EventCollector(), storage_engine=storage)

    decision = governor.evaluate(run_mode="LIVE", recovery_complete=True, now=NOW)

    assert decision.status == DailyRiskDecisionStatus.DATA_UNAVAILABLE
    assert decision.reason == "DATA_UNAVAILABLE:storage:STORAGE_TRADE_OUTCOMES_READ_FAILED"
    assert decision.blocks_new_entries is True


def test_live_fail_closed_when_lifecycle_read_fails() -> None:
    class _LifecycleReader:
        def build_portfolio_state(self):
            raise RuntimeError("lifecycle unavailable")

    governor = DailyRiskGovernor(
        event_collector=EventCollector(),
        trade_lifecycle_engine=_LifecycleReader(),
    )

    decision = governor.evaluate(run_mode="LIVE", recovery_complete=True, now=NOW)

    assert decision.status == DailyRiskDecisionStatus.DATA_UNAVAILABLE
    assert decision.reason == "DATA_UNAVAILABLE:lifecycle:LIFECYCLE_READ_FAILED"
    assert decision.blocks_new_entries is True


def test_read_only_evaluation_does_not_mutate_governor_state() -> None:
    governor = _governor()

    decision = governor.evaluate(run_mode="READ_ONLY", recovery_complete=True, now=NOW)

    assert decision.status == DailyRiskDecisionStatus.READ_ONLY_EVALUATED
    assert governor.state is None
    assert governor.last_decision is None


def test_sim_and_paper_decisions_are_deterministic_for_same_state() -> None:
    events = EventCollector()
    _record_closed_trade(events, -1.0)
    governor = _governor(events)

    sim = governor.evaluate(run_mode="SIM", recovery_complete=True, now=NOW).to_dict()
    paper = governor.evaluate(run_mode="PAPER", recovery_complete=True, now=NOW).to_dict()

    assert sim["status"] == paper["status"]
    assert sim["reason"] == paper["reason"]
    assert sim["realized_pnl"] == paper["realized_pnl"]


def test_daily_reset_respects_configured_timezone_and_reset_time() -> None:
    _set_config(DAILY_RISK_TIMEZONE="UTC", DAILY_RISK_RESET_TIME_LOCAL="09:30")
    governor = _governor()

    before_reset = governor.trading_day_for(datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc))
    after_reset = governor.trading_day_for(datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc))

    assert before_reset == "2026-06-04"
    assert after_reset == "2026-06-05"


def test_windows_timezone_name_is_normalized_for_reset_logic() -> None:
    _set_config(DAILY_RISK_TIMEZONE="GMT Summer Time")

    governor = _governor()

    assert governor.timezone_name == "Europe/London"


def test_governor_decision_event_is_audited() -> None:
    events = EventCollector()
    governor = _governor(events)

    decision = governor.evaluate(run_mode="PAPER", recovery_complete=True, now=NOW)

    audit_events = events.filter_by_type("DAILY_RISK_DECISION")
    assert len(audit_events) == 1
    assert audit_events[0].payload["decision_id"] == decision.decision_id
    assert audit_events[0].payload["status"] == "ALLOW"


def test_storage_recovery_uses_persisted_trade_outcomes_when_events_absent() -> None:
    class _Store:
        def fetch_trade_outcomes(self, run_id: str):
            return [{"closed_at": NOW.isoformat(), "net_realised_pnl": -4.0}]

    storage = SimpleNamespace(_store=_Store(), run_id="run-p10")
    governor = DailyRiskGovernor(storage_engine=storage)

    decision = governor.evaluate(run_mode="PAPER", recovery_complete=True, now=NOW)

    assert decision.realized_pnl == -4.0
    assert decision.daily_trade_count == 1


def test_broker_fill_reconciliation_uses_provider_fills() -> None:
    class _Provider:
        def get_daily_fills(self):
            return [{"timestamp": NOW.isoformat(), "realized_pnl": -3.0}]

    governor = DailyRiskGovernor(provider=_Provider())

    decision = governor.evaluate(run_mode="PAPER", recovery_complete=True, now=NOW)

    assert decision.realized_pnl == -3.0
    assert decision.losing_trade_count == 1


def test_same_day_storage_and_event_losses_are_combined() -> None:
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=10.0)
    events = EventCollector()
    _record_closed_trade(events, -3.0, trade_id="event-loss")

    class _Store:
        def fetch_trade_outcomes(self, run_id: str):
            return [
                {
                    "trade_id": "stored-loss",
                    "symbol": "AAPL",
                    "closed_at": NOW.isoformat(),
                    "net_realised_pnl": -8.0,
                }
            ]

    storage = SimpleNamespace(_store=_Store(), run_id="run-p10")
    governor = DailyRiskGovernor(event_collector=events, storage_engine=storage)

    decision = governor.evaluate(run_mode="PAPER", recovery_complete=True, now=NOW)

    assert decision.realized_pnl == -11.0
    assert decision.daily_trade_count == 2
    assert decision.reason == "MAX_DAILY_LOSS_AMOUNT"


def test_duplicate_daily_history_trade_is_not_double_counted() -> None:
    events = EventCollector()
    _record_closed_trade(events, -4.0, trade_id="same-trade")

    class _Store:
        def fetch_trade_outcomes(self, run_id: str):
            return [
                {
                    "trade_id": "same-trade",
                    "symbol": "AAPL",
                    "closed_at": NOW.isoformat(),
                    "net_realised_pnl": -4.0,
                }
            ]

    storage = SimpleNamespace(_store=_Store(), run_id="run-p10")
    governor = DailyRiskGovernor(event_collector=events, storage_engine=storage)

    decision = governor.evaluate(run_mode="PAPER", recovery_complete=True, now=NOW)

    assert decision.realized_pnl == -4.0
    assert decision.daily_trade_count == 1


def test_orchestrator_gate_blocks_before_strategy_when_daily_risk_locked(monkeypatch) -> None:
    import src.core.orchestrator as orchestrator_module
    class CoreClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)
    monkeypatch.setattr(orchestrator_module, "datetime", CoreClock)
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=10.0)
    events = EventCollector()
    _record_closed_trade(events, -11.0)
    halted: list[dict[str, object]] = []
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator.daily_risk_governor = DailyRiskGovernor(event_collector=events)
    orchestrator.run_mode = RunMode.PAPER
    orchestrator.event_collector = events
    orchestrator.storage_engine = None
    orchestrator.trade_lifecycle_engine = None
    orchestrator.execution_engine = SimpleNamespace(
        provider=_P10Provider(),
        startup_recovery_complete=lambda: True,
    )
    orchestrator._ensure_cycle_id = lambda: "cycle-p10"
    orchestrator._trace_halt = lambda **payload: halted.append(payload)

    allowed = CoreOrchestrator._daily_risk_allows_new_entries(
        orchestrator,
        cycle_started_at=NOW,
    )

    assert allowed is False
    assert halted[0]["reason_code"] == "DAILY_RISK_MANAGED_ONLY"


def test_execution_backstop_blocks_force_execute_when_daily_risk_locked() -> None:
    _set_config(RUN_MODE="LIVE", DAILY_RISK_MAX_LOSS_AMOUNT=10.0)
    events = EventCollector()
    _record_closed_trade(events, -11.0)
    provider = _P10Provider()
    engine = ExecutionEngine(
        provider=provider,
        trade_registry=ActiveTradeRegistry(),
        event_collector=events,
        price_feed=DeterministicPriceFeed(),
    )

    result = engine.execute_trade(_decision(force_execute=True))

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("DAILY_RISK_MANAGED_ONLY:MAX_DAILY_LOSS_AMOUNT")
    assert provider.submitted_orders == []


def test_execution_backstop_allows_existing_position_exit_when_locked() -> None:
    _set_config(RUN_MODE="LIVE", DAILY_RISK_MAX_LOSS_AMOUNT=10.0)
    events = EventCollector()
    _record_closed_trade(events, -11.0)
    provider = _P10Provider()
    engine = ExecutionEngine(
        provider=provider,
        trade_registry=ActiveTradeRegistry(),
        event_collector=events,
        price_feed=DeterministicPriceFeed(),
    )

    result = engine.execute_trade(_decision(direction="SELL"))

    assert result.status == "Filled"
    assert len(provider.submitted_orders) == 1


# Consumer controls use the actual strict canonical/storage owners.  They do not
# supply prepared governor decisions or add a TRADE_CLOSED producer.
from test_trade_lifecycle_engine import native_lifecycle, _native_event, _apply_native


def _canonical_fill(engine, event_id, event_type, quantity, price, *,
                    root="NATIVE-ROOT", timestamp=NOW, native_id=None):
    event, identity = _native_event(event_id, event_type, quantity, price,
        native_id=native_id or (71 if event_type == "ENTRY_FILL" else 72),
        timestamp=timestamp.isoformat(), root=root)
    before = engine.get_trade(root)
    _apply_native(engine, event, identity, before.quantity_open if before else 0)
    return engine.get_trade(root)


def _native_governor(engine, storage):
    return DailyRiskGovernor(event_collector=EventCollector(), storage_engine=storage,
        trade_lifecycle_engine=engine)


def _persist_existing_outcome(storage, trade, *, timestamp=NOW, commission=0.0,
                              alias="trade_id", account="SYNTHETIC_TEST"):
    """Controlled legacy storage input derived from actual canonical fills.

    TradeOutcomeFactory owns its established gross/commission/net convention;
    this inserts into the existing table, not another outcome stream/ledger.
    """
    import json
    from dataclasses import asdict
    from src.core.trade_outcome_factory import TradeOutcomeFactory
    from src.models.data_models import ExecutionResult as ClosedExecution
    result = ClosedExecution(symbol=trade.symbol, trader_type="HISTORY", attempted=True,
        status="CLOSED", rationale="canonical consumer history fixture", direction="LONG",
        quantity=trade.quantity_closed, entry_price=trade.entry_avg_price,
        exit_price=trade.exit_avg_price, commission=commission)
    outcome = TradeOutcomeFactory.from_execution_result(result, trade.strategy_name, "HISTORY")
    payload = asdict(outcome)
    payload.update({alias: trade.lifecycle_trade_id, "account": account})
    storage._store.insert_trade_outcomes([dict(payload,
        trade_outcome_id="history-" + trade.lifecycle_trade_id + "-" + alias,
        run_id=storage.run_id, cycle_id=None, closed_at=timestamp.isoformat(),
        payload_json=json.dumps(payload), created_at=timestamp.isoformat())])
    return outcome


@pytest.mark.parametrize("loss,limit,blocked", [(0.19, 0.20, False), (0.20, 0.20, True), (0.21, 0.20, True)])
def test_canonical_daily_loss_preserves_existing_inclusive_comparator(native_lifecycle, loss, limit, blocked):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=limit)
    _canonical_fill(engine, "entry", "ENTRY_FILL", 1, 10.53)
    _canonical_fill(engine, "exit", "STOP_EXIT", 1, 10.53-loss)
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -loss
    assert decision.daily_trade_count == decision.losing_trade_count == 1
    assert decision.blocks_new_entries is blocked
    assert engine.get_trade("NATIVE-ROOT").target_price is None


def test_canonical_partial_realized_loss_reaches_daily_gate_before_flat(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.20)
    _canonical_fill(engine, "entry", "ENTRY_FILL", 2, 10.53)
    trade = _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.28)
    governor = _native_governor(engine, storage)
    partial = governor.evaluate(run_mode="PAPER", now=NOW)
    assert trade.quantity_open == 1 and trade.target_price is None
    assert partial.realized_pnl == -.25 and partial.blocks_new_entries
    assert partial.daily_trade_count == partial.losing_trade_count == partial.consecutive_losses == 0
    assert partial.allows_existing_position_management
    _canonical_fill(engine, "final", "EXIT_FILL", 1, 10.43)
    final = governor.evaluate(run_mode="PAPER", now=NOW)
    assert final.realized_pnl == -.35 and final.daily_trade_count == final.losing_trade_count == 1
    assert final.consecutive_losses == 1
    for _ in range(2):
        repeat = governor.evaluate(run_mode="PAPER", now=NOW)
        assert repeat.realized_pnl == -.35 and repeat.daily_trade_count == 1


def test_canonical_partial_wins_and_final_outcome_counts_remain_distinct(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config()
    _canonical_fill(engine, "entry", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "win", "PARTIAL_EXIT", 1, 10.83)
    partial = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert partial.realized_pnl == .30 and partial.daily_trade_count == 0
    _canonical_fill(engine, "loss", "EXIT_FILL", 1, 10.33)
    final = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert final.realized_pnl == .10 and final.daily_trade_count == 1
    assert final.losing_trade_count == final.consecutive_losses == 0


def test_required_pending_and_uncertain_accounting_block_entries_even_when_optional_governor_disabled(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_GOVERNOR_ENABLED=False)
    _, identity = _native_event("pending", "ENTRY_FILL", 1, 10.53)
    engine.require_native_feedback("pending", identity)
    governor = _native_governor(engine, storage)
    for mode in ("PAPER", "LIVE"):
        decision = governor.evaluate(run_mode=mode, now=NOW)
        assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
        assert decision.blocks_new_entries and decision.allows_existing_position_management
        assert "NATIVE_FEEDBACK_PENDING" in decision.reason
    engine.mark_native_feedback_uncertain("pending", "controlled persistence uncertainty")
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert "NATIVE_FEEDBACK_UNCERTAIN" in decision.reason


def test_canonical_and_existing_stored_outcomes_keep_distinct_native_loss(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.50)
    _canonical_fill(engine, "a-in", "ENTRY_FILL", 1, 10.53, root="A")
    trade_a = _canonical_fill(engine, "a-out", "STOP_EXIT", 1, 10.28, root="A")
    _persist_existing_outcome(storage, trade_a, commission=.02, alias="lifecycle_trade_id")
    _canonical_fill(engine, "b-in", "ENTRY_FILL", 1, 10.53, root="B")
    _canonical_fill(engine, "b-out", "STOP_EXIT", 1, 10.28, root="B")
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.52  # A net -.27 once, plus distinct B gross -.25.
    assert decision.daily_trade_count == decision.losing_trade_count == 2
    assert decision.reason == "MAX_DAILY_LOSS_AMOUNT"


def test_canonical_duplicate_alias_outcomes_do_not_double_count(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config()
    _canonical_fill(engine, "in", "ENTRY_FILL", 1, 10.53)
    trade = _canonical_fill(engine, "out", "EXIT_FILL", 1, 10.28)
    _persist_existing_outcome(storage, trade, alias="trade_id")
    _persist_existing_outcome(storage, trade, alias="root_order_id")
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.25 and decision.daily_trade_count == 1


def test_canonical_wrong_account_overlap_is_unavailable_not_another_trade(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config()
    _canonical_fill(engine, "in", "ENTRY_FILL", 1, 10.53)
    trade = _canonical_fill(engine, "out", "EXIT_FILL", 1, 10.28)
    _persist_existing_outcome(storage, trade, account="OTHER_ACCOUNT")
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert decision.blocks_new_entries and "OWNERSHIP_CONFLICT" in decision.reason


def test_canonical_partial_and_final_day_attribution_uses_execution_stamps(native_lifecycle):
    from datetime import timedelta
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_TIMEZONE="UTC", DAILY_RISK_RESET_TIME_LOCAL="09:30", DAILY_RISK_MAX_LOSS_AMOUNT=.20)
    before = NOW.replace(hour=9, minute=29)
    after = NOW.replace(hour=9, minute=31)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53, timestamp=before-timedelta(minutes=1))
    _canonical_fill(engine, "early", "PARTIAL_EXIT", 1, 10.43, timestamp=before)
    _canonical_fill(engine, "late", "EXIT_FILL", 1, 10.38, timestamp=after)
    governor = _native_governor(engine, storage)
    current = governor.evaluate(run_mode="PAPER", now=after)
    assert current.realized_pnl == -.15 and current.daily_trade_count == current.losing_trade_count == 1
    assert not current.blocks_new_entries
    previous = governor.evaluate(run_mode="PAPER", now=before)
    assert previous.realized_pnl == -.10 and previous.daily_trade_count == 0


def test_late_arriving_exit_does_not_move_terminal_count_to_arrival_or_older_day(native_lifecycle):
    from datetime import timedelta
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_TIMEZONE="UTC")
    yesterday = NOW-timedelta(days=1)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53, timestamp=yesterday)
    _canonical_fill(engine, "later-exec-first-arrival", "PARTIAL_EXIT", 1, 10.43, timestamp=NOW)
    _canonical_fill(engine, "older-exec-late-arrival", "EXIT_FILL", 1, 10.38, timestamp=yesterday+timedelta(minutes=1))
    current = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert current.realized_pnl == -.10 and current.daily_trade_count == 1
    old = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=yesterday+timedelta(hours=1))
    assert old.realized_pnl == -.15 and old.daily_trade_count == 0


def test_multi_day_whole_trade_net_adjustment_does_not_invent_fee_allocation(native_lifecycle):
    from datetime import timedelta
    engine, storage = native_lifecycle
    _set_config()
    yesterday = NOW-timedelta(days=1)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53, timestamp=yesterday)
    _canonical_fill(engine, "a", "PARTIAL_EXIT", 1, 10.43, timestamp=yesterday)
    trade = _canonical_fill(engine, "b", "EXIT_FILL", 1, 10.38, timestamp=NOW)
    _persist_existing_outcome(storage, trade, commission=.02)
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert "NET_DAY_ATTRIBUTION_UNAVAILABLE" in decision.reason


def test_current_reopened_root_suppresses_old_terminal_counts_until_final_close(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config()
    _canonical_fill(engine, "partial-entry", "ENTRY_FILL", 1, 10.53)
    _canonical_fill(engine, "first-stop", "STOP_EXIT", 1, 10.43)
    _canonical_fill(engine, "remaining-existing-buy", "ENTRY_FILL", 1, 10.63)
    open_decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert open_decision.realized_pnl == -.10 and open_decision.daily_trade_count == 0
    _canonical_fill(engine, "final-stop", "STOP_EXIT", 1, 10.43, native_id=73)
    final = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert final.realized_pnl == -.30 and final.daily_trade_count == final.losing_trade_count == 1


def test_unidentified_realized_aggregate_is_not_native_dedupe_evidence():
    _set_config()
    decision = _governor(lifecycle=_Lifecycle(realized=-.25)).evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert "IDENTITY_UNAVAILABLE" in decision.reason


def test_paper_read_failure_keeps_management_available_and_entries_closed():
    class Broken:
        def fetch_trade_outcomes(self, run_id):
            raise OSError("controlled read failure")
    storage = SimpleNamespace(_store=Broken(), run_id="current")
    decision = DailyRiskGovernor(storage_engine=storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert decision.blocks_new_entries and decision.allows_existing_position_management


def _actual_canonical_execution_history(engine, event_id, *, commission=0.0):
    """Raw provider-history facts bound to a committed real canonical event."""
    event = next(row for row in engine.native_feedback_snapshot()["events"] if row["event_id"] == event_id)
    identity = event["metadata"]["native_identity"]
    gross = event["metadata"]["realized_increment"]
    return dict(execution_id=event["execution_id"], trade_id=identity["root_order_id"],
        account=identity["account"], strategy_name=identity["strategy"], symbol=identity["symbol"],
        timestamp=event["timestamp"], quantity=event["quantity"], price=event["price"],
        order_id=event["order_id"], side="SELL", client_id=identity["client_id"],
        connection_epoch=identity["connection_epoch"], con_id=identity.get("con_id"), gross_realized_pnl=gross,
        net_realized_pnl=round(gross-commission, 2), commission=commission)


def test_native_partial_execution_history_dedupes_without_claiming_trade_closed(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config()
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.43)
    row = _actual_canonical_execution_history(engine, "partial", commission=.02)
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [SimpleNamespace(**row), SimpleNamespace(**row)])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.12
    assert decision.daily_trade_count == decision.losing_trade_count == 0
    assert not decision.blocks_new_entries


@pytest.mark.parametrize("field,value,reason", [
    ("trade_id", "WRONG", "ROOT_CONFLICT"),
    ("side", "BUY", "SIDE_CONFLICT"),
    ("quantity", 2, "QUANTITY_CONFLICT"),
    ("price", 10.44, "PRICE_CONFLICT"),
    ("order_id", "999", "ORDER_CONFLICT"),
    ("client_id", 999, "CLIENT_CONFLICT"),
    ("connection_epoch", 99, "EPOCH_CONFLICT"),
    ("con_id", 456, "SECURITY_CONFLICT"),
    ("symbol", "WRONG", "SYMBOL_CONFLICT"),
])
def test_native_execution_history_contradictions_fail_closed(native_lifecycle, field, value, reason):
    engine, storage = native_lifecycle
    _set_config()
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.43)
    row = _actual_canonical_execution_history(engine, "partial")
    row[field] = value
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [row])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert decision.realized_pnl == -.10  # Known committed gross is not replaced by zero.
    assert reason in decision.reason and decision.allows_existing_position_management


def test_native_per_execution_net_history_preserves_day_and_final_loss_count(native_lifecycle):
    from datetime import timedelta
    engine, storage = native_lifecycle
    _set_config()
    previous = NOW-timedelta(days=1)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53, timestamp=previous)
    _canonical_fill(engine, "old", "PARTIAL_EXIT", 1, 10.63, timestamp=previous)
    _canonical_fill(engine, "today", "EXIT_FILL", 1, 10.48, timestamp=NOW)
    # Gross whole-trade +.05 becomes net -.05 after known prior-day fees.
    old = _actual_canonical_execution_history(engine, "old", commission=.10)
    today = _actual_canonical_execution_history(engine, "today")
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [old, today, old])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.05 and decision.daily_trade_count == 1
    assert decision.losing_trade_count == decision.consecutive_losses == 1
    old_day = governor.evaluate(run_mode="PAPER", now=previous)
    assert old_day.realized_pnl == 0.0 and old_day.daily_trade_count == 0


def test_disabled_optional_governor_preserves_legacy_no_required_accounting_semantics():
    _set_config(DAILY_RISK_GOVERNOR_ENABLED=False)
    decision = _governor(lifecycle=_Lifecycle(realized=-.25)).evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.ALLOW
    assert decision.reason == "DAILY_RISK_GOVERNOR_DISABLED"


def test_native_fill_identity_cannot_alias_an_intake_event_id(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config()
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.43)
    row = _actual_canonical_execution_history(engine, "partial")
    row["execution_id"] = "partial"  # Intake/event identity is not execution identity.
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [row])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert "FILL_IDENTITY_CONFLICT" in decision.reason


def test_broker_object_execution_alias_can_resolve_root_without_weak_child_order_alias(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config()
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.43)
    row = _actual_canonical_execution_history(engine, "partial")
    row.pop("trade_id")
    row["execId"] = row.pop("execution_id")
    row["time"] = row.pop("timestamp")
    row["client_order_id"] = "CHILD-REQUEST-IS-NOT-THE-ROOT"
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [SimpleNamespace(**row)])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.10 and decision.daily_trade_count == 0
    assert not decision.blocks_new_entries


def test_same_day_net_outcome_and_gross_execution_overlap_preserve_net_precedence(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config()
    _canonical_fill(engine, "in", "ENTRY_FILL", 1, 10.53)
    trade = _canonical_fill(engine, "out", "EXIT_FILL", 1, 10.28)
    _persist_existing_outcome(storage, trade, commission=.02)
    gross = _actual_canonical_execution_history(engine, "out")
    gross.pop("net_realized_pnl")
    gross.pop("commission")
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [gross])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.27 and decision.daily_trade_count == 1
    assert decision.losing_trade_count == 1


@pytest.mark.parametrize("fault", ["missing_time", "invalid_time", "unknown_pnl"])
def test_required_history_unavailability_never_substitutes_now_or_zero(native_lifecycle, fault):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_GOVERNOR_ENABLED=False)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.43)
    row = _actual_canonical_execution_history(engine, "partial")
    if fault == "missing_time":
        row.pop("timestamp")
    elif fault == "invalid_time":
        row["timestamp"] = "not-an-authoritative-time"
    else:
        row["net_realized_pnl"] = row["gross_realized_pnl"] = None
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [row])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert decision.realized_pnl == -.10 and decision.blocks_new_entries
    assert decision.allows_existing_position_management
    assert "UNAVAILABLE" in decision.reason or "INVALID" in decision.reason


def test_required_feedback_does_not_override_explicit_manual_halt_or_readonly_contract(native_lifecycle):
    engine, storage = native_lifecycle
    _, identity = _native_event("pending", "ENTRY_FILL", 1, 10.53)
    engine.require_native_feedback("pending", identity)
    _set_config(DAILY_RISK_MANUAL_HALT=True)
    governor = _native_governor(engine, storage)
    halted = governor.evaluate(run_mode="PAPER", now=NOW)
    assert halted.status == DailyRiskDecisionStatus.MANUAL_HALT and halted.blocks_new_entries
    _set_config(DAILY_RISK_MANUAL_HALT=False)
    readonly = _native_governor(engine, storage)
    decision = readonly.evaluate(run_mode="READ_ONLY", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.READ_ONLY_EVALUATED
    assert readonly.state is None and readonly.last_decision is None


def test_complete_execution_net_cannot_be_overwritten_by_conflicting_net_summary(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.28)
    _canonical_fill(engine, "in", "ENTRY_FILL", 1, 10.53)
    trade = _canonical_fill(engine, "out", "EXIT_FILL", 1, 10.28)
    _persist_existing_outcome(storage, trade, commission=.02)  # Whole-trade NET -.27.
    execution = _actual_canonical_execution_history(engine, "out", commission=.05)  # Complete NET -.30.
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [execution])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.blocks_new_entries, decision
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert "NATIVE_NET_SUMMARY_CONFLICT" in decision.reason
    assert decision.allows_existing_position_management


def test_complete_net_coverage_uses_unique_exit_identities_and_detects_summary_conflict(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.28)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "first", "PARTIAL_EXIT", 1, 10.43)
    trade = _canonical_fill(engine, "last", "EXIT_FILL", 1, 10.38)
    _persist_existing_outcome(storage, trade, commission=.02)
    first = _actual_canonical_execution_history(engine, "first", commission=.02)
    last = _actual_canonical_execution_history(engine, "last", commission=.03)
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [last, first, first, last])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert "NATIVE_NET_SUMMARY_CONFLICT" in decision.reason
    assert decision.blocks_new_entries and decision.allows_existing_position_management


def test_matching_complete_net_execution_and_summary_results_remain_usable(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.28)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "first", "PARTIAL_EXIT", 1, 10.43)
    trade = _canonical_fill(engine, "last", "EXIT_FILL", 1, 10.38)
    _persist_existing_outcome(storage, trade, commission=.05)
    first = _actual_canonical_execution_history(engine, "first", commission=.02)
    last = _actual_canonical_execution_history(engine, "last", commission=.03)
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [last, first, first])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.30 and decision.daily_trade_count == 1
    assert decision.reason == "MAX_DAILY_LOSS_AMOUNT"


def test_partial_net_coverage_duplicates_do_not_invent_complete_commission_allocation(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.33)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "first", "PARTIAL_EXIT", 1, 10.43)
    trade = _canonical_fill(engine, "last", "EXIT_FILL", 1, 10.38)
    _persist_existing_outcome(storage, trade, commission=.07)
    first = _actual_canonical_execution_history(engine, "first", commission=.05)
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [first, first])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.32 and decision.daily_trade_count == 1
    assert not decision.blocks_new_entries


def test_complete_zero_adjustment_net_coverage_still_rejects_conflicting_summary_when_limits_disabled(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_GOVERNOR_ENABLED=False)
    _canonical_fill(engine, "in", "ENTRY_FILL", 1, 10.53)
    trade = _canonical_fill(engine, "out", "EXIT_FILL", 1, 10.28)
    _persist_existing_outcome(storage, trade, commission=.02)
    execution = _actual_canonical_execution_history(engine, "out", commission=0)
    governor = _native_governor(engine, storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [execution])
    decision = governor.evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert "NATIVE_NET_SUMMARY_CONFLICT" in decision.reason
    assert decision.blocks_new_entries


def test_strict_native_open_position_without_requested_unrealized_mark_fails_closed(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True, DAILY_RISK_MAX_LOSS_AMOUNT=.20)
    trade = _canonical_fill(engine, "in", "ENTRY_FILL", 1, 10.53)
    assert trade.quantity_open == 1 and trade.last_mark_price is None
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.blocks_new_entries, decision
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert "NATIVE_UNREALIZED_VALUATION_UNAVAILABLE" in decision.reason
    assert decision.allows_existing_position_management


@pytest.mark.parametrize("mark", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_requested_native_mark_preserves_known_partial_realized_loss(native_lifecycle, mark):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True, DAILY_RISK_MAX_LOSS_AMOUNT=1.0)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    trade = _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.28)
    engine.apply_mark_price(trade_id=trade.lifecycle_trade_id, price=mark)
    assert engine.native_feedback_snapshot()["native_unrealized_marks_present"] is False
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert "NATIVE_UNREALIZED_VALUATION_UNAVAILABLE" in decision.reason
    assert decision.realized_pnl == -.25 and decision.daily_trade_count == 0
    assert decision.allows_existing_position_management


@pytest.mark.parametrize("mark", [None, float("nan")])
def test_nonrequired_missing_or_invalid_native_valuation_does_not_erase_realized_or_veto(native_lifecycle, mark):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=False, DAILY_RISK_MAX_LOSS_AMOUNT=1.0)
    _canonical_fill(engine, "in", "ENTRY_FILL", 2, 10.53)
    trade = _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.28)
    if mark is not None:
        engine.apply_mark_price(trade_id=trade.lifecycle_trade_id, price=mark)
    assert engine.native_feedback_snapshot()["native_unrealized_marks_present"] is False
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.25 and decision.daily_trade_count == 0
    assert not decision.blocks_new_entries and not decision.include_unrealized
    assert decision.reason == "DAILY_RISK_APPROVED"


@pytest.mark.parametrize("mode", ["PAPER", "LIVE"])
def test_required_native_valuation_absence_veto_precedes_optional_limit_disable(native_lifecycle, mode):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True, DAILY_RISK_GOVERNOR_ENABLED=False)
    _canonical_fill(engine, "in", "ENTRY_FILL", 1, 10.53)
    snapshot = engine.native_feedback_snapshot()
    assert snapshot["available"] and snapshot["native_unrealized_marks_present"] is False
    decision = _native_governor(engine, storage).evaluate(run_mode=mode, now=NOW)
    assert decision.status == DailyRiskDecisionStatus.MANAGED_ONLY
    assert decision.blocks_new_entries and "NATIVE_UNREALIZED_VALUATION_UNAVAILABLE" in decision.reason
    assert decision.allows_existing_position_management


def test_flat_strict_native_root_does_not_need_an_unrealized_mark(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True, DAILY_RISK_MAX_LOSS_AMOUNT=1.0)
    _canonical_fill(engine, "in", "ENTRY_FILL", 1, 10.53)
    trade = _canonical_fill(engine, "out", "STOP_EXIT", 1, 10.28)
    assert trade.quantity_open == 0 and trade.last_mark_price is None
    assert engine.native_feedback_snapshot()["native_unrealized_marks_present"] is True
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.realized_pnl == -.25 and decision.daily_trade_count == 1
    assert not decision.blocks_new_entries


def test_unrealized_mark_absence_barrier_does_not_enroll_legacy_roots(native_lifecycle):
    from src.core.engines.trade_lifecycle_engine import LifecycleEvent
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True)
    event = LifecycleEvent("legacy-entry", "LEGACY-ROOT", "LEGACY", "LONG", "ENTRY_FILL", 1, 10.53,
        NOW.isoformat(), order_id="legacy-order", execution_id="legacy-exec")
    trade = engine.apply_event(event, strategy_name="legacy_strategy", stop_price=10.0)
    snapshot = engine.native_feedback_snapshot()
    assert not snapshot["required"] and snapshot["native_unrealized_marks_present"] is True
    assert trade.last_mark_price is None
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert not decision.blocks_new_entries


def _qualified_native_mark(engine, *, now=NOW, price=10.32, market_time=None):
    from threading import Event
    from src.core.engines.trade_lifecycle_engine import NativeValuationObservation
    required, = engine.native_valuation_requirements()
    observation = NativeValuationObservation(**{key: value for key, value in required.items()
        if key != "native_order_id"}, price=price,
        market_timestamp=(market_time or now).isoformat(),
        acquisition_completed_at=now.isoformat(), request_id=91,
        source="IBKR", timestamp_kind="LAST_TRADE", market_data_type="LIVE", completed=True)
    client = SimpleNamespace(client_id=required["client_id"],
        _position_connection_epoch=required["connection_epoch"],
        isConnected=lambda: True, _stop_event=Event())
    engine.apply_native_valuation(observation, now=now, max_age_seconds=15, source_client=client)
    return observation


@pytest.mark.parametrize("price,blocked", [(10.34, False), (10.33, True), (10.32, True)])
def test_qualified_native_unrealized_loss_obeys_existing_inclusive_daily_comparator(native_lifecycle, price, blocked):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True, DAILY_RISK_MAX_LOSS_AMOUNT=.20)
    _canonical_fill(engine, "entry", "ENTRY_FILL", 1, 10.53)
    _qualified_native_mark(engine, price=price)
    governor = _native_governor(engine, storage)
    for _ in range(2):
        decision = governor.evaluate(run_mode="PAPER", now=NOW)
        assert governor.state.recovered and governor.state.recovery_error is None
        assert decision.realized_pnl == 0
        assert decision.unrealized_pnl == round(price - 10.53, 2)
        assert decision.daily_trade_count == decision.losing_trade_count == 0
        assert decision.blocks_new_entries is blocked
        assert decision.allows_existing_position_management
    assert engine.get_trade("NATIVE-ROOT").target_price is None
    assert len(engine.native_feedback_snapshot()["events"]) == 1


@pytest.mark.parametrize("age,blocked", [(0, False), (15, False), (15.000001, True), (-.000001, True)])
def test_native_valuation_age_is_rechecked_at_daily_admission_without_renewal(native_lifecycle, age, blocked):
    from datetime import timedelta
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True, DAILY_RISK_MAX_LOSS_AMOUNT=1.0,
        IBKR_SNAPSHOT_MAX_AGE_SECONDS=15)
    _canonical_fill(engine, "entry", "ENTRY_FILL", 1, 10.53)
    _qualified_native_mark(engine, price=10.43)
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW + timedelta(seconds=age))
    assert decision.blocks_new_entries is blocked
    assert decision.daily_trade_count == 0 and decision.realized_pnl == 0
    if blocked:
        assert "NATIVE_UNREALIZED_VALUATION_UNAVAILABLE" in decision.reason
    else:
        assert decision.unrealized_pnl == -.10
    mark, = engine.native_valuation_snapshot(now=NOW, max_age_seconds=15)["marks"]
    assert mark["market_timestamp"] == NOW.isoformat()


def test_legacy_hand_mark_cannot_certify_strict_native_valuation(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True)
    trade = _canonical_fill(engine, "entry", "ENTRY_FILL", 1, 10.53)
    engine.apply_mark_price(trade_id=trade.lifecycle_trade_id, price=10.43)
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.blocks_new_entries
    assert "NATIVE_UNREALIZED_VALUATION_UNAVAILABLE" in decision.reason
    assert decision.realized_pnl == 0 and decision.daily_trade_count == 0


def test_real_fill_invalidates_previous_quantity_valuation_before_daily_gate(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True, DAILY_RISK_MAX_LOSS_AMOUNT=1.0)
    _canonical_fill(engine, "entry", "ENTRY_FILL", 2, 10.53)
    _qualified_native_mark(engine, price=10.43)
    _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.28)
    governor = _native_governor(engine, storage)
    missing = governor.evaluate(run_mode="PAPER", now=NOW)
    assert missing.blocks_new_entries and missing.realized_pnl == -.25
    assert "NATIVE_UNREALIZED_VALUATION_UNAVAILABLE" in missing.reason
    assert missing.daily_trade_count == 0 and missing.allows_existing_position_management
    _qualified_native_mark(engine, price=10.43)
    refreshed = governor.evaluate(run_mode="PAPER", now=NOW)
    assert governor.state.recovered and not refreshed.blocks_new_entries
    assert refreshed.realized_pnl == -.25 and refreshed.unrealized_pnl == -.10
    assert refreshed.daily_trade_count == 0


def test_revoked_quote_does_not_reuse_previous_fresh_native_mark(native_lifecycle):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True)
    _canonical_fill(engine, "entry", "ENTRY_FILL", 1, 10.53)
    _qualified_native_mark(engine, price=10.43)
    engine.mark_native_valuation_unavailable("NATIVE-ROOT", "EXTERNAL_QUOTE_MISSING")
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.blocks_new_entries and "EXTERNAL_QUOTE_MISSING" in decision.reason
    assert decision.realized_pnl == 0 and decision.daily_trade_count == 0


def test_uncertain_mark_commit_preserves_real_fill_and_realized_daily_risk(native_lifecycle, monkeypatch):
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True, DAILY_RISK_MAX_LOSS_AMOUNT=1.0)
    _canonical_fill(engine, "entry", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.28)
    persist = storage.persist_native_lifecycle_feedback
    def commit_then_lose_ack(*args, **kwargs):
        persist(*args, **kwargs)
        raise OSError("synthetic native mark acknowledgement lost")
    monkeypatch.setattr(storage, "persist_native_lifecycle_feedback", commit_then_lose_ack)
    with pytest.raises(OSError, match="acknowledgement lost"):
        _qualified_native_mark(engine, price=10.43)
    governor = _native_governor(engine, storage)
    uncertain = governor.evaluate(run_mode="PAPER", now=NOW)
    assert uncertain.blocks_new_entries and uncertain.realized_pnl == -.25
    assert uncertain.daily_trade_count == 0 and uncertain.allows_existing_position_management
    assert engine.native_feedback_snapshot()["available"]
    monkeypatch.setattr(storage, "persist_native_lifecycle_feedback", persist)
    _canonical_fill(engine, "final", "STOP_EXIT", 1, 10.28)
    final = governor.evaluate(run_mode="PAPER", now=NOW)
    assert final.realized_pnl == -.50 and final.daily_trade_count == final.losing_trade_count == 1
    assert final.blocks_new_entries and "NATIVE_UNREALIZED_VALUATION_UNAVAILABLE" in final.reason
    assert engine.get_trade("NATIVE-ROOT").quantity_open == 0
    assert engine.native_feedback_snapshot()["available"]
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=False, DAILY_RISK_MAX_LOSS_AMOUNT=1.0)
    excluded = governor.evaluate(run_mode="PAPER", now=NOW)
    assert excluded.realized_pnl == -.50 and excluded.daily_trade_count == 1
    assert not excluded.blocks_new_entries


def test_invalid_legacy_valuation_cannot_erase_committed_native_partial_loss(native_lifecycle):
    from src.core.engines.trade_lifecycle_engine import LifecycleEvent
    engine, storage = native_lifecycle
    _set_config(DAILY_RISK_INCLUDE_UNREALIZED=True, DAILY_RISK_MAX_LOSS_AMOUNT=1.0)
    _canonical_fill(engine, "entry", "ENTRY_FILL", 2, 10.53)
    _canonical_fill(engine, "partial", "PARTIAL_EXIT", 1, 10.28)
    _qualified_native_mark(engine, price=10.43)
    legacy = LifecycleEvent("legacy-entry", "LEGACY-ROOT", "LEGACY", "LONG", "ENTRY_FILL", 1, 10.53,
        NOW.isoformat(), order_id="legacy-order", execution_id="legacy-exec")
    engine.apply_event(legacy, strategy_name="legacy_strategy", stop_price=10.0)
    engine.apply_mark_price(trade_id="LEGACY-ROOT", price=float("nan"))
    decision = _native_governor(engine, storage).evaluate(run_mode="PAPER", now=NOW)
    assert decision.blocks_new_entries and decision.allows_existing_position_management
    assert decision.realized_pnl == -.25
    assert decision.daily_trade_count == decision.losing_trade_count == 0
    assert "NATIVE_UNREALIZED_VALUATION_UNAVAILABLE" in decision.reason


# These consumer controls use actual strict financial fills, native fee callbacks
# and SQLite. The currency result is a typed component input; the joined Core
# scenario separately exercises the actual request/End owner.
from test_trade_lifecycle_engine import FEE_NOW, _native_fee_case, _native_fee_observation


def _commit_native_fees(h):
    return h.engine.apply_native_roundtrip_fees(_native_fee_observation(h),
        source_client=h.client, now=FEE_NOW, max_age_seconds=15,
        trading_day_for=h.trading_day_for)


@pytest.mark.parametrize('limit,blocked', [(.27, True), (.28, True), (.29, False)])
def test_complete_positive_native_fee_net_preserves_inclusive_limit_and_one_trade(
        native_lifecycle, monkeypatch, limit, blocked):
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=limit)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    before = h.engine._trade_snapshot_payload(h.engine.get_trade('NATIVE-ROOT'))
    _commit_native_fees(h)
    governor = _native_governor(h.engine, h.storage)
    for _ in range(2):
        decision = governor.evaluate(run_mode='PAPER', now=FEE_NOW)
        assert governor.state.recovered
        assert decision.realized_pnl == -.28 and decision.unrealized_pnl == 0
        assert decision.daily_trade_count == decision.losing_trade_count == decision.consecutive_losses == 1
        assert decision.blocks_new_entries is blocked
        assert decision.source_counts['lifecycle'] == 1
        assert decision.allows_existing_position_management
    after = h.engine._trade_snapshot_payload(h.engine.get_trade('NATIVE-ROOT'))
    assert {key: value for key, value in after.items() if key not in {'created_at', 'updated_at'}} == {
        key: value for key, value in before.items() if key not in {'created_at', 'updated_at'}}
    assert len(h.engine.native_feedback_snapshot()['events']) == 2
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_unenrolled_fee_source_keeps_existing_gross_convention_without_certifying_zero(
        native_lifecycle, monkeypatch):
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.26)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    # A source report is not higher-owner enrollment or a NET certificate.
    assert not h.engine.native_fee_feedback_snapshot(now=FEE_NOW, max_age_seconds=15)['required']
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.realized_pnl == -.25 and decision.daily_trade_count == 1
    assert not decision.blocks_new_entries
    assert len(h.storage.fetch_trade_lifecycle_events()) == 2


def test_committed_fee_is_static_not_an_expiring_quote(native_lifecycle, monkeypatch):
    from datetime import timedelta
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=1.)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    _commit_native_fees(h)
    governor = _native_governor(h.engine, h.storage)
    later = FEE_NOW + timedelta(seconds=30)
    decision = governor.evaluate(run_mode='PAPER', now=later)
    assert governor.state.recovered and not decision.blocks_new_entries
    assert decision.realized_pnl == -.28 and decision.daily_trade_count == 1
    assert h.engine.native_fee_feedback_snapshot(now=later, max_age_seconds=15)['available']
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_matching_legacy_and_execution_net_do_not_deduct_canonical_fees_twice(native_lifecycle, monkeypatch):
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.29)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    _commit_native_fees(h)
    trade = h.engine.get_trade('NATIVE-ROOT')
    _persist_existing_outcome(h.storage, trade,
        timestamp=FEE_NOW - timedelta(seconds=40), commission=.03)
    row = _actual_canonical_execution_history(h.engine, 'fee-exit', commission=.03)
    governor = _native_governor(h.engine, h.storage)
    governor.provider = SimpleNamespace(get_daily_fills=lambda: [row, row])
    decision = governor.evaluate(run_mode='PAPER', now=FEE_NOW)
    assert governor.state.recovered and not decision.blocks_new_entries
    assert decision.realized_pnl == -.28 and decision.daily_trade_count == 1
    assert h.engine.get_trade('NATIVE-ROOT').gross_realized_pnl == pytest.approx(-.25)


@pytest.mark.parametrize('history_kind', ['summary', 'complete_execution'])
def test_conflicting_full_net_preserves_known_canonical_fee_net_and_veto(
        native_lifecycle, monkeypatch, history_kind):
    from datetime import timedelta
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.275)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    _commit_native_fees(h)
    governor = _native_governor(h.engine, h.storage)
    if history_kind == 'summary':
        _persist_existing_outcome(h.storage, h.engine.get_trade('NATIVE-ROOT'),
            timestamp=FEE_NOW-timedelta(seconds=40), commission=.02)
    else:
        row = _actual_canonical_execution_history(h.engine, 'fee-exit', commission=.02)
        governor.provider = SimpleNamespace(get_daily_fills=lambda: [row])
    decision = governor.evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.blocks_new_entries and not governor.state.recovered
    assert decision.realized_pnl == -.28 and decision.daily_trade_count == 1
    assert 'CONFLICT' in decision.reason
    assert decision.allows_existing_position_management


@pytest.mark.parametrize('failure', ['before_write', 'lost_ack'])
@pytest.mark.parametrize('enabled', [True, False])
def test_selected_fee_write_uncertainty_blocks_even_optional_governor_off(
        native_lifecycle, monkeypatch, failure, enabled):
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.26, DAILY_RISK_GOVERNOR_ENABLED=enabled)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    writer = h.storage.persist_native_lifecycle_feedback
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(args[1]['event_id'])
        if failure == 'lost_ack':
            writer(*args, **kwargs)
        raise OSError('FEE_WRITE_UNKNOWN')
    monkeypatch.setattr(h.storage, 'persist_native_lifecycle_feedback', interrupted)
    with pytest.raises(OSError, match='FEE_WRITE_UNKNOWN'):
        _commit_native_fees(h)
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.blocks_new_entries and decision.realized_pnl == -.25
    assert decision.daily_trade_count == 1 and decision.allows_existing_position_management
    assert 'NATIVE_FEE_FEEDBACK_UNAVAILABLE' in decision.reason
    assert h.engine.native_feedback_snapshot()['available']
    monkeypatch.setattr(h.storage, 'persist_native_lifecycle_feedback', writer)
    with pytest.raises(RuntimeError, match='NO_RETRY'):
        _commit_native_fees(h)
    assert len(calls) == 1


def test_fee_source_conflict_keeps_known_paid_charges_while_entries_close(native_lifecycle, monkeypatch):
    from ibapi.commission_report import CommissionReport
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.29)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    _commit_native_fees(h)
    report = CommissionReport()
    report.execId, report.commission, report.currency = 'EXEC-fee-exit', .04, 'USD'
    h.client.commissionReport(report)
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.realized_pnl == -.28 and decision.daily_trade_count == 1
    assert decision.blocks_new_entries and 'NATIVE_FEE_FEEDBACK_UNAVAILABLE' in decision.reason
    assert h.engine.native_feedback_snapshot()['available']
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_financial_reopen_keeps_covered_fees_without_blocking_the_factual_fill(native_lifecycle, monkeypatch):
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.29)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    _commit_native_fees(h)
    event, identity = _native_event('fee-reopen', 'ENTRY_FILL', 1, 10.53,
        native_id=71, timestamp=FEE_NOW.isoformat())
    identity['connection_epoch'] = h.client._position_connection_epoch
    trade = _apply_native(h.engine, event, identity, 0)
    assert trade.quantity_open == 1 and h.engine.native_feedback_snapshot()['available']
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.realized_pnl == -.28 and decision.daily_trade_count == 0
    assert decision.blocks_new_entries and 'NATIVE_FEE_FEEDBACK_UNAVAILABLE' in decision.reason
    assert len(h.storage.fetch_trade_lifecycle_events()) == 4


def test_another_pending_financial_root_does_not_erase_known_fee_charges(native_lifecycle, monkeypatch):
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.29)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    _commit_native_fees(h)
    _, identity = _native_event('other-pending', 'ENTRY_FILL', 1, 10.53, root='OTHER-ROOT', native_id=74)
    identity['connection_epoch'] = h.client._position_connection_epoch
    h.engine.require_native_feedback('OTHER-PENDING', identity)
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.blocks_new_entries and decision.realized_pnl == -.28
    assert 'NATIVE_FEEDBACK_PENDING' in decision.reason


def test_committed_fee_does_not_charge_the_following_trading_day(native_lifecycle, monkeypatch):
    from datetime import timedelta
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.01)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    _commit_native_fees(h)
    decision = _native_governor(h.engine, h.storage).evaluate(
        run_mode='PAPER', now=FEE_NOW+timedelta(days=1))
    assert decision.realized_pnl == 0 and decision.daily_trade_count == 0
    assert not decision.blocks_new_entries


@pytest.mark.parametrize('fees,report_currencies', [
    ((None, .02), ('USD', 'USD')),
    ((0, .02), ('USD', 'USD')),
    ((-.01, .02), ('USD', 'USD')),
    ((.01, .02), ('EUR', 'USD')),
])
def test_ineligible_fee_reports_keep_pre_enrollment_gross_without_invented_net(
        native_lifecycle, monkeypatch, fees, report_currencies):
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.26)
    h = _native_fee_case(native_lifecycle, monkeypatch, fees=fees, report_currencies=report_currencies)
    views = h.client.cached_native_execution_fees(71)+h.client.cached_native_execution_fees(72)
    assert any(row['report_status'] != 'BOUND_API_REPORT' for row in views)
    assert all(row['net_status'] == 'UNAVAILABLE_FOR_NET' for row in views)
    assert not h.engine.native_fee_feedback_snapshot(now=FEE_NOW, max_age_seconds=15)['required']
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert not decision.blocks_new_entries and decision.realized_pnl == -.25
    assert decision.daily_trade_count == 1
    assert len(h.storage.fetch_trade_lifecycle_events()) == 2


def test_actual_late_fee_callbacks_use_fill_day_not_receipt_day(native_lifecycle, monkeypatch):
    from dataclasses import replace
    from ibapi.commission_report import CommissionReport
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=.01)
    h = _native_fee_case(native_lifecycle, monkeypatch, fees=(None, None))
    later = FEE_NOW + timedelta(days=1)
    class LateFeeClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return later if tz is None else later.astimezone(tz)
    monkeypatch.setattr(native_module, 'datetime', LateFeeClock)
    for execution_id, fee in [('EXEC-fee-entry', .01), ('EXEC-fee-exit', .02)]:
        report = CommissionReport()
        report.execId, report.commission, report.currency = execution_id, fee, 'USD'
        h.client.commissionReport(report)
    observed = replace(_native_fee_observation(h),
        account_currency_result=replace(h.currency, completed_at=later))
    h.engine.apply_native_roundtrip_fees(observed, source_client=h.client, now=later,
        max_age_seconds=15, trading_day_for=h.trading_day_for)
    fee_snapshot = h.engine.native_fee_feedback_snapshot(now=later, max_age_seconds=15)
    assert {row['trading_day'] for row in fee_snapshot['covered_charges']} == {'2026-10-20'}
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=later)
    assert decision.realized_pnl == 0 and decision.daily_trade_count == 0
    assert not decision.blocks_new_entries


def test_known_positive_fees_classify_small_gross_win_as_one_net_loss(native_lifecycle, monkeypatch):
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=1., DAILY_RISK_MAX_CONSECUTIVE_LOSSES=1)
    h = _native_fee_case(native_lifecycle, monkeypatch, exit_price=10.54)
    assert h.engine.get_trade('NATIVE-ROOT').gross_realized_pnl == pytest.approx(.01)
    _commit_native_fees(h)
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.realized_pnl == -.02 and decision.daily_trade_count == 1
    assert decision.losing_trade_count == decision.consecutive_losses == 1
    assert decision.blocks_new_entries and 'MAX_CONSECUTIVE_LOSSES' in decision.reason
    assert h.engine.get_trade('NATIVE-ROOT').gross_realized_pnl == pytest.approx(.01)


def test_invalid_legacy_valuation_retains_committed_native_fee_net(native_lifecycle, monkeypatch):
    from src.core.engines.trade_lifecycle_engine import LifecycleEvent
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=1., DAILY_RISK_INCLUDE_UNREALIZED=True)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    _commit_native_fees(h)
    legacy = LifecycleEvent('legacy-fee-entry', 'LEGACY-ROOT', 'LEGACY', 'LONG',
        'ENTRY_FILL', 1, 10.53, FEE_NOW.isoformat(), order_id='legacy-order', execution_id='legacy-exec')
    h.engine.apply_event(legacy, strategy_name='legacy_strategy', stop_price=10.)
    h.engine.apply_mark_price(trade_id='LEGACY-ROOT', price=float('nan'))
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.blocks_new_entries and 'NATIVE_UNREALIZED_VALUATION_UNAVAILABLE' in decision.reason
    assert decision.realized_pnl == -.28 and decision.daily_trade_count == decision.losing_trade_count == 1
    assert decision.allows_existing_position_management


def test_eligible_fee_without_canonical_writer_is_unknown_not_gross_permission(native_lifecycle, monkeypatch):
    _set_config(DAILY_RISK_GOVERNOR_ENABLED=False, DAILY_RISK_MAX_LOSS_AMOUNT=.26)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    monkeypatch.setattr(h.storage, 'persist_native_lifecycle_feedback', None)
    with pytest.raises(RuntimeError, match='NATIVE_FEE_STORAGE_REQUIRED'):
        _commit_native_fees(h)
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.blocks_new_entries
    assert decision.realized_pnl == -.25 and decision.daily_trade_count == 1
    assert 'NATIVE_FEE_FEEDBACK_UNAVAILABLE' in decision.reason
    assert h.engine.native_feedback_snapshot()['available']
    assert len(h.storage.fetch_trade_lifecycle_events()) == 2


def test_account_day_currency_conflict_retains_usd_fee_and_vetoes_eur_enrollment(
        native_lifecycle, monkeypatch):
    from test_trade_lifecycle_engine import _native_fee_second_currency_case
    _set_config(DAILY_RISK_MAX_LOSS_AMOUNT=1.)
    h = _native_fee_case(native_lifecycle, monkeypatch)
    _commit_native_fees(h)
    eur = _native_fee_second_currency_case(h, monkeypatch)
    before = h.storage.fetch_trade_lifecycle_events()
    with pytest.raises(ValueError, match='ACCOUNT_DAY_CURRENCY'):
        _commit_native_fees(eur)
    assert h.storage.fetch_trade_lifecycle_events() == before
    snapshot = h.engine.native_fee_feedback_snapshot(now=FEE_NOW, max_age_seconds=15)
    assert not snapshot['available']
    assert {row['currency'] for row in snapshot['covered_charges']} == {'USD'}
    assert {row['root_order_id'] for row in snapshot['evidence']} == {'NATIVE-ROOT'}
    assert snapshot['currency_conflicts'][0]['rejected_currency'] == 'EUR'
    decision = _native_governor(h.engine, h.storage).evaluate(run_mode='PAPER', now=FEE_NOW)
    assert decision.blocks_new_entries
    assert 'ACCOUNT_DAY_CURRENCY' in decision.reason
    # This is an unavailable legacy scalar projection, not an FX-converted NET:
    # preserve both existing gross rows and the already confirmed USD charges;
    # do not deduct the rejected EUR reports or fabricate a conversion.
    assert decision.realized_pnl == -.53 and decision.daily_trade_count == 2
    assert decision.losing_trade_count == 2
    assert h.engine.native_feedback_snapshot()['available']
    assert all(trade.quantity_open == 0 for trade in h.engine._trades.values())
    assert all(trade.gross_realized_pnl == pytest.approx(-.25) for trade in h.engine._trades.values())
