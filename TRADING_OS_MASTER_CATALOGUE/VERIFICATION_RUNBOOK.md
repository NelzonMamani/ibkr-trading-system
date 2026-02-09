# VERIFICATION_RUNBOOK

## Purpose
Define what verification means for each core and metadata epoch in plain language, including the exact commands to run during the execution stage. Do not run these commands during planning.

## Environment Assumptions
- Run from repository root.
- Python environment with dependencies installed.
- Use the run-mode scripts in the repo root when applicable.

## Baseline Commands (All Epochs)
```
python -m compileall src
pytest
```

## Core Epoch Verification
| Epoch | Verification Intent | Commands |
| --- | --- | --- |
| E0 System Law & Purpose | Ensure constitution/state governance is intact and referenced by runtime. | `pytest tests/test_config_sanity.py` |
| E1 Traceability & Observability | Validate event schema and trace collection. | `pytest tests/test_traceability.py tests/test_event_collector_snapshot_policy.py` |
| E2 Position Lifecycle Engine | Validate lifecycle transitions and persistence. | `pytest tests/test_position_lifecycle_engine.py tests/test_position_lifecycle_persistence.py` |
| E3 Risk Engine Completeness | Validate risk gating between strategy and execution. | `pytest tests/test_epoch3_risk_execution.py` |
| E4 Data Quality & Market State | Validate market data quality, session state, and replay rules. | `pytest tests/test_market_data_validation.py tests/test_market_session_phase.py tests/test_replay_from_storage_epoch4.py tests/test_replay_locked_in_live_modes_epoch4.py` |
| E5 Execution Engine Authority | Validate execution authority and intent modes. | `pytest tests/test_execution_authority_epoch5.py tests/test_execution_intent_modes.py tests/test_order_gateway_retry.py` |
| E6 Scanner → Strategy Contract | Validate scanner contracts and policy bridges. | `pytest tests/test_scanner_contract_54.py tests/test_scanner_policy_from_strategy.py tests/test_orchestrator_scanner_request.py` |
| E7 Mode Parity & Safety | Validate read-only guards and orchestrator safety. | `pytest tests/test_read_only_guard.py tests/test_orchestrator_shutdown.py` |
| E8 Regime & Microstructure Layer | Validate regime determinism and policy application. | `pytest tests/test_regime_baselines.py tests/test_regime_classifier.py tests/test_regime_policy_application.py tests/test_regime_determinism.py` |
| E9 Performance Analytics | Validate performance registry and reporting. | `pytest tests/test_performance_reports_epoch4.py` |
| E10 Capital Allocation | Validate allocation, arbitration, and portfolio contracts. | `pytest tests/strategy_portfolio/test_allocation.py tests/strategy_portfolio/test_arbitration.py tests/strategy_portfolio/test_contracts.py` |
| E11 Learning System | Validate learning policies, reporting, and storage. | `pytest tests/test_learning_policy_proposal.py tests/test_learning_reporting.py` |
| E12 Recovery & Housekeeping | Validate storage recovery and serialization. | `pytest tests/test_storage_recovery.py tests/test_storage_serialization.py` |
| E13 Strategy Factory Standard | Validate strategy registry compliance. | `pytest tests/test_ross_strategy_registry.py` |
| E14 Decision Artifacts | Validate signal/intent adapters. | `pytest tests/test_signal_adapter.py` |
| E15 Failure Modes | Validate fault handling and stop controller. | `pytest tests/test_faults.py tests/test_stop_controller.py` |
| E16 No-Trade Contexts | Validate read-only/guard rails and no-trade gating. | `pytest tests/test_read_only_guard.py tests/test_ibkr_readonly.py` |
| E17 Strategy Interaction Rules | Validate non-interference and arbitration behavior. | `pytest tests/strategy_portfolio/test_non_interference.py tests/strategy_portfolio/test_end_to_end_smoke.py` |
| E18 Strategy Foundation Layer | Validate strategy base and contracts. | `pytest tests/strategy_portfolio/test_registry.py tests/strategy_portfolio/test_normaliser_defaults.py` |
| E19 Strategy Interface & Certification | Validate strategy contracts and adapters. | `pytest tests/strategy_portfolio/test_contracts.py tests/strategy_portfolio/test_ross_adapter.py` |
| E20 Strategy Foundation Completion | Validate strategy orchestration end-to-end. | `pytest tests/strategy_portfolio/test_end_to_end_smoke.py` |
| E21 Trading Ready Verification & End-to-End Simulation | Validate full-mode parity and run scripts. | `pytest tests/smoke` and `RUN_SIMULATION.ps1` `RUN_PAPER_TRADING.ps1` `RUN_LIVE_READ_ONLY.ps1` |

## Metadata Epoch Verification
| Epoch | Verification Intent | Commands |
| --- | --- | --- |
| M0 Canon & Sources of Truth | Validate read-order compliance and locked rules. | `pytest tests/test_config_sanity.py` |
| M1 Architecture Map | Confirm system tree reports align with codebase. | `python src/directory_tree_report.py` |
| M2 Contract Registry | Ensure contract docs exist and match code contracts. | `pytest tests/test_scanner_contract_54.py tests/strategy_portfolio/test_contracts.py` |
| M3 Mode Semantics Certification | Validate mode safety and read-only guards. | `pytest tests/test_read_only_guard.py tests/test_execution_intent_modes.py` |
| M4 Traceability Semantics | Validate event schemas and trace invariants. | `pytest tests/test_traceability.py` |
| M5 Verification Authority | Ensure verification rules are enforced via config sanity. | `pytest tests/test_config_sanity.py` |
| M6 Data Lifecycle Governance | Validate storage schema and serialization rules. | `pytest tests/test_storage_schema_epoch4.py tests/test_storage_serialization.py` |
| M7 Epoch Audit & Certification | Ensure audit evidence outputs are generated. | `pytest tests/test_storage_cli_epoch4.py` |
| M8 Change Control | Ensure enforcement hooks exist in tooling. | `pytest tests/test_config_sanity.py` |
| M9 Signal Semantics Registry | Validate signal registry contracts. | `pytest tests/test_signal_adapter.py` |
| M10 Data Provenance Ledger | Validate storage schema and persistence. | `pytest tests/test_sqlite_persistence.py` |

## Strategy Verification (Catalogue Context)
- Use strategy-specific tests when available (e.g. Statistical Intraday Momentum):
  - `pytest tests/strategies/statistical_intraday_momentum/test_contract_compliance.py`
  - `pytest tests/strategies/statistical_intraday_momentum/test_intraday_end_to_end_smoke.py`
  - `pytest tests/strategies/statistical_intraday_momentum/test_risk_policy.py`
- For strategies without tests, verification must use the Strategy Interface Contract (E19) and portfolio end-to-end smoke tests.

## Evidence Requirements
- Store command outputs in the relevant epoch audit folder within the catalogue.
- Attach summaries to the certification records in M7.
