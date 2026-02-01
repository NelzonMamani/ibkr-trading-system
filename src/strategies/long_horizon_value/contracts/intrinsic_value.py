from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class SensitivityPoint:
    growth: float
    discount: float
    value: float


@dataclass
class IntrinsicValueRange:
    symbol: str
    low: float
    base: float
    high: float
    method_notes: str
    sensitivity: List[SensitivityPoint]
