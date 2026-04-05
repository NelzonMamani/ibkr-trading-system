from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import json
from typing import Dict, Iterable


class TerminalOutcome(str, Enum):
    SCANNER_REJECTED = "SCANNER_REJECTED"
    WATCHLIST_REJECTED = "WATCHLIST_REJECTED"
    FOCUS_REJECTED = "FOCUS_REJECTED"
    MISSING_MARKET_CONTEXT = "MISSING_MARKET_CONTEXT"
    MISSING_PATTERN_INPUTS = "MISSING_PATTERN_INPUTS"
    NO_PATTERN_DETECTED = "NO_PATTERN_DETECTED"
    PATTERN_DETECTED_BUT_SUPPRESSED = "PATTERN_DETECTED_BUT_SUPPRESSED"
    TRIGGER_NOT_FIRED = "TRIGGER_NOT_FIRED"
    INTENT_NOT_EMITTED = "INTENT_NOT_EMITTED"
    INTENT_REJECTED_BY_POLICY = "INTENT_REJECTED_BY_POLICY"
    RISK_BLOCKED = "RISK_BLOCKED"
    EXECUTION_PRECHECK_BLOCKED = "EXECUTION_PRECHECK_BLOCKED"
    EXECUTION_SUBMISSION_FAILED = "EXECUTION_SUBMISSION_FAILED"
    EXECUTION_SUBMITTED = "EXECUTION_SUBMITTED"
    CALLBACK_PENDING = "CALLBACK_PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    POSITION_RECONCILED_ONLY = "POSITION_RECONCILED_ONLY"
    SKIPPED_MODE_OR_SESSION_POLICY = "SKIPPED_MODE_OR_SESSION_POLICY"

    # Backward-compatible legacy names retained for existing callers/tests.
    NOT_IN_FOCUS = "FOCUS_REJECTED"
    FOCUS_SELECTED_NO_PATTERN = "NO_PATTERN_DETECTED"
    FOCUS_SELECTED_PATTERN_REJECTED = "PATTERN_DETECTED_BUT_SUPPRESSED"
    DECISION_REJECTED = "INTENT_REJECTED_BY_POLICY"
    TRADE_INTENT_CREATED = "INTENT_NOT_EMITTED"
    EXECUTION_BLOCKED = "EXECUTION_PRECHECK_BLOCKED"


@dataclass
class TerminalRecord:
    outcome: TerminalOutcome
    reason: str
    stage: str


@dataclass
class TradePathTrace:
    cycle_id: str
    timestamp_utc: str
    runtime_mode: str | None
    strategy_key: str | None
    symbol: str
    symbol_source: str | None = None
    session_label: str | None = None
    session_phase: str | None = None
    scanner_seen: bool = False
    watchlist_seen: bool = False
    focus_seen: bool = False
    pattern_inputs_ready: bool = False
    pattern_detected: bool = False
    trigger_fired: bool = False
    intent_emitted: bool = False
    risk_approved: bool = False
    execution_attempted: bool = False
    execution_submitted: bool = False
    callback_state: str | None = None
    final_verdict: str | None = None
    blocking_stage: str | None = None
    blocking_reason: str | None = None
    supporting_reasons: list[str] = field(default_factory=list)
    order_ref: str | None = None
    broker_order_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_execution_reason(reason: str | None) -> str:
    value = str(reason or "").strip().upper()
    if not value:
        return "UNKNOWN_EXECUTION_REASON"
    if "EXECUTION_DISABLED" in value:
        return "EXECUTION_DISABLED"
    if "BROKER_NOT_CONNECTED" in value:
        return "BROKER_NOT_CONNECTED"
    if "PRICE" in value and "AUTH" in value:
        return "PRICE_AUTHORITY_BLOCKED"
    if "DUPLICATE_POSITION" in value:
        return "DUPLICATE_POSITION_BLOCKED"
    if "INVALID_ORDER" in value and "QUANTITY" in value:
        return "INVALID_QTY"
    if "INVALID_ORDER" in value:
        return "INVALID_ORDER_CONFIG"
    if "NO_IBKR_ORDER_ID" in value or "NO_BROKER_ORDER_ID" in value:
        return "NO_BROKER_ORDER_ID"
    if "EXCEPTION" in value:
        return "SUBMISSION_EXCEPTION"
    if "SUBMITTED" in value or "ORDER_SUBMITTED" in value:
        return "SUBMITTED"
    if "CALLBACK" in value and "PENDING" in value:
        return "CALLBACK_PENDING"
    if "SESSION" in value or "RUN_MODE_BLOCK" in value or "READ_ONLY" in value:
        return "MODE_OR_SESSION_POLICY"
    return value


class PipelineAudit:
    def __init__(self, cycle_id: str, *, runtime_mode: str | None = None, strategy_key: str | None = None) -> None:
        self.cycle_id = cycle_id
        self.runtime_mode = runtime_mode
        self.strategy_key = strategy_key
        self.kept_symbols: list[str] = []
        self.records: Dict[str, TerminalRecord] = {}
        self._traces: Dict[str, TradePathTrace] = {}

    def mark_kept(self, symbols: Iterable[str]) -> None:
        self.kept_symbols = [str(s).upper() for s in symbols if s]
        for symbol in self.kept_symbols:
            trace = self.ensure_symbol(symbol)
            trace.scanner_seen = True

    def ensure_symbol(self, symbol: str) -> TradePathTrace:
        normalized = str(symbol or "").upper()
        if not normalized:
            raise ValueError("symbol is required")
        existing = self._traces.get(normalized)
        if existing is not None:
            return existing
        trace = TradePathTrace(
            cycle_id=self.cycle_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            runtime_mode=self.runtime_mode,
            strategy_key=self.strategy_key,
            symbol=normalized,
        )
        self._traces[normalized] = trace
        return trace

    def mark_stage(self, symbol: str, stage: str, **updates: object) -> None:
        trace = self.ensure_symbol(symbol)
        stage_upper = str(stage or "").upper()
        trace.supporting_reasons.append(f"STAGE:{stage_upper}")
        for key, value in updates.items():
            if hasattr(trace, key):
                setattr(trace, key, value)

    def record(self, symbol: str, outcome: TerminalOutcome, reason: str, stage: str) -> None:
        normalized = str(symbol or "").upper()
        if not normalized:
            return
        normalized_reason = normalize_execution_reason(reason) if str(stage).upper() == "EXECUTION" else reason
        self.records[normalized] = TerminalRecord(outcome=outcome, reason=normalized_reason, stage=stage)
        trace = self.ensure_symbol(normalized)
        trace.final_verdict = outcome.value
        trace.blocking_stage = stage
        trace.blocking_reason = normalized_reason
        trace.supporting_reasons.append(normalized_reason)
        trace.execution_attempted = trace.execution_attempted or stage.lower() == "execution"
        trace.execution_submitted = trace.execution_submitted or outcome == TerminalOutcome.EXECUTION_SUBMITTED
        if outcome == TerminalOutcome.EXECUTION_SUBMITTED and not trace.callback_state:
            trace.callback_state = "CALLBACK_PENDING"

    def summary_payload(self) -> dict:
        counts: dict[str, int] = {outcome.value: 0 for outcome in TerminalOutcome}
        symbols: dict[str, dict] = {}
        readiness = {
            "symbols_pattern_ready": 0,
            "symbols_trigger_ready": 0,
            "symbols_intent_ready": 0,
            "symbols_risk_ready": 0,
            "symbols_execution_ready": 0,
            "symbols_submitted": 0,
        }
        for symbol in self.kept_symbols:
            trace = self._traces.get(symbol)
            record = self.records.get(symbol)
            if trace is None and record is None:
                continue
            if trace is not None:
                readiness["symbols_pattern_ready"] += int(trace.pattern_detected)
                readiness["symbols_trigger_ready"] += int(trace.trigger_fired)
                readiness["symbols_intent_ready"] += int(trace.intent_emitted)
                readiness["symbols_risk_ready"] += int(trace.risk_approved)
                readiness["symbols_execution_ready"] += int(trace.execution_attempted)
                readiness["symbols_submitted"] += int(trace.execution_submitted)
            if record is not None:
                counts[record.outcome.value] += 1
                symbols[symbol] = {
                    "outcome": record.outcome.value,
                    "reason": record.reason,
                    "stage": record.stage,
                }
        dominant_verdicts = {k: v for k, v in sorted(counts.items(), key=lambda item: item[1], reverse=True) if v > 0}
        reason_counts: dict[str, int] = {}
        for rec in self.records.values():
            reason_counts[rec.reason] = reason_counts.get(rec.reason, 0) + 1
        dominant_reasons = {k: v for k, v in sorted(reason_counts.items(), key=lambda item: item[1], reverse=True) if v > 0}

        return {
            "cycle_id": self.cycle_id,
            "kept_symbols": list(self.kept_symbols),
            "counts": counts,
            "symbols": symbols,
            "readiness": readiness,
            "dominant_final_verdicts": dominant_verdicts,
            "dominant_blocking_reasons": dominant_reasons,
            "trade_path_traces": [self._traces[s].to_dict() for s in self.kept_symbols if s in self._traces],
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
        traces_path = base_dir / "trade_path_traces.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        outcomes_path.write_text(json.dumps(summary.get("symbols", {}), indent=2, sort_keys=True), encoding="utf-8")
        traces_path.write_text(json.dumps(summary.get("trade_path_traces", []), indent=2, sort_keys=True), encoding="utf-8")

        violations = self.contract_violations()
        violation_path = base_dir / "contract_violations.json"
        if violations:
            violation_path.write_text(json.dumps(violations, indent=2, sort_keys=True), encoding="utf-8")
        elif violation_path.exists():
            violation_path.unlink()

        return {
            "summary": summary_path.as_posix(),
            "outcomes": outcomes_path.as_posix(),
            "traces": traces_path.as_posix(),
            "violations": violation_path.as_posix(),
        }
