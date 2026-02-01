from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from src.strategies.long_horizon_value.contracts.types import SymbolRef


@dataclass(frozen=True)
class UniverseSnapshot:
    mode: str
    symbols: List[SymbolRef]
    counts_by_market: Dict[str, int]
    timestamp_utc: str
