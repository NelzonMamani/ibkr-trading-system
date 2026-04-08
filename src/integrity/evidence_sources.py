from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PLACEHOLDER_MARKERS = (
    "placeholder",
    "placeholder_structural_compliance",
    "placeholder_structural_compliance_only",
    "not yet regenerated",
    "Minimal scaffold for CI compliance",
    "structural compliance layer",
)

HIGH_AUTHORITY_FILES = {
    "pipeline_summary.json",
    "runtime_stage_verification.json",
    "runtime_path_audit.json",
    "no_trade_root_causes.json",
    "kept_symbol_terminal_outcomes.json",
    "verification_bundle.json",
    "reconciliation_report.json",
    "e23_evidence_manifest.json",
    "platform_state.json",
    "platform_integrity_state.json",
    "system_state_certified.md",
    "final_gate_closure.md",
    "verification_output.json",
    "summary.md",
}

MEDIUM_AUTHORITY_GLOBS = (
    "smoke_*.json",
    "decision_engine_verification.json",
    "setup_families_completeness.json",
    "premarket_prep_watchlist.json",
    "latest_pattern_failure_trace.json",
    "*capability*report*.json",
    "*coverage*report*.json",
)

LOW_AUTHORITY_SUFFIXES = (".log", ".txt")

RUNTIME_DOMAIN_HINTS = (
    "final_gate",
    "make_it_trade_guarantee",
    "ross_make_it_trade_layer",
    "p01_runtime_detection_audit",
    "p01_setup_family_sprint",
    "p01_premarket_prep",
    "runtime_mode_authority_repair",
    "regression_repair_pr407",
    "pr408_local_regression_repair",
    "strategy",
    "platform",
    "e24",
    "e25",
    "e26",
)


@dataclass(frozen=True)
class EvidenceRecord:
    path: str
    source_class: str
    authority: str
    domain: str
    placeholder: bool
    size_bytes: int
    modified_at_epoch: float
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_authority(path: Path) -> str:
    lower_name = path.name.lower()
    if lower_name in HIGH_AUTHORITY_FILES:
        return "HIGH"
    for pattern in MEDIUM_AUTHORITY_GLOBS:
        if path.match(pattern):
            return "MEDIUM"
    if path.suffix.lower() in LOW_AUTHORITY_SUFFIXES:
        return "LOW"
    if path.suffix.lower() in {".json", ".md"}:
        return "MEDIUM"
    return "LOW"


def is_placeholder_evidence(path: Path) -> bool:
    payload = _read_text(path).lower()
    return any(marker.lower() in payload for marker in PLACEHOLDER_MARKERS)


def infer_domain(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    parts = [part.lower() for part in rel.parts]
    for part in parts:
        for hint in RUNTIME_DOMAIN_HINTS:
            if hint in part:
                return hint
    return parts[0] if parts else "unknown"


def scan_evidence_root(root: Path, source_class: str) -> list[EvidenceRecord]:
    if not root.exists():
        return []
    records: list[EvidenceRecord] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".md", ".txt", ".log"}:
            continue
        stat = path.stat()
        records.append(
            EvidenceRecord(
                path=str(path),
                source_class=source_class,
                authority=classify_authority(path),
                domain=infer_domain(path, root),
                placeholder=is_placeholder_evidence(path),
                size_bytes=stat.st_size,
                modified_at_epoch=stat.st_mtime,
                sha256=_sha256(path),
            )
        )
    return records


def summarize_evidence_binding(runtime_root: Path, catalogue_root: Path) -> dict[str, Any]:
    runtime_records = scan_evidence_root(runtime_root, "RUNTIME_REAL_EVIDENCE")
    catalogue_records = scan_evidence_root(catalogue_root, "CATALOGUE_GOVERNED_EVIDENCE")

    domains = sorted({r.domain for r in runtime_records + catalogue_records})
    domain_status: dict[str, str] = {}
    unresolved: list[dict[str, str]] = []

    for domain in domains:
        domain_runtime = [r for r in runtime_records if r.domain == domain]
        domain_catalogue = [r for r in catalogue_records if r.domain == domain]
        has_real = any(not r.placeholder for r in domain_runtime)
        has_placeholder_only_catalogue = bool(domain_catalogue) and all(r.placeholder for r in domain_catalogue)
        if has_real:
            domain_status[domain] = "REAL_EVIDENCE_PRESENT"
        elif has_placeholder_only_catalogue:
            domain_status[domain] = "STRUCTURAL_ONLY"
            unresolved.append(
                {
                    "domain": domain,
                    "issue": "placeholder catalogue evidence has no runtime backing",
                }
            )
        elif domain_catalogue:
            domain_status[domain] = "STRUCTURAL_ONLY"
            unresolved.append(
                {
                    "domain": domain,
                    "issue": "catalogue evidence exists but runtime evidence is missing",
                }
            )
        else:
            domain_status[domain] = "MISSING"

    high_runtime_count = sum(1 for r in runtime_records if r.authority == "HIGH" and not r.placeholder)
    if not runtime_records:
        final_posture = "NOT_CERTIFIED"
    elif unresolved:
        final_posture = "STRUCTURAL_ONLY"
    elif high_runtime_count > 0:
        final_posture = "CERTIFIED"
    else:
        final_posture = "REAL_EVIDENCE_PRESENT"

    return {
        "runtime_root": str(runtime_root),
        "catalogue_root": str(catalogue_root),
        "runtime_records": [r.to_dict() for r in runtime_records],
        "catalogue_records": [r.to_dict() for r in catalogue_records],
        "placeholder_artifacts_detected": [
            r.to_dict() for r in runtime_records + catalogue_records if r.placeholder
        ],
        "real_artifacts_detected": [
            r.to_dict() for r in runtime_records if not r.placeholder
        ],
        "domain_status": domain_status,
        "unresolved_gaps": unresolved,
        "final_posture": final_posture,
    }


def write_catalogue_binding_outputs(catalogue_root: Path, summary: dict[str, Any]) -> None:
    catalogue_root.mkdir(parents=True, exist_ok=True)

    reconciliation_path = catalogue_root / "E23_EVIDENCE_RECONCILIATION.json"
    reconciliation_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    report_lines = [
        "# E23 Evidence Source Binding Report",
        "",
        f"- Runtime roots scanned: `{summary.get('runtime_root')}`",
        f"- Catalogue roots scanned: `{summary.get('catalogue_root')}`",
        f"- Placeholder artifacts detected: {len(summary.get('placeholder_artifacts_detected', []))}",
        f"- Real runtime artifacts detected: {len(summary.get('real_artifacts_detected', []))}",
        f"- Final platform certification posture: **{summary.get('final_posture')}**",
        "",
        "## Domain Mapping",
    ]
    for domain, status in sorted(summary.get("domain_status", {}).items()):
        report_lines.append(f"- {domain}: {status}")

    report_lines.append("")
    report_lines.append("## Unresolved Gaps")
    gaps = summary.get("unresolved_gaps", [])
    if not gaps:
        report_lines.append("- None")
    else:
        for gap in gaps:
            report_lines.append(f"- {gap.get('domain')}: {gap.get('issue')}")

    (catalogue_root / "E23_EVIDENCE_SOURCE_BINDING_REPORT.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )
