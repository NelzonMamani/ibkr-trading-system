from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


def _record_closed_trade(events: EventCollector, pnl: float, *, timestamp: datetime = NOW) -> None:
    events.record_event(
        SystemEvent(
            event_type="TRADE_CLOSED",
            source="unit_test",
            timestamp=timestamp,
            payload={
                "symbol": "AAPL",
                "trader_type": "P10_TEST",
                "strategy_name": "unit_strategy",
                "net_realised_pnl": pnl,
                "realised_pnl": pnl,
            },
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


def test_orchestrator_gate_blocks_before_strategy_when_daily_risk_locked() -> None:
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
