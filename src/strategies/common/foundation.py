"""Strategy foundation primitives and canonical enumerations (E18/E20)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, Sequence

FOUNDATION_VERSION = "E20.0"

SETUP_FAMILIES: tuple[str, ...] = (
    "SF_GAP_AND_GO",
    "SF_GAP_FILL",
    "SF_GAP_CONTINUATION",
    "SF_FAILED_GAP_REVERSAL",
    "SF_OPENING_RANGE_BREAKOUT",
    "SF_OPENING_RANGE_BREAKDOWN",
    "SF_OPENING_RANGE_FAKEOUT",
    "SF_PREMARKET_HIGH_BREAK",
    "SF_PREMARKET_LOW_BREAK",
    "SF_FIRST_PULLBACK",
    "SF_SECOND_PULLBACK",
    "SF_MICRO_PULLBACK",
    "SF_BULL_FLAG",
    "SF_TIGHT_FLAG",
    "SF_FLAT_TOP_BREAKOUT",
    "SF_ASCENDING_TRIANGLE",
    "SF_MOMENTUM_STAIRCASE",
    "SF_PARABOLIC_CONTINUATION",
    "SF_KEY_LEVEL_BREAK",
    "SF_KEY_LEVEL_RECLAIM",
    "SF_HIGH_OF_DAY_BREAK",
    "SF_LOW_OF_DAY_BREAK",
    "SF_PRIOR_DAY_HIGH_BREAK",
    "SF_PRIOR_DAY_LOW_BREAK",
    "SF_PRIOR_DAY_CLOSE_RECLAIM",
    "SF_WEEKLY_LEVEL_INTERACTION",
    "SF_VWAP_TREND_DAY",
    "SF_VWAP_RECLAIM",
    "SF_VWAP_FADE",
    "SF_MEAN_REVERSION_EXTENSION",
    "SF_MEAN_REVERSION_BOUNCE",
    "SF_MEAN_REVERSION_FAILURE",
    "SF_ABCD_CONTINUATION",
    "SF_ABCD_REVERSAL",
    "SF_CUP_AND_HANDLE_INTRADAY",
    "SF_HEAD_AND_SHOULDERS",
    "SF_INVERSE_HEAD_AND_SHOULDERS",
    "SF_ROUNDED_BOTTOM",
    "SF_ROUNDED_TOP",
    "SF_BOX_RANGE",
    "SF_RANGE_EXPANSION",
    "SF_RANGE_FAILURE",
    "SF_VOLATILITY_SQUEEZE",
    "SF_COMPRESSION_COIL",
    "SF_INSIDE_DAY",
    "SF_OUTSIDE_DAY",
    "SF_FAILED_BREAKOUT",
    "SF_FAILED_BREAKDOWN",
    "SF_BULL_TRAP",
    "SF_BEAR_TRAP",
    "SF_LIQUIDITY_SWEEP",
    "SF_STOP_RUN_REVERSAL",
    "SF_HALT_RESUME",
    "SF_NEWS_SPIKE",
    "SF_EARNINGS_REACTION",
    "SF_EVENT_CONTINUATION",
    "SF_EVENT_REVERSAL",
    "SF_OPENING_DRIVE",
    "SF_MIDDAY_COMPRESSION",
    "SF_POWER_HOUR_EXPANSION",
    "SF_LATE_DAY_BREAKDOWN",
    "SF_END_OF_DAY_REVERSION",
    "SF_RELATIVE_STRENGTH_LEADER",
    "SF_RELATIVE_WEAKNESS_LEADER",
    "SF_PAIR_DIVERGENCE",
    "SF_SPREAD_EXPANSION",
    "SF_SPREAD_REVERSION",
    "SF_ZSCORE_EXTREME",
    "SF_VOLATILITY_EXPANSION",
    "SF_VOLATILITY_CONTRACTION",
    "SF_HIGH_VOLATILITY_REGIME",
    "SF_LOW_VOLATILITY_REGIME",
    "SF_DAILY_TREND_PULLBACK",
    "SF_WEEKLY_BASE_BREAKOUT",
    "SF_LONG_TERM_ACCUMULATION",
    "SF_LONG_TERM_DISTRIBUTION",
    "SF_MACRO_REGIME_SHIFT",
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
    "C_MARKET_IS_OPEN",
    "C_MARKET_IS_PREMARKET",
    "C_MARKET_IS_AFTERHOURS",
    "C_MARKET_IS_CLOSED",
    "C_SESSION_PHASE_ALLOWED",
    "C_TIME_OF_DAY_ALLOWED",
    "C_HALT_STATE_ALLOWED",
    "C_SSR_STATE_ALLOWED",
    "C_DATA_QUALITY_OK",
    "C_REFERENCE_PRICE_VALID",
    "C_STALE_DATA_REJECT",
    "C_HAS_BID_ASK",
    "C_SPREAD_WITHIN_LIMIT",
    "C_LIQUIDITY_WITHIN_MIN",
    "C_FLOAT_KNOWN_OR_ALLOWED",
    "C_TREND_ALIGNMENT",
    "C_VWAP_SIDE",
    "C_EMA_STACK",
    "C_LEVELS_BUILT_OK",
    "C_INVALIDATION_DEFINED",
    "C_SETUP_FAMILY_ACTIVE",
    "C_VOLATILITY_STATE_ALLOWED",
    "C_ATR_WITHIN_BOUNDS",
    "C_COMPRESSION_PRESENT",
    "C_RANGE_EXPANSION_PRESENT",
    "C_MEAN_DISTANCE_EXTREME",
    "C_RELATIVE_VOLUME_OK",
    "C_ABSOLUTE_VOLUME_OK",
    "C_PREMARKET_VOLUME_OK",
    "C_VOLUME_ACCELERATION_PRESENT",
    "C_VOLUME_DECELERATION_PRESENT",
    "C_RISK_ENGINE_APPROVED",
    "C_NO_TRADE_CONTEXT_FALSE",
    "C_STRATEGY_PERMISSION_OK",
    "C_MAX_CONSECUTIVE_LOSSES_NOT_REACHED",
    "C_SYMBOL_COOLDOWN_EXPIRED",
)

CONFIRMATIONS: tuple[str, ...] = (
    "K_DATA_QUALITY_CONFIRM",
    "K_SPREAD_CONFIRM",
    "K_LIQUIDITY_CONFIRM",
    "K_VOLUME_CONFIRM",
    "K_RELATIVE_VOLUME_CONFIRM",
    "K_LEVEL_HOLD_CONFIRM",
    "K_BREAK_AND_HOLD_CONFIRM",
    "K_RETEST_CONFIRM",
    "K_INVALIDATION_PRESENT_CONFIRM",
    "K_RISK_ENGINE_GREEN_CONFIRM",
    "K_TAPE_STRENGTH_CONFIRM",
    "K_L2_BID_STACK_CONFIRM",
    "K_L2_ASK_THIN_CONFIRM",
    "K_PULLBACK_WEAK_VOLUME_CONFIRM",
    "K_NO_PARABOLIC_EXHAUSTION_CONFIRM",
    "K_NO_TOPPING_TAILS_CONFIRM",
    "K_MARKET_REGIME_CONFIRM",
    "K_SECTOR_STRENGTH_CONFIRM",
    "K_INDEX_TREND_CONFIRM",
    "K_NEWS_CATALYST_CONFIRM",
    "K_HALT_RESUME_STABILITY_CONFIRM",
    "K_VOLATILITY_WINDOW_CONFIRM",
    "K_TIME_OF_DAY_CONFIRM",
)

LEVELS: tuple[str, ...] = (
    "LVL_PREVIOUS_CLOSE",
    "LVL_PREMARKET_HIGH",
    "LVL_PREMARKET_LOW",
    "LVL_OPEN_PRICE",
    "LVL_HIGH_OF_DAY",
    "LVL_LOW_OF_DAY",
    "LVL_PRIOR_DAY_HIGH",
    "LVL_PRIOR_DAY_LOW",
    "LVL_PRIOR_DAY_CLOSE",
    "LVL_WEEKLY_HIGH",
    "LVL_WEEKLY_LOW",
    "LVL_MONTHLY_HIGH",
    "LVL_MONTHLY_LOW",
    "LVL_ALL_TIME_HIGH",
    "LVL_ALL_TIME_LOW",
    "LVL_VWAP",
    "LVL_ANCHORED_VWAP",
    "LVL_SESSION_VWAP",
    "LVL_EMA_9",
    "LVL_EMA_20",
    "LVL_EMA_50",
    "LVL_EMA_200",
    "LVL_SMA_50",
    "LVL_SMA_200",
    "LVL_VOLUME_WEIGHTED_MID",
)

ZONES: tuple[str, ...] = (
    "ZONE_INTRADAY_SUPPORT",
    "ZONE_INTRADAY_RESISTANCE",
    "ZONE_DAILY_SUPPORT",
    "ZONE_DAILY_RESISTANCE",
    "ZONE_WEEKLY_SUPPORT",
    "ZONE_WEEKLY_RESISTANCE",
    "ZONE_MAJOR_SUPPLY",
    "ZONE_MAJOR_DEMAND",
    "ZONE_CONSOLIDATION",
    "ZONE_BALANCE_AREA",
    "ZONE_GAP_UP",
    "ZONE_GAP_DOWN",
    "ZONE_GAP_FILL_AREA",
    "ZONE_GAP_CONTINUATION",
    "ZONE_GAP_FAILURE",
    "ZONE_SESSION_RANGE",
    "ZONE_OPENING_RANGE",
    "ZONE_PREMARKET_RANGE",
    "ZONE_VALUE_AREA_HIGH",
    "ZONE_VALUE_AREA_LOW",
    "ZONE_POINT_OF_CONTROL",
    "ZONE_ROTATION_RANGE",
    "ZONE_LIQUIDITY_POOL_HIGH",
    "ZONE_LIQUIDITY_POOL_LOW",
    "ZONE_STOP_CLUSTER",
    "ZONE_STOP_RUN",
    "ZONE_SWEEP_AND_REJECT",
    "ZONE_MEASURED_MOVE_TARGET",
    "ZONE_EXTENSION_127",
    "ZONE_EXTENSION_161",
    "ZONE_EXTENSION_200",
    "ZONE_RETRACEMENT_382",
    "ZONE_RETRACEMENT_50",
    "ZONE_RETRACEMENT_618",
    "ZONE_OPENING_DRIVE",
    "ZONE_MIDDAY_CHOP",
    "ZONE_POWER_HOUR",
    "ZONE_LATE_DAY_BREAK",
    "ZONE_LONG_TERM_BASE",
    "ZONE_ACCUMULATION",
    "ZONE_DISTRIBUTION",
    "ZONE_MACRO_SUPPORT",
    "ZONE_MACRO_RESISTANCE",
)

STRUCTURES: tuple[str, ...] = (
    "CH_UPTREND_CHANNEL",
    "CH_DOWNTREND_CHANNEL",
    "CH_PARALLEL_CHANNEL",
    "CH_EXPANDING_CHANNEL",
    "CH_CONTRACTING_CHANNEL",
    "WDG_RISING_WEDGE",
    "WDG_FALLING_WEDGE",
    "TRI_ASCENDING",
    "TRI_DESCENDING",
    "TRI_SYMMETRICAL",
    "TRI_EXPANDING",
    "FLAG_BULL",
    "FLAG_BEAR",
    "FLAG_TIGHT",
    "FLAG_FLAT_TOP",
    "FLAG_PENNANT",
    "INV_STRUCTURE_BREAK",
    "INV_LOWER_LOW",
    "INV_HIGHER_HIGH",
    "INV_TRENDLINE_BREAK",
    "INV_LEVEL_LOSS",
    "INV_VWAP_LOSS",
    "INV_RANGE_FAILURE",
    "INV_PATTERN_FAILURE",
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
