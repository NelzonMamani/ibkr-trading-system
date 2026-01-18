from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal, Dict, List


Timeframe = Literal["D1", "M5", "M1", "S10"]
SessionMode = Literal["OPEN_FAST", "MIDDAY_SLOW", "LATE_SLOW"]


@dataclass(frozen=True)
class L2Iceberg:
    side: Literal["BID", "ASK"]
    price: float
    size: int  # shares


@dataclass
class SymbolIndicators:
    vwap: Optional[float] = None
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None


@dataclass
class Candle:
    ts: datetime
    o: float
    h: float
    l: float
    c: float
    v: int

    @property
    def body(self) -> float:
        return abs(self.c - self.o)

    @property
    def range(self) -> float:
        return self.h - self.l

    @property
    def upper_wick(self) -> float:
        return max(0.0, self.h - max(self.o, self.c))

    @property
    def lower_wick(self) -> float:
        return max(0.0, min(self.o, self.c) - self.l)


@dataclass
class SymbolContext:
    symbol: str

    # Selection gates
    last: Optional[float] = None
    prev_close: Optional[float] = None
    gap_pct: Optional[float] = None
    rvol: Optional[float] = None
    float_shares: Optional[int] = None

    # Intraday state
    session_mode: SessionMode = "OPEN_FAST"
    indicators_1m: SymbolIndicators = field(default_factory=SymbolIndicators)
    indicators_10s: SymbolIndicators = field(default_factory=SymbolIndicators)

    # Recent candles (most-recent last)
    candles_1m: List[Candle] = field(default_factory=list)
    candles_10s: List[Candle] = field(default_factory=list)

    # Microstructure (optional)
    l2_icebergs: List[L2Iceberg] = field(default_factory=list)
    spread: Optional[float] = None


@dataclass
class StrategyContext:
    now: datetime
    mode: SessionMode
    market_regime: Dict[str, float] = field(default_factory=dict)
    symbols: Dict[str, SymbolContext] = field(default_factory=dict)
    open_positions: Dict[str, Dict] = field(default_factory=dict)  # broker-neutral
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    consecutive_losses: int = 0
    safety_flags: Dict[str, bool] = field(default_factory=dict)

@dataclass(frozen=True)
class Candle:
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


@dataclass(frozen=True)
class SymbolIndicators:
    vwap: Optional[float] = None
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    rvol: Optional[float] = None
    float_shares: Optional[float] = None


@dataclass(frozen=True)
class SymbolContext:
    symbol: str
    timestamp: datetime
    mode: SessionMode

    # price/volume snapshot
    last: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    last_size: Optional[int] = None
    day_volume: Optional[float] = None

    # key levels
    prev_close: Optional[float] = None
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    hod: Optional[float] = None
    lod: Optional[float] = None

    # candles by timeframe (latest first)
    candles: Dict[Timeframe, List[Candle]] = field(default_factory=dict)

    # derived indicators
    ind: SymbolIndicators = field(default_factory=SymbolIndicators)

    # optional orderflow
    top_iceberg: Optional[L2Iceberg] = None


@dataclass(frozen=True)
class AccountContext:
    equity: float
    realised_pnl: float
    unrealised_pnl: float
    max_loss_limit: float
    is_halted: bool = False


@dataclass(frozen=True)
class StrategyContext:
    now: datetime
    market_is_open: bool
    account: AccountContext
    symbols: Dict[str, SymbolContext]
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None


@dataclass(frozen=True)
class SymbolPreMarket:
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    gap_percent: Optional[float] = None


@dataclass(frozen=True)
class SymbolLiquidity:
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[float] = None
    rvol: Optional[float] = None


@dataclass(frozen=True)
class SymbolContext:
    symbol: str
    now: datetime
    mode: SessionMode

    # candles by timeframe: most recent candle is last element
    candles: Dict[Timeframe, List[Candle]] = field(default_factory=dict)

    premarket: SymbolPreMarket = field(default_factory=SymbolPreMarket)
    liquidity: SymbolLiquidity = field(default_factory=SymbolLiquidity)
    indicators: SymbolIndicators = field(default_factory=SymbolIndicators)

    # optional advanced feeds
    l2_icebergs: List[L2Iceberg] = field(default_factory=list)
    gap_percent: Optional[float] = None
    news_catalyst: Optional[bool] = None


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
    candles: Dict[Timeframe, List[Candle]] = field(default_factory=dict)
    premarket: SymbolPreMarket = field(default_factory=SymbolPreMarket)
    md: SymbolMarketData = field(default_factory=SymbolMarketData)
    ind: SymbolIndicators = field(default_factory=SymbolIndicators)
    l2_iceberg: Optional[L2Iceberg] = None  # optional if no Level2 subscription


@dataclass(frozen=True)
class StrategyContext:
    timestamp: datetime
    mode: SessionMode
    account_equity: float
    open_pnl: float
    realized_pnl: float
    positions: Dict[str, int] = field(default_factory=dict)
    symbols: Dict[str, SymbolContext] = field(default_factory=dict)
class SymbolContext:
    symbol: str
    as_of: datetime
    mode: SessionMode

    market: SymbolMarketData
    premarket: SymbolPreMarket
    ind: SymbolIndicators

    candles: Dict[Timeframe, List[Candle]] = field(default_factory=dict)

    # optional microstructure
    l2_icebergs: List[L2Iceberg] = field(default_factory=list)
   
    # helper metadata
    float_millions: Optional[float] = None
    halted: bool = False


@dataclass(frozen=True)
class StrategyContext:
    as_of: datetime
    mode: SessionMode
    symbols: Dict[str, SymbolContext]

    # account / risk state (read-only)
    equity: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    daily_max_loss: Optional[float] = None
    breaker_tripped: bool = False
    float_millions: Optional[float] = None
    is_halted: bool = False


@dataclass(frozen=True)
class StrategyContext:
    run_id: str
    now: datetime
    mode: SessionMode
    account_equity: float
    daily_pnl: float
    max_daily_loss: float

    symbols: Dict[str, SymbolContext]

    # Global market regime hints (optional)
    spy_trend: Optional[Literal["UP", "DOWN", "CHOP"]] = None
    spy_trend: Optional[Literal["UP", "DOWN", "CHOP"]] = None


# The Strategy Policy declares what it requires from this schema.
