from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import (
    RunMode,
    get_execution_enabled,
    get_ibkr_api_write_allowed,
    get_ibkr_order_submission_enabled,
    get_ibkr_order_translation_enabled,
    get_ibkr_readonly_enabled,
)
from src.core.managers.connection_manager import ConnectionManager
from src.metadata.m0_canon_helpers import write_json


@dataclass(frozen=True)
class ModeCheck:
    name: str
    expected: Any
    actual: Any


@dataclass(frozen=True)
class ModeExpectation:
    run_mode: str
    execution_enabled: bool
    expected_execution: bool
    expected_readonly: bool
    expected_submission: bool
    expected_api_write: bool
    expected_translation: bool


def _record_violation(violations: list[dict], check: ModeCheck) -> None:
    violations.append(
        {
            "check": check.name,
            "expected": check.expected,
            "actual": check.actual,
        }
    )


def _verify_execution_gate(violations: list[dict], expectation: ModeExpectation) -> None:
    set_config_overrides(
        {
            "RUN_MODE": expectation.run_mode,
            "EXECUTION_ENABLED": expectation.execution_enabled,
        }
    )
    actual_execution = get_execution_enabled()
    actual_readonly = get_ibkr_readonly_enabled()
    actual_submission = get_ibkr_order_submission_enabled()
    actual_api_write = get_ibkr_api_write_allowed()
    actual_translation = get_ibkr_order_translation_enabled()

    checks = (
        ModeCheck(
            name=f"EXECUTION_ENABLED_EFFECTIVE[{expectation.run_mode}|{expectation.execution_enabled}]",
            expected=expectation.expected_execution,
            actual=actual_execution,
        ),
        ModeCheck(
            name=f"IBKR_READONLY_ENABLED[{expectation.run_mode}|{expectation.execution_enabled}]",
            expected=expectation.expected_readonly,
            actual=actual_readonly,
        ),
        ModeCheck(
            name=f"IBKR_ORDER_SUBMISSION_ENABLED[{expectation.run_mode}|{expectation.execution_enabled}]",
            expected=expectation.expected_submission,
            actual=actual_submission,
        ),
        ModeCheck(
            name=f"IBKR_API_WRITE_ALLOWED[{expectation.run_mode}|{expectation.execution_enabled}]",
            expected=expectation.expected_api_write,
            actual=actual_api_write,
        ),
        ModeCheck(
            name=f"IBKR_ORDER_TRANSLATION_ENABLED[{expectation.run_mode}|{expectation.execution_enabled}]",
            expected=expectation.expected_translation,
            actual=actual_translation,
        ),
    )

    for check in checks:
        if check.actual != check.expected:
            _record_violation(violations, check)

    set_config_overrides(None)


def _verify_sim_broker_isolation(violations: list[dict]) -> None:
    manager = ConnectionManager(RunMode.SIM)
    try:
        manager.ensure_connected()
    except RuntimeError as exc:
        message = str(exc)
        if message != "Live broker connections are forbidden in SIM mode":
            _record_violation(
                violations,
                ModeCheck(
                    name="SIM_BROKER_ISOLATION_MESSAGE",
                    expected="Live broker connections are forbidden in SIM mode",
                    actual=message,
                ),
            )
        return
    _record_violation(
        violations,
        ModeCheck(
            name="SIM_BROKER_ISOLATION_ENFORCED",
            expected="RuntimeError",
            actual="NO_EXCEPTION",
        ),
    )


def verify_mode_semantics() -> dict:
    violations: list[dict] = []
    expectations = (
        ModeExpectation(
            run_mode="LIVE",
            execution_enabled=True,
            expected_execution=True,
            expected_readonly=False,
            expected_submission=True,
            expected_api_write=True,
            expected_translation=True,
        ),
        ModeExpectation(
            run_mode="READ_ONLY",
            execution_enabled=True,
            expected_execution=False,
            expected_readonly=True,
            expected_submission=False,
            expected_api_write=False,
            expected_translation=False,
        ),
        ModeExpectation(
            run_mode="PAPER",
            execution_enabled=True,
            expected_execution=True,
            expected_readonly=False,
            expected_submission=True,
            expected_api_write=True,
            expected_translation=True,
        ),
        ModeExpectation(
            run_mode="SIM",
            execution_enabled=True,
            expected_execution=False,
            expected_readonly=True,
            expected_submission=False,
            expected_api_write=False,
            expected_translation=False,
        ),
    )

    for expectation in expectations:
        _verify_execution_gate(violations=violations, expectation=expectation)
    _verify_sim_broker_isolation(violations)

    return {
        "epoch": "M3_MODE_SEMANTICS_CERTIFICATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "violations": violations,
        "valid": not violations,
    }


def write_summary(result: dict, output_md) -> None:
    lines = [
        "# M3 Mode Semantics Verification Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Violations: {len(result.get('violations', []))}",
    ]
    if result.get("violations"):
        lines.append("")
        lines.append("## Violations")
        for violation in result["violations"]:
            lines.append(
                "- {check} (expected={expected}, actual={actual})".format(
                    check=violation.get("check"),
                    expected=violation.get("expected"),
                    actual=violation.get("actual"),
                )
            )
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(result: dict, output_json, output_md) -> None:
    write_json(output_json, result)
    write_summary(result, output_md)
