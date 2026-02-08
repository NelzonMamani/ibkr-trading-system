"""ibkr_trading_os_master_catalog.py

Purpose
-------
Single, human-readable + machine-readable master catalogue for:
  (1) Core Architecture Epochs (what a trading OS must have)
  (2) Metadata Epochs (how truth, contracts, verification, and change-control work)
  (3) Setup Families (macro / thesis-level market structures)
  (4) Strategies (bundles of families + execution logic + governance)
  (5) Execution Logic (how entries/adds/exits are triggered)
  (6) Conditions (binary/scalar gates; never tradable alone)
  (7) Confirmations/Filters (raise/lower confidence; never initiate alone)

This file is intentionally:
  - deterministic (stable names)
  - auditable (reasons included)
  - refactor-friendly (IDs are stable; ordering is priority-first)
  - enforceable (taxonomy rules are explicit)

Canonical Rules (LOCKED)
------------------------
R1. Only thesis-level market structures are allowed to be Setup Families.
    Everything else must be one of:
      - Execution Logic (how)
      - Conditions (context gates)
      - Confirmations/Filters (confidence modifiers)

R2. Strategies MUST be composed of:
      Strategy = {one or more Setup Families} + {approved Execution Logic}
                 + {Conditions/Confirmations} + {Risk + Position Lifecycle hooks}
    No strategy may be a renamed execution trigger (e.g., "ABCD strategy").

R3. Traceability is mandatory:
    every cycle emits stage events that allow a third party to reconstruct:
      universe -> watchlist -> focus -> decisions -> intents -> execution -> positions

Updated
-------
2026-02-02 (Europe/Amsterdam)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


# =============================================================================
# SECTION 1 — CORE ARCHITECTURE EPOCHS (FULL)
# =============================================================================
# These are "house wiring" epochs: they define the operating system foundations
# required before multiple strategies can be trusted in READ_ONLY/PAPER/LIVE.
#
# NOTE: Names are stable IDs. Each epoch has a reason (why it exists) and
# a verification intent (what you must be able to prove).
# =============================================================================

CORE_ARCH_EPOCHS: List[Tuple[str, str]] = [
    ("E0_SYSTEM_LAW_TRUTH",
     "System Law & Truth — constitution/state/canon; prevents drift & false beliefs."),
    ("E1_TRACEABILITY_OBSERVABILITY",
     "Traceability & Observability — no silent decisions; stage-by-stage reconstruction."),
    ("E2_POSITION_LIFECYCLE_ENGINE",
     "Position Lifecycle Engine — entry/add/trail/exit is uniform across strategies."),
    ("E3_RISK_ENGINE_COMPLETENESS",
     "Risk Engine Completeness — the authority that gates execution with reasons."),
    ("E4_DATA_QUALITY_MARKET_STATE",
     "Data Quality & Market State — session semantics + integrity gates + degraded mode."),
    ("E5_EXECUTION_ENGINE_AUTHORITY",
     "Execution Engine Authority — broker routing + paper/sim provider + hard blocks."),
    ("E6_SCANNER_STRATEGY_CONTRACT",
     "Scanner–Strategy Contract — scanner is mechanical; policy lives in strategy."),
    ("E7_MODE_PARITY",
     "Mode Parity — READ_ONLY/PAPER/LIVE behave identically except execution authority."),
    ("E8_REGIME_LAYER",
     "Regime Layer — measurement->classifier->policy permission; avoids regime mismatch."),
    ("E9_PERFORMANCE_ANALYTICS",
     "Performance & Analytics — PnL, slippage, attribution, reports; prove edge vs noise."),
    ("E10_CAPITAL_ALLOCATION",
     "Capital Allocation — portfolio-level governance; prevent strategy overlap conflicts."),
    ("E11_LEARNING_SYSTEM",
     "Learning System — telemetry->proposals->human approval; safe improvement loop."),
    ("E12_RECOVERY_AND_HOUSEKEEPING",
     "Recovery & Housekeeping — backups/resets/safe-to-delete; fast recovery under growth."),
    ("E13_STRATEGY_FACTORY_STANDARD",
     "Strategy Factory Standard — uniform wiring, contracts, and test rules for every strategy."),
    # Optional but high-value expansions (not required for first live strategy, but
    # required for scaling multi-strategy with low fragility).
    ("E14_MARKET_IMPACT_MODEL",
     "Market Impact & Liquidity Modeling — size-aware fills; avoids fantasy PnL."),
    ("E15_LATENCY_AND_TIMING_AUTHORITY",
     "Latency/Clock/Bar Truth — clock sync, bar close truth, timing determinism."),
    ("E16_EVENT_DRIVEN_SIGNAL_BUS",
     "Event Signal Authority — HALT/REGIME/NEWS events; strategy reacts deterministically."),
    ("E17_FAILSAFE_AND_DEGRADED_MODES",
     "Failsafe & Degraded Modes — connectivity/data faults => safe behavior, not chaos."),
    ("E18_SESSION_AWARENESS_ENGINE",
     "Session Semantics Engine — PRE/open/midday/power-hour/close semantics as first-class."),
    ("E19_CAPITAL_EFFICIENCY_OPTIMIZER",
     "Capital Efficiency — exposure overlap control; opportunity cost & concurrency mgmt."),
]


# =============================================================================
# SECTION 2 — METADATA EPOCHS (FULL)
# =============================================================================
# These epochs define the "operating manual" of the operating system:
# contracts, verification authority, provenance, and change-control.
# Without these, refactors and multi-epoch work becomes chaos.
# =============================================================================

METADATA_EPOCHS: List[Tuple[str, str]] = [
    ("M0_CANON",
     "Canon — what is true: law/state/glossary; prevents contradictory documentation."),
    ("M1_ARCHITECTURE_MAP",
     "Architecture map & ownership — module boundaries + responsibilities."),
    ("M2_CONTRACT_REGISTRY",
     "Contract registry — versioned interfaces across scanner/strategy/risk/execution."),
    ("M3_MODE_SEMANTICS_CERT",
     "Mode semantics certification — truth tables + proofs for RO/PAPER/LIVE behavior."),
    ("M4_TRACEABILITY_SEMANTICS",
     "Trace semantics — required fields per stage; ensures consistent audits."),
    ("M5_VERIFICATION_AUTHORITY",
     "Verification authority — defines what commands prove reality (compileall/pytest/CLI)."),
    ("M6_DATA_LIFECYCLE_GOV",
     "Data lifecycle governance — retention policy; safe-to-delete folders; recovery rules."),
    ("M7_EPOCH_AUDIT_CERTIFICATION",
     "Epoch audit & completion — formal criteria and completion certificate per epoch."),
    ("M8_CHANGE_CONTROL",
     "Change control — approvals for refactors; prevents accidental deletion of invariants."),
    ("M9_REGIME_DEFINITION_CANON",
     "Regime definition canon — formal regimes + invariants; reproducible classifier outputs."),
    ("M10_SIGNAL_SEMANTICS_REGISTRY",
     "Signal meaning registry — standard meaning of break/reclaim/failure across strategies."),
    ("M11_DATA_PROVENANCE_LEDGER",
     "Data provenance ledger — lineage from source->transform->decision; debuggability."),
    ("M12_DECISION_AUTHORITY_MAP",
     "Decision authority map — human vs system decisions; who can override what."),
    ("M13_FAILURE_POSTMORTEM_ARCHIVE",
     "Failure archive — incident templates + knowledge base; prevents repeat failures."),
]


# =============================================================================
# SECTION 3 — SETUP FAMILIES (MACRO / THESIS) — FULL
# =============================================================================
# Setup family = WHY the trade exists (market structure thesis).
# Must be non-overlapping as much as possible.
# Execution triggers are NOT allowed here.
# =============================================================================

SETUP_FAMILIES: List[Tuple[str, str]] = [
    ("SF_GAP_AND_GO",
     "Gap & Go (Opening Drive) — gap + RVOL + catalyst; break PMH/ORB with continuation."),
    ("SF_ORB",
     "Opening Range Breakout — break/hold above ORH after initial balance."),
    ("SF_FIRST_PULLBACK_FIRST_FLAG",
     "First Pullback / First Flag — first controlled pullback after breakout/drive."),
    ("SF_BULL_FLAG_TIGHT_FLAG",
     "Bull Flag / High-Tight Flag — impulse then consolidation; continuation on break."),
    ("SF_KEY_LEVEL_BREAK",
     "Key Level Break — PMH, whole/half dollar, PDH, multi-day high; break with volume."),
    ("SF_CUP_AND_HANDLE_INTRADAY",
     "Cup & Handle (intraday) — rounded base + handle; break handle high."),
    ("SF_FLAT_TOP_ASCENDING",
     "Flat-Top / Ascending Breakout — repeated resistance tests; break with expansion."),
    ("SF_SUPPORT_RESIST_BOUNCE_BREAK",
     "Support/Resistance Bounce + Break — bounce or break/reclaim of key levels."),
    ("SF_PREMARKET_HIGH_BREAK",
     "Premarket High Break — reclaim and hold above PMH; overlaps but treated explicitly."),
    ("SF_HALT_RESUME",
     "Halt Resume Continuation — volatility halt then continuation if order flow supports."),
    ("SF_VWAP_TREND_DAY",
     "VWAP Trend Day — holds one side of VWAP; pullbacks to VWAP/EMAs get bought."),
    ("SF_EMA_TREND_STAIRCASE",
     "EMA Stair-Step Trend — 9/20 EMAs act as dynamic support; clean trend continuation."),
    ("SF_TRENDLINE_BREAK_HOLD",
     "Trendline Break + Hold — structure-driven break/retest then continuation."),
    ("SF_VWAP_RECLAIM_REVERSAL",
     "VWAP Reclaim (Reversal) — early flush -> base -> reclaim VWAP -> hold."),
    ("SF_PDC_RECLAIM",
     "Prior Day Close reclaim — sentiment shift above yesterday close; continuation."),
    ("SF_GAP_FILL_REVERSAL",
     "Gap Fill -> Reversal — partial/full gap fill then reclaim and continuation."),
    ("SF_FAILED_BREAKDOWN_REVERSAL",
     "Failed Breakdown -> Reclaim — flush below support then immediate reclaim (trapped shorts)."),
    ("SF_VOLATILITY_SQUEEZE",
     "Volatility Squeeze — compression (declining vol/volume) then expansion break."),
    ("SF_BOX_RANGE_BREAK",
     "Box Range Break — horizontal range 5–30m; break+hold outside."),
    ("SF_HOD_LOD_BREAK",
     "High/Low-of-Day Break — repeated pushes into HOD/LOD; breakout with confirmation."),
    ("SF_LIQUIDITY_SWEEP_RECLAIM",
     "Liquidity Sweep -> Instant Reclaim — stop run then reclaim; reversal/continuation."),
    ("SF_POWER_HOUR_EXPANSION",
     "Power Hour Expansion — late-day compression then 3–4pm expansion."),
    ("SF_PARABOLIC_EXHAUSTION_AVOID",
     "Parabolic Exhaustion (Avoid/Exit) — climactic push; exit/stop-trading signal."),
]


# =============================================================================
# SECTION 4 — STRATEGIES (FULL)
# =============================================================================
# Strategy = bundle of setup families + execution logic + risk + position lifecycle.
# Each strategy must trade (PAPER) end-to-end, then be LIVE-eligible once risk allows.
# =============================================================================

STRATEGIES: List[Tuple[str, str]] = [
    ("S_ROSS_MOMENTUM",
     "Ross Momentum — multi-setup intraday momentum suite (Opening Drive, flags, breakouts)."),
    ("S_STATISTICAL_INTRADAY_MOMENTUM",
     "Statistical Intraday Momentum — quantitative continuation/reversion models."),
    ("S_MEAN_REVERSION",
     "Mean Reversion — regime gated; uses VWAP/EMA deviations + exhaustion/failure signals."),
    ("S_LONG_HORIZON_VALUE",
     "Long Horizon Value — multi-month fundamental compounding; market-closed workflows."),
    ("S_OPENING_DRIVE_SPECIALIST",
     "Opening Drive Specialist — focuses on first 5–30 minutes impulse setups."),
    ("S_VWAP_RECLAIM_SPECIALIST",
     "VWAP Reclaim Specialist — reversal + reclaim families; R2G/PDC reclaim contexts."),
    ("S_POWER_HOUR_SPECIALIST",
     "Power Hour Specialist — late-day expansion families; afternoon order flow."),
    ("S_VOL_EXPANSION_SPECIALIST",
     "Volatility Expansion Specialist — squeeze/box->expansion; compressions and breaks."),
    ("S_TREND_DAY_CONTINUATION",
     "Trend Day Continuation — VWAP trend day + EMA staircase + late adds."),
    ("S_REVERSAL_RECLAIM",
     "Reversal & Reclaim — failed breakdown, gap-fill reversal, liquidity sweep reclaim."),
    ("S_LIQUIDITY_TRAP_EXPLOITATION",
     "Trap/Squeeze Exploitation — failed breakdowns, trapped shorts, reclaim dynamics."),
    ("S_RANGE_TO_EXPANSION",
     "Compression->Expansion — box + squeeze; breakout with confirmation."),
    ("S_REGIME_ADAPTIVE_ROUTER",
     "Meta-strategy router — allocates capital/permissions based on regime & performance."),
    ("S_RISK_OFF_CAPITAL_PRESERVER",
     "Risk-Off / No-Trade Mode — capital preservation; blocks trading under risk-off regimes."),
]


# =============================================================================
# SECTION 5 — EXECUTION LOGIC (HOW) — LOCKED
# =============================================================================
# These are NOT strategies and NOT setup families.
# They are triggers and mechanics reusable across families.
# =============================================================================

EXECUTION_LOGIC: List[Tuple[str, str]] = [
    ("XL_MICRO_PULLBACK",
     "Micro Pullback trigger — 2–3 pullback candles; enter on reclaim (1m or 10s/15s)."),
    ("XL_FIRST_PULLBACK",
     "First Pullback trigger — enter on reclaim of pullback high after initial impulse."),
    ("XL_BREAK_AND_HOLD",
     "Break-and-hold — enter once resistance breaks AND holds for defined bars/seconds."),
    ("XL_BREAK_AND_RETEST",
     "Break then retest — enter on successful retest of broken level."),
    ("XL_FLAG_HIGH_BREAK",
     "Flag high break — enter when flag high breaks with expansion."),
    ("XL_TRENDLINE_RECLAIM",
     "Trendline reclaim — enter after reclaim/hold of trendline following shakeout."),
    ("XL_VWAP_RECLAIM_TRIGGER",
     "VWAP reclaim trigger — enter once VWAP reclaimed and held (reversal/continuation)."),
    ("XL_EMA_RECLAIM_TRIGGER",
     "EMA reclaim trigger — reclaim 9/20 EMA(s) then continuation."),
    ("XL_ABCD_MEASURED_MOVE",
     "ABCD / measured move — enter on C->D continuation with defined invalidation."),
    ("XL_HOD_LOD_BREAK_TRIGGER",
     "HOD/LOD break trigger — enter on break with tape/volume confirmation."),
    ("XL_SCALE_IN_ADD_MODEL",
     "Scale-in adds — predefined add rules (break levels, micro pullback adds)."),
    ("XL_TRAIL_EXIT_MODEL",
     "Trail/exit — predefined trailing stop logic (VWAP, EMA, ATR, LOD/HOD)."),
]


# =============================================================================
# SECTION 6 — CONDITIONS (CONTEXT GATES) — LOCKED
# =============================================================================
# Conditions gate permission/size/confidence. They never initiate trades alone.
# =============================================================================

CONDITIONS: List[Tuple[str, str]] = [
    ("CND_RVOL_THRESHOLD",
     "Relative Volume threshold — ensures participation beyond baseline."),
    ("CND_GAP_THRESHOLD",
     "Gap % threshold — defines abnormal open context."),
    ("CND_FLOAT_CONSTRAINT",
     "Float constraint — maintains move potential; avoids sluggish names."),
    ("CND_SPREAD_CONSTRAINT",
     "Spread constraint — prevents untradeable names or slippage traps."),
    ("CND_LIQUIDITY_CONSTRAINT",
     "Liquidity constraint — min $ volume; avoids fills fantasy."),
    ("CND_TIME_OF_DAY_WINDOW",
     "Time-of-day window — open vs midday vs power hour behave differently."),
    ("CND_SESSION_SEMANTICS",
     "Session (PRE/RTH/AH/OVN) — percent-change & volume semantics differ by session."),
    ("CND_REGIME_PERMISSION",
     "Regime permission — trend/chop/risk-off gates; strategy must have permission."),
    ("CND_NEWS_CATALYST",
     "News/catalyst presence — supports continuation; optional per strategy."),
    ("CND_VOLATILITY_STATE",
     "Volatility state — high vol risk-off days may block or reduce size."),
]


# =============================================================================
# SECTION 7 — CONFIRMATIONS / FILTERS — LOCKED
# =============================================================================
# Confirmations refine probability. They should adjust confidence or size.
# They never create a trade by themselves.
# =============================================================================

CONFIRMATIONS: List[Tuple[str, str]] = [
    ("CNF_R2G_G2R",
     "Red-to-Green / Green-to-Red — contextual confirmation or warning."),
    ("CNF_VOLUME_EXPANSION",
     "Volume expansion on break — confirms participation on breakout."),
    ("CNF_VWAP_SLOPE_ALIGNMENT",
     "VWAP slope alignment — trend confirmation; blocks countertrend entries."),
    ("CNF_HIGHER_TIMEFRAME_ALIGNMENT",
     "HTF alignment — daily/5m structure supports trade thesis."),
    ("CNF_INDEX_ALIGNMENT",
     "SPY/QQQ alignment — market tailwind/headwind gating."),
    ("CNF_SECTOR_REL_STRENGTH",
     "Sector strength — confirms sympathy / group move."),
    ("CNF_TAPE_SPEED_MOMENTUM",
     "Tape speed — confirms real momentum; optional if tape data available."),
    ("CNF_FAILURE_SIGNALS",
     "Failure signals — topping tails/rejections; reduce size or trigger exits."),
]


# =============================================================================
# OPTIONAL: STRUCTURED TYPES (useful if you later want to generate docs/reports)
# =============================================================================

@dataclass(frozen=True)
class CatalogSection:
    title: str
    items: List[Tuple[str, str]]


CATALOG: List[CatalogSection] = [
    CatalogSection("CORE_ARCH_EPOCHS", CORE_ARCH_EPOCHS),
    CatalogSection("METADATA_EPOCHS", METADATA_EPOCHS),
    CatalogSection("SETUP_FAMILIES", SETUP_FAMILIES),
    CatalogSection("STRATEGIES", STRATEGIES),
    CatalogSection("EXECUTION_LOGIC", EXECUTION_LOGIC),
    CatalogSection("CONDITIONS", CONDITIONS),
    CatalogSection("CONFIRMATIONS", CONFIRMATIONS),
]


def dump_catalog_text() -> str:
    """Return a deterministic, human-readable text dump of the entire catalogue."""
    lines: List[str] = []
    for section in CATALOG:
        lines.append("=" * 90)
        lines.append(section.title)
        lines.append("=" * 90)
        for key, desc in section.items:
            lines.append(f"- {key}: {desc}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(dump_catalog_text())
