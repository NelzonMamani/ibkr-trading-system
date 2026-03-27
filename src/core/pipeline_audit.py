from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json
from typing import Dict, Iterable


class TerminalOutcome(str, Enum):
    NOT_IN_FOCUS = "NOT_IN_FOCUS"
    FOCUS_SELECTED_NO_PATTERN = "FOCUS_SELECTED_NO_PATTERN"
    FOCUS_SELECTED_PATTERN_REJECTED = "FOCUS_SELECTED_PATTERN_REJECTED"
    DECISION_REJECTED = "DECISION_REJECTED"
    TRIGGER_NOT_FIRED = "TRIGGER_NOT_FIRED"
    TRADE_INTENT_CREATED = "TRADE_INTENT_CREATED"
    RISK_BLOCKED = "RISK_BLOCKED"
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
    EXECUTION_SUBMITTED = "EXECUTION_SUBMITTED"


@dataclass
class TerminalRecord:
    outcome: TerminalOutcome
    reason: str
    stage: str


class PipelineAudit:
    def __init__(self, cycle_id: str) -> None:
        self.cycle_id = cycle_id
        self.kept_symbols: list[str] = []
        self.records: Dict[str, TerminalRecord] = {}

    def mark_kept(self, symbols: Iterable[str]) -> None:
        self.kept_symbols = [str(s).upper() for s in symbols if s]

    def record(self, symbol: str, outcome: TerminalOutcome, reason: str, stage: str) -> None:
        normalized = str(symbol or "").upper()
        if not normalized:
            return
        self.records[normalized] = TerminalRecord(outcome=outcome, reason=reason, stage=stage)

    def summary_payload(self) -> dict:
        counts: dict[str, int] = {outcome.value: 0 for outcome in TerminalOutcome}
        symbols: dict[str, dict] = {}
        for symbol in self.kept_symbols:
            record = self.records.get(symbol)
            if record is None:
                continue
            counts[record.outcome.value] += 1
            symbols[symbol] = {
                "outcome": record.outcome.value,
                "reason": record.reason,
                "stage": record.stage,
            }
        return {
            "cycle_id": self.cycle_id,
            "kept_symbols": list(self.kept_symbols),
            "counts": counts,
            "symbols": symbols,
        }

    def contract_violations(self) -> list[dict]:
        violations: list[dict] = []
        for symbol in self.kept_symbols:
            if symbol in self.records:
                continue
            violations.append(
                {
                    "symbol": symbol,
                    "reason": "MISSING_TERMINAL_OUTCOME",
                    "last_stage": "SCANNER_KEEP",
                }
            )
        return violations

    def persist(self, *, base_dir: Path) -> dict[str, str]:
        base_dir.mkdir(parents=True, exist_ok=True)
        summary = self.summary_payload()
        summary_path = base_dir / "pipeline_summary.json"
        outcomes_path = base_dir / "kept_symbol_terminal_outcomes.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        outcomes_path.write_text(json.dumps(summary.get("symbols", {}), indent=2, sort_keys=True), encoding="utf-8")

        violations = self.contract_violations()
        violation_path = base_dir / "contract_violations.json"
        if violations:
            violation_path.write_text(json.dumps(violations, indent=2, sort_keys=True), encoding="utf-8")
        elif violation_path.exists():
            violation_path.unlink()

        return {
            "summary": summary_path.as_posix(),
            "outcomes": outcomes_path.as_posix(),
            "violations": violation_path.as_posix(),
        }
