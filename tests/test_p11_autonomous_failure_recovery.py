from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.core.orchestrator import CoreOrchestrator
from src.execution.autonomous_recovery_authority import (
    AutonomousFailureType,
    AutonomousRecoveryAction,
    AutonomousRecoveryAuthority,
    AutonomousRecoveryStatus,
    FAILURE_CLASSIFICATIONS,
)
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import OrderSnapshot, PositionSnapshot
from src.models.data_models import RiskDecision
from src.models.execution_result import ExecutionResult
from src.sim.price_feed import DeterministicPriceFeed


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


def _risk_decision(
    *,
    symbol: str = "AAPL",
    direction: str = "BUY",
    force_execute: bool = False,
) -> RiskDecision:
    decision = RiskDecision(
        symbol=symbol,
        allowed=True,
        max_position_size=1,
        risk_level="LOW",
        rationale="p11 autonomous recovery gate",
        trader_type="P11_TEST",
        strategy_name="unit_strategy",
        direction=direction,
        stop_loss_price=99.0 if direction.upper() != "SELL" else 101.0,
        decision_id=f"risk-p11-{symbol}-{direction}",
        intent_id=f"intent-p11-{symbol}-{direction}",
    )
    decision.force_execute = force_execute
    return decision


class _P11Provider:
    def __init__(self) -> None:
        self.submitted_orders: list[object] = []

    def name(self) -> str:
        return "P11_TEST_PROVIDER"

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
            rationale="p11_test_fill",
            direction=request.direction,
            quantity=request.quantity,
            requested_quantity=request.quantity,
            filled_quantity=request.quantity,
            remaining_quantity=0,
            fill_status="FULL",
            average_fill_price=Decimal("100.00"),
            client_order_id=request.client_order_id,
            ibkr_order_id=1101,
            attempt_number=request.attempt_number,
        )

    def cancel(self, order_id: str):
        return {"order_id": order_id, "status": "NOT_SUPPORTED", "rationale": "test"}

    def place_stop_order(self, **kwargs):
        return {"broker_order_id": "STOP-P11", "status": "Submitted", "order_type": "STP"}

    def place_target_order(self, **kwargs):
        return {"broker_order_id": "TGT-P11", "status": "Submitted", "order_type": "LMT"}

    def modify_stop_order(self, **kwargs):
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Submitted"}

    def cancel_order(self, *, broker_order_id: str):
        return {"broker_order_id": broker_order_id, "status": "Cancelled"}


def _engine_with_authority(authority: AutonomousRecoveryAuthority, provider: _P11Provider) -> ExecutionEngine:
    return ExecutionEngine(
        provider=provider,
        trade_registry=ActiveTradeRegistry(),
        event_collector=authority.event_collector or EventCollector(),
        price_feed=DeterministicPriceFeed(),
        autonomous_recovery_authority=authority,
    )


def test_all_required_failure_classifications_exist() -> None:
    assert set(FAILURE_CLASSIFICATIONS) == set(AutonomousFailureType)
    for classification in FAILURE_CLASSIFICATIONS.values():
        assert classification.audit_reason
        assert classification.max_retry_count >= 0


def test_live_broker_unavailable_fails_closed() -> None:
    decision = AutonomousRecoveryAuthority().evaluate(
        run_mode="LIVE",
        broker_connected=False,
    )

    assert decision.recovery_status == AutonomousRecoveryStatus.FAIL_CLOSED
    assert decision.action == AutonomousRecoveryAction.FAIL_CLOSED
    assert decision.blocks_new_entries is True
    assert decision.allows_existing_position_management is False
    assert decision.requires_broker_resync is True


def test_live_storage_unavailable_during_required_replay_fails_closed() -> None:
    decision = AutonomousRecoveryAuthority().evaluate(
        run_mode="LIVE",
        storage_available=False,
        storage_replay_required=True,
    )

    assert decision.recovery_status == AutonomousRecoveryStatus.FAIL_CLOSED
    assert decision.failure_classification.failure_type == AutonomousFailureType.STORAGE_UNAVAILABLE
    assert decision.requires_storage_replay is True


def test_live_storage_unavailable_with_broker_flat_proof_is_managed_only() -> None:
    decision = AutonomousRecoveryAuthority().evaluate(
        run_mode="LIVE",
        storage_available=False,
        storage_replay_required=True,
        broker_truth_flat=True,
    )

    assert decision.recovery_status == AutonomousRecoveryStatus.MANAGED_ONLY
    assert decision.blocks_new_entries is True
    assert decision.allows_existing_position_management is True


def test_unknown_order_state_blocks_new_entries() -> None:
    decision = AutonomousRecoveryAuthority().evaluate(
        run_mode="LIVE",
        order_state_known=False,
    )

    assert decision.recovery_status == AutonomousRecoveryStatus.MANAGED_ONLY
    assert decision.requires_order_reconciliation is True
    assert decision.blocks_new_entries is True


def test_position_mismatch_enters_managed_only() -> None:
    decision = AutonomousRecoveryAuthority().evaluate(
        run_mode="LIVE",
        position_state_matches=False,
    )

    assert decision.recovery_status == AutonomousRecoveryStatus.MANAGED_ONLY
    assert decision.failure_classification.failure_type == AutonomousFailureType.POSITION_STATE_MISMATCH
    assert decision.requires_broker_resync is True


def test_missing_stop_protection_recommends_stop_repair_and_blocks_entries() -> None:
    decision = AutonomousRecoveryAuthority().evaluate(
        run_mode="LIVE",
        stop_protection_missing=True,
    )

    assert decision.recovery_status == AutonomousRecoveryStatus.MANAGED_ONLY
    assert decision.requires_stop_repair is True
    assert {"authority": "StopLossAuthority", "intent": "STOP_REPAIR"} in (
        AutonomousRecoveryAuthority.action_recommendations(decision)
    )


def test_daily_risk_unreconstructed_blocks_new_entries() -> None:
    decision = AutonomousRecoveryAuthority().evaluate(
        run_mode="LIVE",
        daily_risk_recovered=False,
    )

    assert decision.recovery_status == AutonomousRecoveryStatus.FAIL_CLOSED
    assert decision.requires_daily_risk_recheck is True
    assert decision.blocks_new_entries is True


def test_retryable_broker_disconnect_retries_deterministically_in_paper() -> None:
    decision = AutonomousRecoveryAuthority().evaluate(
        run_mode="PAPER",
        broker_connected=False,
        retry_counts={AutonomousFailureType.BROKER_DISCONNECTED.value: 1},
    )

    assert decision.recovery_status == AutonomousRecoveryStatus.RETRYING
    assert decision.action == AutonomousRecoveryAction.RETRY
    assert decision.evidence["retry_count"] == 1


def test_retry_exhaustion_halts_in_paper() -> None:
    decision = AutonomousRecoveryAuthority().evaluate(
        run_mode="PAPER",
        broker_connected=False,
        retry_counts={AutonomousFailureType.BROKER_DISCONNECTED.value: 3},
    )

    assert decision.recovery_status == AutonomousRecoveryStatus.HALTED
    assert decision.action == AutonomousRecoveryAction.HALT


def test_read_only_evaluates_without_mutating_recovery_state() -> None:
    authority = AutonomousRecoveryAuthority()

    decision = authority.evaluate(run_mode="READ_ONLY", broker_connected=False)

    assert decision.blocks_new_entries is True
    assert authority.last_decision is None


def test_paper_and_sim_decisions_are_deterministic() -> None:
    paper = AutonomousRecoveryAuthority().evaluate(
        run_mode="PAPER",
        market_data_stale=True,
        retry_counts={AutonomousFailureType.MARKET_DATA_STALE.value: 0},
    )
    sim = AutonomousRecoveryAuthority().evaluate(
        run_mode="SIM",
        market_data_stale=True,
        retry_counts={AutonomousFailureType.MARKET_DATA_STALE.value: 0},
    )

    assert paper.recovery_status == sim.recovery_status
    assert paper.action == sim.action
    assert paper.failure_classification.failure_type == sim.failure_classification.failure_type


def test_orchestrator_managed_only_blocks_new_entries_after_position_management_tick() -> None:
    events = EventCollector()
    authority = AutonomousRecoveryAuthority(event_collector=events)
    halted: list[dict[str, object]] = []
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator.autonomous_recovery_authority = authority
    orchestrator.run_mode = RunMode.PAPER
    orchestrator.event_collector = events
    orchestrator._ensure_cycle_id = lambda: "cycle-p11"
    orchestrator._trace_halt = lambda **payload: halted.append(payload)
    orchestrator.autonomous_recovery_evidence_provider = lambda **_kwargs: {
        "position_state_matches": False,
    }

    allowed = CoreOrchestrator._autonomous_recovery_allows_new_entries(
        orchestrator,
        cycle_started_at=NOW,
    )

    assert allowed is False
    assert halted[0]["reason_code"] == "AUTONOMOUS_RECOVERY_MANAGED_ONLY"


def test_orchestrator_refreshes_stale_blocking_decision_on_later_healthy_cycle() -> None:
    events = EventCollector()
    authority = AutonomousRecoveryAuthority(event_collector=events)
    authority.evaluate(run_mode="PAPER", position_state_matches=False)
    halted: list[dict[str, object]] = []
    evidence_sequence = iter(
        [
            {"position_state_matches": False},
            {"position_state_matches": True},
        ]
    )
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator.autonomous_recovery_authority = authority
    orchestrator.run_mode = RunMode.PAPER
    orchestrator.event_collector = events
    orchestrator._ensure_cycle_id = lambda: "cycle-p11"
    orchestrator._trace_halt = lambda **payload: halted.append(payload)
    orchestrator.autonomous_recovery_evidence_provider = lambda **_kwargs: next(evidence_sequence)

    first_cycle = CoreOrchestrator._autonomous_recovery_allows_new_entries(
        orchestrator,
        cycle_started_at=NOW,
    )
    later_cycle = CoreOrchestrator._autonomous_recovery_allows_new_entries(
        orchestrator,
        cycle_started_at=NOW,
    )

    assert first_cycle is False
    assert later_cycle is True
    assert authority.last_decision is not None
    assert authority.last_decision.recovery_status == AutonomousRecoveryStatus.RECOVERED
    audit_events = events.filter_by_type("AUTONOMOUS_RECOVERY_DECISION")
    assert audit_events[-1].payload["recovery_status"] == "RECOVERED"


def test_managed_only_blocks_new_entries_in_execution_backstop() -> None:
    _set_config(RUN_MODE="LIVE")
    events = EventCollector()
    authority = AutonomousRecoveryAuthority(event_collector=events)
    authority.evaluate(run_mode="LIVE", position_state_matches=False)
    provider = _P11Provider()
    engine = _engine_with_authority(authority, provider)

    result = engine.execute_trade(_risk_decision())

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("AUTONOMOUS_RECOVERY_MANAGED_ONLY:")
    assert provider.submitted_orders == []


def test_managed_only_allows_existing_position_exit() -> None:
    _set_config(RUN_MODE="LIVE")
    events = EventCollector()
    authority = AutonomousRecoveryAuthority(event_collector=events)
    authority.evaluate(run_mode="LIVE", position_state_matches=False)
    provider = _P11Provider()
    engine = _engine_with_authority(authority, provider)

    result = engine.execute_trade(_risk_decision(direction="SELL"))

    assert result.status == "Filled"
    assert len(provider.submitted_orders) == 1


def test_force_execute_cannot_bypass_p11_recovery_lock() -> None:
    _set_config(RUN_MODE="LIVE")
    events = EventCollector()
    authority = AutonomousRecoveryAuthority(event_collector=events)
    authority.evaluate(run_mode="LIVE", stop_protection_missing=True)
    provider = _P11Provider()
    engine = _engine_with_authority(authority, provider)

    result = engine.execute_trade(_risk_decision(force_execute=True))

    assert result.status == "BLOCKED"
    assert result.rationale.startswith("AUTONOMOUS_RECOVERY_MANAGED_ONLY:")
    assert provider.submitted_orders == []


def test_recovery_decision_emits_audit_event() -> None:
    events = EventCollector()
    authority = AutonomousRecoveryAuthority(event_collector=events)

    decision = authority.evaluate(run_mode="LIVE", order_state_known=False)

    audit_events = events.filter_by_type("AUTONOMOUS_RECOVERY_DECISION")
    action_events = events.filter_by_type("AUTONOMOUS_RECOVERY_ACTION")
    assert audit_events[0].payload["decision_id"] == decision.decision_id
    assert action_events[0].payload["action_recommendations"] == [
        {"authority": "ExecutionEngine", "intent": "ORDER_RECONCILIATION"}
    ]


def test_p11_authority_does_not_submit_broker_orders_directly() -> None:
    provider = SimpleNamespace(submitted_orders=[])
    authority = AutonomousRecoveryAuthority()

    decision = authority.evaluate(
        run_mode="LIVE",
        stop_protection_missing=True,
        audit_payload={"provider": provider},
    )

    assert decision.requires_stop_repair is True
    assert provider.submitted_orders == []
