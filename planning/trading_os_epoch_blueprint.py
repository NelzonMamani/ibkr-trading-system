"""
trading_os_epoch_blueprint.py

INTENT (FOR YOU ONLY):
This file is a *blueprint container* — not an implementation.

It defines 4 sections that someone (Codex / a developer / future you) will implement against:
1) Core Architecture Epochs (what a trading system must have to be complete) — priority ordered
2) Metadata Epochs (what a trading operating system needs to be auditable, governable, refactor-safe)
3) Setup Families (Ross-style macro setups + related catalog items)
4) Strategies (distinct strategy modules your system should ultimately support)

RULES:
- These are “targets + acceptance criteria”, not code.
- Each epoch has: goal, why, deliverables, verification, completion criteria.
- Keep everything explicit, measurable, and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ======================================================================================
# Shared Schema (used by all sections)
# ======================================================================================

@dataclass(frozen=True)
class BlueprintItem:
    key: str
    name: str
    priority: int  # 1 = highest priority
    goal: str
    why: str
    deliverables: List[str] = field(default_factory=list)
    mandatory_verification: List[str] = field(default_factory=list)
    completion_criteria: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _todo_verify_commands() -> List[str]:
    """
    Placeholder verification commands. Replace with your real canonical commands.
    """
    return [
        "python -m compileall src",
        "pytest -q",
        "python -m src.main --mode READ_ONLY --cycles 1 --strategy <strategy_key>",
        "python -m src.main --mode PAPER --cycles 1 --strategy <strategy_key>",
        # LIVE verification must be safe-gated; run only when market session + broker connectivity is available
        "python -m src.main --mode LIVE --cycles 1 --strategy <strategy_key>  # only when safe/connected",
    ]


# ======================================================================================
# SECTION 1 — CORE ARCHITECTURE EPOCHS (Trading System Completeness)
# Priority-ordered for “no more chaos”: safety, determinism, parity, execution, then learning/scaling.
# ======================================================================================

CORE_ARCHITECTURE_EPOCHS: List[BlueprintItem] = [
    BlueprintItem(
        key="E0_SYSTEM_LAW_TRUTH",
        name="System Law & Truth (Constitution + State + Canon)",
        priority=1,
        goal="Establish canonical truth documents and enforce them as source-of-truth for runtime behaviour.",
        why="Without canonical law/state, the system drifts, refactors break invariants, and audits become impossible.",
        deliverables=[
            "SYSTEM_CONSTITUTION.md (immutable law, non-negotiables)",
            "SYSTEM_STATE.md (current enforced reality, not intent)",
            "RUN_MODES_REFERENCE.md (canonical semantics table)",
            "README.md (public charter, setup, how to run)",
        ],
        mandatory_verification=[
            "pytest -q tests/test_config_sanity.py",
            "pytest -q tests/test_execution_intent_modes.py",
            "pytest -q tests/test_ibkr_readonly.py",
        ],
        completion_criteria=[
            "Docs match code (no contradictions on run modes, safety locks, gating).",
            "CI/verification commands pass with deterministic results.",
        ],
        notes=[
            "This epoch is the ‘constitution layer’ and must be updated whenever behaviour changes.",
        ],
    ),
    BlueprintItem(
        key="E1_TRACEABILITY_OBSERVABILITY",
        name="Traceability & Observability (No Silent Decisions)",
        priority=2,
        goal="Every material decision emits trace events with reason codes, stage labels, and inputs/outputs.",
        why="If you can’t trace, you can’t debug; if you can’t debug, you can’t trust.",
        deliverables=[
            "Trace event taxonomy (stages: CONFIG, SESSION, UNIVERSE, WATCHLIST, FOCUS, STRATEGY, RISK, EXECUTION, STORAGE, HALT)",
            "Reason codes registry (consistent across modules)",
            "Logs + JSONL trace bus (persisted artifacts)",
            "Minimal dashboards/reports (daily ops summary)",
        ],
        mandatory_verification=[
            "pytest -q tests/test_traceability.py",
            "pytest -q tests/test_scanner_watchlist_prints.py",
        ],
        completion_criteria=[
            "All strategies emit: received watchlist, considered count, signals count, intents count, blocks with reasons.",
            "All blocks are explicit (no silent failure).",
        ],
    ),
    BlueprintItem(
        key="E2_POSITION_LIFECYCLE_ENGINE",
        name="Position Lifecycle Engine (Entry→Add→Trail→Exit)",
        priority=3,
        goal="A unified, deterministic lifecycle for positions: open, add, reduce, exit, emergency exit.",
        why="A strategy that can only enter is not tradable; lifecycle is the real trading engine.",
        deliverables=[
            "ActiveTrade registry + state machine",
            "Exit engine (profit targets, stops, trailing, time exits)",
            "Order intent lifecycle (dedup, idempotency, retries)",
            "Position reconciliation hooks (broker vs internal state)",
        ],
        mandatory_verification=[
            "pytest -q tests/test_trade_exit_engine.py",
            "pytest -q tests/test_sqlite_persistence.py",
        ],
        completion_criteria=[
            "Paper lifecycle test covers: buy → add → trail → partial sell → full exit.",
            "No duplicate orders for same intent_id; all retries are safe.",
        ],
    ),
    BlueprintItem(
        key="E3_RISK_ENGINE_COMPLETENESS",
        name="Risk Engine Completeness (Authority + Circuit Breakers)",
        priority=4,
        goal="Centralize all permissioning and risk constraints; strategies never bypass risk.",
        why="Risk is the single point of truth for ‘allowed to trade’ in each mode and scenario.",
        deliverables=[
            "Risk decision API + reason codes",
            "Circuit breakers (daily loss, max trades, volatility halts, connectivity degradation)",
            "Per-strategy locks and mode gating",
            "Kill-switch and stop controller integration",
        ],
        mandatory_verification=[
            "pytest -q tests/test_epoch3_risk_execution.py",
            "pytest -q tests/test_stop_controller.py",
        ],
        completion_criteria=[
            "READ_ONLY cannot execute under any circumstance.",
            "PAPER executes simulated only; LIVE executes only if risk permits.",
        ],
    ),
    BlueprintItem(
        key="E4_DATA_QUALITY_MARKET_STATE",
        name="Data Quality & Market State (Session + Integrity Gates)",
        priority=5,
        goal="Detect session phase, enforce data quality, degrade safely, and record missingness.",
        why="Bad data causes bad trades; session-awareness is mandatory for %change/RVOL semantics.",
        deliverables=[
            "Session detection (PRE/RTH/AH/CLOSED + holidays/weekends)",
            "Data quality flags (price missing, bid/ask missing, stale snapshot, OTC/subscription issues)",
            "Connectivity manager (IBKR retry/backoff + degrade states)",
            "Market state model (risk-off, high volatility, news-driven)",
        ],
        mandatory_verification=[
            "pytest -q tests/test_market_session_phase.py",
            "pytest -q tests/test_market_data_validation.py",
            "pytest -q tests/test_market_data_client_disconnect.py",
        ],
        completion_criteria=[
            "Scanner/strategies operate deterministically in CLOSED mode (no crashes, explicit empties allowed).",
            "Degraded connectivity emits HALT with reason codes.",
        ],
    ),
    BlueprintItem(
        key="E5_EXECUTION_ENGINE_AUTHORITY",
        name="Execution Engine Authority (Broker Routing + Sim Provider)",
        priority=6,
        goal="Unify execution routing; paper/sim providers are first-class; broker adapter is isolated.",
        why="Execution is where money is lost; it must be controlled, tested, and mode-safe.",
        deliverables=[
            "Execution engine with provider interface (IBKR/PAPER/SIM)",
            "Order gateway with retries + idempotency",
            "Commission/slippage models (at least placeholders)",
            "Broker translator and submission guard",
        ],
        mandatory_verification=[
            "pytest -q tests/test_liquidity_execution.py",
            "pytest -q tests/test_order_gateway_retry.py",
            "pytest -q tests/test_ibkr_order_submitter.py",
        ],
        completion_criteria=[
            "Orders are never sent in READ_ONLY.",
            "PAPER generates fills and updates positions deterministically.",
        ],
    ),
    BlueprintItem(
        key="E6_SCANNER_STRATEGY_CONTRACT",
        name="Scanner–Strategy Contract (Mechanical Scanner, Policy in Strategy)",
        priority=7,
        goal="Scanner is mechanical and fast; all selection logic lives in strategy policy; contract is versioned.",
        why="This prevents duplicated logic and makes strategies truly portable and testable.",
        deliverables=[
            "StockSelectionSpec contract (TopN → gates → WatchlistK → FocusM)",
            "Session-aware %change reference contract",
            "Scanner diagnostics prints (Top50 expanded columns, Watchlist15 same columns)",
            "Strategy-owned ranking intent hook",
        ],
        mandatory_verification=[
            "pytest -q tests/test_scanner_contract.py",
            "pytest -q tests/test_scanner_policy_from_strategy.py",
        ],
        completion_criteria=[
            "Watchlist K is deterministic even when empty; emptiness is valid and explicit.",
            "Scanner outputs include drop reason summaries.",
        ],
    ),
    BlueprintItem(
        key="E7_MODE_PARITY",
        name="Mode Parity (READ_ONLY / PAPER / LIVE)",
        priority=8,
        goal="Every strategy must run end-to-end in all modes with predictable semantics and verified artifacts.",
        why="If it can’t run in PAPER reliably, LIVE readiness is fiction.",
        deliverables=[
            "Per-strategy mode verification scripts/logs",
            "Global verify_all harness",
            "Mode parity test suite",
        ],
        mandatory_verification=[
            "python -m src.main --mode READ_ONLY --cycles 1 --strategy <strategy_key>",
            "python -m src.main --mode PAPER --cycles 1 --strategy <strategy_key>",
            "python -m src.main --mode LIVE --cycles 1 --strategy <strategy_key>  # safe-gated",
        ],
        completion_criteria=[
            "Each strategy: watchlist → intents → (paper fills) → lifecycle updates → storage writes.",
            "All failures are explicit with reason codes.",
        ],
    ),
    BlueprintItem(
        key="E8_REGIME_LAYER",
        name="Regime Layer (Measurement → Classifier → Policy)",
        priority=9,
        goal="Provide regime facts that strategies can use as hard gates or soft scoring components.",
        why="Regime awareness reduces trading in bad environments and improves robustness.",
        deliverables=[
            "Regime observers + baselines + classifier",
            "Regime snapshot events and storage",
            "Strategy consumption contracts",
        ],
        mandatory_verification=[
            "pytest -q tests/test_regime_classifier.py",
            "pytest -q tests/test_regime_contracts.py",
        ],
        completion_criteria=[
            "Regime snapshots are emitted and persisted deterministically.",
            "Strategies can run with regime disabled and enabled (parity).",
        ],
    ),
    BlueprintItem(
        key="E9_PERFORMANCE_ANALYTICS",
        name="Performance & Analytics (PnL, Slippage, Attribution, Reports)",
        priority=10,
        goal="Generate daily/weekly/monthly reports and per-strategy attribution.",
        why="You need measurement to learn and iterate safely.",
        deliverables=[
            "Performance registry + storage reports",
            "Trade review queries",
            "Ops summaries and dashboards (file outputs acceptable)",
        ],
        mandatory_verification=[
            "pytest -q tests/test_performance_reports_epoch4.py",
        ],
        completion_criteria=[
            "Reports are produced even if no trades occur (empty is valid).",
        ],
    ),
    BlueprintItem(
        key="E10_CAPITAL_ALLOCATION",
        name="Capital Allocation (Portfolio-Level Governance)",
        priority=11,
        goal="Allocate capital across strategies using rules and hard risk budgets.",
        why="Multi-strategy systems require allocation; otherwise strategies interfere indirectly.",
        deliverables=[
            "Allocation engine (risk budgets per strategy)",
            "Arbitration rules and non-interference guarantees",
            "Portfolio contracts and registry",
        ],
        mandatory_verification=[
            "pytest -q tests/strategy_portfolio/test_allocation.py",
            "pytest -q tests/strategy_portfolio/test_non_interference.py",
        ],
        completion_criteria=[
            "Conflicting intents are arbitrated deterministically.",
            "Portfolio-level risk budgets enforced.",
        ],
    ),
    BlueprintItem(
        key="E11_LEARNING_SYSTEM",
        name="Learning System (Telemetry → Proposals → Human Approval)",
        priority=12,
        goal="Capture learning telemetry and produce policy proposals without auto-mutation.",
        why="Learning must be controlled and auditable; never self-modify silently.",
        deliverables=[
            "Learning storage schema",
            "Policy proposal generator",
            "Approval workflow (manual/explicit)",
        ],
        mandatory_verification=[
            "pytest -q tests/test_learning_policy_proposal.py",
            "pytest -q tests/test_learning_reporting.py",
        ],
        completion_criteria=[
            "No strategy changes itself; proposals are explicit artifacts only.",
        ],
    ),
    BlueprintItem(
        key="E12_RECOVERY_AND_HOUSEKEEPING",
        name="Recovery & Housekeeping (Backups, Resets, Safe-to-Delete)",
        priority=13,
        goal="Fast recovery after corruption/growth: DB backup/reset, log rotation, cache management.",
        why="Your repo already hit size/space issues; recovery must be routine, not emergency.",
        deliverables=[
            "db_admin utilities (status/backup/hard-reset)",
            "SAFE_TO_DELETE.md (explicit list)",
            "RECOVERY_PLAYBOOK.md (rebuild from scratch)",
        ],
        mandatory_verification=[
            "python -m src.storage.db_admin status",
            "python -m src.storage.db_admin backup --out <path>",
            "python -m src.storage.db_admin hard-reset  # only on disposable environments",
        ],
        completion_criteria=[
            "System can cold-start after deleting caches/logs/reports; must rebuild deterministically.",
        ],
    ),
    BlueprintItem(
        key="E13_STRATEGY_FACTORY_STANDARD",
        name="Strategy Factory Standard (Uniform Wiring + Tests Location Rule)",
        priority=14,
        goal="All strategies follow the same folder structure, contracts, wiring, and test conventions.",
        why="Without a standard, each strategy becomes a bespoke integration headache.",
        deliverables=[
            "Per-strategy folder: src/strategies/<strategy>/ (policy, adapters, scanner_policy, strategy runner adapter, tests/)",
            "Rule: pure strategy unit tests live inside strategy folder",
            "Cross-system tests live in top-level tests/",
        ],
        mandatory_verification=[
            "pytest -q src/strategies/<strategy>/tests",
            "pytest -q tests/smoke/test_imports.py",
        ],
        completion_criteria=[
            "New strategy can be added via template with minimal boilerplate and clear verification.",
        ],
    ),
]


# ======================================================================================
# SECTION 2 — METADATA EPOCHS (Trading Operating System Governance Layer)
# These are “govern the governors”: auditability, contracts, refactor safety, certification.
# ======================================================================================

METADATA_EPOCHS: List[BlueprintItem] = [
    BlueprintItem(
        key="M0_CANON",
        name="Canon: What is True (Law/State/Glossary)",
        priority=1,
        goal="Define canonical documents and a glossary of terms; eliminate ambiguity.",
        why="Prevents endless redefinition of run modes, strategies, and contracts.",
        deliverables=[
            "SYSTEM_CONSTITUTION.md",
            "SYSTEM_STATE.md",
            "GLOSSARY.md (session labels, watchlist, focus, intent, execution, etc.)",
        ],
        mandatory_verification=[
            "Docs lint (optional): ensure required headings exist",
            "pytest -q tests/test_config_sanity.py",
        ],
        completion_criteria=[
            "No contradictory definitions; docs match runtime prints and behaviour.",
        ],
    ),
    BlueprintItem(
        key="M1_ARCHITECTURE_MAP",
        name="Architecture Map & Ownership (Module Boundaries)",
        priority=2,
        goal="Document module boundaries and enforce dependency direction (no illegal imports).",
        why="Stops architecture erosion during fast iteration.",
        deliverables=[
            "SYSTEM_ARCHITECTURE.md (current)",
            "SYSTEM_TREE_AND_MODULE_MAP.md (current)",
            "Ownership map: each module has an owner + responsibility + forbidden deps",
        ],
        mandatory_verification=[
            "Import boundary test (custom): fail if forbidden imports exist",
        ],
        completion_criteria=[
            "Refactors cannot silently create cycles; boundary test prevents it.",
        ],
    ),
    BlueprintItem(
        key="M2_CONTRACT_REGISTRY",
        name="Contract Registry (Versioned Interfaces)",
        priority=3,
        goal="Central registry of contracts + versioning rules + breaking change workflow.",
        why="Most bugs come from implicit contracts drifting across modules.",
        deliverables=[
            "CONTRACT_REGISTRY.md",
            "Scanner contracts, strategy contracts, risk/execution contracts listed with version",
        ],
        mandatory_verification=[
            "Contract compliance tests (per contract)",
        ],
        completion_criteria=[
            "Any breaking change requires: doc update + tests + verification report.",
        ],
    ),
    BlueprintItem(
        key="M3_MODE_SEMANTICS_CERT",
        name="Mode Semantics Certification (Truth Tables + Enforcement Proof)",
        priority=4,
        goal="Formalize mode semantics and prove enforcement with tests and logs.",
        why="Mode confusion is the #1 source of safety failures.",
        deliverables=[
            "RUN_MODES_REFERENCE.md",
            "Mode truth tables for READ_ONLY/PAPER/LIVE",
            "Enforcement tests for execution gating",
        ],
        mandatory_verification=[
            "pytest -q tests/test_execution_intent_modes.py",
            "pytest -q tests/test_ibkr_readonly.py",
        ],
        completion_criteria=[
            "No order path exists in READ_ONLY (provable).",
        ],
    ),
    BlueprintItem(
        key="M4_TRACEABILITY_SEMANTICS",
        name="Traceability Semantics (Stages + Required Fields)",
        priority=5,
        goal="Define required trace stages and required fields; enforce via tests.",
        why="Trace is your system’s “black box recorder”.",
        deliverables=[
            "TRACE_SPEC.md (stage glossary + required fields per stage)",
            "Reason-code registry (single file)",
        ],
        mandatory_verification=[
            "pytest -q tests/test_traceability.py",
        ],
        completion_criteria=[
            "All strategies emit minimum trace contract each cycle.",
        ],
    ),
    BlueprintItem(
        key="M5_VERIFICATION_AUTHORITY",
        name="Verification Authority (What Proves Reality)",
        priority=6,
        goal="Define mandatory verification commands and how PASS/WARN/FAIL is interpreted.",
        why="Stops endless arguments; green logs become law.",
        deliverables=[
            "PR_VERIFICATION_REPORT.md template",
            "VERIFY_ALL.ps1 script or python harness",
        ],
        mandatory_verification=_todo_verify_commands(),
        completion_criteria=[
            "One command produces a summary report + per-strategy logs.",
        ],
    ),
    BlueprintItem(
        key="M6_DATA_LIFECYCLE_GOV",
        name="Data Lifecycle Governance (Safe-to-Delete + Recovery)",
        priority=7,
        goal="Document what can be deleted and how system rebuilds deterministically.",
        why="Repo growth and corruption are guaranteed over time.",
        deliverables=[
            "SAFE_TO_DELETE.md",
            "RECOVERY_PLAYBOOK.md",
            "Retention rules (logs, reports, cache, DB backups)",
        ],
        mandatory_verification=[
            "Recovery drill: delete caches/logs/reports; system still starts and regenerates",
        ],
        completion_criteria=[
            "Cold rebuild is documented and proven.",
        ],
    ),
    BlueprintItem(
        key="M7_EPOCH_AUDIT_CERTIFICATION",
        name="Epoch Audit & Certification (Completion Stamps)",
        priority=8,
        goal="Certify each epoch with an audit report and prevent regressions.",
        why="This is how you stop the endless ‘we’re almost done’ loop.",
        deliverables=[
            "EPOCH_<N>/AUDIT_REPORT.md",
            "EPOCH_<N>/CHECKLIST.md",
            "Regression tests pinned to epoch acceptance criteria",
        ],
        mandatory_verification=[
            "Full verify_all suite",
        ],
        completion_criteria=[
            "Epoch is either CERTIFIED or NOT CERTIFIED. No ambiguity.",
        ],
    ),
    BlueprintItem(
        key="M8_CHANGE_CONTROL",
        name="Change Control (Approval Workflow for Refactors)",
        priority=9,
        goal="Define how refactors are proposed, reviewed, verified, and merged.",
        why="Prevents architecture churn and accidental deletions.",
        deliverables=[
            "CHANGE_CONTROL.md",
            "PR gates: what must be included (docs, tests, logs)",
        ],
        mandatory_verification=[
            "PR template enforcement (manual or tooling)",
        ],
        completion_criteria=[
            "Every significant change includes updated docs + verification artifacts.",
        ],
    ),
]


# ======================================================================================
# SECTION 3 — SETUP FAMILIES (Macro Setups / Ross-style Catalogue)
# These are “what the Ross momentum system trades” at a macro structure level.
# NOTE: Some items overlap; this list de-duplicates and normalizes.
# ======================================================================================

SETUP_FAMILIES: List[BlueprintItem] = [
    BlueprintItem(
        key="SF_GAP_AND_GO",
        name="Gap & Go (Opening Drive)",
        priority=1,
        goal="Trade strong gappers with RVOL + catalyst breaking PMH/ORH with continuation.",
        why="Primary Ross edge; defines the daily playbook.",
        deliverables=[
            "Setup definition + entry/exit rules",
            "Failure modes and no-trade conditions",
        ],
    ),
    BlueprintItem(
        key="SF_ORB",
        name="Opening Range Breakout (ORB)",
        priority=2,
        goal="Break and hold above ORH after initial consolidation; continuation entry.",
        why="Structured breakout with clear risk points.",
        deliverables=["Setup definition + triggers (1m/5m)"],
    ),
    BlueprintItem(
        key="SF_FIRST_PULLBACK_FIRST_FLAG",
        name="First Pullback / First Flag",
        priority=3,
        goal="First controlled pullback after breakout/drive; continuation entry on reclaim.",
        why="High probability continuation setup.",
        deliverables=["Setup definition + validation gates"],
    ),
    BlueprintItem(
        key="SF_MICRO_PULLBACK",
        name="Micro Pullback (10s/15s execution)",
        priority=4,
        goal="2–3 small pullback candles in uptrend; enter on reclaim trigger.",
        why="Execution-level trigger for adds and re-entries.",
        deliverables=["Micro trigger rules (conservative/aggressive)"],
    ),
    BlueprintItem(
        key="SF_BULL_FLAG_TIGHT_FLAG",
        name="Bull Flag / High-Tight Flag",
        priority=5,
        goal="Impulse → tight consolidation → breakout of flag high.",
        why="Classic momentum continuation structure.",
        deliverables=["Pattern geometry + volume confirmation rules"],
    ),
    BlueprintItem(
        key="SF_KEY_LEVEL_BREAK",
        name="Break of Key Level",
        priority=6,
        goal="Break/reclaim key levels (PMH, whole/half dollar, PDH, multi-day high) with volume.",
        why="Liquidity and crowd focus concentrate at key levels.",
        deliverables=["Key-level hierarchy + confirmation checklist"],
    ),
    BlueprintItem(
        key="SF_ABCD_CONTINUATION",
        name="ABCD Continuation / Measured Move",
        priority=7,
        goal="Stair-step continuation with pullbacks; entry on triggers; manage measured move target.",
        why="Defines continuation legs and objective targets.",
        deliverables=["Measured move rules + invalidations"],
    ),
    BlueprintItem(
        key="SF_CUP_AND_HANDLE_INTRADAY",
        name="Cup & Handle (Intraday)",
        priority=8,
        goal="Rounded base + tight handle; breakout of handle high with volume.",
        why="Compression then expansion; tradable during mid-morning/midday.",
        deliverables=["Structure validation + breakout trigger rules"],
    ),
    BlueprintItem(
        key="SF_MOMENTUM_RECLAIM",
        name="Momentum Reclaim (VWAP/EMA reclaim)",
        priority=9,
        goal="Reclaim VWAP or key EMA after shakeout; continuation if momentum returns.",
        why="Captures second-chance continuation after stop-out liquidity event.",
        deliverables=["Reclaim rules + failure triggers"],
    ),
    BlueprintItem(
        key="SF_R2G_G2R_CONTEXT",
        name="Red-to-Green / Green-to-Red (Context Signal)",
        priority=10,
        goal="Use R2G/G2R as confirmation/warning, not standalone edge.",
        why="Improves timing and risk control.",
        deliverables=["Context usage guidelines"],
    ),
    BlueprintItem(
        key="SF_FLAT_TOP_ASCENDING",
        name="Flat-Top / Ascending Breakout",
        priority=11,
        goal="Repeated tests of resistance; breakout with volume.",
        why="Compression against resistance is a frequent pre-breakout structure.",
        deliverables=["Resistance test-count rule + volume rule"],
    ),
    BlueprintItem(
        key="SF_SUPPORT_RESIST_BOUNCE_BREAK",
        name="Support/Resistance Bounce + Break/Reclaim",
        priority=12,
        goal="Bounce off key level or break/reclaim as continuation trigger.",
        why="Defines structured entries around strong levels.",
        deliverables=["Level selection + entry confirmation"],
    ),
    BlueprintItem(
        key="SF_PREMARKET_HIGH_BREAK",
        name="Pre-market High Break (PMH reclaim/hold)",
        priority=13,
        goal="Break/reclaim and hold above PMH; often overlaps Gap & Go but treated explicitly.",
        why="PMH is a primary trigger level in Ross systems.",
        deliverables=["PMH detection + hold criteria"],
    ),
    BlueprintItem(
        key="SF_HALT_RESUME",
        name="Halt Resume Continuation",
        priority=14,
        goal="After volatility halt, trade resumption continuation if liquidity/order flow supports.",
        why="High-risk/high-reward; must be governed strictly.",
        deliverables=["Halt risk rules + execution restrictions"],
    ),
    BlueprintItem(
        key="SF_PARABOLIC_EXHAUSTION_AVOID",
        name="Parabolic Exhaustion (Avoid/Exit Family)",
        priority=15,
        goal="Detect climactic push; treat as exit/stop-trading signal, not entry.",
        why="Prevents giving back gains on blow-off tops.",
        deliverables=["Exhaustion markers + stop-trading rules"],
    ),
]


# ======================================================================================
# SECTION 4 — STRATEGIES (Distinct Tradable Modules)
# Strategy != setup family. A strategy can trade multiple families or be a different style (mean reversion, long-horizon).
# “Locked for now” items: OPENING_DRIVE / VWAP_RECLAIM / POWER_HOUR / VOL_EXPANSION (as strategies).
# ======================================================================================

STRATEGIES: List[BlueprintItem] = [
    BlueprintItem(
        key="S_ROSS_MOMENTUM",
        name="Ross Momentum (multi-setup intraday momentum)",
        priority=1,
        goal="End-to-end tradable Ross-style momentum across core setups with paper parity and live-safe gating.",
        why="Primary system strategy; drives scanner design and watchlist cadence.",
        deliverables=[
            "Complete setup library implementation (macro + micro triggers)",
            "Entry/add/exit mapping per setup",
            "Session-aware premarket prep and key levels",
            "Full PAPER lifecycle verification",
        ],
        mandatory_verification=_todo_verify_commands(),
        completion_criteria=[
            "Generates intents in PAPER with deterministic lifecycle outcomes.",
            "Trace shows per-setup decision reasons and invalidations.",
        ],
    ),
    BlueprintItem(
        key="S_STATISTICAL_INTRADAY_MOMENTUM",
        name="Statistical Intraday Momentum (quant continuation/reversion)",
        priority=2,
        goal="Fully tradable quant strategy with calibrated scoring, risk policy, and mode parity.",
        why="Second major trading pillar; requires alignment to architecture contracts.",
        deliverables=[
            "Signal engine, scoring, regime gating",
            "Risk policy integration and intent emission",
            "Paper lifecycle verification",
        ],
        mandatory_verification=_todo_verify_commands(),
        completion_criteria=[
            "End-to-end paper trading works: entries/exits with traceable logic.",
        ],
        notes=["You explicitly requested a final realignment of statistical after the next strategy wave."],
    ),
    BlueprintItem(
        key="S_MEAN_REVERSION",
        name="Mean Reversion (intraday reversion to mean with regime permission)",
        priority=3,
        goal="Fully tradable mean reversion system with scanner facts, entry/exit models, and paper parity.",
        why="Diversifies away from pure momentum and adds regime-aware countertrend capability.",
        deliverables=[
            "Strategy policy + adapters + scanner policy + runner wiring",
            "Local unit tests in strategy folder (LOCKED RULE)",
            "System-level smoke tests and verification logs",
        ],
        mandatory_verification=_todo_verify_commands(),
        completion_criteria=[
            "In PAPER: can open, manage, and close positions via lifecycle engine.",
        ],
    ),
    BlueprintItem(
        key="S_LONG_HORIZON_VALUE",
        name="Long Horizon Value (multi-month fundamental compounding)",
        priority=4,
        goal="Tradable long-horizon strategy with paper execution and explicit live locks unless overridden.",
        why="Completes the system with a separate strategy class (Epoch 6 boundary).",
        deliverables=[
            "Universe discovery, fundamentals assembly, quality gates",
            "Intrinsic value + margin of safety ranking",
            "Portfolio construction + monitoring",
            "PAPER trading + verification harness",
        ],
        mandatory_verification=[
            "python -m src.main --mode PAPER --cycles 1 --strategy long_horizon_value",
        ],
        completion_criteria=[
            "PAPER: can buy, rebalance, and track holdings over time without interfering with intraday systems.",
        ],
    ),

    # ---- Locked for now as STRATEGIES (your instruction) ----
    BlueprintItem(
        key="S_OPENING_DRIVE",
        name="OPENING_DRIVE (strategy specialization)",
        priority=5,
        goal="A specialized Ross subset strategy focusing on the opening drive window (first 5–30 minutes).",
        why="Tighter specialization allows sharper rules and better risk control than a monolithic Ross strategy.",
        deliverables=["Dedicated policy gates + time-window restrictions + verification scripts"],
    ),
    BlueprintItem(
        key="S_VWAP_RECLAIM",
        name="VWAP_RECLAIM (strategy specialization)",
        priority=6,
        goal="A strategy centered on VWAP reclaim patterns (momentum reclaim family).",
        why="VWAP reclaim behaves differently from gap breakouts and benefits from separate rules.",
        deliverables=["VWAP regime gates + reclaim triggers + failure exits"],
    ),
    BlueprintItem(
        key="S_POWER_HOUR",
        name="POWER_HOUR (strategy specialization)",
        priority=7,
        goal="Late-day momentum strategy (last ~60–90 minutes), distinct liquidity/volatility behaviour.",
        why="Different microstructure; should not share identical rules with morning strategies.",
        deliverables=["Time-window enforcement + pattern subset + risk limits"],
    ),
    BlueprintItem(
        key="S_VOL_EXPANSION",
        name="VOL_EXPANSION (strategy specialization)",
        priority=8,
        goal="Volatility expansion/breakout strategy focused on range compression → expansion dynamics.",
        why="Cross-cuts multiple setups but can be treated as its own alpha bucket with clear risk logic.",
        deliverables=["Compression detection + breakout confirmation + exit logic"],
    ),
]


# ======================================================================================
# Utility: Simple prints (optional)
# ======================================================================================

def print_summary() -> None:
    def _print(items: List[BlueprintItem], title: str) -> None:
        print("\n" + "=" * 90)
        print(title)
        print("=" * 90)
        for item in sorted(items, key=lambda x: (x.priority, x.key)):
            print(f"[P{item.priority}] {item.key} — {item.name}")

    _print(CORE_ARCHITECTURE_EPOCHS, "SECTION 1 — CORE ARCHITECTURE EPOCHS")
    _print(METADATA_EPOCHS, "SECTION 2 — METADATA EPOCHS")
    _print(SETUP_FAMILIES, "SECTION 3 — SETUP FAMILIES")
    _print(STRATEGIES, "SECTION 4 — STRATEGIES")


if __name__ == "__main__":
    print_summary()
