# REALITY_MAP

## Purpose
Reality-first catalogue map that records what exists now, what is partial, and what is missing. This is the baseline for execution-stage planning and verification.

## Core Epochs (E0–E21)
| Epoch | Current Evidence (files/modules) | Status | Notes |
| --- | --- | --- | --- |
| E0 System Law & Purpose | `TRADING_OS_MASTER_CATALOGUE/SYSTEM_CONSTITUTION*.md`, `SYSTEM_STATE*.md` | OK | Governance canon exists in catalogue. |
| E1 Traceability & Observability | `src/events/`, `src/core/trace_bus.py`, `src/core/event_collector.py`, `src/logs/trace_*.jsonl` | PARTIAL | Event schema and trace bus exist; unified audit requirements still need end-to-end enforcement. |
| E2 Position Lifecycle Engine | `src/core/position_lifecycle_engine.py`, `src/core/active_trade_registry.py` | PARTIAL | Lifecycle components exist; explicit lifecycle contracts and verification remain incomplete. |
| E3 Risk Engine Completeness | `src/risk/risk_engine.py`, `src/risk/risk_audit.py` | PARTIAL | Risk engine present; policy gating contracts and mode parity not fully specified. |
| E4 Data Quality & Market State | `src/market_data/`, `src/sim/price_feed.py`, `src/market_data/market_data_hub.py` | PARTIAL | Market data infrastructure exists; canonical market state taxonomy not fully codified. |
| E5 Execution Engine Authority | `src/execution/execution_engine.py`, `src/execution/order_router.py` | PARTIAL | Execution components exist; authority boundary contracts require formalization. |
| E6 Scanner → Strategy Contract | `src/scanner/scanner_contract.py`, `src/strategies/strategy_contracts.py` | PARTIAL | Implicit contracts exist; need canonical contract document and registry alignment. |
| E7 Mode Parity & Safety | `RUN_*` scripts, `src/sim/clock.py`, `src/core/readiness.py` | PARTIAL | Multiple modes exist; formal parity checks and safety gates are incomplete. |
| E8 Regime & Microstructure Layer | `src/regime/` | PARTIAL | Regime scaffolding exists; integration across strategy selection is partial. |
| E9 Performance Analytics | `src/performance/`, `src/core/performance_registry.py` | PARTIAL | Analytics modules exist; certification-ready reporting is incomplete. |
| E10 Capital Allocation | `src/strategy_portfolio/allocation.py`, `src/strategy_portfolio/registry.py` | PARTIAL | Allocation framework exists; portfolio-level governance and constraints are partial. |
| E11 Learning System | `src/learning/` | PARTIAL | Learning modules exist; lifecycle governance and audit trails incomplete. |
| E12 Recovery & Housekeeping | `src/storage/`, `src/core/stop_controller.py` | PARTIAL | Storage and stop control exist; recovery runbooks and cleanup contracts are incomplete. |
| E13 Strategy Factory Standard | `src/strategies/strategy_registry.py`, `src/strategies/strategy_base.py` | PARTIAL | Registry exists; standardized discovery and certification workflows incomplete. |
| E14 Decision Artifacts | `src/core/intent.py`, `src/signals/` | PARTIAL | Intent/signal artifacts exist; archival and audit requirements incomplete. |
| E15 Failure Modes | `src/core/faults.py`, `src/core/stop_controller.py` | PARTIAL | Fault mechanisms exist; formal failure taxonomy and tests incomplete. |
| E16 No-Trade Contexts | `src/risk/`, `src/market_data/` | PARTIAL | Gating components exist; explicit no-trade taxonomy and enforcement missing. |
| E17 Strategy Interaction Rules | `src/strategy_portfolio/arbitration.py` | PARTIAL | Arbitration exists; interaction rules and proofs are incomplete. |
| E18 Strategy Foundation Layer | `src/strategies/common/` | PARTIAL | Common strategy utilities exist; foundation contract is not yet formalized. |
| E19 Strategy Interface & Certification | `src/strategies/strategy_contracts.py`, `src/strategies/strategy_registry.py` | PARTIAL | Interface definitions exist but certification workflow is incomplete. |
| E20 Strategy Foundation Completion | `src/strategies/` | PARTIAL | Strategy base layers exist; end-to-end foundation sign-off is missing. |
| E21 Trading Ready Verification & End-to-End Simulation | `RUN_SIMULATION.ps1`, `RUN_LIVE_READ_ONLY.ps1` | PARTIAL | Run scripts exist; consolidated verification ladder is not certified. |

## Metadata Epochs (M0–M10)
| Epoch | Current Evidence (files/modules) | Status | Notes |
| --- | --- | --- | --- |
| M0 Canon & Sources of Truth | `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/`, `SYSTEM_CONSTITUTION*.md` | OK | Canonical governance exists. |
| M1 Architecture Map | `src/directory_tree_report.txt`, `SYSTEM_TREE_AND_MODULE_MAP.md` | PARTIAL | Architecture map exists but not fully synchronized with catalogue. |
| M2 Contract Registry | `src/scanner/contracts.py`, `src/strategies/strategy_contracts.py` | PARTIAL | Contracts are implicit; registry is not consolidated. |
| M3 Mode Semantics Certification | `RUN_*` scripts, `src/sim/` | PARTIAL | Mode scripts exist; certification evidence is incomplete. |
| M4 Traceability Semantics | `src/events/event_schema.py`, `src/events/event_types.py` | OK | Schemas exist; traceability semantics certified. |
| M5 Verification Authority | `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/01_PROGRAM_RULES_LOCKED.md` | PARTIAL | Authority is declared; operational governance still requires evidence. |
| M6 Data Lifecycle Governance | `src/storage/`, `src/learning/storage.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M6_DATA_LIFECYCLE_GOVERNANCE/` | OK | Lifecycle governance verification evidence captured. |
| M7 Epoch Audit & Certification | `TRADING_OS_MASTER_CATALOGUE/01_CORE_EPOCHS/*/audit/` | PARTIAL | Audit structure exists; uniform certification criteria incomplete. |
| M8 Change Control | `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/01_PROGRAM_RULES_LOCKED.md` | PARTIAL | Change control is policy-only; enforcement tooling missing. |
| M9 Signal Semantics Registry | `src/signals/registry.py`, `src/signals/signal_types.py` | PARTIAL | Registry exists; canonical mapping to strategies incomplete. |
| M10 Data Provenance Ledger | `src/storage/schema_map.py` | PARTIAL | Storage schema exists; provenance ledger is not yet formalized. |

## Strategy Catalogue (P01–P20)
| Strategy | Current Evidence (files/modules) | Status | Notes |
| --- | --- | --- | --- |
| P01 Ross Momentum | `src/strategies/ross_momentum/`, `src/strategies/ross_momentum_strategy_v1.py` | PARTIAL | Strategy implementation exists; certification alignment pending. |
| P02 Statistical Intraday Momentum | `src/strategies/statistical_intraday_momentum/` | PARTIAL | Strategy modules present; contract alignment pending. |
| P03 Mean Reversion | `src/strategies/mean_reversion/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P04 Long Horizon Value | `src/strategies/long_horizon_value/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P05 Opening Drive | `src/strategies/opening_drive/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P06 VWAP Reclaim | `src/strategies/vwap_reclaim/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P07 Power Hour | `src/strategies/power_hour/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P08 Volatility Expansion | `src/strategies/volatility_expansion/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P09 Range Bound Fade | `src/strategies/range_bound_fade/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P10 Support Resistance Channel | `src/strategies/support_resistance_channel/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P11 Event Earnings Reaction | `src/strategies/event_earnings_reaction/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P12 Event News Shock Continuation | `src/strategies/event_news_shock_continuation/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P13 Volatility Contraction Breakout | `src/strategies/volatility_contraction_breakout/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P14 Volatility Carry Risk Premium | `src/strategies/volatility_carry_risk_premium/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P15 Pairs Divergence Reversion | `src/strategies/pairs_divergence_reversion/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P16 Cross-Sectional Relative Strength Rotation | `src/strategies/cross_sectional_relative_strength_rotation/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P17 Time-Based Seasonality | `src/strategies/time_based_seasonality/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P18 Trend Following Classic | `src/strategies/trend_following_classic/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P19 Long Horizon Quality Compounder | `src/strategies/long_horizon_quality_compounder/` | PARTIAL | Strategy modules present; certification evidence pending. |
| P20 Regime Adaptive Meta Allocator | `src/strategies/regime_adaptive_meta_allocator/` | PARTIAL | Strategy modules present; certification evidence pending. |
