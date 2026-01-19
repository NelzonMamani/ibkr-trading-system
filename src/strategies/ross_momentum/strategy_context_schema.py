from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Literal

Timeframe = Literal["D1", "M5", "M1", "S10"]
SessionMode = Literal["OPEN_FAST", "MIDDAY_SLOW", "LATE_SLOW"]
SessionPhase = Literal[
    "PREMARKET",
    "OPENING_0_30",
    "MORNING",
    "MIDDAY",
    "LATE",
    "POWER_HOUR",
    "CLOSED",
]


@dataclass(frozen=True)
class L2Iceberg:
    side: Literal["BID", "ASK"]
    price: float
    size: int


@dataclass(frozen=True)
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return max(0.0, self.high - self.low)

    @property
    def upper_wick(self) -> float:
        return max(0.0, self.high - max(self.open, self.close))

    @property
    def lower_wick(self) -> float:
        return max(0.0, min(self.open, self.close) - self.low)


@dataclass(frozen=True)
class SymbolIndicators:
    vwap: Optional[float] = None
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    rvol: Optional[float] = None
    float_shares: Optional[float] = None


@dataclass(frozen=True)
class SymbolMarketData:
    last: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    last_size: Optional[int] = None
    day_volume: Optional[float] = None
    rel_volume: Optional[float] = None


@dataclass(frozen=True)
class SymbolContext:
    symbol: str
    timestamp: datetime
    mode: SessionMode

    md: SymbolMarketData = field(default_factory=SymbolMarketData)
    ind: SymbolIndicators = field(default_factory=SymbolIndicators)
    candles: Dict[Timeframe, List[Candle]] = field(default_factory=dict)

    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    hod: Optional[float] = None
    lod: Optional[float] = None
    key_levels: Dict[str, float] = field(default_factory=dict)

    l2_icebergs: List[L2Iceberg] = field(default_factory=list)
    halted: bool = False
    data_quality_flags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyContext:
    now: datetime
    ny_time: datetime
    uk_time: datetime
    session_phase: SessionPhase
    mode: SessionMode
    symbols: Dict[str, SymbolContext] = field(default_factory=dict)
    open_positions: Dict[str, int] = field(default_factory=dict)
    active_trades: Dict[str, dict] = field(default_factory=dict)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    consecutive_losses: int = 0
    safety_flags: Dict[str, bool] = field(default_factory=dict)
    watchlist_k: List[str] = field(default_factory=list)
    focus_m: List[str] = field(default_factory=list)
