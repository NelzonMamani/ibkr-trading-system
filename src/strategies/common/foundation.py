"""Strategy foundation primitives and canonical enumerations (E18/E20)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, Sequence

FOUNDATION_VERSION = "E18-E20.1"

SETUP_FAMILIES: tuple[str, ...] = (
    "00_SF_GAP_AND_GO",
    "01_SF_ORB",
    "02_SF_FIRST_PULLBACK_FIRST_FLAG",
    "03_SF_BULL_FLAG_TIGHT_FLAG",
    "04_SF_KEY_LEVEL_BREAK",
    "05_SF_ABCD_CONTINUATION",
    "06_SF_CUP_AND_HANDLE_INTRADAY",
    "07_SF_MOMENTUM_RECLAIM",
    "08_SF_VWAP_TREND_DAY",
    "09_SF_EMA_TREND_STAIRCASE",
    "10_SF_VOLATILITY_SQUEEZE",
    "11_SF_BOX_RANGE_BREAK",
    "12_SF_HOD_LOD_BREAK",
    "13_SF_FAILED_BREAKDOWN_REVERSAL",
    "14_SF_PDC_RECLAIM",
    "15_SF_POWER_HOUR_EXPANSION",
    "16_SF_HALT_RESUME",
    "17_SF_PARABOLIC_EXHAUSTION_AVOID",
)

EXECUTION_TRIGGERS: tuple[str, ...] = (
    "00_XL_MICRO_PULLBACK",
    "01_XL_ORB_BREAK",
    "02_XL_ORB_RETEST",
    "03_XL_FLAG_BREAK",
    "04_XL_FLAG_RECLAIM",
    "05_XL_VWAP_RECLAIM",
    "06_XL_EMA_RECLAIM",
    "07_XL_HOD_BREAK",
    "08_XL_RANGE_BREAK",
    "09_XL_ABCD",
    "10_XL_MEASURED_MOVE",
    "11_XL_LIQUIDITY_SWEEP_RECLAIM",
)

CONDITIONS: tuple[str, ...] = (
    "00_C_R2G_G2R",
    "01_C_TREND_ALIGNMENT",
    "02_C_VWAP_SIDE",
    "03_C_EMA_STACK",
    "04_C_REGIME_PERMISSION",
    "05_C_TIME_OF_DAY",
    "06_C_RELATIVE_VOLUME_STATE",
    "07_C_LIQUIDITY_STATE",
    "08_C_VOLATILITY_STATE",
)

CONFIRMATIONS: tuple[str, ...] = (
    "00_K_VOLUME_CONFIRM",
    "01_K_RELATIVE_VOLUME_CONFIRM",
    "02_K_SPREAD_CONFIRM",
    "03_K_LIQUIDITY_CONFIRM",
    "04_K_LEVEL_HOLD",
    "05_K_BREAK_AND_HOLD",
    "06_K_RETEST_CONFIRM",
    "07_K_NO_PARABOLIC_EXHAUSTION",
    "08_K_DATA_QUALITY_CONFIRM",
)

SINGLE_CANDLE_PATTERNS: tuple[str, ...] = (
    "Hammer",
    "Inverted Hammer",
    "Hanging Man",
    "Shooting Star",
    "Doji",
    "Dragonfly Doji",
    "Gravestone Doji",
    "Spinning Top",
    "Marubozu Bull",
    "Marubozu Bear",
    "Long Lower Wick Rejection",
    "Long Upper Wick Rejection",
    "Wide Range Expansion Bar",
    "Narrow Range Bar",
)

MULTI_CANDLE_PATTERNS: tuple[str, ...] = (
    "Bullish Engulfing",
    "Bearish Engulfing",
    "Inside Bar",
    "Outside Bar",
    "Tweezer Top",
    "Tweezer Bottom",
    "Morning Star",
    "Evening Star",
    "Three White Soldiers",
    "Three Black Crows",
    "Rising Three Methods",
    "Falling Three Methods",
    "Micro Pullback Sequence",
    "Tight Flag Compression Sequence",
    "Gap-and-Go Opening Sequence",
    "Failed Breakout Sequence",
    "Failed Breakdown Sequence",
)


class MarketStructureState(str, Enum):
    STRUCTURE_TREND_UP = "STRUCTURE_TREND_UP"
    STRUCTURE_TREND_DOWN = "STRUCTURE_TREND_DOWN"
    STRUCTURE_BALANCED = "STRUCTURE_BALANCED"
    STRUCTURE_COMPRESSION = "STRUCTURE_COMPRESSION"
    STRUCTURE_EXPANSION = "STRUCTURE_EXPANSION"
    STRUCTURE_BREAK = "STRUCTURE_BREAK"
    STRUCTURE_RECLAIM = "STRUCTURE_RECLAIM"
    STRUCTURE_FAILURE = "STRUCTURE_FAILURE"
    FOLLOW_THROUGH_PRESENT = "FOLLOW_THROUGH_PRESENT"
    CHOP_STATE = "CHOP_STATE"


class InvalidationSeverity(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    TIME = "time"
    DATA = "data"


@dataclass(frozen=True)
class InvalidationEvent:
    invalidation_id: str
    scope: str
    severity: InvalidationSeverity
    reason_code: str
    context: dict[str, object]
    timestamp_utc: datetime


class LevelType(str, Enum):
    VWAP = "VWAP"
    EMA = "EMA"
    PDC = "PDC"
    PDH = "PDH"
    PDL = "PDL"
    HOD = "HOD"
    LOD = "LOD"
    WHOLE_DOLLAR = "WholeDollar"
    HALF_DOLLAR = "HalfDollar"
    CUSTOM = "Custom"


class ZoneType(str, Enum):
    SUPPLY = "supply"
    DEMAND = "demand"
    VOLATILITY_BAND = "volatility_band"
    CUSTOM = "custom"


class InteractionState(str, Enum):
    APPROACH = "approach"
    BREAK = "break"
    HOLD = "hold"
    REJECT = "reject"
    RECLAIM = "reclaim"
    FAIL = "fail"


@dataclass(frozen=True)
class LevelPrimitive:
    level_id: str
    level_type: LevelType
    timeframe: str
    source: str
    price: float | None = None
    bounds: tuple[float, float] | None = None
    tolerance: float | None = None
    strength: float | None = None
    freshness_flags: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ZonePrimitive:
    zone_id: str
    zone_type: ZoneType
    upper: float
    lower: float
    origin: str
    created_timestamp: datetime
    freshness_flags: dict[str, bool] = field(default_factory=dict)
    decay_profile: dict[str, object] | None = None


@dataclass(frozen=True)
class SymbolContext:
    symbol: str
    key_levels: dict[str, float] = field(default_factory=dict)
    zones: list[ZonePrimitive] = field(default_factory=list)
    levels: list[LevelPrimitive] = field(default_factory=list)
    market_structure: list[MarketStructureState] = field(default_factory=list)
    has_news: bool = False
    hydration_complete: bool = False


@dataclass(frozen=True)
class FoundationTranslationReport:
    strategy_id: str
    foundation_version: str
    setup_families: list[str]
    execution_triggers: list[str]
    conditions: list[str]
    confirmations: list[str]
    missing_components: list[str]
    extra_components: list[str]
    compatible: bool


@dataclass
class FoundationStateLifecycle:
    """Regenerable state holder for strategy foundation data."""

    version: str = FOUNDATION_VERSION
    hydrated: bool = False
    last_reset: datetime | None = None

    def soft_reset(self) -> None:
        self.hydrated = False
        self.last_reset = datetime.utcnow()

    def hard_reset(self) -> None:
        self.hydrated = False
        self.last_reset = datetime.utcnow()

    def version_reset(self, version: str) -> None:
        self.version = version
        self.hydrated = False
        self.last_reset = datetime.utcnow()


def is_foundation_compatible(version: str) -> bool:
    """Compatibility check for foundation versioning."""

    return version.split(".")[0] == FOUNDATION_VERSION.split(".")[0]


def validate_foundation_components(
    components: Iterable[str],
    allowed: Sequence[str],
) -> list[str]:
    allowed_set = set(allowed)
    return sorted({component for component in components if component not in allowed_set})


def build_translation_report(
    *,
    strategy_id: str,
    foundation_version: str,
    setup_families: Iterable[str] = (),
    execution_triggers: Iterable[str] = (),
    conditions: Iterable[str] = (),
    confirmations: Iterable[str] = (),
) -> FoundationTranslationReport:
    missing: list[str] = []
    extra: list[str] = []
    extra.extend(validate_foundation_components(setup_families, SETUP_FAMILIES))
    extra.extend(validate_foundation_components(execution_triggers, EXECUTION_TRIGGERS))
    extra.extend(validate_foundation_components(conditions, CONDITIONS))
    extra.extend(validate_foundation_components(confirmations, CONFIRMATIONS))
    compatible = is_foundation_compatible(foundation_version)
    return FoundationTranslationReport(
        strategy_id=strategy_id,
        foundation_version=foundation_version,
        setup_families=list(setup_families),
        execution_triggers=list(execution_triggers),
        conditions=list(conditions),
        confirmations=list(confirmations),
        missing_components=missing,
        extra_components=extra,
        compatible=compatible,
    )


def hydrate_symbol_context(
    symbol: str,
    *,
    key_levels: dict[str, float] | None = None,
    levels: list[LevelPrimitive] | None = None,
    zones: list[ZonePrimitive] | None = None,
    market_structure: list[MarketStructureState] | None = None,
    has_news: bool = False,
) -> SymbolContext:
    return SymbolContext(
        symbol=symbol,
        key_levels=key_levels or {},
        levels=levels or [],
        zones=zones or [],
        market_structure=market_structure or [],
        has_news=has_news,
        hydration_complete=True,
    )
