# Pytest Failure Analysis — 2026-03-19

Baseline command: `pytest -q`

Initial result: **25 failed, 381 passed**.
Final result after remediation: see `pytest_final_output.txt` (**406 passed**).

## Failure inventory

| Test name | File | Failure type | Root cause hypothesis | Classification |
|---|---|---|---|---|
| `test_orchestrator_readonly_cycle` | `tests/smoke/test_orchestrator_cycle.py` | runtime | READ_ONLY scanner/orchestrator paths attempted a real IBKR handshake; connection failures escaped as fatal runtime instead of degrading cleanly. | `REGRESSION_FROM_PR_456` |
| `test_scanner_contract_prints_lists` | `tests/smoke/test_scanner_contract.py` | runtime | Derived config logic overwrote explicit `SCANNER_DATA_SOURCE=MOCK`, so smoke tests incorrectly instantiated the live IBKR provider. | `REGRESSION_FROM_PR_456` |
| `test_manager_reuses_single_connected_client` | `tests/test_ibkr_connection_manager_unification.py` | runtime | `IbkrConnectionConfig` added required `run_mode` without backward-compatible default, breaking existing constructor contract. | `REGRESSION_FROM_PR_456` |
| `test_manager_retries_deterministic_client_ids_and_keeps_config` | `tests/test_ibkr_connection_manager_unification.py` | runtime | Same `IbkrConnectionConfig` backward-compatibility break as above. | `REGRESSION_FROM_PR_456` |
| `test_manager_heartbeat_reconnects_when_connection_lost` | `tests/test_ibkr_connection_manager_unification.py` | runtime | Same `IbkrConnectionConfig` backward-compatibility break as above. | `REGRESSION_FROM_PR_456` |
| `test_manager_heartbeat_no_reconnect_when_healthy` | `tests/test_ibkr_connection_manager_unification.py` | runtime | Same `IbkrConnectionConfig` backward-compatibility break as above. | `REGRESSION_FROM_PR_456` |
| `test_reconnect_preserves_immutable_config` | `tests/test_ibkr_connection_manager_unification.py` | runtime | Same `IbkrConnectionConfig` backward-compatibility break as above. | `REGRESSION_FROM_PR_456` |
| `test_shutdown_prevents_reconnect` | `tests/test_ibkr_connection_manager_unification.py` | runtime | Same `IbkrConnectionConfig` backward-compatibility break as above. | `REGRESSION_FROM_PR_456` |
| `test_metadata_exposes_reconnect_and_disconnect_fields` | `tests/test_ibkr_connection_manager_unification.py` | runtime | Same `IbkrConnectionConfig` backward-compatibility break as above. | `REGRESSION_FROM_PR_456` |
| `test_connection_config_is_immutable_dataclass` | `tests/test_ibkr_connection_resilience.py` | runtime | Same `IbkrConnectionConfig` backward-compatibility break as above. | `REGRESSION_FROM_PR_456` |
| `test_live_intent_not_blocked_for_nonblocking_data_quality_flags` | `tests/test_risk_data_quality_alignment.py` | assertion | Test assumed a tradable LIVE session, but wall-clock session gating could block it overnight/weekend; failure was time-dependent rather than caused by PR #456 logic. Stabilized by making the session allowance explicit in the test. | `FLAKY / NON-DETERMINISTIC` |
| `test_env_overrides_runtime_thresholds_take_precedence` | `tests/test_ross_live_focus_runtime_tuning.py` | assertion | Runtime threshold resolution treated default `ROSS_RVOL_MIN` / `ALLOW_UNKNOWN_FLOAT` values as if they were explicit overrides, masking real override provenance. | `REGRESSION_FROM_PR_456` |
| `test_pre_missing_rvol_without_strong_anchor_is_rejected` | `tests/test_scanner_pct_change_fallback.py` | assertion | PRE-session gate ordering returned `DROP_PCT_CHANGE` before surfacing the expected missing-RVOL rejection on weak anchors. | `REGRESSION_FROM_PR_456` |
| `test_scanner_policy_limits_applied_in_teaching_mode` | `tests/test_scanner_policy_from_strategy.py` | runtime | Explicit mock/provider override was lost, so policy tests fell into live IBKR connectivity instead of deterministic mock data. | `REGRESSION_FROM_PR_456` |
| `test_scanner_keeps_top_k_and_drops_only_below_watchlist_rank` | `tests/test_scanner_policy_from_strategy.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_scanner_uses_strategy_ranking_for_ross` | `tests/test_scanner_ranking_authority.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_scanner_request_ibkr_top_gainers_skips_scanner_symbols_error` | `tests/test_scanner_universe_request.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_watchlist_print_format` | `tests/test_scanner_watchlist_prints.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_watchlist_print_suppressed_when_unchanged` | `tests/test_scanner_watchlist_prints.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_focus_print_rows_match_focus_symbols_order` | `tests/test_scanner_watchlist_prints.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_watchlist_keeps_all_gated_survivors_when_survivors_leq_k` | `tests/test_scanner_watchlist_restore_prep.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_overnight_prep_builds_watchlist_even_when_execution_disabled` | `tests/test_scanner_watchlist_restore_prep.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_weekend_closed_prep_builds_watchlist_with_valid_survivors` | `tests/test_scanner_watchlist_restore_prep.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_strict_policy_watchlist_stays_bounded_in_prep_mode` | `tests/test_scanner_watchlist_restore_prep.py` | runtime | Same explicit mock/provider override regression as above. | `REGRESSION_FROM_PR_456` |
| `test_live_readonly_connectivity_retry` | `tests/test_traceability.py` | runtime | READ_ONLY connectivity failures bubbled as fatal `SystemExit` from the IBKR connection manager, bypassing orchestrator degraded-mode handling and the traceability retry path. | `REGRESSION_FROM_PR_456` |

## Classification summary

- `REGRESSION_FROM_PR_456`: 24
- `FLAKY / NON-DETERMINISTIC`: 1
- `PRE_EXISTING_FAILURE`: 0
- `MISALIGNED_TEST`: 0

## Remediation summary

- Restored explicit config authority so `SCANNER_DATA_SOURCE=MOCK` and runtime gate overrides are honored before derived defaults.
- Restored backward compatibility for `IbkrConnectionConfig` by providing a default `run_mode`.
- Converted non-LIVE IBKR connection failures from fatal `SystemExit` escapes into regular runtime errors so degraded-mode handling can classify them correctly.
- Prioritized PRE-session missing-RVOL rejection ahead of weaker pct-change failures when the anchor is insufficient.
- Stabilized the LIVE data-quality test by explicitly allowing all sessions, removing wall-clock dependence.
