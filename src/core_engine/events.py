"""Event records for core engine cycles."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass(frozen=True)
class CycleEvent:
    event_type: str
    timestamp: datetime
    payload: Dict[str, object]
    source: Optional[str] = None
