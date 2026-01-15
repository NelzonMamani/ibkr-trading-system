"""State containers for core engine cycles."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ScannerArtifact:
    topn_count: int
    survivors_count: int
    watchlist: List[str]
    focus: List[str]
    drop_summary: Dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CycleSummary:
    cycle_id: int
    mode: str
    session: str
    scanner: ScannerArtifact
    intents_count: int = 0
    risk_decisions: int = 0
    execution_actions: int = 0
    storage_ok: bool = True
    health_status: str = "OK"
    health_reasons: List[str] = field(default_factory=list)
    notes: Optional[str] = None
