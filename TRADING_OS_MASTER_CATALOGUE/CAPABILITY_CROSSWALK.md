# CAPABILITY_CROSSWALK

## Purpose
Map catalogue requirements to existing system components with explicit OK / PARTIAL / MISSING status and evidence pointers.

## Core Epoch Crosswalk
| Catalogue Item | Capability Anchor | Evidence Pointer(s) | Status |
| --- | --- | --- | --- |
| E0 System Law & Purpose | Governance canon | `TRADING_OS_MASTER_CATALOGUE/SYSTEM_CONSTITUTION*.md`, `SYSTEM_STATE*.md` | OK |
| E1 Traceability & Observability | Event schema + trace bus | `src/events/event_schema.py`, `src/core/trace_bus.py` | PARTIAL |
| E2 Position Lifecycle Engine | Lifecycle state machine | `src/core/position_lifecycle_engine.py` | PARTIAL |
| E3 Risk Engine Completeness | Risk gating | `src/risk/risk_engine.py` | PARTIAL |
| E4 Data Quality & Market State | Market data hub | `src/market_data/market_data_hub.py` | PARTIAL |
| E5 Execution Engine Authority | Execution router | `src/execution/execution_engine.py`, `src/execution/order_router.py` | PARTIAL |
| E6 Scanner → Strategy Contract | Scanner contracts | `src/scanner/scanner_contract.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/BLOCKER_01/pytest.txt` | PARTIAL |
| E7 Mode Parity & Safety | Mode scripts | `RUN_SIMULATION.ps1`, `RUN_LIVE_READ_ONLY.ps1` | PARTIAL |
| E8 Regime & Microstructure | Regime layer | `src/regime/` | PARTIAL |
| E9 Performance Analytics | Performance registry | `src/performance/performance_registry.py` | PARTIAL |
| E10 Capital Allocation | Allocation arbitration | `src/strategy_portfolio/allocation.py` | PARTIAL |
| E11 Learning System | Learning pipeline | `src/learning/` | PARTIAL |
| E12 Recovery & Housekeeping | Storage + stop control | `src/storage/`, `src/core/stop_controller.py` | PARTIAL |
| E13 Strategy Factory Standard | Registry + base | `src/strategies/strategy_registry.py`, `src/strategies/strategy_base.py` | PARTIAL |
| E14 Decision Artifacts | Intent + signal models | `src/core/intent.py`, `src/signals/` | PARTIAL |
| E15 Failure Modes | Fault handling | `src/core/faults.py` | PARTIAL |
| E16 No-Trade Contexts | Risk/market gating | `src/risk/`, `src/market_data/` | PARTIAL |
| E17 Strategy Interaction Rules | Arbitration | `src/strategy_portfolio/arbitration.py` | PARTIAL |
| E18 Strategy Foundation Layer | Common strategy utilities | `src/strategies/common/` | PARTIAL |
| E19 Strategy Interface & Certification | Strategy contracts | `src/strategies/strategy_contracts.py` | PARTIAL |
| E20 Strategy Foundation Completion | Strategy foundation | `src/strategies/` | PARTIAL |
| E21 Trading Ready Verification | Run scripts | `RUN_SIMULATION.ps1`, `RUN_PAPER_TRADING.ps1` | PARTIAL |

## Metadata Epoch Crosswalk
| Catalogue Item | Capability Anchor | Evidence Pointer(s) | Status |
| --- | --- | --- | --- |
| M0 Canon & Sources of Truth | Programme canon | `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/` | OK |
| M1 Architecture Map | System tree | `src/directory_tree_report.txt`, `SYSTEM_TREE_AND_MODULE_MAP.md` | PARTIAL |
| M2 Contract Registry | Contract artifacts | `src/scanner/contracts.py`, `src/strategies/strategy_contracts.py` | PARTIAL |
| M3 Mode Semantics Certification | Mode scripts | `RUN_*` scripts, `src/sim/` | PARTIAL |
| M4 Traceability Semantics | Event schema | `src/events/event_schema.py` | PARTIAL |
| M5 Verification Authority | Programme rules | `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/01_PROGRAM_RULES_LOCKED.md` | PARTIAL |
| M6 Data Lifecycle Governance | Storage engine | `src/storage/storage_engine.py`, `src/learning/storage.py` | PARTIAL |
| M7 Epoch Audit & Certification | Audit folders | `TRADING_OS_MASTER_CATALOGUE/01_CORE_EPOCHS/*/audit/` | PARTIAL |
| M8 Change Control | Locked rules | `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/04_IMPLEMENTATION_ENFORCEMENT.md` | PARTIAL |
| M9 Signal Semantics Registry | Signal registry | `src/signals/registry.py` | PARTIAL |
| M10 Data Provenance Ledger | Storage schema | `src/storage/schema_map.py` | PARTIAL |

## Strategy Crosswalk (P01–P20)
| Strategy | Evidence Pointer(s) | Status |
| --- | --- | --- |
| P01 Ross Momentum | `src/strategies/ross_momentum/`, `src/strategies/ross_momentum_strategy_v1.py` | PARTIAL |
| P02 Statistical Intraday Momentum | `src/strategies/statistical_intraday_momentum/` | PARTIAL |
| P03 Mean Reversion | `src/strategies/mean_reversion/` | PARTIAL |
| P04 Long Horizon Value | `src/strategies/long_horizon_value/` | PARTIAL |
| P05 Opening Drive | `src/strategies/opening_drive/` | PARTIAL |
| P06 VWAP Reclaim | `src/strategies/vwap_reclaim/` | PARTIAL |
| P07 Power Hour | `src/strategies/power_hour/` | PARTIAL |
| P08 Volatility Expansion | `src/strategies/volatility_expansion/` | PARTIAL |
| P09 Range Bound Fade | `src/strategies/range_bound_fade/` | PARTIAL |
| P10 Support Resistance Channel | `src/strategies/support_resistance_channel/` | PARTIAL |
| P11 Event Earnings Reaction | `src/strategies/event_earnings_reaction/` | PARTIAL |
| P12 Event News Shock Continuation | `src/strategies/event_news_shock_continuation/` | PARTIAL |
| P13 Volatility Contraction Breakout | `src/strategies/volatility_contraction_breakout/` | PARTIAL |
| P14 Volatility Carry Risk Premium | `src/strategies/volatility_carry_risk_premium/` | PARTIAL |
| P15 Pairs Divergence Reversion | `src/strategies/pairs_divergence_reversion/` | PARTIAL |
| P16 Cross-Sectional Relative Strength Rotation | `src/strategies/cross_sectional_relative_strength_rotation/` | PARTIAL |
| P17 Time-Based Seasonality | `src/strategies/time_based_seasonality/` | PARTIAL |
| P18 Trend Following Classic | `src/strategies/trend_following_classic/` | PARTIAL |
| P19 Long Horizon Quality Compounder | `src/strategies/long_horizon_quality_compounder/` | PARTIAL |
| P20 Regime Adaptive Meta Allocator | `src/strategies/regime_adaptive_meta_allocator/` | PARTIAL |
