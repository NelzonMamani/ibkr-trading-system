from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass(frozen=True)
class SystemEvent:
    event_type: str
    source: str
    payload: Dict[str, Any]
    tick: int | None = None
    seq: int | None = None
    timestamp: datetime = field(default_factory=datetime.now)
