from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.config.config_resolver import resolve_config, set_config_overrides
from src.config.runtime_config import RunMode
from src.core.managers.connection_manager import ConnectionManager
from src.metadata.m0_canon_helpers import write_json


@dataclass(frozen=True)
class ModeCheck:
    name: str
    expected: Any
    actual: Any


def _record_violation(violations: list[dict], check: ModeCheck) -> None:
    violations.append(
        {
            "check": check.name,
            "expected": check.expected,
            "actual": check.actual,
        }
    )


def _verify_execution_gate(
    violations: list[dict],
    run_mode: str,
    execution_enabled: bool,
    expected_effective: bool,
    expected_submission: bool,
    expected_translation: bool,
) -> None:
    set_config_overrides(
        {
            "RUN_MODE": run_mode,
            "EXECUTION_ENABLED": execution_enabled,
        }
    )
    resolved = resolve_config()
    effective = bool(resolved["EXECUTION_ENABLED_EFFECTIVE"].value)
    submission = bool(resolved["IBKR_ORDER_SUBMISSION_ENABLED"].value)
    translation = bool(resolved["IBKR_ORDER_TRANSLATION_ENABLED"].value)

    check = ModeCheck(
        name=f"EXECUTION_ENABLED_EFFECTIVE[{run_mode}|{execution_enabled}]",
        expected=expected_effective,
        actual=effective,
    )
    if effective != expected_effective:
        _record_violation(violations, check)

    submission_check = ModeCheck(
        name=f"IBKR_ORDER_SUBMISSION_ENABLED[{run_mode}|{execution_enabled}]",
        expected=expected_submission,
        actual=submission,
    )
    if submission != expected_submission:
        _record_violation(violations, submission_check)

    translation_check = ModeCheck(
        name=f"IBKR_ORDER_TRANSLATION_ENABLED[{run_mode}|{execution_enabled}]",
        expected=expected_translation,
        actual=translation,
    )
    if translation != expected_translation:
        _record_violation(violations, translation_check)

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
    _verify_execution_gate(
        violations=violations,
        run_mode="LIVE",
        execution_enabled=False,
        expected_effective=False,
        expected_submission=False,
        expected_translation=False,
    )
    _verify_execution_gate(
        violations=violations,
        run_mode="LIVE",
        execution_enabled=True,
        expected_effective=True,
        expected_submission=True,
        expected_translation=True,
    )
    _verify_execution_gate(
        violations=violations,
        run_mode="PAPER",
        execution_enabled=False,
        expected_effective=True,
        expected_submission=True,
        expected_translation=True,
    )
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
