from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class DataQualityFlags:
    flags: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.flags


@dataclass
class FundamentalsSeries:
    years: List[int]
    revenue: List[float]
    operating_cashflow: List[float]
    capex: List[float]
    net_debt_to_ebitda: float
    interest_coverage: float
    shares_outstanding: float
    dividends: List[float]


@dataclass
class FundamentalsRecord:
    symbol: str
    currency: str
    series: FundamentalsSeries
    data_quality: DataQualityFlags


@dataclass
class FundamentalsDataset:
    records: Dict[str, FundamentalsRecord]
    generated_at: str
    cache_hits: List[str] = field(default_factory=list)
