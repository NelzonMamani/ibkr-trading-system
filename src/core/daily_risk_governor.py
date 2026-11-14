from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from enum import Enum
import math
from typing import Any, Iterable
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.config.config_resolver import get_config


class DailyRiskDecisionStatus(str, Enum):
    ALLOW = "ALLOW"
    WARNING = "WARNING"
    BLOCK_NEW_ENTRIES = "BLOCK_NEW_ENTRIES"
    MANAGED_ONLY = "MANAGED_ONLY"
    LOCKED = "LOCKED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    RECOVERY_NOT_COMPLETE = "RECOVERY_NOT_COMPLETE"
    READ_ONLY_EVALUATED = "READ_ONLY_EVALUATED"
    MANUAL_HALT = "MANUAL_HALT"


class DailyRiskLockStatus(str, Enum):
    UNLOCKED = "UNLOCKED"
    WARNING = "WARNING"
    LOCKED = "LOCKED"


class DailyRiskExistingPositionPolicy(str, Enum):
    MANAGED_ONLY = "MANAGED_ONLY"
    FLATTEN = "FLATTEN"
    HOLD = "HOLD"


@dataclass(frozen=True)
class DailyRiskState:
    trading_day: str
    timezone_name: str
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    daily_trade_count: int = 0
    losing_trade_count: int = 0
    consecutive_losses: int = 0
    lock_status: DailyRiskLockStatus = DailyRiskLockStatus.UNLOCKED
    manual_halt_active: bool = False
    recovered: bool = True
    recovery_error: str | None = None
    reset_key: str = ""
    source_counts: dict[str, int] = field(default_factory=dict)

    @property
    def total_pnl_for_loss_limit(self) -> float:
        return round(float(self.realized_pnl or 0.0) + float(self.unrealized_pnl or 0.0), 2)


@dataclass(frozen=True)
class DailyRiskDecision:
    decision_id: str
    status: DailyRiskDecisionStatus
    reason: str
    run_mode: str
    trading_day: str
    timezone_name: str
    realized_pnl: float
    unrealized_pnl: float
    include_unrealized: bool
    daily_trade_count: int
    losing_trade_count: int
    consecutive_losses: int
    lock_status: DailyRiskLockStatus
    existing_position_policy: DailyRiskExistingPositionPolicy
    recommended_existing_position_action: str
    reasons: tuple[str, ...] = ()
    limit_snapshot: dict[str, Any] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)
    audit_payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def blocks_new_entries(self) -> bool:
        return self.status in {
            DailyRiskDecisionStatus.BLOCK_NEW_ENTRIES,
            DailyRiskDecisionStatus.MANAGED_ONLY,
            DailyRiskDecisionStatus.LOCKED,
            DailyRiskDecisionStatus.DATA_UNAVAILABLE,
            DailyRiskDecisionStatus.RECOVERY_NOT_COMPLETE,
            DailyRiskDecisionStatus.MANUAL_HALT,
        }

    @property
    def allows_existing_position_management(self) -> bool:
        if self.status in {
            DailyRiskDecisionStatus.DATA_UNAVAILABLE,
            DailyRiskDecisionStatus.RECOVERY_NOT_COMPLETE,
            DailyRiskDecisionStatus.MANUAL_HALT,
        }:
            return False
        return True

    def to_event_payload(self) -> dict[str, Any]:
        payload = {
            "decision_id": self.decision_id,
            "status": self.status.value,
            "reason": self.reason,
            "run_mode": self.run_mode,
            "trading_day": self.trading_day,
            "timezone_name": self.timezone_name,
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "include_unrealized": bool(self.include_unrealized),
            "daily_trade_count": int(self.daily_trade_count),
            "losing_trade_count": int(self.losing_trade_count),
            "consecutive_losses": int(self.consecutive_losses),
            "lock_status": self.lock_status.value,
            "existing_position_policy": self.existing_position_policy.value,
            "recommended_existing_position_action": self.recommended_existing_position_action,
            "blocks_new_entries": bool(self.blocks_new_entries),
            "allows_existing_position_management": bool(self.allows_existing_position_management),
            "reasons": list(self.reasons),
            "limit_snapshot": dict(self.limit_snapshot),
            "source_counts": dict(self.source_counts),
            "audit_payload": dict(self.audit_payload),
            "timestamp": self.timestamp,
        }
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["lock_status"] = self.lock_status.value
        payload["existing_position_policy"] = self.existing_position_policy.value
        payload["blocks_new_entries"] = self.blocks_new_entries
        payload["allows_existing_position_management"] = self.allows_existing_position_management
        return payload


@dataclass(frozen=True)
class _DailyRiskMetrics:
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    daily_trade_count: int = 0
    losing_trade_count: int = 0
    consecutive_losses: int = 0
    source_count: int = 0
    read_attempted: bool = False
    read_failed: bool = False
    failure_reason: str | None = None
    trade_payloads: tuple[dict[str, Any], ...] = ()
    required_accounting: bool = False
    canonical_payloads: bool = False
    history_payloads: tuple[dict[str, Any], ...] = ()
    source_kind: str = "closed"


class DailyRiskGovernor:
    """Canonical account-level daily risk governor for P10."""

    _WINDOWS_TZ_ALIASES = {
        "GMT SUMMER TIME": "Europe/London",
        "GMT STANDARD TIME": "Europe/London",
        "EASTERN STANDARD TIME": "America/New_York",
    }

    def __init__(
        self,
        *,
        event_collector: Any | None = None,
        storage_engine: Any | None = None,
        trade_lifecycle_engine: Any | None = None,
        provider: Any | None = None,
    ) -> None:
        self.event_collector = event_collector
        self.storage_engine = storage_engine
        self.trade_lifecycle_engine = trade_lifecycle_engine
        self.provider = provider
        self.state: DailyRiskState | None = None
        self.last_decision: DailyRiskDecision | None = None

    @property
    def enabled(self) -> bool:
        return self._bool_config("DAILY_RISK_GOVERNOR_ENABLED", True)

    @property
    def timezone_name(self) -> str:
        raw = str(self._config("DAILY_RISK_TIMEZONE", "America/New_York") or "America/New_York")
        return self._WINDOWS_TZ_ALIASES.get(raw.strip().upper(), raw.strip())

    @property
    def timezone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError:
            return ZoneInfo("America/New_York")

    def recover(
        self,
        *,
        run_mode: str = "SIM",
        recovery_complete: bool = True,
        now: datetime | None = None,
        event_collector: Any | None = None,
        storage_engine: Any | None = None,
        trade_lifecycle_engine: Any | None = None,
        provider: Any | None = None,
    ) -> DailyRiskState:
        if event_collector is not None:
            self.event_collector = event_collector
        if storage_engine is not None:
            self.storage_engine = storage_engine
        if trade_lifecycle_engine is not None:
            self.trade_lifecycle_engine = trade_lifecycle_engine
        if provider is not None:
            self.provider = provider

        state = self._build_state_snapshot(
            now=now,
            run_mode=run_mode,
            recovery_complete=recovery_complete,
        )
        self.state = state
        print(
            "[DAILY_RISK][RECOVERY] "
            f"state={'COMPLETE' if state.recovered else 'FAILED'} "
            f"day={state.trading_day} realized={state.realized_pnl:.2f} "
            f"unrealized={state.unrealized_pnl:.2f} reason={state.recovery_error or 'OK'}"
        )
        return state

    def evaluate(
        self,
        *,
        run_mode: str = "SIM",
        recovery_complete: bool = True,
        now: datetime | None = None,
        is_new_entry: bool = True,
        audit_payload: dict[str, Any] | None = None,
        event_collector: Any | None = None,
        storage_engine: Any | None = None,
        trade_lifecycle_engine: Any | None = None,
        provider: Any | None = None,
    ) -> DailyRiskDecision:
        if event_collector is not None:
            self.event_collector = event_collector
        if storage_engine is not None:
            self.storage_engine = storage_engine
        if trade_lifecycle_engine is not None:
            self.trade_lifecycle_engine = trade_lifecycle_engine
        if provider is not None:
            self.provider = provider

        run_mode_u = str(run_mode or "SIM").upper()
        state = self._build_state_snapshot(
            now=now,
            run_mode=run_mode_u,
            recovery_complete=recovery_complete,
        )
        include_unrealized = self._bool_config("DAILY_RISK_INCLUDE_UNREALIZED", False)
        policy = self._existing_position_policy()
        limit_snapshot = self._limit_snapshot()
        reasons: list[str] = []

        if self.enabled and run_mode_u == "READ_ONLY":
            status = DailyRiskDecisionStatus.READ_ONLY_EVALUATED
            reason = "READ_ONLY_EVALUATED_NO_STATE_MUTATION"
            lock_status = DailyRiskLockStatus.UNLOCKED
        elif self.enabled and self._bool_config("DAILY_RISK_MANUAL_HALT", False):
            status = DailyRiskDecisionStatus.MANUAL_HALT
            reason = "MANUAL_HALT"
            reasons.append(reason)
            lock_status = DailyRiskLockStatus.LOCKED
        elif not state.recovered and str(state.recovery_error or "").startswith("CANONICAL_ACCOUNTING_UNAVAILABLE"):
            # Entry uncertainty must not suppress already-authorized factual
            # accounting, protection or exits.  Core evaluates those first.
            status = DailyRiskDecisionStatus.MANAGED_ONLY
            reason = state.recovery_error or "CANONICAL_ACCOUNTING_UNAVAILABLE"
            reasons.append(reason)
            lock_status = DailyRiskLockStatus.LOCKED
        elif not self.enabled:
            status = DailyRiskDecisionStatus.ALLOW
            reason = "DAILY_RISK_GOVERNOR_DISABLED"
            lock_status = DailyRiskLockStatus.UNLOCKED
        elif not recovery_complete:
            status = DailyRiskDecisionStatus.RECOVERY_NOT_COMPLETE
            reason = "RECOVERY_NOT_COMPLETE"
            reasons.append(reason)
            lock_status = DailyRiskLockStatus.LOCKED
        elif run_mode_u == "PAPER" and not state.recovered:
            status = DailyRiskDecisionStatus.MANAGED_ONLY
            reason = state.recovery_error or "DATA_UNAVAILABLE"
            reasons.append(reason)
            lock_status = DailyRiskLockStatus.LOCKED
        elif (
            run_mode_u == "LIVE"
            and self._bool_config("DAILY_RISK_LIVE_FAIL_CLOSED", True)
            and not state.recovered
        ):
            status = DailyRiskDecisionStatus.DATA_UNAVAILABLE
            reason = state.recovery_error or "DATA_UNAVAILABLE"
            reasons.append(reason)
            lock_status = DailyRiskLockStatus.LOCKED
        else:
            reasons.extend(self._breach_reasons(state, include_unrealized=include_unrealized))
            if reasons:
                lock_status = DailyRiskLockStatus.LOCKED
                status = self._status_for_locked_policy(policy, is_new_entry=is_new_entry)
                reason = reasons[0]
            else:
                lock_status = DailyRiskLockStatus.UNLOCKED
                status = DailyRiskDecisionStatus.ALLOW
                reason = "DAILY_RISK_APPROVED"

        effective_state = replace(
            state,
            lock_status=lock_status,
            manual_halt_active=(status == DailyRiskDecisionStatus.MANUAL_HALT),
        )
        decision = DailyRiskDecision(
            decision_id=f"daily-risk-{uuid4().hex[:12]}",
            status=status,
            reason=reason,
            run_mode=run_mode_u,
            trading_day=effective_state.trading_day,
            timezone_name=effective_state.timezone_name,
            realized_pnl=effective_state.realized_pnl,
            unrealized_pnl=effective_state.unrealized_pnl,
            include_unrealized=include_unrealized,
            daily_trade_count=effective_state.daily_trade_count,
            losing_trade_count=effective_state.losing_trade_count,
            consecutive_losses=effective_state.consecutive_losses,
            lock_status=lock_status,
            existing_position_policy=policy,
            recommended_existing_position_action=self._recommended_existing_action(policy),
            reasons=tuple(reasons or [reason]),
            limit_snapshot=limit_snapshot,
            source_counts=effective_state.source_counts,
            audit_payload=dict(audit_payload or {}),
        )
        if run_mode_u != "READ_ONLY":
            self.state = effective_state
            self.last_decision = decision
        self._emit_decision(decision)
        return decision

    def _build_state_snapshot(
        self,
        *,
        now: datetime | None,
        run_mode: str,
        recovery_complete: bool,
    ) -> DailyRiskState:
        now_utc = self._as_aware(now or datetime.now(timezone.utc))
        trading_day = self.trading_day_for(now_utc)
        reset_key = f"{trading_day}:{self.timezone_name}:{self._reset_time_local().isoformat(timespec='minutes')}"
        event_metrics = self._metrics_from_events(trading_day)
        storage_metrics = self._metrics_from_storage(trading_day)
        lifecycle_metrics = self._metrics_from_lifecycle(trading_day, now=now_utc, run_mode=run_mode)
        broker_metrics = self._metrics_from_broker_fills(trading_day)

        realized_metrics = self._merge_realized_metrics(
            event_metrics,
            storage_metrics,
            broker_metrics,
            lifecycle_metrics,
            trading_day=trading_day,
        )
        realized = realized_metrics.realized_pnl
        trade_count = realized_metrics.daily_trade_count
        losing_count = realized_metrics.losing_trade_count
        consecutive_losses = realized_metrics.consecutive_losses

        source_counts = {
            "events": event_metrics.source_count,
            "storage": storage_metrics.source_count,
            "broker_fills": broker_metrics.source_count,
            "lifecycle": lifecycle_metrics.source_count,
        }
        recovered = True
        recovery_error = None
        source_metrics = {
            "events": event_metrics,
            "storage": storage_metrics,
            "broker_fills": broker_metrics,
            "lifecycle": lifecycle_metrics,
        }
        if realized_metrics.required_accounting and (
            realized_metrics.read_failed or any(metrics.read_failed for metrics in source_metrics.values())
        ):
            recovered = False
            errors = [metrics.failure_reason or "READ_FAILED" for metrics in source_metrics.values() if metrics.read_failed]
            if realized_metrics.failure_reason:
                errors.append(realized_metrics.failure_reason)
            recovery_error = "CANONICAL_ACCOUNTING_UNAVAILABLE:" + ",".join(dict.fromkeys(errors or ["INCOMPLETE"]))
        elif not recovery_complete:
            recovered = False
            recovery_error = "RECOVERY_NOT_COMPLETE"
        elif (str(run_mode or "").upper() == "PAPER" or
              str(run_mode or "").upper() == "LIVE" and self._bool_config("DAILY_RISK_LIVE_FAIL_CLOSED", True)):
            failed_reads = [
                f"{source}:{metrics.failure_reason or 'READ_FAILED'}"
                for source, metrics in source_metrics.items()
                if metrics.read_failed
            ]
            successful_read = any(
                metrics.read_attempted and not metrics.read_failed
                for metrics in source_metrics.values()
            )
            if failed_reads:
                recovered = False
                recovery_error = "DATA_UNAVAILABLE:" + ",".join(failed_reads)
            elif not successful_read:
                recovered = False
                recovery_error = "DAILY_RISK_STATE_UNRECONSTRUCTED"

        return DailyRiskState(
            trading_day=trading_day,
            timezone_name=self.timezone_name,
            realized_pnl=round(float(realized or 0.0), 2),
            unrealized_pnl=round(float(lifecycle_metrics.unrealized_pnl or 0.0), 2),
            daily_trade_count=int(trade_count or 0),
            losing_trade_count=int(losing_count or 0),
            consecutive_losses=int(consecutive_losses or 0),
            recovered=recovered,
            recovery_error=recovery_error,
            reset_key=reset_key,
            source_counts=source_counts,
        )

    def trading_day_for(self, timestamp: datetime) -> str:
        local = self._as_aware(timestamp).astimezone(self.timezone)
        reset_time = self._reset_time_local()
        resolved = local.date()
        if local.time() < reset_time:
            resolved = resolved - timedelta(days=1)
        return resolved.isoformat()

    def _metrics_from_events(self, trading_day: str) -> _DailyRiskMetrics:
        collector = self.event_collector
        if collector is None or not hasattr(collector, "snapshot_all"):
            return _DailyRiskMetrics()
        try:
            payloads = []
            for event in list(collector.snapshot_all() or []):
                if getattr(event, "event_type", None) != "TRADE_CLOSED":
                    continue
                payload = dict(getattr(event, "payload", {}) or {})
                timestamp = payload.get("closed_at") or payload.get("timestamp") or getattr(event, "timestamp", None)
                self._accounting_timestamp(timestamp)
                payload.update(timestamp=timestamp, event_id=getattr(event, "event_id", None) or payload.get("event_id"))
                payloads.append(payload)
            today = [row for row in payloads if self.trading_day_for(self._accounting_timestamp(row["timestamp"])) == trading_day]
            return replace(self._metrics_from_trade_payloads(today, read_attempted=True), history_payloads=tuple(payloads))
        except Exception:
            return _DailyRiskMetrics(read_attempted=True, read_failed=True, failure_reason="EVENT_HISTORY_READ_FAILED")

    def _metrics_from_storage(self, trading_day: str) -> _DailyRiskMetrics:
        storage = self.storage_engine
        store = getattr(storage, "_store", None)
        run_id = getattr(storage, "run_id", None)
        if store is None or not run_id:
            return _DailyRiskMetrics()
        payloads: list[dict[str, Any]] = []
        read_attempted = False
        for method_name, failure in (("fetch_trade_outcomes", "STORAGE_TRADE_OUTCOMES_READ_FAILED"),
                                     ("fetch_events", "STORAGE_EVENTS_READ_FAILED")):
            getter = getattr(store, method_name, None)
            if not callable(getter):
                continue
            read_attempted = True
            try:
                for row in list(getter(run_id) or []):
                    if method_name == "fetch_events" and str(row.get("event_type") or "") != "TRADE_CLOSED":
                        continue
                    payload = self._payload_from_storage_event(row)
                    # Outcome payload_json carries real identity on the existing
                    # schema.  A nullable outer column must not erase that fact.
                    payload.update({key: value for key, value in row.items()
                                    if value is not None and key not in {"payload", "payload_json"}})
                    timestamp = payload.get("closed_at") or payload.get("timestamp") or payload.get("created_at")
                    self._accounting_timestamp(timestamp)
                    payload["timestamp"] = timestamp
                    payloads.append(payload)
            except Exception:
                return _DailyRiskMetrics(read_attempted=True, read_failed=True, failure_reason=failure)
        today = [row for row in payloads if self.trading_day_for(self._accounting_timestamp(row["timestamp"])) == trading_day]
        return replace(self._metrics_from_trade_payloads(today, read_attempted=read_attempted), history_payloads=tuple(payloads))

    @staticmethod
    def _accounting_timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            result = value
        else:
            text = str(value or "").strip()
            if not text:
                raise ValueError("ACCOUNTING_TIMESTAMP_UNAVAILABLE")
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        # Preserve the established UTC interpretation of legacy naive stamps;
        # native bridge timestamps are explicitly required to carry a timezone.
        return DailyRiskGovernor._as_aware(result)

    @staticmethod
    def _finite_number(value: Any) -> float:
        if value is None or isinstance(value, bool):
            raise ValueError("ACCOUNTING_VALUE_UNAVAILABLE")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("ACCOUNTING_VALUE_NONFINITE")
        return result

    @staticmethod
    def _owner_root(payload: dict[str, Any]) -> tuple[str, str, str]:
        root = payload.get("root_order_id") or payload.get("lifecycle_trade_id") or payload.get("trade_id") or payload.get("client_order_id")
        account = payload.get("account") or payload.get("account_id") or payload.get("broker_account") or payload.get("acctNumber")
        strategy = payload.get("strategy_name") or payload.get("strategy")
        return str(account or ""), str(root or ""), str(strategy or "")

    def _metrics_from_lifecycle(self, trading_day: str, *, now: datetime,
                                run_mode: str | None = None) -> _DailyRiskMetrics:
        engine = self.trade_lifecycle_engine
        if engine is None:
            return _DailyRiskMetrics()
        getter = getattr(engine, "native_feedback_snapshot", None)
        if callable(getter):
            required: bool | None = None
            try:
                snapshot = getter()
                history_reader = getattr(engine, "committed_accounting_snapshot", None)
                history = (history_reader(run_mode=run_mode,trading_day_for=self.trading_day_for)
                    if callable(history_reader) else None)
                if history and history.get("required"):
                    # This is accounting inspection only. Runtime native/source
                    # fences and recovery/quarantine remain owned elsewhere.
                    independently_available = set(history["verified_historical_roots"])
                    if snapshot.get("available") is True:
                        independently_available.update(row["lifecycle_trade_id"] for row in snapshot.get("events", ()))
                    trades = {row["lifecycle_trade_id"]:row for row in snapshot.get("trades", ())}
                    trades.update({row["lifecycle_trade_id"]:row for row in history["trades"]})
                    snapshot = dict(snapshot, required=True,
                        available=snapshot.get("available") is True and history["available"],
                        events=[*snapshot.get("events", ()), *history["events"]],trades=list(trades.values()),
                        available_accounting_roots=independently_available,
                        historical_roots=history["historical_roots"],
                        historical_open_roots=history["open_roots"],
                        historical_reason=history.get("reason"))
                required = bool(snapshot.get("required"))
                available = bool(snapshot.get("available"))
                pending = bool(snapshot.get("pending"))
                uncertain = bool(snapshot.get("uncertain"))
                payloads = self._canonical_daily_payloads(snapshot, trading_day, available=available)
                metrics = self._metrics_from_trade_payloads(payloads, read_attempted=True, canonical=True)
                failed = required and (not available or pending or uncertain)
                fee_required = fee_failed = False
                fee_reason = None
                fee_reader = getattr(engine, "native_fee_feedback_snapshot", None)
                if callable(fee_reader):
                    try:
                        fees = fee_reader(now=now,
                            max_age_seconds=get_config("IBKR_SNAPSHOT_MAX_AGE_SECONDS"))
                        if not isinstance(fees, dict):
                            raise ValueError("NATIVE_FEE_SNAPSHOT_INVALID")
                        if history and history.get("fees", {}).get("required"):
                            historical_fees = history["fees"]
                            fees = dict(fees,required=True,
                                available=fees.get("available") is True and historical_fees["available"],
                                reason=fees.get("reason") or historical_fees.get("reason"),
                                evidence=[*fees.get("evidence", ()), *historical_fees["evidence"]],
                                covered_charges=[*fees.get("covered_charges", ()), *historical_fees["covered_charges"]])
                        fee_required = fees.get("required") is True
                        if fee_required:
                            self._project_native_fee_evidence(payloads, snapshot, fees, trading_day)
                            metrics = self._metrics_from_trade_payloads(payloads, read_attempted=True, canonical=True)
                            fee_failed = fees.get("available") is not True
                            fee_reason = str(fees.get("reason") or "INCOMPLETE")
                    except Exception as exc:
                        # Previously reconstructed facts remain visible when a
                        # required auxiliary source cannot establish completeness.
                        return replace(metrics, read_failed=True, required_accounting=True,
                            failure_reason="NATIVE_FEE_FEEDBACK_UNAVAILABLE:" + str(exc))
                include_unrealized = self._bool_config("DAILY_RISK_INCLUDE_UNREALIZED", False)
                raw_unrealized = snapshot.get("unrealized_pnl", 0.0)
                if not failed and required and include_unrealized:
                    try:
                        if snapshot.get("historical_open_roots"):
                            raise ValueError("COMMITTED_OPEN_POSITION_HAS_NO_FRESH_VALUATION_AUTHORITY")
                        valuation_reader = getattr(engine, "native_valuation_snapshot", None)
                        valuation = (valuation_reader(now=now,
                            max_age_seconds=get_config("IBKR_SNAPSHOT_MAX_AGE_SECONDS"))
                            if callable(valuation_reader) else None)
                        if not isinstance(valuation, dict) or valuation.get("available") is not True:
                            detail = valuation.get("reason") if isinstance(valuation, dict) else "OWNER_UNAVAILABLE"
                            raise ValueError(str(detail or "INCOMPLETE"))
                        raw_unrealized = (self._finite_number(valuation.get("unrealized_pnl"))
                            + self._finite_number(valuation.get("legacy_unrealized_pnl", 0.0)))
                    except Exception as exc:
                        # Valuation uncertainty must retain already committed
                        # realized deltas and counts, never replace them by zero.
                        return replace(metrics, read_failed=True, required_accounting=True,
                            failure_reason="NATIVE_UNREALIZED_VALUATION_UNAVAILABLE:" + str(exc))
                try:
                    if snapshot.get("historical_roots"):
                        # Recovered native snapshots can carry old mark values,
                        # including when financial history is incomplete. None
                        # grants fresh valuation authority in this process.
                        raw_unrealized = sum(self._finite_number(row.get("unrealized_pnl",0.))
                            for row in snapshot.get("trades",())
                            if row["lifecycle_trade_id"] not in snapshot["historical_roots"]
                            and row.get("quantity_open",0) > 0)
                    unrealized = self._finite_number(raw_unrealized)
                except (TypeError, ValueError) as exc:
                    if include_unrealized:
                        if required:
                            return replace(metrics, read_failed=True, required_accounting=True,
                                failure_reason="NATIVE_UNREALIZED_VALUATION_UNAVAILABLE:" + str(exc))
                        raise
                    # Excluded valuation cannot erase committed realized data.
                    # include_unrealized=False makes this an ignored projection.
                    unrealized = 0.0
                return replace(metrics,
                    unrealized_pnl=unrealized,
                    required_accounting=required or fee_required or metrics.required_accounting,
                    read_failed=failed or fee_failed,
                    failure_reason=(("NATIVE_FEEDBACK_UNCERTAIN" if uncertain else "NATIVE_FEEDBACK_PENDING" if pending else snapshot.get("historical_reason") or "NATIVE_FEEDBACK_UNAVAILABLE") if failed
                        else "NATIVE_FEE_FEEDBACK_UNAVAILABLE:" + fee_reason if fee_failed else None))
            except Exception as exc:
                return _DailyRiskMetrics(read_attempted=True, read_failed=True,
                    required_accounting=required is not False,
                    failure_reason="LIFECYCLE_ACCOUNTING_INVALID:" + str(exc))
        try:
            if hasattr(engine, "build_portfolio_state"):
                state = engine.build_portfolio_state()
                realized = self._finite_number(getattr(state, "total_realized_pnl", 0.0))
                # An undated aggregate is not a trade/fill identity and cannot
                # establish either daily attribution or mixed-source dedupe.
                return _DailyRiskMetrics(unrealized_pnl=self._finite_number(getattr(state, "total_unrealized_pnl", 0.0)),
                    source_count=1, read_attempted=True, read_failed=bool(realized),
                    failure_reason="LIFECYCLE_REALIZED_IDENTITY_UNAVAILABLE" if realized else None)
            if hasattr(engine, "get_open_lifecycle_trades"):
                trades = list(engine.get_open_lifecycle_trades() or [])
                return _DailyRiskMetrics(unrealized_pnl=round(sum(float(getattr(t, "unrealized_pnl", 0.0) or 0.0) for t in trades), 2),
                    source_count=len(trades), read_attempted=True)
        except Exception:
            return _DailyRiskMetrics(read_attempted=True, read_failed=True, failure_reason="LIFECYCLE_READ_FAILED")
        return _DailyRiskMetrics()

    def _project_native_fee_evidence(self, payloads: list[dict[str, Any]], snapshot: dict[str, Any],
                                     fees: dict[str, Any], trading_day: str) -> None:
        """Apply committed charges to one existing root payload, never a second trade."""
        roots = {self._owner_root(row): row for row in payloads if row.get("_native")}
        executions: dict[tuple[tuple[str, str, str], str], dict[str, Any]] = {}
        basis: dict[tuple[str, str, str], list[str]] = {}
        for event in snapshot.get("events", ()):
            identity = (event.get("metadata") or {}).get("native_identity") or {}
            owner = self._owner_root(identity)
            execution_id = event.get("execution_id")
            if owner not in roots or not isinstance(execution_id, str) or not execution_id:
                raise ValueError("NATIVE_FEE_FINANCIAL_IDENTITY_UNAVAILABLE")
            key = (owner, execution_id)
            if key in executions:
                raise ValueError("NATIVE_FEE_FINANCIAL_EXECUTION_CONFLICT")
            executions[key] = event
            basis.setdefault(owner, []).append(event["event_id"])

        covered: dict[tuple[tuple[str, str, str], str], tuple[Decimal, str, str]] = {}
        zero_witnesses: dict[tuple[tuple[str, str, str], str], dict[str, Any]] = {}
        for charge in fees.get("covered_charges", ()):
            owner = self._owner_root(charge)
            execution_id = charge.get("execution_id")
            event = executions.get((owner, execution_id))
            if event is None or owner not in roots:
                raise ValueError("NATIVE_FEE_COVERAGE_IDENTITY_CONFLICT")
            identity = event["metadata"]["native_identity"]
            if (charge.get("symbol") != roots[owner]["symbol"]
                    or str(charge.get("native_order_id")) != str(identity["native_order_id"])):
                raise ValueError("NATIVE_FEE_COVERAGE_BINDING_CONFLICT")
            amount = Decimal(str(charge.get("amount")))
            self._finite_number(amount)
            if not amount.is_finite() or amount < 0:
                raise ValueError("NATIVE_FEE_COVERAGE_AMOUNT_INVALID")
            if amount == 0:
                from src.adapters.brokers.ibkr.ibkr_client import (
                    SDK_COMMISSION_PRESENCE_SOURCE, SDK_COMMISSION_SCHEMA)
                witness = charge.get("zero_commission_witness")
                keys = {"commission_field_present", "commission_presence_source", "commission_decoder_schema",
                    "commission_client_object_id", "commission_decoder_object_id", "commission_decoder_epoch",
                    "commission_decoder_generation", "commission_decoder_thread_id"}
                if (not isinstance(witness, Mapping) or set(witness) != keys
                        or witness.get("commission_field_present") is not True
                        or witness.get("commission_presence_source") != SDK_COMMISSION_PRESENCE_SOURCE
                        or witness.get("commission_decoder_schema") != SDK_COMMISSION_SCHEMA
                        or any(type(witness.get(key)) is not int or witness[key] <= 0 for key in (
                            "commission_client_object_id", "commission_decoder_object_id", "commission_decoder_thread_id"))
                        or type(witness.get("commission_decoder_epoch")) is not int
                        or witness["commission_decoder_epoch"] != identity["connection_epoch"]
                        or type(witness.get("commission_decoder_generation")) is not int
                        or witness["commission_decoder_generation"] != 1):
                    raise ValueError("NATIVE_FEE_ZERO_COMMISSION_WITNESS_REQUIRED")
                key = (owner, execution_id)
                if key in zero_witnesses and zero_witnesses[key] != dict(witness):
                    raise ValueError("NATIVE_FEE_ZERO_COMMISSION_WITNESS_CONFLICT")
                zero_witnesses[key] = dict(witness)
            currency = charge.get("currency")
            day = charge.get("trading_day")
            if (not isinstance(currency, str) or len(currency) != 3 or not currency.isascii()
                    or not currency.isalpha() or currency != currency.upper()
                    or day != self.trading_day_for(self._accounting_timestamp(event["timestamp"]))):
                raise ValueError("NATIVE_FEE_COVERAGE_UNIT_OR_DAY_CONFLICT")
            value = (amount, currency, day)
            old = covered.get((owner, execution_id))
            if old is not None and old != value:
                raise ValueError("NATIVE_FEE_COVERAGE_CONFLICT")
            covered[(owner, execution_id)] = value

        for owner, payload in roots.items():
            charges = {execution_id: value for (key, execution_id), value in covered.items() if key == owner}
            if not charges:
                continue
            currencies = {row[1] for row in charges.values()}
            if len(currencies) != 1:
                raise ValueError("NATIVE_FEE_COVERAGE_CURRENCY_CONFLICT")
            payload["_known_fee_total"] = round(float(sum((row[0] for row in charges.values()), Decimal(0))), 4)
            payload["_known_fee_day"] = round(float(sum((row[0] for row in charges.values()
                if row[2] == trading_day), Decimal(0))), 4)
            matching = ([row for row in fees.get("evidence", ())
                if self._owner_root(row) == owner and row.get("matched_current_basis") is True]
                if payload["_closed"] else [])
            for evidence in matching:
                ids = tuple(evidence.get("basis_event_ids") or ())
                execution_ids = tuple(evidence.get("execution_ids") or ())
                expected_ids = {execution_id for (key, execution_id) in executions if key == owner}
                days = {self.trading_day_for(self._accounting_timestamp(event["timestamp"]))
                    for (key, _), event in executions.items() if key == owner}
                terminal = self._accounting_timestamp(evidence.get("terminal_timestamp"))
                if (not payload["_closed"] or ids != tuple(basis[owner])
                        or len(execution_ids) != len(expected_ids) or set(execution_ids) != expected_ids
                        or set(charges) != expected_ids or len(days) != 1
                        or evidence.get("trading_day") not in days
                        or evidence.get("currency") not in currencies
                        or evidence.get("symbol") != payload["symbol"]
                        or terminal != self._accounting_timestamp(payload["timestamp"])
                        or round(self._finite_number(evidence.get("gross_realized_pnl")), 2) != round(payload["_all_pnl"], 2)
                        or round(self._finite_number(evidence.get("total_commission")), 4) != payload["_known_fee_total"]):
                    raise ValueError("NATIVE_FEE_COMPLETE_BASIS_CONFLICT")
                gross = round(payload["_all_pnl"], 2)
                summary = dict(trade_id=owner[1], account=owner[0], strategy_name=owner[2],
                    symbol=payload["symbol"], gross_realized_pnl=gross,
                    commission=payload["_known_fee_total"],
                    net_realized_pnl=round(gross-payload["_known_fee_total"], 2),
                    timestamp=terminal, closed_at=terminal)
                if payload.get("_native_fee_summary") not in (None, summary):
                    raise ValueError("NATIVE_FEE_COMPLETE_EVIDENCE_CONFLICT")
                payload["_native_fee_summary"] = summary
            self._project_native_overlaps(payload, [], trading_day)

    def _project_native_overlaps(self, native: dict[str, Any], overlaps: list[dict[str, Any]],
                                 trading_day: str | None) -> None:
        # This helper may run once for known canonical metrics and again for
        # mixed history. Always restart from the immutable gross fill facts.
        native["realized_pnl"] = sum(row["pnl"] for row in native["_exits"]
            if trading_day is None or self.trading_day_for(row["timestamp"]) == trading_day)
        native["_terminal_pnl"] = native["_all_pnl"]
        summary = native.get("_native_fee_summary")
        if summary is not None:
            self._merge_native_overlap(native, [summary, *overlaps], trading_day)
            return
        known = native.get("_known_fee_total", 0.0)
        if "_known_fee_total" in native and any(self._net_payload(row) for row in overlaps):
            # A prior completed basis has known charges, but no current complete
            # basis exists to reconcile their overlap with another NET result.
            raise ValueError("NATIVE_FEE_COVERAGE_OVERLAP_UNRESOLVED")
        if overlaps:
            self._merge_native_overlap(native, overlaps, trading_day)
        native["realized_pnl"] -= native.get("_known_fee_day", 0.0)
        native["_terminal_pnl"] -= known

    def _canonical_daily_payloads(self, snapshot: dict[str, Any], trading_day: str, *, available: bool) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        seen_events: dict[str, dict[str, Any]] = {}
        trades = {str(row["lifecycle_trade_id"]): row for row in snapshot.get("trades", [])}
        for row in snapshot.get("events", []):
            event = dict(row)
            event_id = str(event.get("event_id") or "")
            if not event_id:
                raise ValueError("CANONICAL_EVENT_ID_UNAVAILABLE")
            if event_id in seen_events:
                if seen_events[event_id] != event:
                    raise ValueError("CANONICAL_EVENT_ID_CONFLICT")
                continue
            seen_events[event_id] = event
            metadata = event.get("metadata") or {}
            if metadata.get("native_feedback_committed") is not True:
                raise ValueError("CANONICAL_EVENT_NOT_COMMITTED")
            identity = metadata.get("native_identity") or {}
            key = self._owner_root(identity)
            if not all(key) or key[1] != str(event.get("lifecycle_trade_id") or ""):
                raise ValueError("CANONICAL_ROOT_IDENTITY_INVALID")
            if str(identity.get("side") or "").upper() != "LONG" or str(event.get("side") or "").upper() != "LONG":
                raise ValueError("CANONICAL_SIDE_INVALID")
            symbol = str(event.get("symbol") or "").upper()
            if not symbol or symbol != str(identity.get("symbol") or "").upper():
                raise ValueError("CANONICAL_SYMBOL_INVALID")
            timestamp = self._accounting_timestamp(event.get("timestamp"))
            if isinstance(event.get("timestamp"), str) and datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("CANONICAL_TIMESTAMP_UNZONED")
            quantity = self._finite_number(event.get("quantity"))
            before = self._finite_number(metadata.get("quantity_before"))
            after = self._finite_number(metadata.get("quantity_after"))
            increment = self._finite_number(metadata.get("realized_increment"))
            self._finite_number(event.get("price"))
            if quantity <= 0 or quantity != int(quantity) or min(before, after) < 0 or before != int(before) or after != int(after):
                raise ValueError("CANONICAL_QUANTITY_INVALID")
            group = groups.setdefault(key, dict(symbol=symbol, quantity=0, pnl=0.0, day_pnl=0.0, exits=[], opened_at=timestamp))
            if group["symbol"] != symbol or group["quantity"] != int(before):
                raise ValueError("CANONICAL_QUANTITY_CHAIN_INVALID")
            entry = str(event.get("event_type") or "").upper() == "ENTRY_FILL"
            if entry:
                if after != before + quantity or increment != 0:
                    raise ValueError("CANONICAL_ENTRY_PROJECTION_INVALID")
            else:
                if str(event.get("event_type") or "").upper().startswith("TAKE_PROFIT"):
                    raise ValueError("CANONICAL_TARGET_EVENT_INVALID")
                if after != before - quantity or quantity > before or bool(metadata.get("terminal")) != (after == 0):
                    raise ValueError("CANONICAL_EXIT_PROJECTION_INVALID")
                group["exits"].append(dict(timestamp=timestamp, pnl=increment, quantity=int(quantity),
                    price=self._finite_number(event["price"]), native_order_id=str(identity.get("native_order_id") or ""),
                    client_id=identity.get("client_id"), connection_epoch=identity.get("connection_epoch"), con_id=identity.get("con_id"),
                    ids={str(event.get("execution_id") or "")}))
                if self.trading_day_for(timestamp) == trading_day:
                    group["day_pnl"] += increment
            group["quantity"] = int(after)
            group["pnl"] += increment
            if not math.isclose(group["pnl"], self._finite_number(metadata.get("trade_pnl_after")), abs_tol=1e-8):
                raise ValueError("CANONICAL_REALIZED_CHAIN_INVALID")
        result = []
        for (account, root, strategy), group in groups.items():
            trade = trades.get(root)
            if trade is None:
                raise ValueError("CANONICAL_TRADE_UNAVAILABLE")
            closed = False
            if available or root in snapshot.get("available_accounting_roots", ()):
                if int(trade.get("quantity_open", -1)) != group["quantity"] or not math.isclose(self._finite_number(trade.get("gross_realized_pnl")), group["pnl"], abs_tol=1e-8):
                    raise ValueError("CANONICAL_SNAPSHOT_CONFLICT")
                if str(trade.get("side") or "").upper() != "LONG" or str(trade.get("strategy_name") or "") != strategy:
                    raise ValueError("CANONICAL_TRADE_OWNERSHIP_INVALID")
                closed = group["quantity"] == 0 and str(trade.get("status") or "").upper() == "CLOSED"
            exits = group["exits"]
            terminal_time = max((row["timestamp"] for row in exits), default=group["opened_at"])
            terminal_day = self.trading_day_for(terminal_time)
            result.append(dict(trade_id=root, account=account, strategy_name=strategy, symbol=group["symbol"],
                realized_pnl=group["day_pnl"], timestamp=terminal_time,
                _native=True, _completed=closed and terminal_day == trading_day,
                _closed=closed, _terminal_day=terminal_day, _terminal_pnl=group["pnl"],
                _all_pnl=group["pnl"], _exit_days={self.trading_day_for(row["timestamp"]) for row in exits},
                _exits=exits))
        # Legacy canonical CLOSED snapshots retain real identity/date.  An open
        # legacy partial has no per-exit day carrier and cannot be called zero.
        native_roots = {key[1] for key in groups}
        for root, trade in trades.items():
            if root in native_roots:
                continue
            realized = self._finite_number(trade.get("gross_realized_pnl", 0.0))
            if int(trade.get("quantity_open", 0)) > 0:
                if realized:
                    raise ValueError("LEGACY_PARTIAL_DAY_ATTRIBUTION_UNAVAILABLE")
                continue
            if str(trade.get("status") or "").upper() != "CLOSED":
                continue
            timestamp = self._accounting_timestamp(trade.get("closed_at"))
            if self.trading_day_for(timestamp) == trading_day:
                result.append(dict(trade_id=root, symbol=trade.get("symbol"), strategy_name=trade.get("strategy_name"),
                    realized_pnl=realized, timestamp=timestamp, _completed=True, _terminal_pnl=realized))
        return result

    def _metrics_from_broker_fills(self, trading_day: str) -> _DailyRiskMetrics:
        provider = self.provider
        if provider is None:
            return _DailyRiskMetrics()
        for method_name in ("get_daily_fills", "get_fills", "get_executions"):
            getter = getattr(provider, method_name, None)
            if not callable(getter):
                continue
            try:
                fills = list(getter() or [])
            except Exception:
                return _DailyRiskMetrics(
                    read_attempted=True,
                    read_failed=True,
                    failure_reason=f"BROKER_FILLS_READ_FAILED:{method_name}",
                )
            payloads = []
            try:
                for fill in fills:
                    payload = self._fill_payload(fill)
                    timestamp = payload.get("timestamp")
                    self._accounting_timestamp(timestamp)
                    payloads.append(payload)
                today = [row for row in payloads if self.trading_day_for(self._accounting_timestamp(row["timestamp"])) == trading_day]
                return replace(self._metrics_from_trade_payloads(today, read_attempted=True), history_payloads=tuple(payloads), source_kind="fill")
            except Exception:
                return _DailyRiskMetrics(read_attempted=True, read_failed=True,
                    failure_reason="BROKER_FILLS_ACCOUNTING_INVALID")
        return _DailyRiskMetrics()

    def _merge_realized_metrics(self, *source_metrics: _DailyRiskMetrics,
                                trading_day: str | None = None) -> _DailyRiskMetrics:
        canonical = []
        legacy = []
        required = any(metrics.required_accounting for metrics in source_metrics)
        try:
            for metrics in source_metrics:
                history = metrics.trade_payloads if metrics.canonical_payloads else (metrics.history_payloads or metrics.trade_payloads)
                for item in history:
                    payload = dict(item)
                    if metrics.canonical_payloads:
                        canonical.append(payload)
                    else:
                        payload = {key: value for key, value in payload.items() if not key.startswith("_")}
                        payload["_history_kind"] = metrics.source_kind
                        legacy.append(payload)
            native = [payload for payload in canonical if payload.get("_native")]
            ordinary = [payload for payload in canonical if not payload.get("_native")]
            resolved: dict[tuple[str, ...], dict[str, Any]] = {}
            native_overlaps: dict[int, list[dict[str, Any]]] = {}
            for payload in legacy + ordinary:
                owner = self._owner_root(payload)
                fill_ids = {str(payload[key]) for key in ("fill_id", "execution_id", "broker_fill_id", "exec_id", "execId") if payload.get(key) is not None}
                fill_candidates = [index for index, row in enumerate(native)
                    if any(fill_ids.intersection(event["ids"]) for event in row["_exits"])
                    and (not owner[0] or self._owner_root(row)[0] == owner[0])
                    and (not owner[2] or self._owner_root(row)[2] == owner[2])]
                if fill_candidates:
                    if len(fill_candidates) != 1:
                        raise ValueError("NATIVE_FILL_IDENTITY_AMBIGUOUS")
                    match = native[fill_candidates[0]]
                    explicit_root = payload.get("root_order_id") or payload.get("lifecycle_trade_id") or payload.get("trade_id")
                    if explicit_root and str(explicit_root) != self._owner_root(match)[1]:
                        raise ValueError("NATIVE_FILL_ROOT_CONFLICT")
                    payload["trade_id"] = self._owner_root(match)[1]
                    owner = self._owner_root(payload)
                same_root = [index for index, row in enumerate(native) if owner[1] and self._owner_root(row)[1] == owner[1]]
                candidates = [index for index in same_root
                    if (not owner[0] or self._owner_root(native[index])[0] == owner[0])
                    and (not owner[2] or self._owner_root(native[index])[2] == owner[2])]
                if same_root and len(candidates) != 1:
                    raise ValueError("NATIVE_HISTORY_OWNERSHIP_CONFLICT")
                if not owner[1] and native:
                    # Symbol/time/PnL similarity cannot prove trade identity.
                    possible = [row for row in native if str(payload.get("symbol") or "").upper() == row.get("symbol")
                        and (not owner[2] or owner[2] == self._owner_root(row)[2])
                        and (not owner[0] or owner[0] == self._owner_root(row)[0])]
                    if possible:
                        raise ValueError("NATIVE_HISTORY_IDENTITY_UNAVAILABLE")
                if candidates:
                    symbol = payload.get("symbol")
                    if symbol is not None and str(symbol).upper() != native[candidates[0]]["symbol"]:
                        raise ValueError("NATIVE_HISTORY_SYMBOL_CONFLICT")
                    native_overlaps.setdefault(candidates[0], []).append(payload)
                    continue
                if trading_day is not None and self.trading_day_for(self._accounting_timestamp(payload.get("timestamp"))) != trading_day:
                    continue
                identity = self._trade_identity(payload)
                previous = resolved.get(identity)
                if owner[1]:
                    matches = [(key, row) for key, row in resolved.items()
                        if self._owner_root(row)[1] == owner[1]
                        and (not owner[0] or not self._owner_root(row)[0] or owner[0] == self._owner_root(row)[0])
                        and (not owner[2] or not self._owner_root(row)[2] or owner[2] == self._owner_root(row)[2])]
                    if len(matches) > 1:
                        raise ValueError("HISTORY_OWNER_IDENTITY_AMBIGUOUS")
                    if matches:
                        identity, previous = matches[0]
                if previous is not None:
                    previous_net = any(previous.get(key) is not None for key in ("net_realised_pnl", "net_realized_pnl"))
                    current_net = any(payload.get(key) is not None for key in ("net_realised_pnl", "net_realized_pnl"))
                    if previous_net == current_net and not math.isclose(self._payload_pnl(previous), self._payload_pnl(payload), abs_tol=1e-8):
                        raise ValueError("DUPLICATE_HISTORY_PNL_CONFLICT")
                    # Preserve the established net-before-gross convention.
                    if current_net and not previous_net:
                        resolved[identity] = payload
                    continue
                resolved[identity] = payload
            for index, payload in enumerate(native):
                overlaps = native_overlaps.get(index, [])
                self._project_native_overlaps(payload, overlaps, trading_day)
                resolved[("native",) + self._owner_root(payload)] = payload
            payloads = list(resolved.values())
            payloads.sort(key=lambda row: self._accounting_timestamp(row.get("timestamp")))
            merged = self._metrics_from_trade_payloads(payloads, read_attempted=any(m.read_attempted for m in source_metrics), canonical=True)
            return replace(merged, required_accounting=required,
                read_failed=any(m.read_failed for m in source_metrics))
        except Exception as exc:
            # Keep known committed canonical facts visible, with unavailable
            # reconstruction explicitly blocking entries.  Unknown history is
            # never presented as a successfully reconstructed factual zero.
            known = next((metrics for metrics in source_metrics if metrics.canonical_payloads), _DailyRiskMetrics(read_attempted=True))
            return replace(known, read_failed=True, required_accounting=required,
                failure_reason="ACCOUNTING_MERGE_INVALID:" + str(exc))

    @staticmethod
    def _net_payload(payload: dict[str, Any]) -> bool:
        return any(payload.get(key) is not None for key in ("net_realised_pnl", "net_realized_pnl"))

    def _overlap_pnl(self, rows: list[dict[str, Any]], gross: float) -> tuple[float, bool]:
        net_rows = [row for row in rows if self._net_payload(row)]
        preferred = net_rows or rows
        value = self._payload_pnl(preferred[0])
        if any(round(self._payload_pnl(row), 2) != round(value, 2) for row in preferred[1:]):
            raise ValueError("NATIVE_HISTORY_PNL_CONFLICT")
        for row in rows:
            explicit_gross = row.get("gross_realised_pnl", row.get("gross_realized_pnl"))
            if explicit_gross is not None and round(self._finite_number(explicit_gross), 2) != round(gross, 2):
                raise ValueError("NATIVE_HISTORY_GROSS_CONFLICT")
            candidate = self._payload_pnl(row)
            if round(candidate, 2) not in {round(value, 2), round(gross, 2)}:
                raise ValueError("NATIVE_HISTORY_PNL_CONFLICT")
            if self._net_payload(row) and explicit_gross is not None and row.get("commission") is not None:
                expected_net = round(self._finite_number(explicit_gross) - self._finite_number(row["commission"]), 2)
                if round(candidate, 2) != expected_net:
                    raise ValueError("NATIVE_HISTORY_COMMISSION_CONFLICT")
        return value, bool(net_rows)

    def _merge_native_overlap(self, native: dict[str, Any], overlaps: list[dict[str, Any]], trading_day: str | None) -> None:
        per_fill: dict[int, list[dict[str, Any]]] = {}
        summaries = []
        for row in overlaps:
            ids = {str(row[key]) for key in ("fill_id", "execution_id", "broker_fill_id", "exec_id", "execId") if row.get(key) is not None}
            matches = [index for index, event in enumerate(native["_exits"]) if ids.intersection(event["ids"])]
            if row.get("_history_kind") == "fill" and ids and not row.get("closed_at"):
                if len(matches) != 1:
                    raise ValueError("NATIVE_FILL_IDENTITY_CONFLICT")
                index = matches[0]
                event = native["_exits"][index]
                if self._accounting_timestamp(row.get("timestamp")) != event["timestamp"]:
                    raise ValueError("NATIVE_FILL_TIMESTAMP_CONFLICT")
                native_id = row.get("order_id", row.get("ibkr_order_id", row.get("orderId")))
                if native_id is not None and str(native_id) != event["native_order_id"]:
                    raise ValueError("NATIVE_FILL_ORDER_CONFLICT")
                client_id = row.get("client_id", row.get("clientId"))
                if client_id is not None and client_id != event["client_id"]:
                    raise ValueError("NATIVE_FILL_CLIENT_CONFLICT")
                if row.get("connection_epoch") is not None and row["connection_epoch"] != event["connection_epoch"]:
                    raise ValueError("NATIVE_FILL_EPOCH_CONFLICT")
                con_id = row.get("con_id", row.get("conId"))
                if con_id is not None and con_id != event["con_id"]:
                    raise ValueError("NATIVE_FILL_SECURITY_CONFLICT")
                if row.get("side") is not None and str(row["side"]).upper() not in {"SELL", "SLD"}:
                    raise ValueError("NATIVE_FILL_SIDE_CONFLICT")
                for field in ("quantity", "filled_quantity", "shares"):
                    if row.get(field) is not None and self._finite_number(row[field]) != event["quantity"]:
                        raise ValueError("NATIVE_FILL_QUANTITY_CONFLICT")
                for field in ("price", "execution_price", "fill_price", "avgFillPrice", "average_fill_price"):
                    if row.get(field) is not None and not math.isclose(self._finite_number(row[field]), event["price"], abs_tol=1e-8):
                        raise ValueError("NATIVE_FILL_PRICE_CONFLICT")
                per_fill.setdefault(index, []).append(row)
            else:
                summaries.append(row)
        adjustments = 0.0
        day_adjustments = 0.0
        net_coverage: set[int] = set()
        for index, rows in per_fill.items():
            event = native["_exits"][index]
            value, is_net = self._overlap_pnl(rows, event["pnl"])
            if is_net:
                net_coverage.add(index)
            adjustment = value-event["pnl"]
            adjustments += adjustment
            if trading_day is None or self.trading_day_for(event["timestamp"]) == trading_day:
                day_adjustments += adjustment
        native["realized_pnl"] += day_adjustments
        native["_terminal_pnl"] = native["_all_pnl"] + adjustments
        if not summaries:
            return
        if not native["_closed"]:
            raise ValueError("NATIVE_OPEN_TRADE_HAS_CLOSED_OUTCOME")
        outcome, is_net = self._overlap_pnl(summaries, native["_all_pnl"])
        if (is_net and native["_exits"] and len(net_coverage) == len(native["_exits"])
                and round(outcome, 2) != round(native["_terminal_pnl"], 2)):
            # Both sources now describe the complete NET result.  Summary
            # precedence over gross facts cannot override this contradiction.
            raise ValueError("NATIVE_NET_SUMMARY_CONFLICT")
        if len(native["_exit_days"]) > 1:
            expected = native["_terminal_pnl"] if is_net else native["_all_pnl"]
            if round(outcome, 2) != round(expected, 2):
                # Whole-trade net difference lacks a per-execution/day fee
                # allocation.  Known per-execution adjustments remain usable.
                raise ValueError("NATIVE_NET_DAY_ATTRIBUTION_UNAVAILABLE")
        elif native["_completed"] and (is_net or not adjustments):
            native["realized_pnl"] = outcome
        if is_net or not adjustments:
            native["_terminal_pnl"] = outcome

    def _payload_pnl(self, payload: dict[str, Any]) -> float:
        for key in ("net_realised_pnl", "net_realized_pnl", "realised_pnl", "realized_pnl", "pnl", "gross_realised_pnl", "gross_realized_pnl"):
            if payload.get(key) is not None:
                return self._finite_number(payload[key])
        raise ValueError("REALIZED_PNL_UNAVAILABLE")

    def _metrics_from_trade_payloads(self, payloads: Iterable[dict[str, Any]], *,
                                   read_attempted: bool = True, canonical: bool = False) -> _DailyRiskMetrics:
        realized = 0.0
        terminal_pnls = []
        normalized = [dict(payload) for payload in payloads]
        try:
            for payload in normalized:
                realized += self._payload_pnl(payload)
                completed = bool(payload.get("_completed", True)) if canonical else True
                if completed:
                    terminal_pnls.append(self._finite_number(payload.get("_terminal_pnl", self._payload_pnl(payload))) if canonical else self._payload_pnl(payload))
        except Exception as exc:
            return _DailyRiskMetrics(read_attempted=read_attempted, read_failed=True,
                failure_reason="REALIZED_ACCOUNTING_INVALID:" + str(exc), required_accounting=canonical)
        consecutive = 0
        for pnl in reversed(terminal_pnls):
            if pnl < 0:
                consecutive += 1
            else:
                break
        return _DailyRiskMetrics(realized_pnl=round(realized, 2), daily_trade_count=len(terminal_pnls),
            losing_trade_count=sum(pnl < 0 for pnl in terminal_pnls), consecutive_losses=consecutive,
            source_count=len(normalized), read_attempted=read_attempted, trade_payloads=tuple(normalized),
            canonical_payloads=canonical)

    def _breach_reasons(self, state: DailyRiskState, *, include_unrealized: bool) -> list[str]:
        reasons: list[str] = []
        loss_pnl = state.total_pnl_for_loss_limit if include_unrealized else state.realized_pnl
        loss_amount = self._float_config("DAILY_RISK_MAX_LOSS_AMOUNT", 10.0)
        if loss_amount > 0 and loss_pnl <= -abs(loss_amount):
            reasons.append("MAX_DAILY_LOSS_AMOUNT")
        loss_pct = self._float_config("DAILY_RISK_MAX_LOSS_PCT", 0.0)
        if loss_pct > 0:
            threshold = self._account_equity() * (loss_pct / 100.0)
            if threshold > 0 and loss_pnl <= -abs(threshold):
                reasons.append("MAX_DAILY_LOSS_PCT")
        drawdown_pnl = loss_pnl
        drawdown_amount = self._float_config("DAILY_RISK_MAX_DRAWDOWN_AMOUNT", 0.0)
        if drawdown_amount > 0 and drawdown_pnl <= -abs(drawdown_amount):
            reasons.append("MAX_DAILY_DRAWDOWN_AMOUNT")
        drawdown_pct = self._float_config("DAILY_RISK_MAX_DRAWDOWN_PCT", 0.0)
        if drawdown_pct > 0:
            threshold = self._account_equity() * (drawdown_pct / 100.0)
            if threshold > 0 and drawdown_pnl <= -abs(threshold):
                reasons.append("MAX_DAILY_DRAWDOWN_PCT")
        max_trades = self._int_config("DAILY_RISK_MAX_TRADES", 0)
        if max_trades > 0 and state.daily_trade_count >= max_trades:
            reasons.append("MAX_DAILY_TRADES")
        max_losing_trades = self._int_config("DAILY_RISK_MAX_LOSING_TRADES", 0)
        if max_losing_trades > 0 and state.losing_trade_count >= max_losing_trades:
            reasons.append("MAX_LOSING_TRADES")
        max_consecutive_losses = self._int_config("DAILY_RISK_MAX_CONSECUTIVE_LOSSES", 0)
        if max_consecutive_losses > 0 and state.consecutive_losses >= max_consecutive_losses:
            reasons.append("MAX_CONSECUTIVE_LOSSES")
        return reasons

    def _status_for_locked_policy(
        self,
        policy: DailyRiskExistingPositionPolicy,
        *,
        is_new_entry: bool,
    ) -> DailyRiskDecisionStatus:
        if not is_new_entry and policy == DailyRiskExistingPositionPolicy.MANAGED_ONLY:
            return DailyRiskDecisionStatus.MANAGED_ONLY
        if policy == DailyRiskExistingPositionPolicy.MANAGED_ONLY:
            return DailyRiskDecisionStatus.MANAGED_ONLY
        if policy == DailyRiskExistingPositionPolicy.FLATTEN:
            return DailyRiskDecisionStatus.LOCKED
        return DailyRiskDecisionStatus.BLOCK_NEW_ENTRIES

    def _recommended_existing_action(self, policy: DailyRiskExistingPositionPolicy) -> str:
        if policy == DailyRiskExistingPositionPolicy.FLATTEN:
            return "FLATTEN_MANUAL_REVIEW"
        if policy == DailyRiskExistingPositionPolicy.HOLD:
            return "HOLD_EXISTING_POSITIONS"
        return "MANAGE_EXISTING_POSITIONS_ONLY"

    def _emit_decision(self, decision: DailyRiskDecision) -> None:
        collector = self.event_collector
        if collector is None or not hasattr(collector, "emit"):
            return
        try:
            collector.emit(
                event_type="DAILY_RISK_DECISION",
                source="DailyRiskGovernor",
                payload=decision.to_event_payload(),
                include_cycle=True,
            )
        except Exception as exc:
            print(f"[DAILY_RISK][AUDIT][FAILED] reason={exc}")

    def _limit_snapshot(self) -> dict[str, Any]:
        return {
            "max_loss_amount": self._float_config("DAILY_RISK_MAX_LOSS_AMOUNT", 10.0),
            "max_loss_pct": self._float_config("DAILY_RISK_MAX_LOSS_PCT", 0.0),
            "max_drawdown_amount": self._float_config("DAILY_RISK_MAX_DRAWDOWN_AMOUNT", 0.0),
            "max_drawdown_pct": self._float_config("DAILY_RISK_MAX_DRAWDOWN_PCT", 0.0),
            "include_unrealized": self._bool_config("DAILY_RISK_INCLUDE_UNREALIZED", False),
            "max_trades": self._int_config("DAILY_RISK_MAX_TRADES", 0),
            "max_losing_trades": self._int_config("DAILY_RISK_MAX_LOSING_TRADES", 0),
            "max_consecutive_losses": self._int_config("DAILY_RISK_MAX_CONSECUTIVE_LOSSES", 0),
            "existing_position_policy": self._existing_position_policy().value,
            "live_fail_closed": self._bool_config("DAILY_RISK_LIVE_FAIL_CLOSED", True),
            "manual_halt": self._bool_config("DAILY_RISK_MANUAL_HALT", False),
            "reset_time_local": self._reset_time_local().isoformat(timespec="minutes"),
        }

    def _existing_position_policy(self) -> DailyRiskExistingPositionPolicy:
        raw = str(self._config("DAILY_RISK_EXISTING_POSITION_POLICY", "MANAGED_ONLY") or "MANAGED_ONLY").upper()
        try:
            return DailyRiskExistingPositionPolicy(raw)
        except ValueError:
            return DailyRiskExistingPositionPolicy.MANAGED_ONLY

    def _reset_time_local(self) -> time:
        raw = str(self._config("DAILY_RISK_RESET_TIME_LOCAL", "00:00") or "00:00")
        try:
            hour, minute = raw.split(":", maxsplit=1)
            return time(hour=int(hour), minute=int(minute[:2]))
        except Exception:
            return time(hour=0, minute=0)

    def _account_equity(self) -> float:
        try:
            return float(self._config("RISK_ACCOUNT_EQUITY", 100000.0) or 100000.0)
        except (TypeError, ValueError):
            return 100000.0

    def _config(self, key: str, default: Any) -> Any:
        try:
            value = get_config(key)
        except Exception:
            return default
        return default if value is None else value

    def _bool_config(self, key: str, default: bool) -> bool:
        value = self._config(key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _float_config(self, key: str, default: float) -> float:
        try:
            return float(self._config(key, default) or 0.0)
        except (TypeError, ValueError):
            return float(default)

    def _int_config(self, key: str, default: int) -> int:
        try:
            return int(self._config(key, default) or 0)
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def _as_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _trade_identity(self, payload: dict[str, Any]) -> tuple[str, ...]:
        owner = self._owner_root(payload)
        if owner[1]:
            return ("trade",) + owner
        for key in ("fill_id", "execution_id", "broker_fill_id", "event_id", "order_id", "ibkr_order_id", "trade_outcome_id"):
            value = payload.get(key)
            if value is not None and str(value):
                namespace = "execution" if key in {"fill_id", "execution_id", "broker_fill_id"} else key
                return (namespace, str(value))
        timestamp = payload.get("timestamp")
        return ("fallback", str(payload.get("symbol") or ""),
                self._accounting_timestamp(timestamp).isoformat() if timestamp else "",
                f"{self._payload_pnl(payload):.8f}")

    @staticmethod
    def _payload_from_storage_event(row: dict[str, Any]) -> dict[str, Any]:
        payload = row.get("payload")
        if isinstance(payload, dict):
            return dict(payload)
        payload_json = row.get("payload_json") or row.get("payload")
        if not payload_json:
            return {}
        try:
            import json

            decoded = json.loads(str(payload_json))
        except Exception:
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}

    @staticmethod
    def _fill_payload(fill: Any) -> dict[str, Any]:
        if isinstance(fill, dict):
            return dict(fill)
        payload: dict[str, Any] = {}
        for key in (
            "net_realised_pnl",
            "net_realized_pnl",
            "realised_pnl",
            "realized_pnl",
            "pnl",
            "timestamp",
            "time",
            "execution_time",
            "trade_id", "lifecycle_trade_id", "root_order_id", "client_order_id",
            "fill_id", "execution_id", "broker_fill_id", "event_id", "order_id", "ibkr_order_id",
            "account", "account_id", "acctNumber", "strategy_name", "strategy", "symbol",
            "exec_id", "execId", "orderId", "side", "direction", "quantity", "filled_quantity", "shares",
            "client_id", "clientId", "connection_epoch", "con_id", "conId",
            "price", "execution_price", "fill_price", "avgFillPrice", "average_fill_price",
            "gross_realised_pnl", "gross_realized_pnl", "commission", "closed_at",
        ):
            if hasattr(fill, key):
                payload[key] = getattr(fill, key)
        if "timestamp" not in payload:
            payload["timestamp"] = payload.get("time") or payload.get("execution_time")
        return payload
