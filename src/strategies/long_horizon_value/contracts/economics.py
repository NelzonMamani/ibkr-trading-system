from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class EconomicsProfile:
    symbol: str
    owner_earnings: List[float]
    reinvestment_rate: float
    stability_score: float
    negative_years: int
