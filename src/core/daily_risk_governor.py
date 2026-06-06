from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
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

        if not self.enabled:
            status = DailyRiskDecisionStatus.ALLOW
            reason = "DAILY_RISK_GOVERNOR_DISABLED"
            lock_status = DailyRiskLockStatus.UNLOCKED
        elif run_mode_u == "READ_ONLY":
            status = DailyRiskDecisionStatus.READ_ONLY_EVALUATED
            reason = "READ_ONLY_EVALUATED_NO_STATE_MUTATION"
            lock_status = DailyRiskLockStatus.UNLOCKED
        elif self._bool_config("DAILY_RISK_MANUAL_HALT", False):
            status = DailyRiskDecisionStatus.MANUAL_HALT
            reason = "MANUAL_HALT"
            reasons.append(reason)
            lock_status = DailyRiskLockStatus.LOCKED
        elif not recovery_complete:
            status = DailyRiskDecisionStatus.RECOVERY_NOT_COMPLETE
            reason = "RECOVERY_NOT_COMPLETE"
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
        lifecycle_metrics = self._metrics_from_lifecycle()
        broker_metrics = self._metrics_from_broker_fills(trading_day)

        realized = event_metrics.realized_pnl
        trade_count = event_metrics.daily_trade_count
        losing_count = event_metrics.losing_trade_count
        consecutive_losses = event_metrics.consecutive_losses
        if event_metrics.source_count == 0 and storage_metrics.source_count > 0:
            realized = storage_metrics.realized_pnl
            trade_count = storage_metrics.daily_trade_count
            losing_count = storage_metrics.losing_trade_count
            consecutive_losses = storage_metrics.consecutive_losses
        if event_metrics.source_count == 0 and storage_metrics.source_count == 0 and broker_metrics.source_count > 0:
            realized = broker_metrics.realized_pnl
            trade_count = broker_metrics.daily_trade_count
            losing_count = broker_metrics.losing_trade_count
            consecutive_losses = broker_metrics.consecutive_losses
        if event_metrics.source_count == 0 and storage_metrics.source_count == 0 and broker_metrics.source_count == 0:
            realized = lifecycle_metrics.realized_pnl

        source_counts = {
            "events": event_metrics.source_count,
            "storage": storage_metrics.source_count,
            "broker_fills": broker_metrics.source_count,
            "lifecycle": lifecycle_metrics.source_count,
        }
        recovered = True
        recovery_error = None
        if not recovery_complete:
            recovered = False
            recovery_error = "RECOVERY_NOT_COMPLETE"
        elif str(run_mode or "").upper() == "LIVE" and self._bool_config("DAILY_RISK_LIVE_FAIL_CLOSED", True):
            source_available = any(
                source is not None
                for source in (
                    self.event_collector,
                    self.storage_engine,
                    self.trade_lifecycle_engine,
                    self.provider,
                )
            )
            if not source_available:
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
        closed_events = []
        for event in list(collector.snapshot_all() or []):
            if getattr(event, "event_type", None) != "TRADE_CLOSED":
                continue
            if self.trading_day_for(getattr(event, "timestamp", None) or datetime.now(timezone.utc)) != trading_day:
                continue
            closed_events.append(event)
        return self._metrics_from_trade_payloads(
            [
                {
                    **dict(getattr(event, "payload", {}) or {}),
                    "timestamp": getattr(event, "timestamp", None),
                }
                for event in closed_events
            ]
        )

    def _metrics_from_storage(self, trading_day: str) -> _DailyRiskMetrics:
        storage = self.storage_engine
        store = getattr(storage, "_store", None)
        run_id = getattr(storage, "run_id", None)
        if store is None or not run_id:
            return _DailyRiskMetrics()
        payloads: list[dict[str, Any]] = []
        fetch_trade_outcomes = getattr(store, "fetch_trade_outcomes", None)
        if callable(fetch_trade_outcomes):
            try:
                for row in list(fetch_trade_outcomes(run_id) or []):
                    timestamp = row.get("closed_at") or row.get("created_at")
                    if timestamp and self.trading_day_for(self._parse_datetime(timestamp)) != trading_day:
                        continue
                    payloads.append(
                        {
                            "net_realised_pnl": row.get("net_realised_pnl"),
                            "realised_pnl": row.get("realised_pnl"),
                            "timestamp": timestamp,
                        }
                    )
            except Exception:
                return _DailyRiskMetrics()
        if not payloads:
            fetch_events = getattr(store, "fetch_events", None)
            if callable(fetch_events):
                try:
                    for row in list(fetch_events(run_id) or []):
                        if str(row.get("event_type") or "") != "TRADE_CLOSED":
                            continue
                        timestamp = row.get("timestamp") or row.get("created_at")
                        if timestamp and self.trading_day_for(self._parse_datetime(timestamp)) != trading_day:
                            continue
                        payload = self._payload_from_storage_event(row)
                        payload["timestamp"] = timestamp
                        payloads.append(payload)
                except Exception:
                    return _DailyRiskMetrics()
        return self._metrics_from_trade_payloads(payloads)

    def _metrics_from_lifecycle(self) -> _DailyRiskMetrics:
        engine = self.trade_lifecycle_engine
        if engine is None:
            return _DailyRiskMetrics()
        try:
            if hasattr(engine, "build_portfolio_state"):
                state = engine.build_portfolio_state()
                return _DailyRiskMetrics(
                    realized_pnl=round(float(getattr(state, "total_realized_pnl", 0.0) or 0.0), 2),
                    unrealized_pnl=round(float(getattr(state, "total_unrealized_pnl", 0.0) or 0.0), 2),
                    source_count=1,
                )
            if hasattr(engine, "get_open_lifecycle_trades"):
                trades = list(engine.get_open_lifecycle_trades() or [])
                return _DailyRiskMetrics(
                    unrealized_pnl=round(
                        sum(float(getattr(trade, "unrealized_pnl", 0.0) or 0.0) for trade in trades),
                        2,
                    ),
                    source_count=len(trades),
                )
        except Exception:
            return _DailyRiskMetrics()
        return _DailyRiskMetrics()

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
                return _DailyRiskMetrics()
            payloads = []
            for fill in fills:
                payload = self._fill_payload(fill)
                timestamp = payload.get("timestamp")
                if timestamp and self.trading_day_for(self._parse_datetime(timestamp)) != trading_day:
                    continue
                payloads.append(payload)
            return self._metrics_from_trade_payloads(payloads)
        return _DailyRiskMetrics()

    def _metrics_from_trade_payloads(self, payloads: Iterable[dict[str, Any]]) -> _DailyRiskMetrics:
        realized = 0.0
        losses = 0
        trade_count = 0
        pnl_values: list[float] = []
        for payload in payloads:
            pnl = self._float_from_payload(
                payload,
                "net_realised_pnl",
                "net_realized_pnl",
                "realised_pnl",
                "realized_pnl",
                "pnl",
            )
            realized += pnl
            pnl_values.append(pnl)
            trade_count += 1
            if pnl < 0:
                losses += 1
        consecutive = 0
        for pnl in reversed(pnl_values):
            if pnl < 0:
                consecutive += 1
            else:
                break
        return _DailyRiskMetrics(
            realized_pnl=round(realized, 2),
            daily_trade_count=trade_count,
            losing_trade_count=losses,
            consecutive_losses=consecutive,
            source_count=trade_count,
        )

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

    def _parse_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return self._as_aware(value)
        if isinstance(value, date):
            return datetime.combine(value, time.min, tzinfo=timezone.utc)
        text = str(value or "").strip()
        if not text:
            return datetime.now(timezone.utc)
        try:
            return self._as_aware(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return datetime.now(timezone.utc)

    @staticmethod
    def _as_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _float_from_payload(payload: dict[str, Any], *keys: str) -> float:
        for key in keys:
            if key not in payload:
                continue
            try:
                return float(payload.get(key) or 0.0)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

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
        ):
            if hasattr(fill, key):
                payload[key] = getattr(fill, key)
        if "timestamp" not in payload:
            payload["timestamp"] = payload.get("time") or payload.get("execution_time")
        return payload
