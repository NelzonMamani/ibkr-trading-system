from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class SystemEvent:
    event_type: str
    source: str
    payload: Dict[str, Any]
    tick: Optional[int] = None
    seq: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
