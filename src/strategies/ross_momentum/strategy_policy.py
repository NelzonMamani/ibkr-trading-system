# strategy_policy.py

"""strategies/ross_momentum/strategy_policy.py

Ross Momentum Strategy Policy (machine-readable)

This policy is intended to be imported by the Orchestrator.

Separation of concerns
- StrategyPolicy: requirements + rules (this file)
- StrategyContext: live facts built by Orchestrator (see strategy_context_schema.py)
- StrategyRunner: evaluates Policy × Context -> intents/actions

Discretionary-to-mechanical translation
- Some Warrior Trading concepts are described as "weak" / "strong".
  This policy expresses those as measured thresholds where possible.
- Where Ross does not publish an exact numeric threshold (e.g., "big red volume"),
  this policy treats the signal as a *telemetry feature* that may be used for
  learning/analytics and optionally enabled with a calibrated threshold.

Sources
- This repository's Ross strategy documents and transcripts.
- Public Warrior Trading educational material (e.g., the "How to Trade a Micro Pullback" article).

"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional, Sequence

from src.scanner.result_models import CandidateMetrics
from src.scanner.session_pct_change import normalize_session_label


class RossTradingMode(str, Enum):
    """Time-of-day / cadence presets.

    Ross trades the open aggressively with fast execution, and slows down later.
    We model this as *cadence presets* rather than different strategies.
    """

    OPENING_DRIVE = "OPENING_DRIVE"   # ~09:30-10:15 ET
    MIDDAY = "MIDDAY"                 # ~10:15-14:30 ET (typically reduced aggression)
    LATE_DAY = "LATE_DAY"             # ~14:30-16:00 ET (slower structure)


class UniverseSource(str, Enum):
    IBKR_TOP_GAINERS = "IBKR_TOP_GAINERS"
    CONFIG_SYMBOLS = "CONFIG_SYMBOLS"


@dataclass(frozen=True)
class UniverseSpec:
    source: UniverseSource = UniverseSource.IBKR_TOP_GAINERS
    ibkr_scan_code: str = "TOP_PERC_GAIN"
    top_n: Optional[int] = None
    region: Optional[str] = None
    instrument: Optional[str] = "STK"
    location_code: Optional[str] = "STK.US.MAJOR"
    exchanges: Sequence[str] = ()


@dataclass(frozen=True)
class TimeframePlan:
    """Which timeframes are used for what, per mode."""

    bias_tf: str
    setup_tf: str
    structure_tf: str
    execution_tf: str


@dataclass(frozen=True)
class MicroPullbackSpec:
    """Micro pullback re-entry (execution timeframe).

    Core idea
    - Impulse leg up establishes momentum.
    - 2-3 small red candles pull back with "weak" selling.
    - Re-entry trigger: first green candle that breaks the high of the last red.

    The *impulse candle* used for normalization is mode-dependent:
    - OPENING_DRIVE: impulse is typically the 1-minute impulse leg.
    - LATE_DAY: impulse is typically the 5-minute impulse leg.
    """

    pullback_red_candles: Sequence[int] = (2, 3)

    # Body-size weakness (mechanical proxy for "small" red candles)
    # These are expressed as ratios of each red candle's body to the impulse body's size.
    max_each_red_body_to_impulse_body: float = 0.30

    # Total pullback depth (mechanical proxy for "controlled" pullback)
    # Expressed as pullback range vs impulse range (range = high-low).
    max_pullback_range_to_impulse_range: float = 0.50

    # Hold-above rules (setup/structure context)
    must_hold_above: Sequence[str] = ("VWAP", "EMA9", "EMA20")

    # Volume weakness (telemetry-first; threshold disabled by default)
    # If enabled, pause/reject when avg red volume is greater than
    # (red_volume_pause_ratio * impulse green volume).
    red_volume_pause_ratio: Optional[float] = None  # e.g., 0.40 .. 0.80 after calibration

    # Entry trigger
    # Enter when the first green candle after the red sequence breaks the last red high.
    require_break_last_red_high: bool = True


@dataclass(frozen=True)
class ToppingRiskSpec:
    """Top/reversal risk management.

    Ross repeatedly emphasises avoiding/recognising topping tails and reversals.

    Mechanical mapping:
    - PAUSE new entries when a candle shows a large upper wick relative to the body.
    - HALT new entries (and consider de-risking) when a *confirmed* reversal candle
      appears (e.g., clear shooting star / topping tail with failure).

    The exact "shooting star" definition varies by trader; this policy provides
    explicit ratios and keeps them configurable.
    """

    # Soft warning: upper wick >= 50% of body => pause new entries
    topping_wick_ratio_pause: float = 0.50

    # Hard warning: upper wick >= 100% of body AND candle closes red => halt new entries
    topping_wick_ratio_halt: float = 1.00

    # Timeframe where topping-risk is monitored (mode-dependent):
    # - OPENING_DRIVE: structure_tf (usually 1m)
    # - LATE_DAY: structure_tf (usually 5m) and execution_tf (1m)
    monitor_timeframes: Sequence[str] = ("STRUCTURE",)


@dataclass(frozen=True)
class IndicatorGates:
    """Indicator gates that Ross commonly references."""

    # MACD
    require_macd_positive_for_entries: bool = True

    # Optional: if MACD crosses against the position, treat as a warning/halt
    halt_on_macd_cross_against: bool = True


@dataclass(frozen=True)
class RiskAndPermissions:
    """Trade-permission controls.

    IMPORTANT
    - Ross does NOT publish a fixed "max trades per symbol". He may take many
      re-entries in a single name while it is in play.
    - Therefore: we do not hard-cap per-symbol trades here.

    Hard stops belong in the global risk engine / stop controller.
    """

    # Global safety (typical Ross rule of thumb: stop after 3 losses)
    max_consecutive_losses: int = 3

    # Strategy-specific guardrail (optional; default None means "no hard cap")
    max_trades_per_symbol: Optional[int] = None

    # Optional: max re-entries per symbol per *active move* (telemetry-first)
    max_reentries_per_symbol: Optional[int] = None


@dataclass(frozen=True)
class RossMomentumPolicy:
    """Top-level policy used by the Orchestrator and Runner."""

    name: str = "ROSS_MOMENTUM"
    version: str = "v1"

    # Timeframe plans per mode
    timeframe_opening: TimeframePlan = TimeframePlan(
        bias_tf="DAILY",
        setup_tf="5MIN",
        structure_tf="1MIN",
        execution_tf="10SEC",
    )
    timeframe_midday: TimeframePlan = TimeframePlan(
        bias_tf="DAILY",
        setup_tf="5MIN",
        structure_tf="1MIN",
        execution_tf="10SEC",
    )
    timeframe_late_day: TimeframePlan = TimeframePlan(
        bias_tf="DAILY",
        setup_tf="15MIN",
        structure_tf="5MIN",
        execution_tf="1MIN",
    )

    micro_pullback: MicroPullbackSpec = MicroPullbackSpec()
    topping_risk: ToppingRiskSpec = ToppingRiskSpec()
    indicator_gates: IndicatorGates = IndicatorGates()
    risk: RiskAndPermissions = RiskAndPermissions()

    # Scanner/Universe policy belongs here; orchestrator imports it and passes it to scanner.
    stock_selection: "StockSelectionSpec" = field(
        default_factory=lambda: StockSelectionSpec()
    )

    # Level 2 / Tape reading (optional; can be disabled without subscriptions)
    # These are left as telemetry flags / hooks.
    level2_iceberg_detection_enabled: bool = False

    # Market hours assumptions
    market_open_time_et: str = "09:30"
    market_close_time_et: str = "16:00"


@dataclass(frozen=True)
class StockSelectionSpec:
    """Ross Momentum stock selection policy (Ross 5 pillars + tradability gates)."""

    policy_name: str = "ROSS_MOMENTUM"
    universe: UniverseSpec = field(default_factory=UniverseSpec)
    price_min: float = 1.0
    price_max: float = 20.0
    gap_min_pct: float = 10.0
    gap_max_pct: Optional[float] = None
    rvol_min: float = 5.0
    float_max_millions: float = 20.0
    liquidity_min_dollar_volume: Optional[float] = None
    min_volume: int = 1_000_000
    min_premarket_volume: int = 100_000
    spread_max_pct: Optional[float] = None
    require_catalyst: bool = True
    allow_halts: bool = False
    allow_ssr: bool = True
    data_quality_require_price: bool = True
    data_quality_require_bid_ask: bool = False
    watchlist_limit_k: int = 15
    focus_limit_m: int = 5
    top_gainers_n: int = 50
    max_symbols_per_cycle: int = 50
    session_allowlist: Sequence[str] = ("PRE", "REG", "AFTER")
    ranking_intent: str = "ROSS_MOMENTUM_STOCK_SELECTION"


def select_watchlist(
    observations: Sequence[CandidateMetrics],
    policy: RossMomentumPolicy | StockSelectionSpec | None = None,
) -> list[CandidateMetrics]:
    if policy is None:
        spec = RossMomentumPolicy().stock_selection
    elif hasattr(policy, "stock_selection"):
        spec = policy.stock_selection
    else:
        spec = policy
    session_allowlist = {
        normalize_session_label(session).upper() for session in spec.session_allowlist
    }
    eligible: list[CandidateMetrics] = []
    for observation in observations:
        reasons: list[str] = []
        raw_session_label = (observation.session_label or "").strip()
        session_label = normalize_session_label(raw_session_label).upper() if raw_session_label else ""
        if session_allowlist and session_label and session_label not in session_allowlist:
            reasons.append("SESSION_NOT_ALLOWED")
        gate_checks = observation.gate_checks or {}
        failed_gates = [name for name, passed in gate_checks.items() if (name != "catalyst_ok" and not passed)]
        if failed_gates:
            reasons.extend([f"GATE_FAIL:{name}" for name in failed_gates])
        if reasons:
            observation = replace(
                observation,
                drop_reasons=list({*observation.drop_reasons, *reasons}),
            )
        else:
            eligible.append(observation)
    ranked = sorted(
        eligible,
        key=lambda row: (
            row.rank_score or 0.0,
            row.pct_change or 0.0,
            row.dollar_volume or 0.0,
        ),
        reverse=True,
    )
    watchlist_limit = int(spec.watchlist_limit_k)
    if watchlist_limit <= 0:
        return []
    return ranked[:watchlist_limit]


RossStockSelectionPolicy = StockSelectionSpec


SESSION_PHASE_TO_MODE = {
    "PREMARKET": RossTradingMode.OPENING_DRIVE,
    "OPENING_0_30": RossTradingMode.OPENING_DRIVE,
    "MORNING": RossTradingMode.OPENING_DRIVE,
    "MIDDAY": RossTradingMode.MIDDAY,
    "LATE": RossTradingMode.LATE_DAY,
    "POWER_HOUR": RossTradingMode.LATE_DAY,
    "CLOSED": RossTradingMode.MIDDAY,
}


def timeframe_plan_for_mode(policy: RossMomentumPolicy, mode: RossTradingMode) -> TimeframePlan:
    if mode == RossTradingMode.OPENING_DRIVE:
        return policy.timeframe_opening
    if mode == RossTradingMode.LATE_DAY:
        return policy.timeframe_late_day
    return policy.timeframe_midday


def mode_for_session_phase(session_phase: str) -> RossTradingMode:
    return SESSION_PHASE_TO_MODE.get(session_phase, RossTradingMode.MIDDAY)


def timeframe_plan_for_session_phase(
    policy: RossMomentumPolicy,
    session_phase: str,
) -> TimeframePlan:
    return timeframe_plan_for_mode(policy, mode_for_session_phase(session_phase))


def stock_selection_policy_for_session_phase(
    policy: RossMomentumPolicy,
    session_phase: str,
) -> StockSelectionSpec:
    normalized = (session_phase or "").upper()
    if normalized in {"PRE", "PREMARKET", "CLOSED"}:
        if policy.stock_selection.top_gainers_n == 50:
            return replace(policy.stock_selection, top_gainers_n=150)
    return policy.stock_selection
