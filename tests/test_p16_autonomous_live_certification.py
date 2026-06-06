from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.core.autonomous_live_certification_authority import (
    DOMAIN_SPECS,
    AutonomousLiveCertificationAuthority,
    AutonomousPlatformState,
)
from src.core.event_collector import EventCollector


NOW = datetime(2026, 6, 5, 14, 0, tzinfo=timezone.utc)


def _complete_evidence() -> dict[str, dict[str, bool]]:
    return {
        spec.name: {check: True for check in spec.checks}
        for spec in DOMAIN_SPECS
    }


def _report(
    *,
    run_mode: str = "LIVE",
    evidence: dict[str, dict[str, bool]] | None = None,
    events: EventCollector | None = None,
    read_only: bool = False,
    emit_audit_event: bool = True,
):
    authority = AutonomousLiveCertificationAuthority(event_collector=events or EventCollector())
    return authority, authority.evaluate(
        run_mode=run_mode,
        now=NOW,
        evidence=evidence or _complete_evidence(),
        read_only=read_only,
        emit_audit_event=emit_audit_event,
    )


def test_startup_certified() -> None:
    _authority, report = _report()

    assert report.startup_status == "PASS"
    assert report.certified is True


def test_startup_failure_is_not_certified() -> None:
    evidence = _complete_evidence()
    evidence["startup"]["startup_sequence_complete"] = False

    _authority, report = _report(evidence=evidence)

    assert report.platform_state == AutonomousPlatformState.NOT_CERTIFIED.value
    assert report.startup_status == "FAIL"
    assert "STARTUP:startup_sequence_complete" in report.critical_failures


def test_recovery_certified() -> None:
    _authority, report = _report()

    assert report.recovery_status == "PASS"


def test_recovery_unavailable_is_not_certified() -> None:
    evidence = _complete_evidence()
    evidence["recovery"]["autonomous_recovery_available"] = False

    _authority, report = _report(evidence=evidence)

    assert report.recovery_status == "FAIL"
    assert "RECOVERY:autonomous_recovery_available" in report.critical_failures


def test_trading_pipeline_certified() -> None:
    _authority, report = _report()

    assert report.trading_status == "PASS"


def test_trading_pipeline_unavailable_is_not_certified() -> None:
    evidence = _complete_evidence()
    evidence["trading"]["execution_path_operational"] = False

    _authority, report = _report(evidence=evidence)

    assert report.trading_status == "FAIL"
    assert "TRADING:execution_path_operational" in report.critical_failures


def test_protection_certified() -> None:
    _authority, report = _report()

    assert report.protection_status == "PASS"


def test_missing_protection_authority_is_not_certified() -> None:
    evidence = _complete_evidence()
    evidence["protection"]["target_authority_available"] = False

    _authority, report = _report(evidence=evidence)

    assert report.protection_status == "FAIL"
    assert "PROTECTION:target_authority_available" in report.critical_failures


def test_audit_certified() -> None:
    _authority, report = _report()

    assert report.audit_status == "PASS"


def test_storage_unavailable_is_not_certified() -> None:
    evidence = _complete_evidence()
    evidence["audit"]["storage_available"] = False

    _authority, report = _report(evidence=evidence)

    assert report.audit_status == "FAIL"
    assert "AUDIT:storage_available" in report.critical_failures


def test_disabled_storage_persistence_is_not_certified_for_paper_or_live() -> None:
    evidence = _complete_evidence()
    evidence["audit"].pop("storage_available")
    storage = SimpleNamespace(enabled=False, _store=object())

    for run_mode, disallowed_state in (
        ("PAPER", AutonomousPlatformState.PAPER_CERTIFIED.value),
        ("LIVE", AutonomousPlatformState.LIVE_CERTIFIED.value),
    ):
        authority = AutonomousLiveCertificationAuthority(event_collector=EventCollector())

        report = authority.evaluate(
            run_mode=run_mode,
            now=NOW,
            storage_engine=storage,
            evidence=evidence,
            emit_audit_event=False,
        )

        assert report.audit_status == "FAIL"
        assert report.certified is False
        assert report.platform_state == AutonomousPlatformState.NOT_CERTIFIED.value
        assert report.platform_state != disallowed_state
        assert "AUDIT:storage_available" in report.critical_failures


def test_determinism_certified() -> None:
    _authority, report = _report()

    assert report.determinism_status == "PASS"


def test_authority_ordering_violation_is_not_certified() -> None:
    evidence = _complete_evidence()
    evidence["determinism"]["authority_ordering_valid"] = False

    _authority, report = _report(evidence=evidence)

    assert report.determinism_status == "FAIL"
    assert "DETERMINISM:authority_ordering_valid" in report.critical_failures


def test_paper_certification_state() -> None:
    _authority, report = _report(run_mode="PAPER")

    assert report.platform_state == AutonomousPlatformState.PAPER_CERTIFIED.value
    assert report.certified is True


def test_live_certification_state() -> None:
    _authority, report = _report(run_mode="LIVE")

    assert report.platform_state == AutonomousPlatformState.LIVE_CERTIFIED.value
    assert report.certified is True


def test_not_certified_state() -> None:
    evidence = _complete_evidence()
    evidence["startup"]["configuration_loaded"] = False

    _authority, report = _report(run_mode="LIVE", evidence=evidence)

    assert report.platform_state == AutonomousPlatformState.NOT_CERTIFIED.value
    assert report.certified is False


def test_certification_report_emitted() -> None:
    events = EventCollector()

    _authority, report = _report(events=events)

    completed = events.filter_by_type("AUTONOMOUS_CERTIFICATION_COMPLETED")
    assert completed[0].payload["platform_state"] == report.platform_state
    assert completed[0].payload["certified"] is True


def test_audit_events_emitted() -> None:
    events = EventCollector()

    _authority, _report_value = _report(events=events)

    assert len(events.filter_by_type("AUTONOMOUS_CERTIFICATION_STARTED")) == 1
    assert len(events.filter_by_type("AUTONOMOUS_CERTIFICATION_COMPLETED")) == 1


def test_read_only_evaluation_does_not_mutate_authority_state() -> None:
    events = EventCollector()
    authority = AutonomousLiveCertificationAuthority(event_collector=events)

    report = authority.evaluate(
        run_mode="READ_ONLY",
        now=NOW,
        evidence=_complete_evidence(),
        read_only=True,
    )

    assert report.platform_state == AutonomousPlatformState.PARTIALLY_CERTIFIED.value
    assert authority.last_report is None
    assert events.filter_by_type("AUTONOMOUS_CERTIFICATION_COMPLETED")


def test_sim_deterministic_evaluation() -> None:
    _first_authority, first = _report(run_mode="SIM", emit_audit_event=False)
    _second_authority, second = _report(run_mode="SIM", emit_audit_event=False)

    assert first.to_event_payload() == second.to_event_payload()
    assert first.platform_state == AutonomousPlatformState.PARTIALLY_CERTIFIED.value


def test_paper_deterministic_evaluation() -> None:
    _first_authority, first = _report(run_mode="PAPER", emit_audit_event=False)
    _second_authority, second = _report(run_mode="PAPER", emit_audit_event=False)

    assert first.to_event_payload() == second.to_event_payload()


def test_live_deterministic_evaluation() -> None:
    _first_authority, first = _report(run_mode="LIVE", emit_audit_event=False)
    _second_authority, second = _report(run_mode="LIVE", emit_audit_event=False)

    assert first.to_event_payload() == second.to_event_payload()
