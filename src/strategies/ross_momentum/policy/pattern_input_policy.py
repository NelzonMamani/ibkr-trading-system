"""Ross pattern input policy section."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.strategies.ross_momentum.strategy_policy import POLICY_V2


class MissingDataBehavior(str, Enum):
    BLOCK = "BLOCK"
    DEGRADE = "DEGRADE"
    WARN = "WARN"
    IGNORE = "IGNORE"


class IndicatorProvenance(str, Enum):
    PRESENT = "PRESENT"
    COMPUTED = "COMPUTED"
    MISSING = "MISSING"
    STALE = "STALE"
    NOT_REQUIRED_FOR_SETUP = "NOT_REQUIRED_FOR_SETUP"
    UNAVAILABLE_FOR_TIMEFRAME = "UNAVAILABLE_FOR_TIMEFRAME"


@dataclass(frozen=True)
class PatternTimeframePlan:
    primary_timeframe: str
    execution_refinement_timeframe: str
    context_timeframe: str
    required_timeframes: tuple[str, ...]
    preferred_timeframes: tuple[str, ...]


@dataclass(frozen=True)
class SetupFamilyInputRequirement:
    setup_family: str
    required_timeframes: tuple[str, ...] = ()
    preferred_timeframes: tuple[str, ...] = ()
    required_indicators: tuple[str, ...] = ()
    optional_indicators: tuple[str, ...] = ()
    required_levels: tuple[str, ...] = ()
    optional_levels: tuple[str, ...] = ()
    missing_data_behavior: dict[str, MissingDataBehavior] = field(default_factory=dict)

    def behavior_for(self, input_name: str) -> MissingDataBehavior:
        return self.missing_data_behavior.get(input_name, MissingDataBehavior.IGNORE)


def _requirements() -> dict[str, SetupFamilyInputRequirement]:
    block = MissingDataBehavior.BLOCK
    degrade = MissingDataBehavior.DEGRADE
    warn = MissingDataBehavior.WARN
    return {
        "MICRO_PULLBACK": SetupFamilyInputRequirement(
            setup_family="MICRO_PULLBACK",
            required_timeframes=("10s", "1m"),
            preferred_timeframes=("5m",),
            required_indicators=("ema9",),
            optional_indicators=("ema20", "vwap", "macd_line", "ema200"),
            missing_data_behavior={"timeframe:10s": block, "timeframe:1m": block, "ema9": block, "ema200": warn, "macd_line": MissingDataBehavior.IGNORE},
        ),
        "FIRST_PULLBACK": SetupFamilyInputRequirement(
            setup_family="FIRST_PULLBACK",
            required_timeframes=("1m",),
            preferred_timeframes=("5m", "10s"),
            required_indicators=("ema9", "ema20"),
            optional_indicators=("vwap", "ema200", "macd_line"),
            missing_data_behavior={"timeframe:1m": block, "timeframe:5m": degrade, "ema9": block, "ema20": block, "ema200": warn},
        ),
        "FLAT_TOP_BREAKOUT": SetupFamilyInputRequirement(
            setup_family="FLAT_TOP_BREAKOUT",
            required_timeframes=("1m",),
            preferred_timeframes=("5m",),
            required_indicators=("vwap",),
            optional_indicators=("ema9", "ema20", "ema200", "macd_line"),
            required_levels=("resistance_levels",),
            missing_data_behavior={"timeframe:1m": block, "timeframe:5m": warn, "vwap": degrade, "resistance_levels": warn},
        ),
        "HOD_BREAK": SetupFamilyInputRequirement(
            setup_family="HOD_BREAK",
            required_timeframes=("1m",),
            preferred_timeframes=("5m",),
            required_levels=("hod",),
            optional_indicators=("ema9", "ema20", "vwap", "ema200", "macd_line"),
            missing_data_behavior={"timeframe:1m": block, "hod": block, "ema200": warn},
        ),
        "PMH_BREAK": SetupFamilyInputRequirement(
            setup_family="PMH_BREAK",
            required_timeframes=("1m",),
            preferred_timeframes=("10s", "5m"),
            required_levels=("premarket_high",),
            optional_indicators=("ema9", "ema20", "vwap", "ema200", "macd_line"),
            missing_data_behavior={"timeframe:1m": block, "timeframe:10s": warn, "premarket_high": block, "ema200": warn},
        ),
        "ORB_GAP_GO": SetupFamilyInputRequirement(
            setup_family="ORB_GAP_GO",
            required_timeframes=("1m", "5m"),
            preferred_timeframes=("10s",),
            required_indicators=("vwap",),
            required_levels=("premarket_high", "premarket_low", "prior_close"),
            optional_indicators=("ema9", "ema20", "ema200", "macd_line"),
            missing_data_behavior={"timeframe:1m": block, "timeframe:5m": block, "timeframe:10s": warn, "vwap": degrade, "premarket_high": block, "premarket_low": block, "prior_close": block},
        ),
        "BULL_FLAG": SetupFamilyInputRequirement(
            setup_family="BULL_FLAG",
            required_timeframes=("1m",),
            preferred_timeframes=("5m", "10s"),
            required_indicators=("ema9", "ema20", "vwap"),
            optional_indicators=("ema200", "macd_line"),
            missing_data_behavior={"timeframe:1m": block, "timeframe:5m": degrade, "ema9": block, "ema20": block, "vwap": block, "ema200": warn},
        ),
        "ABCD_CONTINUATION": SetupFamilyInputRequirement(
            setup_family="ABCD_CONTINUATION",
            required_timeframes=("1m",),
            preferred_timeframes=("5m",),
            required_indicators=("macd_line",),
            optional_indicators=("ema9", "ema20", "vwap", "ema200"),
            missing_data_behavior={"timeframe:1m": block, "timeframe:5m": warn, "macd_line": degrade, "macd_signal": degrade, "macd_histogram": degrade, "ema200": warn},
        ),
        "STAIR_STEP_CONTINUATION": SetupFamilyInputRequirement(
            setup_family="STAIR_STEP_CONTINUATION",
            required_timeframes=("1m", "5m"),
            preferred_timeframes=("10s",),
            required_indicators=("ema9", "ema20"),
            optional_indicators=("vwap", "ema200", "macd_line"),
            missing_data_behavior={"timeframe:1m": block, "timeframe:5m": degrade, "ema9": block, "ema20": block, "ema200": warn},
        ),
        "FAILED_BREAKOUT_CAUTION": SetupFamilyInputRequirement(
            setup_family="FAILED_BREAKOUT_CAUTION",
            required_timeframes=("1m",),
            preferred_timeframes=("10s", "5m"),
            required_levels=("hod",),
            optional_indicators=("vwap", "macd_line", "ema200"),
            missing_data_behavior={"timeframe:1m": block, "timeframe:10s": warn, "hod": warn, "macd_line": warn, "ema200": warn},
        ),
        "EXHAUSTION_EXIT_WARNING": SetupFamilyInputRequirement(
            setup_family="EXHAUSTION_EXIT_WARNING",
            required_timeframes=("1m",),
            preferred_timeframes=("10s", "5m"),
            optional_indicators=("vwap", "macd_line", "ema200"),
            missing_data_behavior={"timeframe:1m": block, "timeframe:10s": warn, "macd_line": warn, "ema200": warn},
        ),
    }


@dataclass(frozen=True)
class PatternInputPolicy:
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    required_timeframes: tuple[str, ...]
    preferred_timeframes: tuple[str, ...]
    session_timeframe_plans: dict[str, PatternTimeframePlan]
    setup_family_requirements: dict[str, SetupFamilyInputRequirement]
    default_missing_data_behavior: MissingDataBehavior = MissingDataBehavior.WARN
    candle_freshness_seconds: dict[str, int] = field(
        default_factory=lambda: {"10s": 60, "1m": 180, "5m": 900}
    )

    @classmethod
    def from_policy_v2(cls) -> "PatternInputPolicy":
        requirements = POLICY_V2.data_requirements
        opening_fast = PatternTimeframePlan(
            primary_timeframe="1m",
            execution_refinement_timeframe="10s",
            context_timeframe="5m",
            required_timeframes=("10s", "1m"),
            preferred_timeframes=("10s", "1m", "5m"),
        )
        steady = PatternTimeframePlan(
            primary_timeframe="1m",
            execution_refinement_timeframe="1m",
            context_timeframe="5m",
            required_timeframes=("1m", "5m"),
            preferred_timeframes=("1m", "5m"),
        )
        return cls(
            required_fields=tuple(requirements.required_fields),
            optional_fields=tuple(requirements.optional_fields),
            required_timeframes=("1m",),
            preferred_timeframes=("10s", "1m", "5m"),
            session_timeframe_plans={
                "PRE": opening_fast,
                "PREMARKET": opening_fast,
                "RTH_OPEN": opening_fast,
                "OPENING_0_30": opening_fast,
                "MORNING": opening_fast,
                "RTH_MID": steady,
                "MIDDAY": steady,
                "RTH_LATE": steady,
                "LATE": steady,
                "POWER_HOUR": steady,
                "AH": steady,
                "AFTER_HOURS": steady,
                "OVN": steady,
                "OVERNIGHT": steady,
                "WEEKEND": steady,
                "CLOSED": steady,
            },
            setup_family_requirements=_requirements(),
        )

    def plan_for_session(self, session_label: str | None) -> PatternTimeframePlan:
        key = str(session_label or "").strip().upper() or "PRE"
        return self.session_timeframe_plans.get(key, self.session_timeframe_plans.get("PRE"))

    def requirement_for_setup(self, setup_family: str) -> SetupFamilyInputRequirement:
        key = str(setup_family or "").strip().upper()
        aliases = {
            "PREMARKET_HIGH_BREAK": "PMH_BREAK",
            "P_PREMARKET_HIGH_BREAK": "PMH_BREAK",
            "P_PREMKT_BREAK": "PMH_BREAK",
            "GAP_GO": "ORB_GAP_GO",
            "GAP_AND_GO": "ORB_GAP_GO",
            "OPENING_RANGE_BREAKOUT": "ORB_GAP_GO",
            "ORB": "ORB_GAP_GO",
            "ABCD": "ABCD_CONTINUATION",
            "TREND_CONTINUATION_STAIR_STEP": "STAIR_STEP_CONTINUATION",
            "STAIR_STEP": "STAIR_STEP_CONTINUATION",
            "FAILED_BREAKOUT": "FAILED_BREAKOUT_CAUTION",
            "EXHAUSTION": "EXHAUSTION_EXIT_WARNING",
        }
        return self.setup_family_requirements[aliases.get(key, key)]

    def behavior_for_missing(self, setup_family: str, input_name: str) -> MissingDataBehavior:
        return self.requirement_for_setup(setup_family).behavior_for(input_name)
