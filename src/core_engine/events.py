"""Event and artifact contracts for Epoch 5 orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.core_engine.health import HealthSnapshot
from src.core_engine.state import CycleContext


@dataclass
class ScannerArtifact:
    context: CycleContext
    topn_count: int
    survivors_count: int
    watchlist_k: List[str]
    focus_m: List[str]
    drop_reason_summary: Dict[str, int]
    new_symbols: List[str]
    continuing_symbols: List[str]
    dropped_symbols: List[str]
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PatternSummary:
    symbol: str
    best_setup: str
    confidence: float
    rationale: str
    all_patterns: List[Dict[str, Any]]


@dataclass
class TradeIntentRecord:
    symbol: str
    intent_id: str
    setup_id: str
    side: str
    entry: str
    stop: str
    rationale: str
    tags: List[str] = field(default_factory=list)
    entry_price: float | None = None
    entry_price_source: str = "UNSET"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskDecisionRecord:
    symbol: str
    intent_id: str
    decision: str
    max_position_size: int
    constraints: List[str]
    triggered_rules: List[str]
    rationale: str
    available_funds: float = 0.0
    order_value: float = 0.0
    risk_allowed: bool = True
    capital_source: str = "UNKNOWN"
    block_reason: str = ""
    approved_quantity: int = 0
    sizing_basis: str = "CAPITAL_PCT_MODE"
    entry_price: float | None = None


@dataclass
class ExecutionEvent:
    symbol: str
    intent_id: str
    action: str
    detail: str


@dataclass
class CycleSummary:
    context: CycleContext
    scanner: ScannerArtifact
    pattern_summaries: List[PatternSummary]
    intents: List[TradeIntentRecord]
    risk_decisions: List[RiskDecisionRecord]
    execution_events: List[ExecutionEvent]
    health: HealthSnapshot
    stage_order: List[str]
