from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class RegimeLabel(str, Enum):
    OPENING_MOMENTUM = "OPENING_MOMENTUM"
    CHOP_LOW_VOL = "CHOP_LOW_VOL"
    TRENDING = "TRENDING"
    HIGH_VOL_RISK_OFF = "HIGH_VOL_RISK_OFF"
    NEWS_DRIVEN = "NEWS_DRIVEN"
    AFTER_HOURS_THIN = "AFTER_HOURS_THIN"
    UNKNOWN = "UNKNOWN"


class RegimeDataQualityFlag(str, Enum):
    MISSING_PRICE = "MISSING_PRICE"
    MISSING_VOLUME = "MISSING_VOLUME"
    MISSING_SPREAD = "MISSING_SPREAD"
    MISSING_RVOL = "MISSING_RVOL"
    MISSING_GAP = "MISSING_GAP"
    MISSING_MOMENTUM = "MISSING_MOMENTUM"
    MISSING_NEWS = "MISSING_NEWS"
    MISSING_ORDERBOOK = "MISSING_ORDERBOOK"
    THIN_LIQUIDITY = "THIN_LIQUIDITY"


@dataclass(frozen=True)
class FeatureVector:
    session: str
    universe_count: int
    median_spread_bps: Optional[float]
    pct_missing_prices: float
    pct_missing_volume: float
    median_rvol: Optional[float]
    median_gap_pct: Optional[float]
    top1_momentum_move_pct: Optional[float]
    news_density_proxy: float
    liquidity_thin_flag: bool
    feature_set: str = "BASIC"
    return_volatility_proxy: Optional[float] = None
    range_expansion_proxy: Optional[float] = None
    orderbook_quality_proxy: Optional[float] = None

    def to_payload(self) -> Dict[str, Optional[float] | str | int | bool]:
        return {
            "session": self.session,
            "universe_count": self.universe_count,
            "median_spread_bps": self.median_spread_bps,
            "pct_missing_prices": self.pct_missing_prices,
            "pct_missing_volume": self.pct_missing_volume,
            "median_rvol": self.median_rvol,
            "median_gap_pct": self.median_gap_pct,
            "top1_momentum_move_pct": self.top1_momentum_move_pct,
            "news_density_proxy": self.news_density_proxy,
            "liquidity_thin_flag": self.liquidity_thin_flag,
            "feature_set": self.feature_set,
            "return_volatility_proxy": self.return_volatility_proxy,
            "range_expansion_proxy": self.range_expansion_proxy,
            "orderbook_quality_proxy": self.orderbook_quality_proxy,
        }


@dataclass(frozen=True)
class RegimeEvidenceItem:
    feature_name: str
    value: Optional[float]
    baseline: Optional[float]
    contribution: float
    note: str

    def to_payload(self) -> Dict[str, Optional[float] | str]:
        return {
            "feature_name": self.feature_name,
            "value": self.value,
            "baseline": self.baseline,
            "contribution": self.contribution,
            "note": self.note,
        }


@dataclass(frozen=True)
class RegimeSnapshot:
    label: RegimeLabel
    confidence: float
    session: str
    features: FeatureVector
    evidence: List[RegimeEvidenceItem] = field(default_factory=list)
    data_quality_flags: List[RegimeDataQualityFlag] = field(default_factory=list)
    baseline_stats: Dict[str, Dict[str, float | None]] = field(default_factory=dict)
    timestamp_utc: Optional[str] = None

    def to_payload(self) -> Dict[str, object]:
        return {
            "label": self.label.value,
            "confidence": self.confidence,
            "session": self.session,
            "features": self.features.to_payload(),
            "evidence": [item.to_payload() for item in self.evidence],
            "data_quality_flags": [flag.value for flag in self.data_quality_flags],
            "baseline_stats": self.baseline_stats,
            "timestamp_utc": self.timestamp_utc,
        }


@dataclass(frozen=True)
class RegimePolicyDecision:
    label: RegimeLabel
    confidence: float
    applied: bool
    eligible_strategies: List[str] = field(default_factory=list)
    strategy_weights: Dict[str, float] = field(default_factory=dict)
    risk_multiplier: float = 1.0
    notes: List[str] = field(default_factory=list)
    data_quality_flags: List[RegimeDataQualityFlag] = field(default_factory=list)
    timestamp_utc: Optional[str] = None

    def to_payload(self) -> Dict[str, object]:
        return {
            "label": self.label.value,
            "confidence": self.confidence,
            "applied": self.applied,
            "eligible_strategies": list(self.eligible_strategies),
            "strategy_weights": dict(self.strategy_weights),
            "risk_multiplier": self.risk_multiplier,
            "notes": list(self.notes),
            "data_quality_flags": [flag.value for flag in self.data_quality_flags],
            "timestamp_utc": self.timestamp_utc,
        }
