from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class AutonomousFailureType(str, Enum):
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    ORDER_STATE_UNKNOWN = "ORDER_STATE_UNKNOWN"
    POSITION_STATE_MISMATCH = "POSITION_STATE_MISMATCH"
    FILL_STATE_MISMATCH = "FILL_STATE_MISMATCH"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    EVENT_REPLAY_INCOMPLETE = "EVENT_REPLAY_INCOMPLETE"
    DAILY_RISK_UNRECONSTRUCTED = "DAILY_RISK_UNRECONSTRUCTED"
    LIFECYCLE_UNRECONSTRUCTED = "LIFECYCLE_UNRECONSTRUCTED"
    STOP_PROTECTION_MISSING = "STOP_PROTECTION_MISSING"
    TARGET_STATE_UNKNOWN = "TARGET_STATE_UNKNOWN"
    TRAILING_STATE_UNKNOWN = "TRAILING_STATE_UNKNOWN"
    CONFIG_INVALID = "CONFIG_INVALID"
    CLOCK_OR_SESSION_INVALID = "CLOCK_OR_SESSION_INVALID"
    UNKNOWN_RUNTIME_EXCEPTION = "UNKNOWN_RUNTIME_EXCEPTION"


class AutonomousFailureSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AutonomousRecoveryAction(str, Enum):
    CONTINUE_TRADING = "CONTINUE_TRADING"
    MANAGED_ONLY = "MANAGED_ONLY"
    RETRY = "RETRY"
    HALT = "HALT"
    FAIL_CLOSED = "FAIL_CLOSED"
    OPERATOR_REQUIRED = "OPERATOR_REQUIRED"


class AutonomousRecoveryStatus(str, Enum):
    RECOVERED = "RECOVERED"
    RECOVERED_WITH_WARNINGS = "RECOVERED_WITH_WARNINGS"
    MANAGED_ONLY = "MANAGED_ONLY"
    RETRYING = "RETRYING"
    HALTED = "HALTED"
    FAIL_CLOSED = "FAIL_CLOSED"
    OPERATOR_REQUIRED = "OPERATOR_REQUIRED"


@dataclass(frozen=True)
class FailureClassification:
    failure_type: AutonomousFailureType
    severity: AutonomousFailureSeverity
    live_action: AutonomousRecoveryAction
    paper_action: AutonomousRecoveryAction
    retry_allowed: bool
    max_retry_count: int
    requires_operator: bool
    blocks_new_entries: bool
    allows_existing_position_management: bool
    audit_reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["failure_type"] = self.failure_type.value
        payload["severity"] = self.severity.value
        payload["live_action"] = self.live_action.value
        payload["paper_action"] = self.paper_action.value
        return payload


@dataclass(frozen=True)
class AutonomousRecoveryDecision:
    decision_id: str
    run_mode: str
    recovery_status: AutonomousRecoveryStatus
    failure_classification: FailureClassification | None
    action: AutonomousRecoveryAction
    blocks_new_entries: bool
    allows_existing_position_management: bool
    requires_broker_resync: bool = False
    requires_storage_replay: bool = False
    requires_lifecycle_rebuild: bool = False
    requires_order_reconciliation: bool = False
    requires_stop_repair: bool = False
    requires_target_repair: bool = False
    requires_daily_risk_recheck: bool = False
    rationale: str = "AUTONOMOUS_RECOVERY_OK"
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def safe_for_new_entries(self) -> bool:
        return not self.blocks_new_entries and self.recovery_status in {
            AutonomousRecoveryStatus.RECOVERED,
            AutonomousRecoveryStatus.RECOVERED_WITH_WARNINGS,
        }

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "run_mode": self.run_mode,
            "recovery_status": self.recovery_status.value,
            "failure_type": (
                self.failure_classification.failure_type.value
                if self.failure_classification is not None
                else "NONE"
            ),
            "severity": (
                self.failure_classification.severity.value
                if self.failure_classification is not None
                else "INFO"
            ),
            "action": self.action.value,
            "blocks_new_entries": bool(self.blocks_new_entries),
            "allows_existing_position_management": bool(self.allows_existing_position_management),
            "requires_broker_resync": bool(self.requires_broker_resync),
            "requires_storage_replay": bool(self.requires_storage_replay),
            "requires_lifecycle_rebuild": bool(self.requires_lifecycle_rebuild),
            "requires_order_reconciliation": bool(self.requires_order_reconciliation),
            "requires_stop_repair": bool(self.requires_stop_repair),
            "requires_target_repair": bool(self.requires_target_repair),
            "requires_daily_risk_recheck": bool(self.requires_daily_risk_recheck),
            "rationale": self.rationale,
            "evidence": dict(self.evidence),
            "timestamp": self.timestamp,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.to_event_payload()
        payload["failure_classification"] = (
            self.failure_classification.to_dict()
            if self.failure_classification is not None
            else None
        )
        return payload


def _policy(
    failure_type: AutonomousFailureType,
    *,
    severity: AutonomousFailureSeverity,
    live_action: AutonomousRecoveryAction,
    paper_action: AutonomousRecoveryAction,
    retry_allowed: bool = False,
    max_retry_count: int = 0,
    requires_operator: bool = False,
    blocks_new_entries: bool = True,
    allows_existing_position_management: bool = True,
    audit_reason: str,
) -> FailureClassification:
    return FailureClassification(
        failure_type=failure_type,
        severity=severity,
        live_action=live_action,
        paper_action=paper_action,
        retry_allowed=retry_allowed,
        max_retry_count=max(0, int(max_retry_count)),
        requires_operator=requires_operator,
        blocks_new_entries=blocks_new_entries,
        allows_existing_position_management=allows_existing_position_management,
        audit_reason=audit_reason,
    )


FAILURE_CLASSIFICATIONS: dict[AutonomousFailureType, FailureClassification] = {
    AutonomousFailureType.BROKER_DISCONNECTED: _policy(
        AutonomousFailureType.BROKER_DISCONNECTED,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.FAIL_CLOSED,
        paper_action=AutonomousRecoveryAction.RETRY,
        retry_allowed=True,
        max_retry_count=3,
        allows_existing_position_management=False,
        audit_reason="Broker truth is unavailable.",
    ),
    AutonomousFailureType.MARKET_DATA_STALE: _policy(
        AutonomousFailureType.MARKET_DATA_STALE,
        severity=AutonomousFailureSeverity.ERROR,
        live_action=AutonomousRecoveryAction.MANAGED_ONLY,
        paper_action=AutonomousRecoveryAction.RETRY,
        retry_allowed=True,
        max_retry_count=2,
        audit_reason="Market data must be refreshed before new risk can be added.",
    ),
    AutonomousFailureType.ORDER_STATE_UNKNOWN: _policy(
        AutonomousFailureType.ORDER_STATE_UNKNOWN,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.MANAGED_ONLY,
        paper_action=AutonomousRecoveryAction.MANAGED_ONLY,
        audit_reason="Open order state is not reconciled.",
    ),
    AutonomousFailureType.POSITION_STATE_MISMATCH: _policy(
        AutonomousFailureType.POSITION_STATE_MISMATCH,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.MANAGED_ONLY,
        paper_action=AutonomousRecoveryAction.MANAGED_ONLY,
        audit_reason="Broker and lifecycle position truth disagree.",
    ),
    AutonomousFailureType.FILL_STATE_MISMATCH: _policy(
        AutonomousFailureType.FILL_STATE_MISMATCH,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.MANAGED_ONLY,
        paper_action=AutonomousRecoveryAction.MANAGED_ONLY,
        audit_reason="Fill truth cannot be reconciled.",
    ),
    AutonomousFailureType.STORAGE_UNAVAILABLE: _policy(
        AutonomousFailureType.STORAGE_UNAVAILABLE,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.FAIL_CLOSED,
        paper_action=AutonomousRecoveryAction.RETRY,
        retry_allowed=True,
        max_retry_count=2,
        allows_existing_position_management=False,
        audit_reason="Storage replay source is unavailable.",
    ),
    AutonomousFailureType.EVENT_REPLAY_INCOMPLETE: _policy(
        AutonomousFailureType.EVENT_REPLAY_INCOMPLETE,
        severity=AutonomousFailureSeverity.ERROR,
        live_action=AutonomousRecoveryAction.FAIL_CLOSED,
        paper_action=AutonomousRecoveryAction.RETRY,
        retry_allowed=True,
        max_retry_count=2,
        allows_existing_position_management=False,
        audit_reason="Event replay did not complete.",
    ),
    AutonomousFailureType.DAILY_RISK_UNRECONSTRUCTED: _policy(
        AutonomousFailureType.DAILY_RISK_UNRECONSTRUCTED,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.FAIL_CLOSED,
        paper_action=AutonomousRecoveryAction.MANAGED_ONLY,
        allows_existing_position_management=False,
        audit_reason="P10 daily risk state is not reconstructed.",
    ),
    AutonomousFailureType.LIFECYCLE_UNRECONSTRUCTED: _policy(
        AutonomousFailureType.LIFECYCLE_UNRECONSTRUCTED,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.MANAGED_ONLY,
        paper_action=AutonomousRecoveryAction.MANAGED_ONLY,
        audit_reason="Position lifecycle continuity is incomplete.",
    ),
    AutonomousFailureType.STOP_PROTECTION_MISSING: _policy(
        AutonomousFailureType.STOP_PROTECTION_MISSING,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.MANAGED_ONLY,
        paper_action=AutonomousRecoveryAction.MANAGED_ONLY,
        audit_reason="A broker position lacks active stop protection.",
    ),
    AutonomousFailureType.TARGET_STATE_UNKNOWN: _policy(
        AutonomousFailureType.TARGET_STATE_UNKNOWN,
        severity=AutonomousFailureSeverity.ERROR,
        live_action=AutonomousRecoveryAction.MANAGED_ONLY,
        paper_action=AutonomousRecoveryAction.MANAGED_ONLY,
        audit_reason="Take-profit target state is not reconciled.",
    ),
    AutonomousFailureType.TRAILING_STATE_UNKNOWN: _policy(
        AutonomousFailureType.TRAILING_STATE_UNKNOWN,
        severity=AutonomousFailureSeverity.ERROR,
        live_action=AutonomousRecoveryAction.MANAGED_ONLY,
        paper_action=AutonomousRecoveryAction.MANAGED_ONLY,
        audit_reason="Trailing stop state is not reconciled.",
    ),
    AutonomousFailureType.CONFIG_INVALID: _policy(
        AutonomousFailureType.CONFIG_INVALID,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.OPERATOR_REQUIRED,
        paper_action=AutonomousRecoveryAction.HALT,
        requires_operator=True,
        allows_existing_position_management=False,
        audit_reason="Runtime configuration is invalid.",
    ),
    AutonomousFailureType.CLOCK_OR_SESSION_INVALID: _policy(
        AutonomousFailureType.CLOCK_OR_SESSION_INVALID,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.OPERATOR_REQUIRED,
        paper_action=AutonomousRecoveryAction.HALT,
        requires_operator=True,
        allows_existing_position_management=False,
        audit_reason="Clock or trading session authority is invalid.",
    ),
    AutonomousFailureType.UNKNOWN_RUNTIME_EXCEPTION: _policy(
        AutonomousFailureType.UNKNOWN_RUNTIME_EXCEPTION,
        severity=AutonomousFailureSeverity.CRITICAL,
        live_action=AutonomousRecoveryAction.OPERATOR_REQUIRED,
        paper_action=AutonomousRecoveryAction.HALT,
        requires_operator=True,
        allows_existing_position_management=False,
        audit_reason="An unclassified runtime exception occurred.",
    ),
}


class AutonomousRecoveryAuthority:
    """P11 coordinator for runtime failure classification and recovery decisions.

    The authority coordinates other recovery systems and emits decisions. It does
    not submit, modify, or cancel broker orders.
    """

    def __init__(self, *, event_collector: Any | None = None) -> None:
        self.event_collector = event_collector
        self.last_decision: AutonomousRecoveryDecision | None = None

    def current_decision(self) -> AutonomousRecoveryDecision | None:
        return self.last_decision

    def evaluate(
        self,
        *,
        run_mode: str = "SIM",
        broker_connected: bool = True,
        broker_truth_available: bool = True,
        broker_truth_flat: bool | None = None,
        storage_available: bool = True,
        storage_replay_required: bool = False,
        event_replay_complete: bool = True,
        daily_risk_recovered: bool = True,
        lifecycle_recovered: bool = True,
        order_state_known: bool = True,
        position_state_matches: bool = True,
        fill_state_matches: bool = True,
        stop_protection_missing: bool = False,
        target_state_unknown: bool = False,
        trailing_state_unknown: bool = False,
        market_data_stale: bool = False,
        config_valid: bool = True,
        clock_or_session_valid: bool = True,
        runtime_exception: BaseException | None = None,
        retry_counts: dict[str, int] | None = None,
        audit_payload: dict[str, Any] | None = None,
        read_only: bool = False,
        event_collector: Any | None = None,
    ) -> AutonomousRecoveryDecision:
        if event_collector is not None:
            self.event_collector = event_collector
        run_mode_u = str(run_mode or "SIM").upper()
        evidence = {
            "broker_connected": bool(broker_connected),
            "broker_truth_available": bool(broker_truth_available),
            "broker_truth_flat": broker_truth_flat,
            "storage_available": bool(storage_available),
            "storage_replay_required": bool(storage_replay_required),
            "event_replay_complete": bool(event_replay_complete),
            "daily_risk_recovered": bool(daily_risk_recovered),
            "lifecycle_recovered": bool(lifecycle_recovered),
            "order_state_known": bool(order_state_known),
            "position_state_matches": bool(position_state_matches),
            "fill_state_matches": bool(fill_state_matches),
            "stop_protection_missing": bool(stop_protection_missing),
            "target_state_unknown": bool(target_state_unknown),
            "trailing_state_unknown": bool(trailing_state_unknown),
            "market_data_stale": bool(market_data_stale),
            "config_valid": bool(config_valid),
            "clock_or_session_valid": bool(clock_or_session_valid),
            "runtime_exception": type(runtime_exception).__name__ if runtime_exception else None,
            "audit_payload": dict(audit_payload or {}),
        }
        failure_type = self._classify_failure(
            broker_connected=broker_connected,
            broker_truth_available=broker_truth_available,
            storage_available=storage_available,
            storage_replay_required=storage_replay_required,
            event_replay_complete=event_replay_complete,
            daily_risk_recovered=daily_risk_recovered,
            lifecycle_recovered=lifecycle_recovered,
            order_state_known=order_state_known,
            position_state_matches=position_state_matches,
            fill_state_matches=fill_state_matches,
            stop_protection_missing=stop_protection_missing,
            target_state_unknown=target_state_unknown,
            trailing_state_unknown=trailing_state_unknown,
            market_data_stale=market_data_stale,
            config_valid=config_valid,
            clock_or_session_valid=clock_or_session_valid,
            runtime_exception=runtime_exception,
        )
        if failure_type is None:
            decision = AutonomousRecoveryDecision(
                decision_id=f"auto-recovery-{uuid4().hex[:12]}",
                run_mode=run_mode_u,
                recovery_status=AutonomousRecoveryStatus.RECOVERED,
                failure_classification=None,
                action=AutonomousRecoveryAction.CONTINUE_TRADING,
                blocks_new_entries=False,
                allows_existing_position_management=True,
                rationale="AUTONOMOUS_RECOVERY_OK",
                evidence=evidence,
            )
            return self._finalize(decision, read_only=read_only or run_mode_u == "READ_ONLY")

        classification = FAILURE_CLASSIFICATIONS[failure_type]
        decision = self._decision_for_failure(
            run_mode=run_mode_u,
            classification=classification,
            retry_count=self._retry_count(retry_counts, failure_type),
            broker_truth_flat=broker_truth_flat,
            evidence=evidence,
        )
        return self._finalize(decision, read_only=read_only or run_mode_u == "READ_ONLY")

    def _decision_for_failure(
        self,
        *,
        run_mode: str,
        classification: FailureClassification,
        retry_count: int,
        broker_truth_flat: bool | None,
        evidence: dict[str, Any],
    ) -> AutonomousRecoveryDecision:
        action = classification.live_action if run_mode == "LIVE" else classification.paper_action
        status = self._status_for_action(action)
        blocks_new_entries = classification.blocks_new_entries
        allows_management = classification.allows_existing_position_management

        if (
            classification.failure_type == AutonomousFailureType.STORAGE_UNAVAILABLE
            and run_mode == "LIVE"
            and evidence.get("storage_replay_required")
            and broker_truth_flat is True
        ):
            action = AutonomousRecoveryAction.MANAGED_ONLY
            status = AutonomousRecoveryStatus.MANAGED_ONLY
            allows_management = True

        if run_mode != "LIVE" and classification.retry_allowed:
            if retry_count < classification.max_retry_count:
                action = AutonomousRecoveryAction.RETRY
                status = AutonomousRecoveryStatus.RETRYING
            else:
                action = AutonomousRecoveryAction.HALT
                status = AutonomousRecoveryStatus.HALTED

        return AutonomousRecoveryDecision(
            decision_id=f"auto-recovery-{uuid4().hex[:12]}",
            run_mode=run_mode,
            recovery_status=status,
            failure_classification=classification,
            action=action,
            blocks_new_entries=blocks_new_entries,
            allows_existing_position_management=allows_management,
            requires_broker_resync=classification.failure_type
            in {
                AutonomousFailureType.BROKER_DISCONNECTED,
                AutonomousFailureType.POSITION_STATE_MISMATCH,
                AutonomousFailureType.FILL_STATE_MISMATCH,
            },
            requires_storage_replay=classification.failure_type
            in {
                AutonomousFailureType.STORAGE_UNAVAILABLE,
                AutonomousFailureType.EVENT_REPLAY_INCOMPLETE,
            },
            requires_lifecycle_rebuild=classification.failure_type
            == AutonomousFailureType.LIFECYCLE_UNRECONSTRUCTED,
            requires_order_reconciliation=classification.failure_type
            == AutonomousFailureType.ORDER_STATE_UNKNOWN,
            requires_stop_repair=classification.failure_type
            == AutonomousFailureType.STOP_PROTECTION_MISSING,
            requires_target_repair=classification.failure_type
            == AutonomousFailureType.TARGET_STATE_UNKNOWN,
            requires_daily_risk_recheck=classification.failure_type
            == AutonomousFailureType.DAILY_RISK_UNRECONSTRUCTED,
            rationale=classification.audit_reason,
            evidence={**evidence, "retry_count": retry_count},
        )

    def _finalize(
        self,
        decision: AutonomousRecoveryDecision,
        *,
        read_only: bool,
    ) -> AutonomousRecoveryDecision:
        self._emit_decision(decision)
        if not read_only:
            self.last_decision = decision
        return decision

    def _emit_decision(self, decision: AutonomousRecoveryDecision) -> None:
        if self.event_collector is None:
            return
        emit = getattr(self.event_collector, "emit", None)
        if not callable(emit):
            return
        try:
            emit(
                event_type="AUTONOMOUS_RECOVERY_DECISION",
                source="AutonomousRecoveryAuthority",
                payload=decision.to_event_payload(),
            )
            if decision.action != AutonomousRecoveryAction.CONTINUE_TRADING:
                emit(
                    event_type="AUTONOMOUS_RECOVERY_ACTION",
                    source="AutonomousRecoveryAuthority",
                    payload={
                        **decision.to_event_payload(),
                        "action_recommendations": self.action_recommendations(decision),
                    },
                )
        except Exception as exc:
            print(f"[AUTONOMOUS_RECOVERY][AUDIT][FAILED] reason={exc}")

    @staticmethod
    def action_recommendations(decision: AutonomousRecoveryDecision) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        if decision.requires_broker_resync:
            recommendations.append({"authority": "ExecutionEngine", "intent": "BROKER_RESYNC"})
        if decision.requires_storage_replay:
            recommendations.append({"authority": "StorageEngine", "intent": "STORAGE_REPLAY"})
        if decision.requires_lifecycle_rebuild:
            recommendations.append({"authority": "TradeLifecycleEngine", "intent": "LIFECYCLE_REBUILD"})
        if decision.requires_order_reconciliation:
            recommendations.append({"authority": "ExecutionEngine", "intent": "ORDER_RECONCILIATION"})
        if decision.requires_stop_repair:
            recommendations.append({"authority": "StopLossAuthority", "intent": "STOP_REPAIR"})
        if decision.requires_target_repair:
            recommendations.append({"authority": "TakeProfitAuthority", "intent": "TARGET_REPAIR"})
        if decision.requires_daily_risk_recheck:
            recommendations.append({"authority": "DailyRiskGovernor", "intent": "DAILY_RISK_RECHECK"})
        return recommendations

    @staticmethod
    def _status_for_action(action: AutonomousRecoveryAction) -> AutonomousRecoveryStatus:
        if action == AutonomousRecoveryAction.CONTINUE_TRADING:
            return AutonomousRecoveryStatus.RECOVERED
        if action == AutonomousRecoveryAction.MANAGED_ONLY:
            return AutonomousRecoveryStatus.MANAGED_ONLY
        if action == AutonomousRecoveryAction.RETRY:
            return AutonomousRecoveryStatus.RETRYING
        if action == AutonomousRecoveryAction.FAIL_CLOSED:
            return AutonomousRecoveryStatus.FAIL_CLOSED
        if action == AutonomousRecoveryAction.OPERATOR_REQUIRED:
            return AutonomousRecoveryStatus.OPERATOR_REQUIRED
        return AutonomousRecoveryStatus.HALTED

    @staticmethod
    def _retry_count(retry_counts: dict[str, int] | None, failure_type: AutonomousFailureType) -> int:
        if not retry_counts:
            return 0
        return int(
            retry_counts.get(failure_type.value, retry_counts.get(failure_type.name, 0)) or 0
        )

    @staticmethod
    def _classify_failure(
        *,
        broker_connected: bool,
        broker_truth_available: bool,
        storage_available: bool,
        storage_replay_required: bool,
        event_replay_complete: bool,
        daily_risk_recovered: bool,
        lifecycle_recovered: bool,
        order_state_known: bool,
        position_state_matches: bool,
        fill_state_matches: bool,
        stop_protection_missing: bool,
        target_state_unknown: bool,
        trailing_state_unknown: bool,
        market_data_stale: bool,
        config_valid: bool,
        clock_or_session_valid: bool,
        runtime_exception: BaseException | None,
    ) -> AutonomousFailureType | None:
        checks: list[tuple[bool, AutonomousFailureType]] = [
            (runtime_exception is not None, AutonomousFailureType.UNKNOWN_RUNTIME_EXCEPTION),
            (not config_valid, AutonomousFailureType.CONFIG_INVALID),
            (not clock_or_session_valid, AutonomousFailureType.CLOCK_OR_SESSION_INVALID),
            (not broker_connected or not broker_truth_available, AutonomousFailureType.BROKER_DISCONNECTED),
            (storage_replay_required and not storage_available, AutonomousFailureType.STORAGE_UNAVAILABLE),
            (not event_replay_complete, AutonomousFailureType.EVENT_REPLAY_INCOMPLETE),
            (not daily_risk_recovered, AutonomousFailureType.DAILY_RISK_UNRECONSTRUCTED),
            (not lifecycle_recovered, AutonomousFailureType.LIFECYCLE_UNRECONSTRUCTED),
            (not order_state_known, AutonomousFailureType.ORDER_STATE_UNKNOWN),
            (not position_state_matches, AutonomousFailureType.POSITION_STATE_MISMATCH),
            (not fill_state_matches, AutonomousFailureType.FILL_STATE_MISMATCH),
            (stop_protection_missing, AutonomousFailureType.STOP_PROTECTION_MISSING),
            (target_state_unknown, AutonomousFailureType.TARGET_STATE_UNKNOWN),
            (trailing_state_unknown, AutonomousFailureType.TRAILING_STATE_UNKNOWN),
            (market_data_stale, AutonomousFailureType.MARKET_DATA_STALE),
        ]
        for failed, failure_type in checks:
            if failed:
                return failure_type
        return None


__all__ = [
    "AutonomousFailureSeverity",
    "AutonomousFailureType",
    "AutonomousRecoveryAction",
    "AutonomousRecoveryAuthority",
    "AutonomousRecoveryDecision",
    "AutonomousRecoveryStatus",
    "FailureClassification",
    "FAILURE_CLASSIFICATIONS",
]
