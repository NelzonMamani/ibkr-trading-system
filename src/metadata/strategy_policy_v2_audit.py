from __future__ import annotations

import importlib
import json
import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

from src.strategy_policy_v2.policy_v2 import StrategyPolicyV2

CATALOGUE_ROOT = Path("TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES")
MATRIX_V2_PATH = (
    CATALOGUE_ROOT / "04_STRATEGY_CERTIFICATION_AND_GOVERNANCE" / "STRATEGY_AUDIT_MATRIX_V2.md"
)
REPORT_PATH = CATALOGUE_ROOT / "STRATEGY_CERTIFICATION_REPORT.md"
BASELINE_SNAPSHOT_PATH = Path("AUDIT_EVIDENCE/strategy_policy_v2_baseline_snapshot.json")
GOVERNANCE_LOCK_STATUS = "GOVERNANCE_LOCKED_BASELINE_V2"

DOMAIN_LABELS: tuple[tuple[str, str], ...] = (
    ("D0", "Strategy Identity"),
    ("D1", "Stock Selection / Universe Definition"),
    ("D2", "Setup Taxonomy"),
    ("D3", "Conditions"),
    ("D4", "Confirmations"),
    ("D5", "Trigger Model"),
    ("D6", "Intrabar Execution Doctrine"),
    ("D7", "Risk Governance"),
    ("D8", "Exit Governance"),
    ("D9", "Position Management"),
    ("D10", "Data Requirements"),
    ("D11", "Safety & Failure Modes"),
    ("D12", "Execution Constraints"),
    ("D13", "Timeframe Authority"),
    ("D14", "Scaling Doctrine"),
)

MIN_REQUIRED_FIELDS = {"symbol", "last_price"}


@dataclass(frozen=True)
class ControlResult:
    control_id: str
    severity: Literal["CRITICAL", "MAJOR", "MINOR"]
    status: Literal["PASS", "FAIL", "NOT_APPLICABLE"]
    message: str


@dataclass
class DomainResult:
    domain_id: str
    name: str
    controls: list[ControlResult] = field(default_factory=list)

    @property
    def verdict(self) -> Literal["PASS", "FAIL", "NOT_APPLICABLE"]:
        critical_fail = any(c.severity == "CRITICAL" and c.status == "FAIL" for c in self.controls)
        major_fail = any(c.severity == "MAJOR" and c.status == "FAIL" for c in self.controls)
        all_na = all(c.status == "NOT_APPLICABLE" for c in self.controls)
        if critical_fail or major_fail:
            return "FAIL"
        if all_na:
            return "NOT_APPLICABLE"
        return "PASS"

    @property
    def missing_controls(self) -> list[str]:
        return [f"{c.control_id}: {c.message}" for c in self.controls if c.status == "FAIL"]


@dataclass
class StrategyAuditResult:
    strategy_id: str
    slug: str
    domains: list[DomainResult]
    default_only: bool
    governance_lock_violation: bool = False
    governance_lock_message: str = ""

    @property
    def critical_failures(self) -> list[str]:
        failures: list[str] = []
        for domain in self.domains:
            for control in domain.controls:
                if control.severity == "CRITICAL" and control.status == "FAIL":
                    failures.append(f"{control.control_id}: {control.message}")
        return failures

    @property
    def minor_failures_only(self) -> bool:
        failed_controls = [
            c
            for domain in self.domains
            for c in domain.controls
            if c.status == "FAIL"
        ]
        return bool(failed_controls) and all(c.severity == "MINOR" for c in failed_controls)

    @property
    def missing_controls(self) -> list[str]:
        missing: list[str] = []
        for domain in self.domains:
            missing.extend(domain.missing_controls)
        return sorted(missing)

    @property
    def verdict(self) -> Literal["CERTIFIED", "CONDITIONALLY_CERTIFIED", "FAIL", "INVALIDATED_PENDING_REVIEW"]:
        if self.governance_lock_violation:
            return "INVALIDATED_PENDING_REVIEW"
        if self.default_only:
            return "FAIL"
        if self.critical_failures:
            return "FAIL"
        if any(d.verdict == "FAIL" for d in self.domains):
            return "FAIL"
        if self.minor_failures_only:
            return "CONDITIONALLY_CERTIFIED"
        return "CERTIFIED"


def _catalogue_strategies() -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for directory in sorted(p for p in CATALOGUE_ROOT.iterdir() if p.is_dir() and p.name.startswith("P")):
        strategy_id, raw_slug = directory.name.split("_", 1)
        if "P01" <= strategy_id <= "P20":
            entries.append((strategy_id, raw_slug.lower()))
    return entries


def _policy_path(slug: str) -> Path:
    return Path("src/strategies") / slug / "strategy_policy_v2.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_baseline_snapshot() -> dict[str, str]:
    if not BASELINE_SNAPSHOT_PATH.exists():
        return {}
    payload = json.loads(BASELINE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    strategies = payload.get("strategies", [])
    baseline: dict[str, str] = {}
    for entry in strategies:
        strategy_id = entry.get("strategy_id")
        sha = entry.get("sha256")
        if isinstance(strategy_id, str) and isinstance(sha, str):
            baseline[strategy_id] = sha
    return baseline


def _note_values(policy: StrategyPolicyV2) -> list[str]:
    values = [
        policy.notes,
        policy.execution_model.notes,
        policy.intrabar_execution.notes,
        policy.data_requirements.notes,
        policy.position_management.notes,
        policy.session_semantics.market_closed_semantics,
    ]
    return [value for value in values if isinstance(value, str)]


def _na_declared(policy: StrategyPolicyV2, *tokens: str) -> bool:
    haystack = "\n".join(_note_values(policy)).upper()
    has_marker = "NOT_APPLICABLE" in haystack or "N/A" in haystack
    return has_marker and all(token.upper() in haystack for token in tokens)


def _is_non_empty_text(value: str) -> bool:
    return bool(value and value.strip())


def _contains_any(values: Iterable[str], options: set[str]) -> bool:
    lowered = {v.lower() for v in values}
    return any(option in lowered for option in options)


def _is_default_only(policy: StrategyPolicyV2) -> bool:
    if _na_declared(policy):
        return False
    return (
        len(policy.setup_families.families) == 0
        and len(policy.trigger_model.entries) == 0
        and len(policy.trigger_model.confirmations) == 0
        and len(policy.exit_model.rules) == 0
        and len(policy.intrabar_execution.phase_specs) == 0
    )


def _control(domain_id: str, control_num: int, severity: Literal["CRITICAL", "MAJOR", "MINOR"], passed: bool, message: str, na: bool = False) -> ControlResult:
    status: Literal["PASS", "FAIL", "NOT_APPLICABLE"]
    if na:
        status = "NOT_APPLICABLE"
    else:
        status = "PASS" if passed else "FAIL"
    return ControlResult(control_id=f"{domain_id}.C{control_num:02d}", severity=severity, status=status, message=message)


def _domain_results(policy: StrategyPolicyV2) -> list[DomainResult]:
    intrabar_na = _na_declared(policy, "INTRABAR")
    trigger_na = _na_declared(policy, "TRIGGER")
    confirm_na = _na_declared(policy, "CONFIRM") or _na_declared(policy, "CONDITION")
    trailing_na = _na_declared(policy, "TRAIL")

    required_fields = tuple(f.lower() for f in policy.data_requirements.required_fields)
    safety_escalation_present = (
        len(policy.safety_model.rules) > 0
        or len(policy.intrabar_execution.safety_throttles) > 0
        or re.search(r"escalat|fail|bail", "\n".join(_note_values(policy)), re.IGNORECASE) is not None
    )

    domains: list[DomainResult] = []

    d0 = DomainResult("D0", "Strategy Identity")
    d0.controls.extend(
        [
            _control("D0", 1, "CRITICAL", _is_non_empty_text(policy.identity.name) and _is_non_empty_text(policy.identity.strategy_id), "identity fields must be non-empty"),
            _control("D0", 2, "MAJOR", all(_is_non_empty_text(v) for v in (policy.mode_semantics.sim_notes, policy.mode_semantics.paper_notes, policy.mode_semantics.read_only_notes, policy.mode_semantics.live_notes)), "mode semantics notes incomplete"),
            _control("D0", 3, "MAJOR", "CLOSED" in policy.session_semantics.sessions or "closed" in policy.session_semantics.market_closed_semantics.lower(), "session semantics missing CLOSED behavior"),
        ]
    )
    domains.append(d0)

    d1 = DomainResult("D1", "Stock Selection / Universe Definition")
    d1.controls.extend(
        [
            _control("D1", 1, "CRITICAL", policy.selection_plan is not None, "selection_plan missing"),
            _control("D1", 2, "CRITICAL", policy.stock_selection_law is not None, "stock_selection_law missing"),
            _control("D1", 3, "MAJOR", policy.liquidity_sanity_model is not None and _is_non_empty_text(policy.liquidity_sanity_model.halt_policy), "liquidity_sanity_model missing halt policy"),
            _control("D1", 4, "MAJOR", policy.ranking_model is not None and (_is_non_empty_text(policy.ranking_model.ranking_commentary) or _na_declared(policy, "RANK")), "ranking model missing rationale", na=_na_declared(policy, "RANK")),
        ]
    )
    domains.append(d1)

    d2 = DomainResult("D2", "Setup Taxonomy")
    d2.controls.extend(
        [
            _control("D2", 1, "MAJOR", len(policy.setup_families.families) >= 1, "setup_families requires >=1", na=_na_declared(policy, "SETUP")),
            _control("D2", 2, "MAJOR", len(policy.pattern_catalog.patterns) >= 1, "pattern_catalog requires >=1", na=_na_declared(policy, "PATTERN")),
            _control("D2", 3, "MINOR", len(policy.structure_model.levels) >= 1, "structure_model levels should be non-empty"),
        ]
    )
    domains.append(d2)

    d3 = DomainResult("D3", "Conditions")
    d3.controls.extend(
        [
            _control("D3", 1, "MAJOR", len(policy.trigger_model.confirmations) >= 1, "conditions/confirmations require >=1", na=confirm_na),
            _control("D3", 2, "MAJOR", any("quality" in c.condition.lower() or "fresh" in c.condition.lower() for c in policy.trigger_model.confirmations), "data-quality condition missing", na=confirm_na),
            _control("D3", 3, "MINOR", any("level" in c.condition.lower() or "break" in c.condition.lower() or "retest" in c.condition.lower() for c in policy.trigger_model.confirmations), "level behavior condition not declared"),
        ]
    )
    domains.append(d3)

    d4 = DomainResult("D4", "Confirmations")
    d4.controls.extend(
        [
            _control("D4", 1, "MAJOR", len(policy.trigger_model.confirmations) >= 1, "confirmations require >=1", na=confirm_na),
            _control("D4", 2, "MAJOR", any("spread" in c.condition.lower() or "liquidity" in c.condition.lower() for c in policy.trigger_model.confirmations) or len(policy.safety_model.rules) > 0, "liquidity/spread confirmation missing"),
            _control("D4", 3, "MINOR", any("volume" in c.condition.lower() or "rvol" in c.condition.lower() for c in policy.trigger_model.confirmations), "volume/rvol confirmation missing"),
        ]
    )
    domains.append(d4)

    d5 = DomainResult("D5", "Trigger Model")
    d5.controls.extend(
        [
            _control("D5", 1, "MAJOR", policy.trigger_model is not None, "trigger_model missing"),
            _control("D5", 2, "MAJOR", len(policy.trigger_model.entries) >= 1, "trigger entries require >=1", na=trigger_na),
            _control("D5", 3, "MINOR", all(_is_non_empty_text(entry.trigger_id) and _is_non_empty_text(entry.entry_type) for entry in policy.trigger_model.entries), "trigger IDs/categories must be non-empty", na=trigger_na),
        ]
    )
    domains.append(d5)

    d6 = DomainResult("D6", "Intrabar Execution Doctrine")
    d6.controls.extend(
        [
            _control("D6", 1, "MAJOR", policy.intrabar_execution is not None, "intrabar execution model missing"),
            _control("D6", 2, "MAJOR", intrabar_na or len(policy.intrabar_execution.phase_specs) >= 1, "intrabar applicability not declared"),
            _control("D6", 3, "MAJOR", intrabar_na or (len(policy.intrabar_execution.phase_specs) >= 1 and len(policy.intrabar_execution.timeframe_map) >= 1), "intrabar phase_specs/timeframe_map required when applicable", na=intrabar_na),
        ]
    )
    domains.append(d6)

    d7 = DomainResult("D7", "Risk Governance")
    d7.controls.extend(
        [
            _control("D7", 1, "CRITICAL", policy.risk_model is not None, "risk_model missing"),
            _control("D7", 2, "MAJOR", len(policy.safety_model.rules) >= 1 or _na_declared(policy, "SAFETY"), "safety_model requires >=1 rule", na=_na_declared(policy, "SAFETY")),
            _control("D7", 3, "MINOR", _is_non_empty_text(policy.session_reference_law.pct_change_reference) or _is_non_empty_text(policy.session_reference_law.gap_reference), "session reference law is empty"),
        ]
    )
    domains.append(d7)

    d8 = DomainResult("D8", "Exit Governance")
    d8.controls.extend(
        [
            _control("D8", 1, "MAJOR", len(policy.exit_model.rules) >= 1, "exit rules require >=1", na=_na_declared(policy, "EXIT")),
            _control("D8", 2, "MINOR", len(policy.trailing_model.rules) >= 1, "trailing rules should be declared", na=trailing_na),
            _control("D8", 3, "MINOR", len(policy.exit_model.rules) >= 1 or len(policy.intrabar_execution.safety_throttles) >= 1, "failure-fast bailout behavior not declared"),
        ]
    )
    domains.append(d8)

    d9 = DomainResult("D9", "Position Management")
    d9.controls.extend(
        [
            _control("D9", 1, "MAJOR", _is_non_empty_text(policy.position_management.notes), "position management doctrine note required"),
            _control("D9", 2, "MINOR", policy.position_management.allow_scale_in or policy.position_management.allow_partials, "scaling/partials doctrine not explicit"),
        ]
    )
    domains.append(d9)

    d10 = DomainResult("D10", "Data Requirements")
    d10.controls.extend(
        [
            _control("D10", 1, "CRITICAL", len(required_fields) > 0, "required_fields must be non-empty"),
            _control("D10", 2, "MAJOR", MIN_REQUIRED_FIELDS.issubset(set(required_fields)) and (_contains_any(required_fields, {"pct_change", "volume", "rvol"})), "required fields must include symbol,last_price and pct_change|volume|rvol"),
            _control("D10", 3, "MAJOR", re.search(r"pause|reject", policy.data_requirements.notes, re.IGNORECASE) is not None, "data requirements notes must define pause/reject behavior"),
        ]
    )
    domains.append(d10)

    d11 = DomainResult("D11", "Safety & Failure Modes")
    d11.controls.extend(
        [
            _control("D11", 1, "CRITICAL", safety_escalation_present, "explicit safety escalation path required"),
            _control("D11", 2, "MAJOR", not _is_default_only(policy), "default-only policy detected"),
        ]
    )
    domains.append(d11)

    d12 = DomainResult("D12", "Execution Constraints")
    d12.controls.extend(
        [
            _control("D12", 1, "MAJOR", len(policy.execution_model.preferred_order_types) >= 1, "preferred_order_types required"),
            _control("D12", 2, "MINOR", _is_non_empty_text(policy.execution_model.notes), "execution constraints notes missing"),
        ]
    )
    domains.append(d12)

    d13 = DomainResult("D13", "Timeframe Authority")
    timeframe_count = len(policy.intrabar_execution.timeframe_map) + len(policy.session_semantics.sessions)
    d13.controls.extend(
        [
            _control("D13", 1, "MAJOR", timeframe_count >= 1, "timeframe authority must be explicit"),
            _control("D13", 2, "MINOR", len(policy.intrabar_execution.cadence_rules) >= 1 or intrabar_na, "cadence authority should be explicit", na=intrabar_na),
        ]
    )
    domains.append(d13)

    d14 = DomainResult("D14", "Scaling Doctrine")
    d14.controls.extend(
        [
            _control("D14", 1, "MAJOR", _is_non_empty_text(policy.position_management.notes), "scaling doctrine notes missing"),
            _control("D14", 2, "MINOR", policy.position_management.max_adds_per_position >= 0, "max_adds_per_position must be >=0"),
        ]
    )
    domains.append(d14)

    return domains


def run_audit() -> list[StrategyAuditResult]:
    results: list[StrategyAuditResult] = []
    baseline_hashes = _load_baseline_snapshot()
    for strategy_id, slug in _catalogue_strategies():
        module = importlib.import_module(f"src.strategies.{slug}.strategy_policy_v2")
        policy: StrategyPolicyV2 = module.POLICY_V2
        policy_path = _policy_path(slug)
        current_hash = _sha256(policy_path)
        expected_hash = baseline_hashes.get(strategy_id)
        violation = bool(expected_hash) and current_hash != expected_hash
        violation_message = ""
        if violation:
            violation_message = (
                f"GOVERNANCE_LOCK_VIOLATION: {strategy_id} strategy_policy_v2.py hash drift detected "
                f"(expected={expected_hash}, actual={current_hash})"
            )
        results.append(
            StrategyAuditResult(
                strategy_id=strategy_id,
                slug=slug,
                domains=_domain_results(policy),
                default_only=_is_default_only(policy),
                governance_lock_violation=violation,
                governance_lock_message=violation_message,
            )
        )
    return results


def _render_matrix(results: list[StrategyAuditResult], generated_at: str) -> str:
    cols = [name for _, name in DOMAIN_LABELS]
    header = ["Strategy", "Verdict", *cols]
    lines = [
        "# STRATEGY_AUDIT_MATRIX_V2",
        "",
        f"STATUS: {GOVERNANCE_LOCK_STATUS}",
        f"Generated (UTC): {generated_at}",
        "",
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for result in results:
        by_domain = {d.domain_id: d.verdict for d in result.domains}
        row = [result.strategy_id, result.verdict, *[by_domain[d] for d, _ in DOMAIN_LABELS]]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def _render_report(results: list[StrategyAuditResult], generated_at: str) -> str:
    lines = ["# STRATEGY_CERTIFICATION_REPORT", "", f"Generated (UTC): {generated_at}", ""]
    lines.extend(
        [
            "## Summary",
            f"- Strategies audited: {len(results)}",
            f"- CERTIFIED: {sum(1 for r in results if r.verdict == 'CERTIFIED')}",
            f"- CONDITIONALLY_CERTIFIED: {sum(1 for r in results if r.verdict == 'CONDITIONALLY_CERTIFIED')}",
            f"- FAIL: {sum(1 for r in results if r.verdict == 'FAIL')}",
            f"- INVALIDATED_PENDING_REVIEW: {sum(1 for r in results if r.verdict == 'INVALIDATED_PENDING_REVIEW')}",
            "",
            "## Per Strategy Results",
            "",
        ]
    )
    lines.append("| Strategy | Verdict | Default-Only | Missing Controls |")
    lines.append("|---|---|---|---|")
    for result in results:
        missing_items = list(result.missing_controls)
        if result.governance_lock_violation and result.governance_lock_message:
            missing_items.append(result.governance_lock_message)
        missing = "<br>".join(missing_items) if missing_items else "None"
        lines.append(f"| {result.strategy_id}_{result.slug} | {result.verdict} | {result.default_only} | {missing} |")

    for result in results:
        lines.extend(["", f"## {result.strategy_id}_{result.slug}", ""])
        lines.append("| Domain | Verdict |")
        lines.append("|---|---|")
        for domain in result.domains:
            lines.append(f"| {domain.domain_id} {domain.name} | {domain.verdict} |")
        lines.append("")
        lines.append("Missing controls:")
        missing_items = list(result.missing_controls)
        if result.governance_lock_violation and result.governance_lock_message:
            missing_items.append(result.governance_lock_message)
        if missing_items:
            for missing in missing_items:
                lines.append(f"- {missing}")
        else:
            lines.append("- None")
    return "\n".join(lines) + "\n"



def _extract_generated_timestamp(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Generated (UTC): "):
            return line.split("Generated (UTC): ", 1)[1].strip()
    return ""


def _write_baseline_snapshot(results: list[StrategyAuditResult], generated_at: str, matrix_generated_at: str, report_generated_at: str) -> None:
    BASELINE_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    strategies: list[dict[str, str]] = []
    for result in results:
        policy_path = _policy_path(result.slug)
        strategies.append(
            {
                "strategy_id": result.strategy_id,
                "strategy_name": result.slug,
                "policy_path": str(policy_path).replace('\\', '/'),
                "sha256": _sha256(policy_path),
            }
        )
    snapshot = {
        "baseline_version": "v2.0.0",
        "generated_at_utc": generated_at,
        "matrix_generation_timestamp_utc": matrix_generated_at,
        "certification_report_timestamp_utc": report_generated_at,
        "strategies": strategies,
    }
    BASELINE_SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")


def generate_audit_artifacts() -> list[StrategyAuditResult]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    results = run_audit()
    MATRIX_V2_PATH.parent.mkdir(parents=True, exist_ok=True)
    matrix_text = _render_matrix(results, generated_at)
    report_text = _render_report(results, generated_at)
    MATRIX_V2_PATH.write_text(matrix_text, encoding="utf-8")
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    _write_baseline_snapshot(
        results,
        generated_at=generated_at,
        matrix_generated_at=_extract_generated_timestamp(matrix_text),
        report_generated_at=_extract_generated_timestamp(report_text),
    )
    return results
