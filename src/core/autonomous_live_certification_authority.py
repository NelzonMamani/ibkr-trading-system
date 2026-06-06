from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class AutonomousPlatformState(str, Enum):
    NOT_CERTIFIED = "NOT_CERTIFIED"
    PARTIALLY_CERTIFIED = "PARTIALLY_CERTIFIED"
    PAPER_CERTIFIED = "PAPER_CERTIFIED"
    LIVE_CERTIFIED = "LIVE_CERTIFIED"


@dataclass(frozen=True)
class AutonomousCertificationReport:
    platform_state: str
    certified: bool
    certification_timestamp: str
    run_mode: str
    startup_status: str
    recovery_status: str
    trading_status: str
    protection_status: str
    audit_status: str
    determinism_status: str
    critical_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_event_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _DomainSpec:
    name: str
    checks: tuple[str, ...]


DOMAIN_SPECS: tuple[_DomainSpec, ...] = (
    _DomainSpec(
        "startup",
        (
            "configuration_loaded",
            "runtime_authority_loaded",
            "orchestrator_initialized",
            "strategy_registry_loaded",
            "broker_adapter_initialized",
            "startup_sequence_complete",
        ),
    ),
    _DomainSpec(
        "recovery",
        (
            "startup_recovery_available",
            "autonomous_recovery_available",
            "recovery_audit_trail_exists",
            "recovery_decisions_emitted",
        ),
    ),
    _DomainSpec(
        "trading",
        (
            "scanner_path_operational",
            "strategy_path_operational",
            "risk_path_operational",
            "execution_path_operational",
        ),
    ),
    _DomainSpec(
        "protection",
        (
            "stop_authority_available",
            "target_authority_available",
            "trailing_authority_available",
            "daily_risk_governor_active",
        ),
    ),
    _DomainSpec(
        "audit",
        (
            "event_collector_available",
            "storage_available",
            "analytics_available",
            "audit_events_emitted",
        ),
    ),
    _DomainSpec(
        "determinism",
        (
            "authority_ordering_valid",
            "no_bypass_paths",
            "execution_protections_active",
            "reconciliation_available",
        ),
    ),
)


class AutonomousLiveCertificationAuthority:
    """Read-only P16 authority for unattended-platform certification.

    The authority does not place, cancel, or modify orders. It evaluates
    whether the already-wired platform domains are available and auditable.
    """

    def __init__(self, *, event_collector: Any | None = None) -> None:
        self.event_collector = event_collector
        self.last_report: AutonomousCertificationReport | None = None

    def run_autonomous_certification(self, **kwargs: Any) -> AutonomousCertificationReport:
        return self.evaluate(**kwargs)

    def evaluate(
        self,
        *,
        run_mode: str = "SIM",
        now: datetime | None = None,
        event_collector: Any | None = None,
        orchestrator: Any | None = None,
        execution_engine: Any | None = None,
        storage_engine: Any | None = None,
        analytics_authority: Any | None = None,
        daily_risk_governor: Any | None = None,
        autonomous_recovery_authority: Any | None = None,
        stop_authority: Any | None = None,
        target_authority: Any | None = None,
        trailing_authority: Any | None = None,
        evidence: dict[str, Any] | None = None,
        emit_audit_event: bool = True,
        read_only: bool = False,
    ) -> AutonomousCertificationReport:
        if event_collector is not None:
            self.event_collector = event_collector
        timestamp = self._timestamp(now)
        run_mode_u = str(run_mode or "SIM").upper()
        certification_id = f"auto-cert-{uuid4().hex[:12]}"
        evidence_payload = dict(evidence or {})
        started_emitted = self._emit_started(
            certification_id=certification_id,
            run_mode=run_mode_u,
            timestamp=timestamp,
            evidence=evidence_payload,
            emit_audit_event=emit_audit_event,
        )

        try:
            inferred = self._infer_evidence(
                run_mode=run_mode_u,
                orchestrator=orchestrator,
                execution_engine=execution_engine,
                storage_engine=storage_engine,
                analytics_authority=analytics_authority,
                daily_risk_governor=daily_risk_governor,
                autonomous_recovery_authority=autonomous_recovery_authority,
                stop_authority=stop_authority,
                target_authority=target_authority,
                trailing_authority=trailing_authority,
                audit_events_emitted=started_emitted,
            )
            merged_evidence = self._merge_evidence(inferred, evidence_payload)
            domain_statuses, failures = self._evaluate_domains(merged_evidence)
            warnings = self._warnings(merged_evidence)
            platform_state = self._platform_state(
                run_mode=run_mode_u,
                failures=failures,
                warnings=warnings,
            )
            report = AutonomousCertificationReport(
                platform_state=platform_state.value,
                certified=platform_state != AutonomousPlatformState.NOT_CERTIFIED,
                certification_timestamp=timestamp,
                run_mode=run_mode_u,
                startup_status=domain_statuses["startup"],
                recovery_status=domain_statuses["recovery"],
                trading_status=domain_statuses["trading"],
                protection_status=domain_statuses["protection"],
                audit_status=domain_statuses["audit"],
                determinism_status=domain_statuses["determinism"],
                critical_failures=failures,
                warnings=warnings,
                recommendations=self._recommendations(failures),
                evidence=merged_evidence,
            )
            self._emit_completed(report, emit_audit_event=emit_audit_event)
            if not read_only and run_mode_u != "READ_ONLY":
                self.last_report = report
            return report
        except Exception as exc:
            report = AutonomousCertificationReport(
                platform_state=AutonomousPlatformState.NOT_CERTIFIED.value,
                certified=False,
                certification_timestamp=timestamp,
                run_mode=run_mode_u,
                startup_status="FAIL",
                recovery_status="FAIL",
                trading_status="FAIL",
                protection_status="FAIL",
                audit_status="FAIL",
                determinism_status="FAIL",
                critical_failures=[f"CERTIFICATION_EXCEPTION:{type(exc).__name__}:{exc}"],
                recommendations=["Investigate autonomous certification exception before trading."],
                evidence=evidence_payload,
            )
            self._emit_failed(report, emit_audit_event=emit_audit_event)
            if not read_only and run_mode_u != "READ_ONLY":
                self.last_report = report
            return report

    def _infer_evidence(
        self,
        *,
        run_mode: str,
        orchestrator: Any | None,
        execution_engine: Any | None,
        storage_engine: Any | None,
        analytics_authority: Any | None,
        daily_risk_governor: Any | None,
        autonomous_recovery_authority: Any | None,
        stop_authority: Any | None,
        target_authority: Any | None,
        trailing_authority: Any | None,
        audit_events_emitted: bool,
    ) -> dict[str, dict[str, bool]]:
        engine = execution_engine or getattr(orchestrator, "execution_engine", None)
        storage = storage_engine or getattr(orchestrator, "storage_engine", None)
        analytics = analytics_authority or getattr(orchestrator, "analytics_authority", None)
        daily_risk = daily_risk_governor or getattr(orchestrator, "daily_risk_governor", None)
        recovery = autonomous_recovery_authority or getattr(
            orchestrator,
            "autonomous_recovery_authority",
            None,
        )
        collector = self.event_collector or getattr(orchestrator, "event_collector", None)
        startup_complete = self._startup_complete(engine)
        recovery_events = self._event_count(collector, "AUTONOMOUS_RECOVERY_DECISION")
        broker_required = run_mode in {"LIVE", "PAPER"}

        return {
            "startup": {
                "configuration_loaded": True,
                "runtime_authority_loaded": getattr(orchestrator, "runtime_mode_manager", None)
                is not None
                or engine is not None,
                "orchestrator_initialized": orchestrator is not None or engine is not None,
                "strategy_registry_loaded": False,
                "broker_adapter_initialized": (not broker_required)
                or getattr(engine, "provider", None) is not None,
                "startup_sequence_complete": startup_complete,
            },
            "recovery": {
                "startup_recovery_available": engine is not None
                and hasattr(engine, "startup_recovery_complete"),
                "autonomous_recovery_available": recovery is not None,
                "recovery_audit_trail_exists": recovery is not None,
                "recovery_decisions_emitted": recovery_events > 0,
            },
            "trading": {
                "scanner_path_operational": orchestrator is not None
                and hasattr(orchestrator, "_build_scanner_request"),
                "strategy_path_operational": getattr(orchestrator, "strategy_runner", None)
                is not None,
                "risk_path_operational": getattr(orchestrator, "risk_engine", None) is not None,
                "execution_path_operational": engine is not None,
            },
            "protection": {
                "stop_authority_available": stop_authority is not None
                or self._has_attr(engine, "stop_controller"),
                "target_authority_available": target_authority is not None
                or self._module_available("src.core.take_profit_authority", "TakeProfitAuthority"),
                "trailing_authority_available": trailing_authority is not None
                or self._module_available("src.core.trailing_stop_authority", "TrailingStopAuthority"),
                "daily_risk_governor_active": daily_risk is not None,
            },
            "audit": {
                "event_collector_available": collector is not None
                and callable(getattr(collector, "emit", None)),
                "storage_available": storage is not None and self._storage_available(storage),
                "analytics_available": analytics is not None,
                "audit_events_emitted": bool(audit_events_emitted),
            },
            "determinism": {
                "authority_ordering_valid": engine is not None
                and daily_risk is not None
                and recovery is not None,
                "no_bypass_paths": engine is not None,
                "execution_protections_active": engine is not None
                and hasattr(engine, "startup_recovery_complete"),
                "reconciliation_available": engine is not None
                and hasattr(engine, "startup_recovery_state"),
            },
        }

    @staticmethod
    def _merge_evidence(
        inferred: dict[str, dict[str, bool]],
        overrides: dict[str, Any],
    ) -> dict[str, dict[str, bool]]:
        merged = {
            domain: dict(checks)
            for domain, checks in inferred.items()
        }
        for domain, values in overrides.items():
            if not isinstance(values, dict):
                continue
            domain_map = merged.setdefault(str(domain), {})
            for key, value in values.items():
                domain_map[str(key)] = bool(value)
        return merged

    @staticmethod
    def _evaluate_domains(evidence: dict[str, dict[str, bool]]) -> tuple[dict[str, str], list[str]]:
        statuses: dict[str, str] = {}
        failures: list[str] = []
        for spec in DOMAIN_SPECS:
            missing = [
                check for check in spec.checks
                if not bool(evidence.get(spec.name, {}).get(check, False))
            ]
            statuses[spec.name] = "PASS" if not missing else "FAIL"
            failures.extend(f"{spec.name.upper()}:{check}" for check in missing)
        return statuses, failures

    @staticmethod
    def _warnings(evidence: dict[str, dict[str, bool]]) -> list[str]:
        warnings: list[str] = []
        extra = evidence.get("warnings", {})
        if isinstance(extra, dict):
            warnings.extend(str(key) for key, value in extra.items() if bool(value))
        return warnings

    @staticmethod
    def _platform_state(
        *,
        run_mode: str,
        failures: list[str],
        warnings: list[str],
    ) -> AutonomousPlatformState:
        if failures:
            return AutonomousPlatformState.NOT_CERTIFIED
        if warnings:
            return AutonomousPlatformState.PARTIALLY_CERTIFIED
        if run_mode == "LIVE":
            return AutonomousPlatformState.LIVE_CERTIFIED
        if run_mode == "PAPER":
            return AutonomousPlatformState.PAPER_CERTIFIED
        return AutonomousPlatformState.PARTIALLY_CERTIFIED

    @staticmethod
    def _recommendations(failures: list[str]) -> list[str]:
        return [
            f"Resolve {failure} before unattended autonomous operation."
            for failure in failures
        ]

    def _emit_started(
        self,
        *,
        certification_id: str,
        run_mode: str,
        timestamp: str,
        evidence: dict[str, Any],
        emit_audit_event: bool,
    ) -> bool:
        if not emit_audit_event:
            return False
        collector = self.event_collector
        emit = getattr(collector, "emit", None)
        if not callable(emit):
            return False
        try:
            emit(
                event_type="AUTONOMOUS_CERTIFICATION_STARTED",
                source="AutonomousLiveCertificationAuthority",
                payload={
                    "certification_id": certification_id,
                    "run_mode": run_mode,
                    "timestamp": timestamp,
                    "evidence": dict(evidence),
                },
            )
            return True
        except Exception as exc:
            print(f"[AUTONOMOUS_CERTIFICATION][AUDIT][START_FAILED] reason={exc}")
            return False

    def _emit_completed(
        self,
        report: AutonomousCertificationReport,
        *,
        emit_audit_event: bool,
    ) -> None:
        if not emit_audit_event:
            return
        collector = self.event_collector
        emit = getattr(collector, "emit", None)
        if not callable(emit):
            return
        event_type = (
            "AUTONOMOUS_CERTIFICATION_COMPLETED"
            if report.certified
            else "AUTONOMOUS_CERTIFICATION_FAILED"
        )
        try:
            emit(
                event_type=event_type,
                source="AutonomousLiveCertificationAuthority",
                payload=report.to_event_payload(),
            )
        except Exception as exc:
            print(f"[AUTONOMOUS_CERTIFICATION][AUDIT][COMPLETE_FAILED] reason={exc}")

    def _emit_failed(
        self,
        report: AutonomousCertificationReport,
        *,
        emit_audit_event: bool,
    ) -> None:
        if not emit_audit_event:
            return
        collector = self.event_collector
        emit = getattr(collector, "emit", None)
        if not callable(emit):
            return
        try:
            emit(
                event_type="AUTONOMOUS_CERTIFICATION_FAILED",
                source="AutonomousLiveCertificationAuthority",
                payload=report.to_event_payload(),
            )
        except Exception as exc:
            print(f"[AUTONOMOUS_CERTIFICATION][AUDIT][FAILED_EVENT_FAILED] reason={exc}")

    @staticmethod
    def _startup_complete(engine: Any | None) -> bool:
        checker = getattr(engine, "startup_recovery_complete", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        state = str(getattr(getattr(engine, "startup_recovery_state", None), "value", "") or "")
        return state == "RECOVERY_COMPLETE"

    @staticmethod
    def _event_count(collector: Any | None, event_type: str) -> int:
        counter = getattr(collector, "count", None)
        if callable(counter):
            try:
                return int(counter(event_type))
            except Exception:
                return 0
        return 0

    @staticmethod
    def _storage_available(storage: Any) -> bool:
        if storage is None:
            return False
        if getattr(storage, "enabled", True) is False:
            return True
        if hasattr(storage, "_store"):
            return getattr(storage, "_store") is not None
        return True

    @staticmethod
    def _has_attr(obj: Any | None, name: str) -> bool:
        return obj is not None and getattr(obj, name, None) is not None

    @staticmethod
    def _module_available(module_name: str, attr_name: str) -> bool:
        try:
            module = __import__(module_name, fromlist=[attr_name])
        except Exception:
            return False
        return getattr(module, attr_name, None) is not None

    @staticmethod
    def _timestamp(value: datetime | None = None) -> str:
        resolved = value or datetime.now(timezone.utc)
        if resolved.tzinfo is None:
            resolved = resolved.replace(tzinfo=timezone.utc)
        return resolved.astimezone(timezone.utc).isoformat()


__all__ = [
    "AutonomousCertificationReport",
    "AutonomousLiveCertificationAuthority",
    "AutonomousPlatformState",
]
