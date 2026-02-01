from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class PortfolioPlan:
    allocations: Dict[str, float]
    total_target_pct: float
    buy_ready: List[str]
    blocked: List[str]
    notes: List[str]
