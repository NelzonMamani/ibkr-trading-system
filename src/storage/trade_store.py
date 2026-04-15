"""Storage integration for Epoch 5."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, List

from src.storage.storage_engine import StorageEngine

from src.core_engine.events import (
    ExecutionEvent,
    PatternSummary,
    RiskDecisionRecord,
    ScannerArtifact,
    TradeIntentRecord,
)


class TradeStore:
    _shared_storage_engine: StorageEngine | None = None

    def __init__(self, path: str = "output/trade_store.jsonl") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if TradeStore._shared_storage_engine is None:
            TradeStore._shared_storage_engine = StorageEngine()

    def persist_cycle(
        self,
        scanner: ScannerArtifact,
        patterns: List[PatternSummary],
        intents: List[TradeIntentRecord],
        risk_decisions: List[RiskDecisionRecord],
        executions: List[ExecutionEvent],
        trade_admission_rows: list[dict[str, Any]] | None = None,
        trade_blocker_rows: list[dict[str, Any]] | None = None,
        trade_analytics_rows: list[dict[str, Any]] | None = None,
        cycle_summary_row: dict[str, Any] | None = None,
    ) -> bool:
        record = {
            "cycle": asdict(scanner.context),
            "scanner": asdict(scanner),
            "patterns": [asdict(summary) for summary in patterns],
            "intents": [asdict(intent) for intent in intents],
            "risk_decisions": [asdict(decision) for decision in risk_decisions],
            "executions": [asdict(event) for event in executions],
        }
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            if TradeStore._shared_storage_engine is not None:
                TradeStore._shared_storage_engine.store_make_it_trade_diagnostics(
                    trade_admission_rows=trade_admission_rows or [],
                    trade_blocker_rows=trade_blocker_rows or [],
                    trade_analytics_rows=trade_analytics_rows or [],
                    cycle_summary_row=cycle_summary_row or {},
                )
            return True
        except Exception as exc:
            print(f"[STORAGE] Failed to persist cycle: {exc}")
            return False
