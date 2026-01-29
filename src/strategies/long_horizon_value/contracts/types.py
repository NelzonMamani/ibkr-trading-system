from dataclasses import dataclass
from typing import List, Optional

@dataclass(frozen=True)
class SymbolRef:
    symbol: str
    exchange: str
    currency: str
    country: str

@dataclass
class Decision:
    allowed: bool
    reasons: List[str]
    notes: Optional[str] = None
