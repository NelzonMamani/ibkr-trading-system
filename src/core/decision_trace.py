from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class SymbolDecisionTrace:
    symbol: str
    strategy_name: str
    strategy_prefix: str
    setup_family_id: str
    trigger_id: str
    setup_id: str
    decision_reason: str
    entry_order_id: str | None = None
    stop_order_id: str | None = None
    target_order_id: str | None = None
    broker_status: str | None = None
    stage_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class DecisionTraceStore:
    """In-memory trace store with optional JSONL persistence."""

    def __init__(self, persist_path: str | None = None) -> None:
        self._by_symbol: Dict[str, SymbolDecisionTrace] = {}
        self._persist_path = Path(persist_path) if persist_path else None

    def upsert(self, trace: SymbolDecisionTrace) -> None:
        self._by_symbol[trace.symbol] = trace
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._persist_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(trace), sort_keys=True) + "\n")

    def update_stage(self, symbol: str, stage: str, payload: Dict[str, Any]) -> None:
        trace = self._by_symbol.get(symbol)
        if trace is None:
            return
        trace.stage_results[stage] = dict(payload)
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._persist_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(trace), sort_keys=True) + "\n")

    def by_symbol(self, symbol: str) -> SymbolDecisionTrace | None:
        return self._by_symbol.get(symbol)

    def snapshot(self) -> List[SymbolDecisionTrace]:
        return list(self._by_symbol.values())
