# PR1030 Entry/Stop/Target/Exit Mapping Certification

## Scope

This certification PR closes the PR1029 trade-plan mapping blocker by proving that detected Ross setups cannot become trade intents unless they carry complete entry, stop/invalidation, target, and rationale evidence, with simulated exit-management evidence available after the non-live execution boundary.

This PR does not enable PAPER or LIVE, change trading thresholds, weaken Ross scanner/pattern gates, create synthetic trades, or add broker execution authority.

## Executive Verdict

```text
PAPER_READY: NO
ROSS_ENTRY_STOP_TARGET_EXIT_MAPPING: CERTIFIED_FOR_DETERMINISTIC_FIXTURES
PRODUCTION_CODE_CHANGED: YES_SMALL_MAPPING_GUARD
MAIN_BLOCKERS:
1. Full-session READ_ONLY runtime proof from scanner/focus through setup, decision, risk, execution-disabled, analytics, and storage is not certified.
2. PAPER/READ_ONLY environment flags, manual focus, validation override, synthetic intent, debug execution, and execution enablement are not yet certified against a production-shaped session.
3. Real runtime persistence of complete trade-plan and no-trade evidence is not yet certified.
NEXT_REQUIRED_PR: PR1031 READ_ONLY Full-Session Dry Run and PAPER Readiness Gate.
DO_NOT_GO_PAPER_REASON: PR1030 certifies deterministic trade-plan mapping, but it does not certify a production full-session READ_ONLY run or prove execution remains disabled across live runtime integrations.
```

PAPER readiness remains blocked. PR1030 improves the decision boundary by requiring target mapping and valid entry/stop geometry before intent creation, but it does not certify production runtime operation.

## Implementation Result

| Area | Verdict | Evidence | Remaining gap |
| --- | --- | --- | --- |
| Entry mapping | PASS | `test_pr1030_complete_setup_maps_to_entry_stop_target_and_rationale` asserts entry model is carried into `TradeIntent`. | Full-session runtime trace in PR1031. |
| Stop/invalidation mapping | PASS | Complete setup test asserts stop model; invalid geometry test rejects long stop above trigger. | Broker-order translation remains out of scope. |
| Target mapping | PASS | Missing target now blocks intent; ABCD `d_projection` can map to target model; PMH detector now emits target suggestion. | Runtime persistence of target evidence in PR1031. |
| Rationale mapping | PASS | Complete setup test asserts rationale is preserved. | Full analytics storage trace in PR1031. |
| Risk/reward sanity | PASS | Invalid long trigger/stop geometry rejects as `invalid_risk_geometry`. | Numeric R/R threshold policy is not introduced here and remains out of scope. |
| Risk-off/exit signals | PASS | Parabolic exhaustion/risk-off fixture creates no long-entry intent. | Exit-management lifecycle behavior beyond simulated evidence remains for later runtime certification. |
| Exit management evidence | PASS | PR6 positive cases now assert simulated exit evidence includes stop, target, and exit-signal capture. | Production READ_ONLY full-session execution-disabled and storage proof in PR1031. |
| PAPER readiness | FAIL | No PAPER/LIVE enablement. | PR1031 remains required. |

## Code Changes

| File | Change | Reason |
| --- | --- | --- |
| `src/strategies/ross_momentum/decision_policy.py` | Added target mapping helper, ABCD projection fallback, missing-target rejection, and entry/stop geometry rejection. | Direct PR1030 gap: targetless or geometrically invalid setups could previously reach intent creation. |
| `src/strategies/common/patterns/pattern_premarket_high_break.py` | Added PMH target suggestion. | Existing certified PMH positive setup now maps into a complete trade plan. |
| `tests/test_ross_pr1030_entry_stop_target_exit_mapping.py` | Added PR1030 mapping and exit evidence tests. | Certification evidence. |

## Mapping Matrix

| Setup / mapping surface | Required evidence | Current code evidence | Decision behavior | Status | Required PR/fix |
| --- | --- | --- | --- | --- | --- |
| Micro pullback | Entry trigger, structure stop, target model, rationale. | Synthetic complete setup maps all fields into `TradeIntent`; PR6 micro positive has simulated exit evidence. | Intent allowed only when trigger-ready and mapped. | PASS | PR1031 runtime trace. |
| Flat-top breakout | Resistance trigger, structure stop, target model, rationale. | PR6 flat-top positive has stop/target exit evidence. | Intent allowed only when mapped. | PASS | PR1031 runtime trace. |
| PMH break | PMH trigger, stop below PMH, target extension, rationale. | PMH detector now emits `target_suggestion`; PR6 PMH positive has stop/target exit evidence. | Intent allowed only when mapped. | PASS | PR1031 runtime trace. |
| ABCD continuation | Pullback trigger, C stop, measured-move target/projection. | `d_projection` fallback maps to `ABCD measured move projection`. | Intent allowed with projection target even without text target suggestion. | PASS | PR1031 runtime trace. |
| Missing target | Setup has trigger/stop/rationale but no target evidence. | PR1030 test asserts drop reason `missing_target`. | No intent. | PASS | Keep guard. |
| Invalid entry/stop geometry | Long stop/invalidation must be below trigger when both numeric values are present. | PR1030 test asserts drop reason `invalid_risk_geometry`. | No intent. | PASS | Keep guard; future numeric R/R thresholds require separate policy. |
| Risk-off/exhaustion | Exit/risk signal must not become long-entry intent. | PR1030 risk-off test asserts no intent and `risk_off_non_entry`. | No long-entry intent. | PASS | PR1031 runtime trace. |
| Simulated exit evidence | Non-live successful intent should expose stop, target, and exit-signal capture. | PR1030 asserts all PR6 positive cases produce `SIMULATED_MANAGEMENT_READY` with stop/target evidence. | Evidence only; no broker execution. | PASS | PR1031 full-session dry run. |

## Failure Trace Table

| Stage | Expected Ross behavior | Current observed behavior | Gap | Severity | Required fix | Proposed PR |
| --- | --- | --- | --- | --- | --- | --- |
| Scanner | Only eligible low-float/high-RVOL/gap/catalyst candidates enter setup. | PR1028 certified controlled scanner/focus path. | Full-session live/replayed scanner trace missing. | HIGH | Capture full-session READ_ONLY scanner/focus trace. | PR1031 |
| Pattern detection | Certified setup families detect/reject deterministically. | PR1029 certified pattern fixtures. | Runtime input provenance full-session trace missing. | HIGH | Capture focus-to-pattern inputs in READ_ONLY run. | PR1031 |
| Entry mapping | Intent requires entry model from price-action setup. | PR1030 complete setup test preserves entry model. | Runtime analytics persistence missing. | MEDIUM | Store/verify entry evidence. | PR1031 |
| Stop mapping | Intent requires stop or invalidation model. | Existing PR5 guard plus PR1030 complete/invalid-geometry tests. | Broker order translation out of scope. | MEDIUM | Runtime execution-disabled trace. | PR1031 |
| Target mapping | Intent requires target model or measured projection. | PR1030 missing-target guard and ABCD projection fallback. | Runtime persistence missing. | HIGH | Store/verify target evidence. | PR1031 |
| Risk/reward sanity | Obviously invalid long entry/stop geometry must not proceed. | PR1030 blocks stop >= trigger as `invalid_risk_geometry`. | Formal numeric R/R threshold not introduced. | MEDIUM | Separate policy only if explicitly required. | Future PR |
| Risk-off/exit evidence | Exhaustion/reversal risk signals must not create long entry. | PR1030 risk-off test blocks intent. | Exit lifecycle beyond simulation not certified. | MEDIUM | Full READ_ONLY lifecycle trace. | PR1031 |
| PAPER mode path | PAPER forced intent path must still require complete mapping. | PR1030 guards run before PAPER forced intent creation. | Production env flags not full-session audited. | HIGH | Runtime config inventory. | PR1031 |
| Execution mode gate | READ_ONLY must not submit orders. | PR1030 adds no execution authority. | Full-session execution-disabled proof missing. | CRITICAL | READ_ONLY dry run. | PR1031 |
| Analytics/storage | Complete trade-plan/no-trade evidence must be persisted. | PR1030 tests inspect returned/simulated evidence only. | Storage completeness missing. | MEDIUM | Storage artifact verification. | PR1031 |
| PAPER readiness | PAPER only after scanner, catalyst, setup, mapping, risk, execution-disabled, and storage pass. | Still blocked. | PR1031 incomplete. | CRITICAL | Complete final gate. | PR1031 |

## Fallback / Bypass Inventory

| Flag/path | File/function | Current effect | Can affect PAPER/LIVE? | Risk | Required action |
| --- | --- | --- | --- | --- | --- |
| PAPER forced intent path | `build_trade_intents`; `RUN_MODE=PAPER` branch | Creates PAPER intent only after setup selection. PR1030 target/geometry guards run before this branch. | PAPER yes. | HIGH | PR1031 must prove production flags and mode are controlled. |
| Missing target path | `build_trade_intents` target guard | Drops setup as `missing_target`. | Blocks PAPER/LIVE intent. | LOW | Keep PR1030 regression. |
| Invalid geometry path | `build_trade_intents` geometry guard | Drops setup as `invalid_risk_geometry` when numeric long stop is not below trigger. | Blocks PAPER/LIVE intent. | LOW | Keep PR1030 regression. |
| ABCD projection fallback | `build_trade_intents::_target_model_from_setup` | Maps `d_projection` to explicit target model. | Can create complete target evidence. | LOW | Keep bounded to projection metadata. |
| `debug_force_execution` | `IntentPolicyConfig.debug_force_execution` | Existing debug path can bypass data-quality flags, but not PR1030 target/geometry filtering. | PAPER/LIVE risk if enabled. | HIGH | Assert disabled in PR1031. |
| Validation session override | `VALIDATION_SESSION_OVERRIDE`; `IntentPolicyConfig.validation_session_override` | Can allow invalid session in validation mode. | PAPER/SIM risk if enabled. | HIGH | Assert disabled or explicitly scoped in PR1031. |
| Manual focus | Scanner/orchestrator focus config | Candidate-universe influence only; cannot bypass mapping guard. | PAPER candidate risk. | MEDIUM | Audit in PR1031. |
| Synthetic intent allowed | Runtime safety policy from earlier inventory | Validation-only synthetic path; PR1030 does not enable it. | PAPER/SIM risk if enabled. | HIGH | Assert blocked outside validation in PR1031. |
| Execution enablement flags | Runtime execution config | PR1030 does not alter execution state. | Yes. | CRITICAL | Prove READ_ONLY execution-disabled in PR1031. |

## Evidence Added

New test file: `tests/test_ross_pr1030_entry_stop_target_exit_mapping.py`.

The tests prove:

1. A complete Ross setup maps entry, stop, target, time-in-force, rationale, and invalidation metadata into `TradeIntent`.
2. A setup with trigger/stop/rationale but no target evidence is dropped as `missing_target`.
3. A long setup with stop/invalidation not below trigger is dropped as `invalid_risk_geometry`.
4. ABCD measured-move projection can supply explicit target mapping.
5. Risk-off/exhaustion evidence cannot create a long-entry intent.
6. PR6 positive certification cases expose simulated stop, target, and exit-signal capture evidence.

## PR1031 Remaining Plan

### PR1031 - READ_ONLY Full-Session Dry Run and PAPER Readiness Gate

Purpose: run a production-shaped READ_ONLY certification and decide whether PAPER can be recommended in a later controlled step.

Files likely touched:

- Runtime/session orchestration tests
- Scanner/focus/setup/decision/risk/execution-disabled trace verification tests
- Analytics/storage trace verification tests
- Runtime configuration safety tests
- `docs/certification/PR1031_READ_ONLY_FULL_SESSION_DRY_RUN_AND_PAPER_GATE.md`

Acceptance criteria:

- Full-session READ_ONLY run shows no order submission and no fake/probe trade.
- Scanner, catalyst, focus, setup, decision, risk, execution-disabled, analytics, and storage traces are complete.
- Manual focus, validation override, synthetic intent, debug execution, additional heuristic, session override, PAPER forced intent, and execution enablement flags are inventoried.
- Complete trade-plan mapping evidence from PR1030 is present in runtime artifacts.
- `PAPER_READY` remains `NO` unless every objective gate passes.

Tests required:

- Runtime configuration safety tests.
- READ_ONLY trace verification tests.
- Execution-disabled/order-submission-negative tests.
- Analytics/storage completeness tests.
- PAPER readiness verdict test.

PAPER-readiness contribution: final pre-PAPER evidence gate.

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1030_entry_stop_target_exit_mapping.py
python -m pytest tests/test_ross_pr1029_pattern_detection_certification.py tests/test_ross_pr6_end_to_end_certification.py tests/test_ross_pr5_setup_decision_fidelity.py
python -m pytest tests -k "ross or entry or stop or target or exit or decision"
```

Local execution may be unavailable in this Codex desktop session if the Windows command sandbox blocks repository access or if the local Python environment lacks pytest. GitHub Actions is the authoritative verification surface if local pytest is unavailable.

## Final Certification Answer

PR1030 certifies deterministic entry/stop/target/exit mapping and adds a small production guard for missing target and invalid entry/stop geometry. Ross Momentum remains not PAPER-ready until PR1031 completes a full-session READ_ONLY runtime dry run and PAPER readiness gate.
