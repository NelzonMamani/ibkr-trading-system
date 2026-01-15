"""Storage integration for Epoch 5."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List

from src.core_engine.events import (
    ExecutionEvent,
    PatternSummary,
    RiskDecisionRecord,
    ScannerArtifact,
    TradeIntentRecord,
)


class TradeStore:
    def __init__(self, path: str = "output/trade_store.jsonl") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def persist_cycle(
        self,
        scanner: ScannerArtifact,
        patterns: List[PatternSummary],
        intents: List[TradeIntentRecord],
        risk_decisions: List[RiskDecisionRecord],
        executions: List[ExecutionEvent],
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
            return True
        except Exception as exc:
            print(f"[STORAGE] Failed to persist cycle: {exc}")
            return False
