from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict


@dataclass(frozen=True)
class SystemEvent:
    event_type: str
    source: str
    payload: Dict[str, Any]
    timestamp: datetime = datetime.utcnow()
