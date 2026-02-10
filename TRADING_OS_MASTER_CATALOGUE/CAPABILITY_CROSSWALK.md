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
| E6 Scanner → Strategy Contract | Scanner contracts | `src/scanner/scanner_contract.py`, `tests/test_scanner_request_validation.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/BLOCKER_01/` | PARTIAL |
| E7 Mode Parity & Safety | Mode scripts | `RUN_SIMULATION.ps1`, `RUN_LIVE_READ_ONLY.ps1`, `tests/test_mode_drift_guard.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/BLOCKER_02/` | PARTIAL |
| E8 Regime & Microstructure | Regime layer | `src/regime/`, `tests/test_regime_classifier.py`, `tests/test_regime_observers.py`, `tests/test_regime_policy_application.py`, `tests/test_regime_live_readonly_missingness.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_08/` | OK |
| E9 Performance Analytics | Performance registry | `src/core/performance_registry.py`, `tests/test_performance_registry_epoch9.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_09/EPOCH_09_E9_PERFORMANCE_ANALYTICS.md` | OK |
| E10 Capital Allocation | Allocation arbitration | `src/strategy_portfolio/allocation.py`, `tests/strategy_portfolio/test_allocation.py`, `tests/strategy_portfolio/test_arbitration.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_10/EPOCH_10_E10_CAPITAL_ALLOCATION.md` | OK |
| E11 Learning System | Learning pipeline | `src/learning/`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_11/EPOCH_11_E11_LEARNING_SYSTEM.md` | OK |
| E12 Recovery & Housekeeping | Storage + stop control | `src/storage/`, `src/core/stop_controller.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_12/EPOCH_12_E12_RECOVERY_AND_HOUSEKEEPING.md` | OK |
| E13 Strategy Factory Standard | Registry + base | `src/strategies/strategy_registry.py`, `src/strategies/strategy_base.py`, `tests/test_strategy_registry_epoch13.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_13/EPOCH_13_E13_STRATEGY_FACTORY_STANDARD.md` | OK |
| E14 Decision Artifacts | Intent + signal models | `src/core/intent.py`, `src/models/data_models.py`, `src/execution/execution_engine.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_14/EPOCH_14_E14_DECISION_ARTIFACTS.md` | OK |
| E15 Failure Modes | Fault handling | `src/core/faults.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_15/EPOCH_15_E15_FAILURE_MODES.md` | OK |
| E16 No-Trade Contexts | Risk/market gating | `src/risk/no_trade_contexts.py`, `src/risk/risk_engine.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_16/EPOCH_16_E16_NO_TRADE_CONTEXTS.md` | OK |
| E17 Strategy Interaction Rules | Arbitration | `src/strategy_portfolio/arbitration.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_17/EPOCH_17_E17_STRATEGY_INTERACTION_RULES.md` | OK |
| E18 Strategy Foundation Layer | Common strategy utilities | `src/strategies/common/`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_18/EPOCH_18_E18_STRATEGY_FOUNDATION_LAYER.md` | OK |
| E19 Strategy Interface & Certification | Strategy contracts | `src/strategies/strategy_contracts.py`, `src/strategies/strategy_registry.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_19/EPOCH_19_E19_STRATEGY_INTERFACE_AND_CERTIFICATION.md` | OK |
| E20 Strategy Foundation Completion | Strategy foundation | `src/strategies/common/foundation.py`, `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_20/EPOCH_20_E20_STRATEGY_FOUNDATION_COMPLETION.md` | OK |
| E21 Trading Ready Verification | Run scripts | `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/EPOCH_21/EPOCH_21_E21_TRADING_READY_VERIFICATION_AND_END_TO_END_SIMULATION.md` | OK |

## Metadata Epoch Crosswalk
| Catalogue Item | Capability Anchor | Evidence Pointer(s) | Status |
| --- | --- | --- | --- |
| M0 Canon & Sources of Truth | Programme canon | `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/` | OK |
| M1 Architecture Map | System tree | `src/directory_tree_report.txt`, `SYSTEM_TREE_AND_MODULE_MAP.md` | PARTIAL |
| M2 Contract Registry | Contract artifacts | `src/scanner/contracts.py`, `src/strategies/strategy_contracts.py` | PARTIAL |
| M3 Mode Semantics Certification | Mode scripts | `RUN_*` scripts, `src/sim/` | PARTIAL |
| M4 Traceability Semantics | Event schema | `src/events/event_schema.py` | OK |
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
