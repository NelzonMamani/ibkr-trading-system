"""Reporting helpers for E21 harness outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


def _timestamp() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_markdown(path: Path, lines: Iterable[str]) -> None:
    content = "\n".join(lines).rstrip() + "\n"
    path.write_text(content, encoding="utf-8")


def build_certification_report(summary: Mapping[str, Any]) -> list[str]:
    verdict = summary.get("verdict", "FAIL")
    criteria = summary.get("criteria", [])
    evidence = summary.get("evidence", [])
    lines = [
        "# E21 Certification Report",
        "",
        "## Scope",
        "- Trading-ready verification evidence and deterministic harness outputs.",
        "",
        "## PASS/FAIL Criteria",
    ]
    for item in criteria:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Evidence",
        ]
    )
    for item in evidence:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Verdict",
            f"**{verdict}** (generated {summary.get('timestamp', _timestamp())}).",
        ]
    )
    return lines


def build_mode_parity_matrix(matrix: Iterable[Mapping[str, Any]]) -> list[str]:
    lines = [
        "# E21 Mode Parity Matrix",
        "",
        "| Mode | Status | Evidence | Notes |",
        "| --- | --- | --- | --- |",
    ]
    for entry in matrix:
        lines.append(
            "| {mode} | {status} | {evidence} | {notes} |".format(
                mode=entry.get("mode"),
                status=entry.get("status"),
                evidence=entry.get("evidence", ""),
                notes=entry.get("notes", ""),
            )
        )
    return lines


def build_scenario_coverage(scenarios: Iterable[Mapping[str, Any]]) -> list[str]:
    lines = [
        "# E21 Scenario Coverage",
        "",
        "| Scenario ID | Description | Validations |",
        "| --- | --- | --- |",
    ]
    for scenario in scenarios:
        validations = ", ".join(scenario.get("validations", []))
        lines.append(
            "| {scenario_id} | {description} | {validations} |".format(
                scenario_id=scenario.get("scenario_id"),
                description=scenario.get("description"),
                validations=validations,
            )
        )
    return lines


def build_failure_drills_report(drills: Iterable[Mapping[str, Any]]) -> list[str]:
    lines = ["# E21 Failure Drills Report", "", "| Drill | Expected | Observed | Result |", "| --- | --- | --- | --- |"]
    for drill in drills:
        lines.append(
            "| {name} | {expected} | {observed} | {result} |".format(
                name=drill.get("name"),
                expected=drill.get("expected"),
                observed=drill.get("observed"),
                result=drill.get("result"),
            )
        )
    return lines


def build_non_interference_proof(proof: Mapping[str, Any]) -> list[str]:
    lines = [
        "# E21 Non-Interference Proof",
        "",
        "## Summary",
        proof.get("summary", ""),
        "",
        "## Evidence",
    ]
    for item in proof.get("evidence", []):
        lines.append(f"- {item}")
    return lines
