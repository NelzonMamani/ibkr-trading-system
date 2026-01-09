from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .contracts import CANONICAL_FIELDS, SCANNER_GIT_SHA, SCANNER_VERSION, ScannerRow54
from .field_mapper import FIELD_SOURCES


def audit_fields(sample_rows: List[ScannerRow54]) -> Dict[str, Any]:
    present_fields: List[str] = []
    missing_fields: List[str] = []
    per_field_notes: Dict[str, str] = {}
    for field_name in CANONICAL_FIELDS:
        values = [getattr(row, field_name, None) for row in sample_rows]
        has_value = any(
            value is not None and value != "" and value != [] for value in values
        )
        if has_value:
            present_fields.append(field_name)
            per_field_notes[field_name] = "Observed non-empty values in sample."
        else:
            missing_fields.append(field_name)
            per_field_notes[field_name] = "No non-empty values observed in sample."
    report = {
        "scanner_version": SCANNER_VERSION,
        "scanner_git_sha": SCANNER_GIT_SHA,
        "sample_size": len(sample_rows),
        "present_fields": present_fields,
        "unwired_fields": [],
        "missing_fields": missing_fields,
        "per_field_notes": per_field_notes,
        "field_sources": FIELD_SOURCES,
    }
    return report


def write_field_audit(report: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def write_mechanical_checklist(report: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    present = set(report.get("present_fields", []))
    missing = set(report.get("missing_fields", []))
    notes = report.get("per_field_notes", {})
    sources = report.get("field_sources", {})
    lines = [
        "# PHASE 24 Scanner Mechanical Checklist",
        "",
        f"Scanner version: `{report.get('scanner_version', '')}`",
        f"Scanner git SHA: `{report.get('scanner_git_sha', '')}`",
        f"Sample size: `{report.get('sample_size', 0)}`",
        "",
        "| # | Field | Status | Source | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for idx, field_name in enumerate(CANONICAL_FIELDS, start=1):
        if field_name in present:
            status = "PRESENT"
        elif field_name in missing:
            status = "MISSING"
        else:
            status = "UNWIRED"
        source = sources.get(field_name, "unknown")
        note = notes.get(field_name, "")
        lines.append(f"| {idx} | `{field_name}` | {status} | {source} | {note} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
