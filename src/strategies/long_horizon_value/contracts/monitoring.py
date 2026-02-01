from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class MonitoringReport:
    symbol: str
    action: str
    reasons: List[str]
