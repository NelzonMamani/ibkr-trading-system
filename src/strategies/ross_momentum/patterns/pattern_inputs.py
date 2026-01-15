"""Pattern input schema for Ross Momentum patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.strategies.common.candles.candle_types import Candle
from src.strategies.strategy_contracts import SessionContext


@dataclass(frozen=True)
class IndicatorSet:
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    vwap: Optional[float] = None


@dataclass(frozen=True)
class LevelSet:
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    hod: Optional[float] = None
    lod: Optional[float] = None
    prior_close: Optional[float] = None
    key_levels: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class LiquidityContext:
    spread: float
    float_millions: Optional[float] = None
    rvol: Optional[float] = None


@dataclass(frozen=True)
class PatternInputs:
    symbol: str
    timeframe: str
    candles: List[Candle]
    session_context: SessionContext
    levels: LevelSet
    indicators: IndicatorSet
    liquidity_context: LiquidityContext
    news_context: Optional[Dict[str, str]] = None
    data_quality_flags: List[str] = field(default_factory=list)
