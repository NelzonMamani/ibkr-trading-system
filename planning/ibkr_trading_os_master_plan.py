"""
ibkr_trading_os_master_plan.py

Purpose
-------
Exhaustive, structured, auditable "Trading Operating System" master plan for the IBKR Trading System.
This file is meant to be:
- A canonical, machine-readable roadmap (for Codex or any engineer/AI).
- A human-readable playbook (prints as Markdown).
- A verification-oriented plan (each unit has evidence + commands + success criteria).
- A governance-first system: nothing is "done" without proof artifacts.

How to use
----------
1) Keep this file at repo root OR in a governance folder (e.g., docs/governance/).
2) Run:
   python ibkr_trading_os_master_plan.py > MASTER_PLAN.md
3) Use the generated Markdown as the authoritative work plan and audit checklist.

Non-negotiables (locked)
------------------------
- No silent decisions: every action/block must yield trace events + reason codes.
- Mode parity: READ_ONLY / PAPER / LIVE semantics are consistent.
- Scanner is mechanical; strategy policy is authoritative.
- Each "Epoch" has:
  - Contracts
  - Tests
  - Verification commands
  - Evidence outputs
  - Completion certificate report
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ==========================================================================================
# 0) Core Types
# ==========================================================================================

class Priority(str, Enum):
    P0 = "P0 (must-have, blocks trading)"
    P1 = "P1 (high value, blocks reliability)"
    P2 = "P2 (important for scale)"
    P3 = "P3 (nice-to-have)"


class Status(str, Enum):
    UNKNOWN = "UNKNOWN"
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    PARTIAL = "PARTIAL"
    DONE = "DONE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Evidence:
    """
    Evidence artifacts that MUST exist when a unit is claimed complete.
    """
    required_files: Tuple[str, ...] = ()
    required_logs: Tuple[str, ...] = ()
    required_reports: Tuple[str, ...] = ()
    required_tests: Tuple[str, ...] = ()
    required_trace_events: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Verification:
    """
    Commands that prove reality. These must be executable and deterministic.
    """
    commands: Tuple[str, ...] = ()
    expected_signals: Tuple[str, ...] = ()  # Strings to grep for in logs, or invariants


@dataclass
class PlanUnit:
    """
    A single auditable unit: an epoch, a strategy, a setup family, or a cross-cutting subsystem.
    """
    unit_id: str
    name: str
    priority: Priority
    goal: str
    why: str
    scope: Tuple[str, ...]
    non_goals: Tuple[str, ...] = ()
    dependencies: Tuple[str, ...] = ()
    deliverables: Tuple[str, ...] = ()
    contracts: Tuple[str, ...] = ()
    invariants: Tuple[str, ...] = ()
    traceability_requirements: Tuple[str, ...] = ()
    failure_modes: Tuple[str, ...] = ()
    verification: Verification = field(default_factory=Verification)
    evidence: Evidence = field(default_factory=Evidence)
    status: Status = Status.UNKNOWN
    notes: str = ""


@dataclass(frozen=True)
class CatalogSection:
    section_key: str
    description: str
    items: Tuple[PlanUnit, ...]


# ==========================================================================================
# 1) Canonical Cross-Cutting Layers (these underpin everything else)
# ==========================================================================================

TRACE_STAGES = (
    "BOOT",
    "SESSION",
    "UNIVERSE",
    "GATES",
    "WATCHLIST",
    "FOCUS",
    "STRATEGY_INPUTS",
    "STRATEGY_DECISION",
    "RISK_DECISION",
    "INTENTS",
    "EXECUTION",
    "POSITION_LIFECYCLE",
    "SHUTDOWN",
)

REASON_CODE_FAMILIES = (
    "DATA_QUALITY_*",
    "MODE_*",
    "RISK_*",
    "CONNECTIVITY_*",
    "STRATEGY_*",
    "EXECUTION_*",
    "PORTFOLIO_*",
)

INTENT_TYPES = (
    "OPEN",
    "ADD",
    "SCALE_OUT",
    "FULL_EXIT",
    "STOP_EXIT",
    "TIME_EXIT",
    "RISK_EXIT",
    "SYSTEM_EXIT",
)

DECISION_ARTIFACTS = (
    "EntryDecision",
    "AddDecision",
    "ReduceDecision",
    "ExitDecision",
    "BlockDecision",
)

NO_TRADE_CONTEXTS = (
    "CHOP_REGIME",
    "NEWS_WHIPSAW",
    "LUNCH_LIQUIDITY_VACUUM",
    "ALGO_GRIND",
    "HALT_UNCERTAINTY",
    "CORRELATED_EXPOSURE_SATURATION",
    "DATA_STALE_CONTEXT",
    "SPREAD_TOO_WIDE_CONTEXT",
)


# ==========================================================================================
# 2) CORE ARCHITECTURE EPOCHS (Trading Operating System)
#    Each epoch is a subsystem that must be provable via tests + logs + reports.
# ==========================================================================================

CORE_ARCH_EPOCHS: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="E0_SYSTEM_LAW_TRUTH",
        name="System Law & Truth (Constitution + State + Canon)",
        priority=Priority.P0,
        goal="Establish immutable law, mutable state, and canonical truth sources for the whole system.",
        why="Without this, changes drift, promises break, and no one can verify what is true.",
        scope=(
            "SYSTEM_CONSTITUTION.md (law)",
            "SYSTEM_STATE.md (current enforced reality)",
            "README.md (public charter + how to run)",
            "Glossary / Canon definitions",
        ),
        deliverables=(
            "SYSTEM_CONSTITUTION.md updated + locked",
            "SYSTEM_STATE.md updated to reflect enforced behavior",
            "README.md updated to match law/state",
            "CANON_GLOSSARY.md (optional but recommended)",
        ),
        invariants=(
            "SYSTEM_STATE reflects actual code behavior (not intent).",
            "Any behavior change requires updating SYSTEM_STATE + tests.",
        ),
        verification=Verification(
            commands=(
                "python -m compileall src",
                "pytest -q",
            ),
            expected_signals=(
                "No failing tests",
                "SYSTEM_STATE 'Last Updated' matches current update cycle",
            ),
        ),
        evidence=Evidence(
            required_files=("SYSTEM_CONSTITUTION.md", "SYSTEM_STATE.md", "README.md"),
            required_tests=("pytest suite passing",),
        ),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E1_TRACEABILITY_OBSERVABILITY",
        name="Traceability & Observability (No Silent Decisions)",
        priority=Priority.P0,
        goal="Every decision, block, and action is emitted as trace events with reason codes.",
        why="Traceability is the foundation of auditability, debugging, and trust.",
        scope=(
            "Trace schema + required fields",
            "Stage taxonomy (BOOT→EXECUTION)",
            "Reason code registry",
            "Structured log outputs + event collector",
        ),
        deliverables=(
            "TRACE_SEMANTICS.md (stages, required fields, examples)",
            "Reason code registry (enum or canonical list)",
            "Trace event emission at every stage",
            "Event summary at shutdown",
        ),
        invariants=(
            "No silent failures: blocks must have explicit reason_code + message",
            "Trace events always include: cycle_id, run_mode, strategy, stage, timestamp",
            f"Stages are limited to {TRACE_STAGES}",
            f"Reason codes follow families {REASON_CODE_FAMILIES}",
        ),
        verification=Verification(
            commands=(
                "pytest -q tests/test_traceability.py",
                "python -m src.main --mode READ_ONLY --cycles 1 --strategy ross_momentum",
            ),
            expected_signals=(
                "[TRACE]",
                "stage=WATCHLIST",
                "stage=STRATEGY_DECISION",
                "stage=RISK_DECISION",
            ),
        ),
        evidence=Evidence(
            required_reports=("output/verification/traceability_smoke.log",),
            required_trace_events=("TRACE_EVENT_ORDER", "TRACE_STAGE_COMPLETE",),
        ),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E2_POSITION_LIFECYCLE_ENGINE",
        name="Position Lifecycle Engine (Entry → Add → Trail → Exit)",
        priority=Priority.P0,
        goal="A unified engine that manages positions across strategies and modes.",
        why="Strategies that can only 'emit entries' are incomplete; lifecycle is the trading system.",
        scope=(
            "Position model and state machine",
            "Entry, add, scale-out, exit, stop exit, time exit",
            "ActiveTrade registry and persistence",
            "Mode parity for lifecycle actions",
        ),
        deliverables=(
            "PositionStateMachine + contracts",
            "Lifecycle events + reason codes",
            "Paper execution supports partial fills + closeouts (simulated)",
            "Persistence of position state in DB",
        ),
        invariants=(
            f"Intent types limited to {INTENT_TYPES}",
            "Lifecycle transitions are deterministic and logged",
            "READ_ONLY never submits broker orders",
        ),
        verification=Verification(
            commands=(
                "pytest -q tests/test_position_lifecycle.py",
                "python -m src.main --mode PAPER --cycles 5 --strategy mean_reversion",
            ),
            expected_signals=(
                "POSITION_OPENED",
                "POSITION_UPDATED",
                "POSITION_CLOSED",
            ),
        ),
        evidence=Evidence(
            required_tests=("tests/test_position_lifecycle.py",),
            required_trace_events=("POSITION_OPENED", "POSITION_CLOSED"),
        ),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E3_RISK_ENGINE_COMPLETENESS",
        name="Risk Engine Completeness (Authority + Circuit Breakers)",
        priority=Priority.P0,
        goal="Risk engine is the only authority that can permit execution.",
        why="Prevents strategy bypass, enforces global safety, avoids catastrophic behavior.",
        scope=(
            "Risk verdict contract",
            "Circuit breakers",
            "Max exposure rules",
            "Data-quality gating integration",
            "Strategy-level locks",
        ),
        deliverables=(
            "RiskEngine verdict reasons are deterministic and logged",
            "Circuit breakers: max daily loss, max trades, max exposure, volatility halt guard",
            "Symbol exposure + correlation caps (portfolio-level optional P2)",
        ),
        invariants=(
            "No strategy may bypass RiskEngine",
            "Risk verdict required for every intent",
            "Risk blocks must emit reason_code",
        ),
        verification=Verification(
            commands=(
                "pytest -q tests/test_risk_engine_authority.py",
                "python -m src.main --mode PAPER --cycles 2 --strategy ross_momentum",
            ),
            expected_signals=(
                "RISK_DECISION",
                "reason_code=",
            ),
        ),
        evidence=Evidence(
            required_tests=("tests/test_risk_engine_authority.py",),
            required_trace_events=("RISK_DECISION",),
        ),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E4_DATA_QUALITY_MARKET_STATE",
        name="Data Quality & Market State (Session + Integrity Gates)",
        priority=Priority.P0,
        goal="Session-aware, integrity-aware market data truth with explicit fallback semantics.",
        why="Most system failures come from wrong session semantics, stale data, or missing subscriptions.",
        scope=(
            "Session awareness engine (PRE/RTH/AH/CLOSED + holidays/weekends)",
            "Reference price truth (pct_change semantics)",
            "Data quality flags (bid/ask, spread, stale timestamps)",
            "Connectivity state machine (OK/DEGRADED/HALT)",
        ),
        deliverables=(
            "Session truth contract",
            "Data quality gating integrated with scanner + risk engine",
            "Connectivity manager emits DEGRADED states with reasons",
        ),
        invariants=(
            "Session label normalization is canonical",
            "Pct change must be session-aware and consistent with system policy",
            "DEGRADED state never silently proceeds into execution",
        ),
        verification=Verification(
            commands=(
                "pytest -q tests/test_session_awareness.py",
                "pytest -q tests/test_data_quality_flags.py",
            ),
            expected_signals=(
                "SESSION",
                "STATE=DEGRADED",
                "DATA_QUALITY",
            ),
        ),
        evidence=Evidence(
            required_tests=("tests/test_session_awareness.py", "tests/test_data_quality_flags.py"),
            required_trace_events=("CONNECTIVITY_FAILURE", "DATA_QUALITY_FLAGGED"),
        ),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E5_EXECUTION_ENGINE_AUTHORITY",
        name="Execution Engine Authority (Broker Routing + Sim Provider)",
        priority=Priority.P0,
        goal="A single execution engine with provider abstraction for READ_ONLY/PAPER/LIVE.",
        why="If execution routing is inconsistent, mode parity breaks and strategy testing is meaningless.",
        scope=(
            "Execution provider interface",
            "IBKR order translation and submission",
            "Paper execution simulator (fills, partials, slippage optional)",
            "Order lifecycle events",
        ),
        deliverables=(
            "Execution provider contract + implementations",
            "Broker adapter mapping correctness tests",
            "Paper fills are deterministic by seed (optional)",
        ),
        invariants=(
            "READ_ONLY: hard-blocked order submission",
            "PAPER: simulated orders only",
            "LIVE: broker orders allowed only with risk approval",
        ),
        verification=Verification(
            commands=(
                "pytest -q tests/test_execution_mode_parity.py",
                "python -m src.main --mode PAPER --cycles 2 --strategy mean_reversion",
            ),
            expected_signals=(
                "EXECUTION",
                "Broker submission: DISABLED (READ_ONLY)",
                "Simulated fill",
            ),
        ),
        evidence=Evidence(
            required_tests=("tests/test_execution_mode_parity.py",),
            required_trace_events=("EXECUTION_SUBMIT", "EXECUTION_FILL", "EXECUTION_REJECT"),
        ),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E6_SCANNER_STRATEGY_CONTRACT",
        name="Scanner–Strategy Contract (Mechanical Scan, Policy in Strategy)",
        priority=Priority.P0,
        goal="Scanner produces candidates; strategies own policy, ranking, and gating semantics.",
        why="Avoids duplication, inconsistent logic, and 'scanner deciding trades' by accident.",
        scope=(
            "Scanner returns CandidateMetrics + snapshots",
            "Strategy provides StockSelectionSpec (universe + basic caps)",
            "Ranking authority lives in strategy policy",
            "Watchlist and focus list semantics are consistent",
        ),
        deliverables=(
            "StockSelectionSpec contract + strategy ownership",
            "Scanner uses strategy-provided spec",
            "Diagnostics prints: TopN + Watchlist with same columns preserved",
        ),
        invariants=(
            "Scanner is pass-through mechanical (no discretionary edge logic)",
            "Strategy policy provides ranking intent",
            "Empty watchlists are valid outcomes",
        ),
        verification=Verification(
            commands=(
                "pytest -q tests/test_scanner_policy_from_strategy.py",
                "pytest -q tests/test_scanner_ranking_authority.py",
            ),
            expected_signals=("source=STRATEGY", "ranking_intent="),
        ),
        evidence=Evidence(
            required_tests=("tests/test_scanner_policy_from_strategy.py",),
            required_trace_events=("SCANNER_UNIVERSE_SNAPSHOT", "WATCHLIST_K_SELECTED"),
        ),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E7_MODE_PARITY",
        name="Mode Parity (READ_ONLY / PAPER / LIVE)",
        priority=Priority.P0,
        goal="Guaranteed consistent semantics across modes; only execution differs.",
        why="Weeks of pain come from mode drift and hidden flags; parity makes testing meaningful.",
        scope=(
            "Canonical run modes",
            "Truth table for flags",
            "Mode manager",
            "Proof via tests and smoke logs",
        ),
        deliverables=(
            "MODE_SEMANTICS.md truth table",
            "Smoke runs logged for each mode per strategy",
            "Tests ensure no drift",
        ),
        invariants=(
            "Only these modes exist: READ_ONLY, PAPER, LIVE",
            "SIM is not a trading mode (test/replay only)",
        ),
        verification=Verification(
            commands=(
                "python -m src.main --mode READ_ONLY --cycles 1 --strategy ross_momentum",
                "python -m src.main --mode PAPER --cycles 1 --strategy ross_momentum",
                "python -m src.main --mode LIVE --cycles 1 --strategy ross_momentum",
            ),
            expected_signals=(
                "Run mode: READ_ONLY",
                "Run mode: PAPER",
                "Run mode: LIVE",
            ),
        ),
        evidence=Evidence(
            required_reports=(
                "output/verification/ross_READ_ONLY.log",
                "output/verification/ross_PAPER.log",
                "output/verification/ross_LIVE.log",
            ),
        ),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E8_REGIME_LAYER",
        name="Regime Layer (Measurement → Classifier → Policy)",
        priority=Priority.P1,
        goal="Measure regime; classify; strategies read regime snapshot to gate behavior.",
        why="Regime prevents strategies from trading in structurally hostile environments.",
        scope=("Regime metrics", "Classifier", "RegimeSnapshot contract", "Policy gates"),
        deliverables=("RegimeSnapshot emitted each cycle", "Tests for regime outputs", "Policy integration"),
        invariants=("RegimeSnapshot must be emitted even in DEGRADED mode (with flags)"),
        verification=Verification(
            commands=("pytest -q tests/test_regime_orchestrator_integration.py",),
            expected_signals=("REGIME_SNAPSHOT",),
        ),
        evidence=Evidence(required_trace_events=("REGIME_SNAPSHOT",)),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E9_PERFORMANCE_ANALYTICS",
        name="Performance & Analytics (PnL, Slippage, Attribution, Reports)",
        priority=Priority.P2,
        goal="Turn trading into measurable performance with robust reporting.",
        why="Without analytics, you can't validate edge, compare strategies, or improve risk.",
        scope=("PnL", "slippage", "fills", "attribution", "reports", "dashboards optional"),
        deliverables=("Daily report artifacts", "Strategy attribution reports", "Trade journal exports"),
        verification=Verification(commands=("pytest -q tests/test_reporting_artifacts.py",), expected_signals=("REPORT_READY",)),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E10_CAPITAL_ALLOCATION",
        name="Capital Allocation (Portfolio-Level Governance)",
        priority=Priority.P2,
        goal="Allocate capital across strategies under shared constraints and priorities.",
        why="Multi-strategy without allocation becomes accidental correlated exposure.",
        scope=("Portfolio caps", "strategy priority", "symbol overlap control", "capital throttles"),
        deliverables=("Allocation engine contract", "Exposure caps across strategies", "Tests"),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E11_LEARNING_SYSTEM",
        name="Learning System (Telemetry → Proposals → Human Approval)",
        priority=Priority.P2,
        goal="Collect telemetry and produce human-reviewed improvement proposals.",
        why="Learning must be controlled; never self-modify live without approval.",
        scope=("Telemetry schema", "proposal generator", "approval workflow"),
        deliverables=("LEARNING_PROPOSALS.md outputs", "human approval gates"),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E12_RECOVERY_AND_HOUSEKEEPING",
        name="Recovery & Housekeeping (Backups, Resets, Safe-to-Delete)",
        priority=Priority.P1,
        goal="System can recover quickly; safe-to-delete folders are explicit.",
        why="Repo bloat and DB growth cause operational failure; recovery is mandatory.",
        scope=("DB backups", "hard reset", "log retention", "safe-to-delete policy"),
        deliverables=("db_admin utility + docs", "SAFE_TO_DELETE.md", "recovery runbook"),
        invariants=("Deleting safe-to-delete folders cannot break system boot"),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E13_STRATEGY_FACTORY_STANDARD",
        name="Strategy Factory Standard (Uniform Wiring + Test Rules)",
        priority=Priority.P0,
        goal="All strategies are wired using the same contracts, tests, and verification outputs.",
        why="Prevents each strategy from being 'a special snowflake' and breaking parity.",
        scope=("Strategy folder structure", "tests placement rules", "wiring checklist"),
        deliverables=("STRATEGY_FACTORY_STANDARD.md", "template strategy skeleton", "CI verification steps"),
        invariants=("Strategy-local tests live inside strategy folder under src/strategies/<strategy>/tests"),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E14_DECISION_ARTIFACTS",
        name="Decision Artifacts (Why we acted / why we didn't)",
        priority=Priority.P0,
        goal="Canonical decision objects for entry/add/reduce/exit/block across all strategies.",
        why="Traceability needs structured artifacts, not just logs.",
        scope=DECISION_ARTIFACTS,
        deliverables=("DecisionArtifact dataclasses", "serialization into events/logs/DB", "tests"),
        invariants=("Every intent must have an associated DecisionArtifact."),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E15_FAILURE_MODES",
        name="Failure Modes (Classification + Degraded Policies)",
        priority=Priority.P1,
        goal="Explicit failure taxonomy and how system responds (degraded/halt).",
        why="Stops chaos: failures become predictable, logged, and recoverable.",
        scope=("Failure taxonomy", "fallback policies", "halt policies"),
        deliverables=("FAILURE_MODES.md", "tests for degraded handling"),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E16_NO_TRADE_CONTEXTS",
        name="No-Trade Contexts (Edge protection)",
        priority=Priority.P1,
        goal="Define and enforce contexts where trading must be blocked or throttled.",
        why="Prevents trades in structurally hostile environments.",
        scope=NO_TRADE_CONTEXTS,
        deliverables=("NO_TRADE_CONTEXTS.md", "risk gates integrating contexts", "tests"),
        status=Status.PLANNED,
    ),

    PlanUnit(
        unit_id="E17_STRATEGY_INTERACTION_RULES",
        name="Strategy Interaction Rules (Multi-strategy safety)",
        priority=Priority.P1,
        goal="Rules for conflicts: priority, mutual exclusion, overlap caps, cooldown propagation.",
        why="Multi-strategy must not self-sabotage by fighting on the same symbols.",
        scope=("Priority rules", "mutual exclusions", "overlap exposure caps", "cooldowns"),
        deliverables=("STRATEGY_INTERACTION_RULES.md", "portfolio router integration", "tests"),
        status=Status.PLANNED,
    ),
)


# ==========================================================================================
# 3) METADATA EPOCHS (governance and audit infrastructure)
# ==========================================================================================

METADATA_EPOCHS: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="M0_CANON",
        name="Canon: What Is True (Law / State / Glossary)",
        priority=Priority.P0,
        goal="Define canonical truth sources and definitions.",
        why="Prevents term drift, contradictory docs, and broken assumptions.",
        scope=("Glossary", "Canonical definitions", "Versioning rules"),
        deliverables=("CANON_GLOSSARY.md",),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M1_ARCHITECTURE_MAP",
        name="Architecture Map & Ownership (Module Boundaries)",
        priority=Priority.P0,
        goal="A map of modules and owners; where each responsibility lives.",
        why="Prevents refactors from breaking boundaries.",
        scope=("Architecture diagram", "ownership list", "boundaries"),
        deliverables=("ARCHITECTURE_MAP.md",),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M2_CONTRACT_REGISTRY",
        name="Contract Registry (Versioned Interfaces)",
        priority=Priority.P0,
        goal="A registry of contracts and their versions.",
        why="Contracts prevent accidental breakage when adding strategies or refactoring.",
        scope=("StrategyInput", "StrategyDecision", "StockSelectionSpec", "RiskVerdict", "ExecutionProvider"),
        deliverables=("CONTRACT_REGISTRY.md",),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M3_MODE_SEMANTICS_CERT",
        name="Mode Semantics Certification (Truth Tables + Proof)",
        priority=Priority.P0,
        goal="Truth table of mode behavior + tests proving it.",
        why="Mode drift is the #1 source of chaos.",
        scope=("Truth tables", "tests", "smoke logs"),
        deliverables=("MODE_SEMANTICS.md",),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M4_TRACEABILITY_SEMANTICS",
        name="Traceability Semantics (Stages + Required Fields)",
        priority=Priority.P0,
        goal="Define trace stages, required fields, and examples.",
        why="Traceability must be consistent and machine-readable.",
        scope=("Trace stages", "trace schema"),
        deliverables=("TRACE_SEMANTICS.md",),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M5_VERIFICATION_AUTHORITY",
        name="Verification Authority (What Proves Reality)",
        priority=Priority.P0,
        goal="Define what commands and artifacts prove 'done'.",
        why="Stops 'it works on my machine' and prevents unverified merges.",
        scope=("Verification templates", "required artifacts", "evidence rules"),
        deliverables=("VERIFICATION_AUTHORITY.md",),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M6_DATA_LIFECYCLE_GOV",
        name="Data Lifecycle Governance (Retention, Safe-to-Delete)",
        priority=Priority.P1,
        goal="Define what can be deleted and what must persist.",
        why="Prevents repo bloat and operational failures.",
        scope=("Retention policies", "safe-to-delete dirs", "DB backup policies"),
        deliverables=("DATA_LIFECYCLE_GOV.md", "SAFE_TO_DELETE.md"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M7_EPOCH_AUDIT_CERTIFICATION",
        name="Epoch Audit & Completion Certification",
        priority=Priority.P0,
        goal="Each epoch has a completion certificate and audit proof.",
        why="Lets you quickly assert what exists and what remains.",
        scope=("Audit template", "completion report generation"),
        deliverables=("EPOCH_AUDIT_TEMPLATE.md",),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M8_CHANGE_CONTROL",
        name="Change Control (Approval Workflow for Refactors)",
        priority=Priority.P1,
        goal="Formal rules for refactors and breaking changes.",
        why="Prevents constant churn and regressions.",
        scope=("Approval workflow", "breaking change rules"),
        deliverables=("CHANGE_CONTROL.md",),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M9_SIGNAL_SEMANTICS_REGISTRY",
        name="Signal Meaning Registry (Break, Reclaim, Failure)",
        priority=Priority.P1,
        goal="Formal definitions of signals across strategies.",
        why="Stops duplicates like 'R2G' being treated as setup vs confirmation.",
        scope=("Signal definitions", "invariants", "examples"),
        deliverables=("SIGNAL_SEMANTICS_REGISTRY.md",),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="M10_DATA_PROVENANCE_LEDGER",
        name="Data Origin, Transformation & Lineage Ledger",
        priority=Priority.P2,
        goal="Track where data came from and how it was transformed.",
        why="Vital for debugging, compliance, and trust in metrics.",
        scope=("Lineage ledger", "transform maps"),
        deliverables=("DATA_PROVENANCE_LEDGER.md",),
        status=Status.PLANNED,
    ),
)


# ==========================================================================================
# 4) SETUP FAMILIES (Macro) — Canonical (non-overlapping as much as possible)
# ==========================================================================================

SETUP_FAMILIES: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="SF_GAP_AND_GO",
        name="Gap & Go (Opening Drive)",
        priority=Priority.P0,
        goal="Trade high RVOL gappers breaking PMH / opening range with continuation.",
        why="Core Ross edge; defines open drive behavior and scanning priorities.",
        scope=("PMH break", "ORB overlap", "news/catalyst optional gating"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_ORB",
        name="Opening Range Breakout (ORB)",
        priority=Priority.P1,
        goal="Break and hold above ORH after initial consolidation.",
        why="More structured than Gap & Go; common execution family.",
        scope=("ORH/ORL levels", "hold condition", "retest logic"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_FIRST_PULLBACK_FIRST_FLAG",
        name="First Pullback / First Flag",
        priority=Priority.P1,
        goal="First controlled pullback after initial impulse; continuation entry.",
        why="High probability continuation; key to scaling edge beyond pure breakouts.",
        scope=("impulse detection", "pullback depth rules", "reclaim trigger"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_BULL_FLAG_TIGHT_FLAG",
        name="Bull Flag / High-Tight Flag",
        priority=Priority.P1,
        goal="Consolidation after impulse; breakout above flag high.",
        why="Classic continuation with definable risk.",
        scope=("flag identification", "volume contraction", "breakout + hold"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_KEY_LEVEL_BREAK",
        name="Break of Key Level",
        priority=Priority.P1,
        goal="Break key levels (whole/half, PDH, multi-day highs) with volume.",
        why="Generalized family applicable across sessions and symbols.",
        scope=("key level catalog", "break validation", "false break filters"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_ABCD_CONTINUATION",
        name="ABCD Continuation / Measured Move",
        priority=Priority.P2,
        goal="Measured continuation using pullbacks and breakouts.",
        why="Useful execution framework but often not a stand-alone family.",
        scope=("A-B leg", "B-C pullback", "C-D target projection"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_CUP_AND_HANDLE_INTRADAY",
        name="Cup & Handle (Intraday)",
        priority=Priority.P2,
        goal="Rounded base + tight handle; break handle high.",
        why="Occurs less often intraday but can be strong when present.",
        scope=("cup recognition", "handle constraints", "break + volume confirmation"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_MOMENTUM_RECLAIM",
        name="Momentum Reclaim (VWAP / EMA)",
        priority=Priority.P1,
        goal="Reclaim VWAP/EMA after shakeout then continuation.",
        why="Captures reclaim continuation and reversals depending on context.",
        scope=("reclaim definition", "hold criteria", "trend alignment"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_VWAP_TREND_DAY",
        name="VWAP Trend Day",
        priority=Priority.P1,
        goal="Price holds one side of VWAP; pullbacks bought/sold all day.",
        why="Institutions defending VWAP; powerful for trend continuation strategies.",
        scope=("VWAP side rule", "pullback entry triggers", "late-day adds"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_EMA_TREND_STAIRCASE",
        name="EMA Stair-Step Trend",
        priority=Priority.P2,
        goal="Higher highs/lows using 9/20 EMA as dynamic support.",
        why="Cleaner than flags; definable reclaim triggers.",
        scope=("stair-step detection", "EMA reclaim triggers", "risk definition"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_VOLATILITY_SQUEEZE",
        name="Volatility Squeeze (Intraday)",
        priority=Priority.P2,
        goal="Tight range + volume decline + EMA compression → expansion breakout.",
        why="Captures midday expansion edge and late moves.",
        scope=("compression metrics", "breakout triggers", "false break filters"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_BOX_RANGE_BREAK",
        name="Box Range Break",
        priority=Priority.P2,
        goal="Horizontal range (5–30 min) break + hold outside range.",
        why="Generalizable breakout family distinct from ORB.",
        scope=("range definition", "break + hold", "retest option"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_HOD_LOD_BREAK",
        name="High-of-Day / Low-of-Day Break",
        priority=Priority.P2,
        goal="Repeated tests into HOD/LOD then breakout with confirmation.",
        why="Common late-morning/afternoon continuation family.",
        scope=("HOD/LOD detection", "tape/volume confirmation proxies"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_FAILED_BREAKDOWN_REVERSAL",
        name="Failed Breakdown → Reclaim",
        priority=Priority.P2,
        goal="Flush below support then instant reclaim (trap reversal).",
        why="Captures trapped participants; high R:R when clean.",
        scope=("support break", "fast reclaim", "risk at breakdown low"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_PDC_RECLAIM",
        name="Prior Day Close (PDC) Reclaim",
        priority=Priority.P2,
        goal="Break above yesterday close and hold as sentiment shift.",
        why="Often signals regime shift; overlaps with R2G context.",
        scope=("PDC level", "hold criteria", "trend confirmation"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_POWER_HOUR_EXPANSION",
        name="Power Hour Expansion",
        priority=Priority.P2,
        goal="Compression 12–2pm then expansion 3–4pm.",
        why="Late-day flow differs; should be treated explicitly.",
        scope=("time window", "compression detection", "breakout triggers"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_HALT_RESUME",
        name="Halt Resume Continuation",
        priority=Priority.P3,
        goal="Volatility halt then resumption continuation when liquidity holds.",
        why="High risk; needs special handling. Often excluded until mature.",
        scope=("halt detection", "resume criteria", "liquidity checks"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="SF_PARABOLIC_EXHAUSTION_AVOID",
        name="Parabolic Exhaustion (Avoid / Exit Family)",
        priority=Priority.P1,
        goal="Detect climactic pushes; used to exit or stop trading.",
        why="Protects capital; prevents late chasing into blow-off tops.",
        scope=("climax detection", "volume spike", "extension metrics"),
        status=Status.PLANNED,
    ),
)


# ==========================================================================================
# 5) STRATEGIES — Canonical list (OS-level, can be extended, but must be wired uniformly)
# ==========================================================================================

STRATEGIES: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="S_ROSS_MOMENTUM",
        name="Ross Momentum (Multi-Setup Intraday Momentum)",
        priority=Priority.P0,
        goal="Primary intraday momentum engine spanning multiple setup families.",
        why="Core of the system; drives scanning and execution patterns.",
        scope=("Gap & Go", "ORB", "flags", "key level breaks", "reclaims", "risk rules"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="S_STATISTICAL_INTRADAY_MOMENTUM",
        name="Statistical Intraday Momentum",
        priority=Priority.P0,
        goal="Quantitative continuation/reversion intraday strategy.",
        why="Diversifies alpha sources and enables regime-driven behavior.",
        scope=("signal engine", "ranking model", "risk overlay"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="S_MEAN_REVERSION",
        name="Mean Reversion (Regime-Gated)",
        priority=Priority.P0,
        goal="Mean reversion engine with strict gating and defined lifecycle.",
        why="Complements momentum; must be live-capable under correct regime.",
        scope=("overextension", "exhaustion", "entry", "stop", "target", "regime permission"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="S_LONG_HORIZON_VALUE",
        name="Long Horizon Value (Multi-Month)",
        priority=Priority.P1,
        goal="Long-horizon value/quality strategy with controlled execution policy.",
        why="Different timescale; must be isolated and governed.",
        scope=("fundamental screens", "valuation", "allocation", "rebalance cycle"),
        status=Status.PLANNED,
    ),

    # Specialist strategies you locked
    PlanUnit(
        unit_id="S_OPENING_DRIVE",
        name="Opening Drive Specialist",
        priority=Priority.P1,
        goal="Specialist intraday strategy optimized for the open drive window.",
        why="Separates open-specific behavior for higher focus and less complexity.",
        scope=("Gap & Go", "ORB", "early momentum"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="S_VWAP_RECLAIM",
        name="VWAP Reclaim Specialist",
        priority=Priority.P1,
        goal="Specialist reclaim strategy (reversal + continuation variants).",
        why="VWAP reclaim is a core family; treating it as a strategy improves clarity.",
        scope=("VWAP reclaim reversal", "VWAP reclaim continuation"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="S_POWER_HOUR",
        name="Power Hour Specialist",
        priority=Priority.P2,
        goal="Late-day expansion engine.",
        why="Power hour flow is distinct; needs time-aware rules.",
        scope=("compression → expansion", "HOD breaks", "late adds"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="S_VOL_EXPANSION",
        name="Volatility Expansion Specialist",
        priority=Priority.P2,
        goal="Range-to-expansion strategy centered on squeezes and box breaks.",
        why="Captures non-impulse-first expansions, often midday.",
        scope=("volatility squeeze", "box range break"),
        status=Status.PLANNED,
    ),
)


# ==========================================================================================
# 6) Execution Logic vs Conditions vs Confirmations (the classification you locked)
# ==========================================================================================

EXECUTION_LOGIC: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="XL_MICRO_PULLBACK",
        name="Micro Pullback (execution trigger family)",
        priority=Priority.P0,
        goal="Define micro-pullback execution trigger logic (entry/add) on lower timeframe.",
        why="This is not a macro family; it's a trigger used inside many families.",
        scope=("2–3 red candles pullback", "reclaim trigger", "aggressive vs conservative"),
        invariants=("Must not be treated as a standalone macro setup family."),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="XL_ABCD",
        name="ABCD (execution framework)",
        priority=Priority.P1,
        goal="Define ABCD measured-move logic as execution framework.",
        why="Used across families; must be consistent and not duplicated.",
        scope=("AB leg", "BC pullback", "CD projection", "targets/stops"),
        status=Status.PLANNED,
    ),
)

CONDITIONS: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="C_R2G_G2R",
        name="R2G / G2R (context condition)",
        priority=Priority.P1,
        goal="Define R2G/G2R as a contextual condition (confirmation/warning).",
        why="Not an edge alone; used to validate or invalidate other setups.",
        scope=("prior close reclaim", "trend/context alignment"),
        invariants=("Not a standalone strategy edge."),
        status=Status.PLANNED,
    ),
)

CONFIRMATIONS: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="K_VOLUME_CONFIRM",
        name="Volume confirmation (generic)",
        priority=Priority.P0,
        goal="Confirm breakouts/reclaims with volume/flow proxies.",
        why="Prevents false breaks and low-quality entries.",
        scope=("volume surge", "rvol thresholds", "spread checks"),
        status=Status.PLANNED,
    ),
    PlanUnit(
        unit_id="K_LEVEL_HOLD",
        name="Hold confirmation (break + hold)",
        priority=Priority.P0,
        goal="Confirm breakouts by hold criteria and retest behavior.",
        why="Reduces whipsaw and improves trade quality.",
        scope=("hold window", "retest behavior", "failure triggers"),
        status=Status.PLANNED,
    ),
)

DECISION_ARTIFACTS_SECTION: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="DA_DECISION_OBJECTS",
        name="Decision Artifacts (canonical objects)",
        priority=Priority.P0,
        goal="Define canonical objects that encode full reasoning for actions/blocks.",
        why="Logs are insufficient; structured artifacts enable audit, replay, learning.",
        scope=DECISION_ARTIFACTS,
        deliverables=("DecisionArtifact schema", "DB persistence optional", "trace integration"),
        status=Status.PLANNED,
    ),
)

FAILURE_MODES_SECTION: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="FM_FAILURE_TAXONOMY",
        name="Failure taxonomy (system-wide)",
        priority=Priority.P1,
        goal="Define a canonical failure taxonomy and system response.",
        why="Without this, behavior under failure becomes chaotic and unsafe.",
        scope=(
            "CONNECTIVITY_FAILURE",
            "DATA_STALE",
            "SUBSCRIPTION_MISSING",
            "BROKER_REJECT",
            "EXECUTION_PROVIDER_MISSING",
            "MODE_VIOLATION",
        ),
        deliverables=("FAILURE_MODES.md", "tests for degraded/halts"),
        status=Status.PLANNED,
    ),
)

NO_TRADE_CONTEXTS_SECTION: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="NTC_NO_TRADE",
        name="No-trade contexts (edge protection)",
        priority=Priority.P1,
        goal="Define explicit contexts where system must block or throttle trading.",
        why="Prevents technically-valid but practically-dangerous trading conditions.",
        scope=NO_TRADE_CONTEXTS,
        deliverables=("NO_TRADE_CONTEXTS.md", "risk integration", "tests"),
        status=Status.PLANNED,
    ),
)

STRATEGY_INTERACTION_RULES_SECTION: Tuple[PlanUnit, ...] = (
    PlanUnit(
        unit_id="SIR_MULTI_STRATEGY_RULES",
        name="Multi-strategy interaction rules",
        priority=Priority.P1,
        goal="Define rules for strategy conflicts, overlap, priority, cooldowns.",
        why="Multi-strategy without interaction rules self-sabotages.",
        scope=("symbol overlap caps", "mutual exclusion pairs", "priority order", "cooldown propagation"),
        deliverables=("STRATEGY_INTERACTION_RULES.md", "portfolio router hooks", "tests"),
        status=Status.PLANNED,
    ),
)


# ==========================================================================================
# 7) Catalog Assembly
# ==========================================================================================

CATALOG: List[CatalogSection] = [
    CatalogSection("CORE_ARCH_EPOCHS", "Trading OS core architecture epochs (system completeness)", CORE_ARCH_EPOCHS),
    CatalogSection("METADATA_EPOCHS", "Governance & audit infrastructure epochs (proof + definitions)", METADATA_EPOCHS),
    CatalogSection("SETUP_FAMILIES", "Macro setup families (what Ross trades at thesis level)", SETUP_FAMILIES),
    CatalogSection("STRATEGIES", "Strategies (runnable modules; must be live-capable with mode parity)", STRATEGIES),

    # Classification lock
    CatalogSection("EXECUTION_LOGIC", "Execution triggers/frameworks (not macro families)", EXECUTION_LOGIC),
    CatalogSection("CONDITIONS", "Context conditions (not standalone edge)", CONDITIONS),
    CatalogSection("CONFIRMATIONS", "Confirmations (validations + warnings)", CONFIRMATIONS),

    # System “last mile” cross-cutting planes
    CatalogSection("DECISION_ARTIFACTS", "Structured decision objects for auditability and learning", DECISION_ARTIFACTS_SECTION),
    CatalogSection("FAILURE_MODES", "Failure taxonomy + degraded policies", FAILURE_MODES_SECTION),
    CatalogSection("NO_TRADE_CONTEXTS", "Explicit no-trade contexts", NO_TRADE_CONTEXTS_SECTION),
    CatalogSection("STRATEGY_INTERACTION_RULES", "Multi-strategy overlap/priority/exposure rules", STRATEGY_INTERACTION_RULES_SECTION),
]


# ==========================================================================================
# 8) Rendering Helpers (Markdown Output)
# ==========================================================================================

def _md_header(title: str, level: int = 1) -> str:
    return f"{'#' * level} {title}\n\n"


def _md_kv(key: str, value: str) -> str:
    return f"- **{key}:** {value}\n"


def _md_list(title: str, items: Tuple[str, ...]) -> str:
    if not items:
        return ""
    out = f"- **{title}:**\n"
    for it in items:
        out += f"  - {it}\n"
    return out


def render_plan_unit_md(u: PlanUnit) -> str:
    out = _md_header(f"{u.unit_id} — {u.name}", 3)
    out += _md_kv("Priority", u.priority.value)
    out += _md_kv("Status", u.status.value)
    out += _md_kv("Goal", u.goal)
    out += _md_kv("Why", u.why)
    out += _md_list("Scope", u.scope)
    out += _md_list("Non-goals", u.non_goals)
    out += _md_list("Dependencies", u.dependencies)
    out += _md_list("Deliverables", u.deliverables)
    out += _md_list("Contracts", u.contracts)
    out += _md_list("Invariants", u.invariants)
    out += _md_list("Traceability requirements", u.traceability_requirements)
    out += _md_list("Failure modes", u.failure_modes)

    if u.verification.commands:
        out += "\n- **Verification commands:**\n"
        for c in u.verification.commands:
            out += f"  - `{c}`\n"
    if u.verification.expected_signals:
        out += "\n- **Expected signals / invariants:**\n"
        for s in u.verification.expected_signals:
            out += f"  - `{s}`\n"

    ev = u.evidence
    if any([ev.required_files, ev.required_logs, ev.required_reports, ev.required_tests, ev.required_trace_events]):
        out += "\n- **Evidence required:**\n"
        out += _md_list("Files", ev.required_files)
        out += _md_list("Logs", ev.required_logs)
        out += _md_list("Reports", ev.required_reports)
        out += _md_list("Tests", ev.required_tests)
        out += _md_list("Trace events", ev.required_trace_events)

    if u.notes:
        out += f"\n- **Notes:** {u.notes}\n"

    out += "\n---\n\n"
    return out


def render_catalog_md() -> str:
    out = ""
    out += _md_header("IBKR Trading OS — Master Plan (Exhaustive)", 1)
    out += (
        "This document is generated from `ibkr_trading_os_master_plan.py`.\n\n"
        "It defines:\n"
        "- Core architecture epochs (system completeness)\n"
        "- Metadata governance epochs (audit + proof)\n"
        "- Setup families (macro)\n"
        "- Strategies (runnable modules)\n"
        "- Classification layers: execution logic / conditions / confirmations\n"
        "- Cross-cutting planes: decision artifacts / failure modes / no-trade contexts / interaction rules\n\n"
        "Completion rule: **Nothing is 'DONE' without passing verification commands and producing evidence artifacts.**\n\n"
    )

    out += _md_header("Catalog Index", 2)
    for section in CATALOG:
        out += f"- {section.section_key}: {section.description} (items={len(section.items)})\n"
    out += "\n"

    for section in CATALOG:
        out += _md_header(f"{section.section_key}", 2)
        out += f"{section.description}\n\n"
        for u in section.items:
            out += render_plan_unit_md(u)
    return out


# ==========================================================================================
# 9) Main
# ==========================================================================================

def main() -> None:
    print(render_catalog_md())


if __name__ == "__main__":
    main()
