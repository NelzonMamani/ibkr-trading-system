# PR1030 Entry/Stop/Target/Exit Mapping Certification

## Scope

This certification PR closes part of the PR1029 trade-plan mapping blocker by proving that detected Ross setups cannot become trade intents unless they carry entry, stop/invalidation, target-model, and rationale evidence. It also proves limited deterministic guards for missing target evidence and obviously invalid long entry/stop geometry, and confirms simulated non-live exit evidence remains visible in the PR6 positive cases.

This PR does not certify numeric target price geometry for every setup, reward/risk calculation, minimum R:R policy, partial-profit scaling, sell-half behavior, breakeven stop movement, trailing-stop lifecycle handoff, real lifecycle execution/management behavior, or runtime storage persistence of complete trade-plan metadata.

This PR does not enable PAPER or LIVE, change trading thresholds, weaken Ross scanner/pattern gates, create synthetic trades, or add broker execution authority.

## Executive Verdict

```text
PAPER_READY: NO
ROSS_ENTRY_STOP_TARGET_EXIT_MAPPING: PARTIAL
ENTRY_MAPPING_CERTIFIED: YES
STOP_MAPPING_CERTIFIED: YES
TARGET_MODEL_PRESENCE_CERTIFIED: YES
NUMERIC_TARGET_GEOMETRY_CERTIFIED: PARTIAL
REWARD_RISK_CERTIFIED: PARTIAL
PARTIAL_EXIT_MAPPING_CERTIFIED: NO
TRAILING_BREAKEVEN_MAPPING_CERTIFIED: NO
RISK_GATE_BOUNDARY_CERTIFIED: PARTIAL
LIFECYCLE_HANDOFF_CERTIFIED: PARTIAL
PRODUCTION_CODE_CHANGED: YES_SMALL_MAPPING_GUARD
MAIN_BLOCKERS:
1. Numeric target price geometry and target-above-entry proof are not certified for every long setup.
2. Reward/risk calculation and minimum R:R enforcement are not certified.
3. Partial exits, sell-half behavior, breakeven movement, and trailing-stop lifecycle handoff are not certified.
4. Full-session READ_ONLY runtime proof from scanner/focus through setup, decision, risk, execution-disabled, analytics, and storage is not certified.
NEXT_REQUIRED_PR: PR1031 READ_ONLY Full-Session Dry Run and PAPER Readiness Gate.
DO_NOT_GO_PAPER_REASON: PR1030 adds stricter deterministic mapping guards, but numeric R:R, partial/trailing/breakeven lifecycle behavior, full runtime storage, and READ_ONLY execution-disabled session proof are not certified.
```

PAPER readiness remains blocked. PR1030 improves the decision boundary by requiring target-model presence and valid long entry/stop geometry before intent creation, but it does not certify full target math, R:R policy, production lifecycle management, or production runtime operation.

## Implementation Result

| Area | Verdict | Evidence | Remaining gap |
| --- | --- | --- | --- |
| Entry mapping | PASS | `test_pr1030_complete_setup_maps_to_entry_stop_target_and_rationale` asserts entry model is carried into `TradeIntent`. | Full-session runtime trace in PR1031. |
| Stop/invalidation mapping | PASS | Complete setup test asserts stop model; invalid geometry test rejects long stop above trigger. | Broker-order translation and lifecycle stop movement remain out of scope. |
| Target model presence | PASS | Missing target now blocks intent; ABCD `d_projection` can map to target model; flat-top and PMH detectors now emit target suggestions. | Numeric target price geometry and persistence of target evidence remain incomplete. |
| Numeric target geometry | PARTIAL | ABCD projection fallback proves one deterministic target-model source; PR6 simulated evidence includes target capture. | Does not prove numeric target price for every setup or target above entry for every long setup. |
| Rationale mapping | PASS | Complete setup test asserts rationale is preserved. | Full analytics storage trace in PR1031. |
| Risk/reward sanity | PARTIAL | Invalid long trigger/stop geometry rejects as `invalid_risk_geometry`. | Reward/risk computation, minimum R:R policy, and target/stop distance validation are not certified. |
| Risk gate boundary | PARTIAL | Obvious invalid long stop geometry is blocked before intent creation. | Broader boundary coverage and runtime risk-gate proof remain for PR1031 or later policy PR. |
| Risk-off/exit signals | PASS | Parabolic exhaustion/risk-off fixture creates no long-entry intent. | Exit-management lifecycle behavior beyond non-entry classification remains uncertified. |
| Exit management evidence | PARTIAL | PR6 positive cases assert simulated exit evidence includes stop, target, and exit-signal capture. | Evidence is simulated/non-live; production lifecycle execution/management is not certified. |
| Partial exit mapping | NO | No PR1030 test proves sell-half, scaling, or partial profit behavior. | Requires explicit lifecycle mapping evidence in later certification. |
| Trailing/breakeven mapping | NO | No PR1030 test proves breakeven movement or trailing-stop handoff. | Requires explicit lifecycle management evidence in later certification. |
| Lifecycle handoff | PARTIAL | Intent metadata and simulated management evidence are inspectable in deterministic tests. | Real runtime handoff, persistence, and execution-disabled session proof remain for PR1031. |
| PAPER readiness | FAIL | No PAPER/LIVE enablement. | PR1031 remains required. |

## Code Changes

| File | Change | Reason |
| --- | --- | --- |
| `src/strategies/ross_momentum/decision_policy.py` | Added target mapping helper, ABCD projection fallback, missing-target rejection, and entry/stop geometry rejection. | Direct PR1030 gap: targetless or geometrically invalid setups could previously reach intent creation. |
| `src/strategies/common/patterns/pattern_flat_top_breakout.py` | Added flat-top target suggestion. | CI exposed that the certified flat-top positive path was targetless under the new PR1030 mapping guard. |
| `src/strategies/common/patterns/pattern_premarket_high_break.py` | Added PMH target suggestion. | Existing certified PMH positive setup now maps into a target-model-bearing trade plan. |
| `tests/test_ross_pr1030_entry_stop_target_exit_mapping.py` | Added PR1030 mapping and simulated exit evidence tests. | Certification evidence for deterministic mapping guards and target-model presence. |

## Mapping Matrix

| Setup / mapping surface | Required evidence | Current code evidence | Decision behavior | Status | Required PR/fix |
| --- | --- | --- | --- | --- | --- |
| Micro pullback | Entry trigger, structure stop, target model, rationale. | Synthetic complete setup maps all fields into `TradeIntent`; PR6 micro positive has simulated exit evidence. | Intent allowed only when trigger-ready and mapped. | PASS | PR1031 runtime trace; later numeric target/R:R certification if required. |
| Flat-top breakout | Resistance trigger, structure stop, target model, rationale. | Flat-top detector now emits `target_suggestion`; PR6 flat-top positive has simulated stop/target exit evidence. | Intent allowed only when mapped. | PASS | PR1031 runtime trace; later numeric target/R:R certification if required. |
| PMH break | PMH trigger, stop below PMH, target model, rationale. | PMH detector now emits `target_suggestion`; PR6 PMH positive has simulated stop/target exit evidence. | Intent allowed only when mapped. | PASS | PR1031 runtime trace; later numeric target/R:R certification if required. |
| ABCD continuation | Pullback trigger, C stop, measured-move projection text. | `d_projection` fallback maps to `ABCD measured move projection`. | Intent allowed with projection target model even without text target suggestion. | PASS | PR1031 runtime trace; numeric target geometry remains partial. |
| Target model presence | Setup must expose target evidence before intent creation. | PR1030 target helper returns explicit `target_suggestion` or ABCD projection text. | No target model means no intent. | PASS | Keep guard. |
| Numeric target price geometry | Numeric target should be present and correctly placed relative to entry/stop for each setup. | PR1030 does not prove numeric target price for every setup. | Not fully enforced by this PR. | PARTIAL | Future numeric target/R:R certification PR if required. |
| Missing target | Setup has trigger/stop/rationale but no target evidence. | PR1030 test asserts drop reason `missing_target`. | No intent. | PASS | Keep guard. |
| Invalid entry/stop geometry | Long stop/invalidation must be below trigger when both numeric values are present. | PR1030 test asserts drop reason `invalid_risk_geometry`. | No intent. | PASS | Keep guard; future numeric R/R thresholds require separate policy. |
| Reward/risk validation | Reward/risk should be computed and checked against a policy threshold before trade readiness. | PR1030 only blocks obvious invalid long stop geometry. | No minimum R:R certification. | PARTIAL | Future policy/certification PR if required. |
| Partial exit mapping | Trade plan should define sell-half/scaling behavior if required by Ross lifecycle. | No PR1030 test proves partial exit mapping. | Not certified. | NO | Later lifecycle certification. |
| Breakeven/trailing mapping | Trade plan should define breakeven movement and trailing handoff if required. | No PR1030 test proves breakeven or trailing behavior. | Not certified. | NO | Later lifecycle certification. |
| Risk-off/exhaustion | Exit/risk signal must not become long-entry intent. | PR1030 risk-off test asserts no intent and `risk_off_non_entry`. | No long-entry intent. | PASS | PR1031 runtime trace. |
| Simulated exit evidence | Non-live successful intent should expose stop, target, and exit-signal capture. | PR1030 asserts all PR6 positive cases produce `SIMULATED_MANAGEMENT_READY` with stop/target evidence. | Evidence only; no broker execution or real lifecycle management. | PARTIAL | PR1031 full-session dry run and storage proof. |
| Lifecycle handoff | Runtime must carry complete plan metadata into disabled execution, analytics, and storage. | PR1030 inspects deterministic return/simulated evidence only. | Runtime handoff not fully certified. | PARTIAL | PR1031 READ_ONLY full-session certification. |

## Failure Trace Table

| Stage | Expected Ross behavior | Current observed behavior | Gap | Severity | Required fix | Proposed PR |
| --- | --- | --- | --- | --- | --- | --- |
| Scanner | Only eligible low-float/high-RVOL/gap/catalyst candidates enter setup. | PR1028 certified controlled scanner/focus path. | Full-session live/replayed scanner trace missing. | HIGH | Capture full-session READ_ONLY scanner/focus trace. | PR1031 |
| Pattern detection | Certified setup families detect/reject deterministically. | PR1029 certified pattern fixtures. | Runtime input provenance full-session trace missing. | HIGH | Capture focus-to-pattern inputs in READ_ONLY run. | PR1031 |
| Entry mapping | Intent requires entry model from price-action setup. | PR1030 complete setup test preserves entry model. | Runtime analytics persistence missing. | MEDIUM | Store/verify entry evidence. | PR1031 |
| Stop mapping | Intent requires stop or invalidation model. | Existing PR5 guard plus PR1030 complete/invalid-geometry tests. | Broker order translation and lifecycle stop movement out of scope. | MEDIUM | Runtime execution-disabled trace. | PR1031 |
| Target model mapping | Intent requires target model or measured projection text. | PR1030 missing-target guard, ABCD projection fallback, and detector target additions. | Numeric target price and target-above-entry proof are incomplete. | HIGH | Certify numeric target geometry if required. | Future PR |
| Risk/reward sanity | Invalid geometry must not proceed and R:R should be computable before readiness. | PR1030 blocks stop >= trigger as `invalid_risk_geometry`. | Formal numeric R/R computation and minimum threshold are not certified. | HIGH | Add explicit R:R policy/certification if required. | Future PR |
| Partial exits | Trade plan should support Ross-style partial profit management if required. | No PR1030 evidence for sell-half or scaling. | Not certified. | MEDIUM | Add lifecycle mapping tests. | Future PR |
| Breakeven/trailing | Stop management should support breakeven/trailing handoff if required. | No PR1030 evidence for breakeven movement or trailing handoff. | Not certified. | MEDIUM | Add lifecycle mapping tests. | Future PR |
| Risk-off/exit evidence | Exhaustion/reversal risk signals must not create long entry. | PR1030 risk-off test blocks intent. | Exit lifecycle beyond simulation not certified. | MEDIUM | Full READ_ONLY lifecycle trace. | PR1031 |
| PAPER mode path | PAPER forced intent path must still require complete target-model and geometry guards. | PR1030 guards run before PAPER forced intent creation. | Production env flags not full-session audited. | HIGH | Runtime config inventory. | PR1031 |
| Execution mode gate | READ_ONLY must not submit orders. | PR1030 adds no execution authority. | Full-session execution-disabled proof missing. | CRITICAL | READ_ONLY dry run. | PR1031 |
| Analytics/storage | Complete trade-plan/no-trade evidence must be persisted. | PR1030 tests inspect returned/simulated evidence only. | Storage completeness missing. | MEDIUM | Storage artifact verification. | PR1031 |
| PAPER readiness | PAPER only after scanner, catalyst, setup, mapping, risk, execution-disabled, and storage pass. | Still blocked. | PR1031 incomplete; numeric R:R and lifecycle proof also not certified by PR1030. | CRITICAL | Complete final gate and keep `PAPER_READY: NO` unless every objective gate passes. | PR1031 |

## Fallback / Bypass Inventory

| Flag/path | File/function | Current effect | Can affect PAPER/LIVE? | Risk | Required action |
| --- | --- | --- | --- | --- | --- |
| PAPER forced intent path | `build_trade_intents`; `RUN_MODE=PAPER` branch | Creates PAPER intent only after setup selection. PR1030 target/geometry guards run before this branch. | PAPER yes. | HIGH | PR1031 must prove production flags and mode are controlled. |
| Missing target path | `build_trade_intents` target guard | Drops setup as `missing_target`. | Blocks PAPER/LIVE intent. | LOW | Keep PR1030 regression. |
| Invalid geometry path | `build_trade_intents` geometry guard | Drops setup as `invalid_risk_geometry` when numeric long stop is not below trigger. | Blocks PAPER/LIVE intent. | LOW | Keep PR1030 regression. |
| ABCD projection fallback | `build_trade_intents::_target_model_from_setup` | Maps `d_projection` to explicit target model text. | Can create target-model presence evidence. | LOW | Keep bounded to projection metadata; do not treat as full numeric R:R proof. |
| `debug_force_execution` | `IntentPolicyConfig.debug_force_execution` | Existing debug path can bypass data-quality flags, but not PR1030 target/geometry filtering. | PAPER/LIVE risk if enabled. | HIGH | Assert disabled in PR1031. |
| Validation session override | `VALIDATION_SESSION_OVERRIDE`; `IntentPolicyConfig.validation_session_override` | Can allow invalid session in validation mode. | PAPER/SIM risk if enabled. | HIGH | Assert disabled or explicitly scoped in PR1031. |
| Manual focus | Scanner/orchestrator focus config | Candidate-universe influence only; cannot bypass mapping guard. | PAPER candidate risk. | MEDIUM | Audit in PR1031. |
| Synthetic intent allowed | Runtime safety policy from earlier inventory | Validation-only synthetic path; PR1030 does not enable it. | PAPER/SIM risk if enabled. | HIGH | Assert blocked outside validation in PR1031. |
| Execution enablement flags | Runtime execution config | PR1030 does not alter execution state. | Yes. | CRITICAL | Prove READ_ONLY execution-disabled in PR1031. |

## Evidence Added

New test file: `tests/test_ross_pr1030_entry_stop_target_exit_mapping.py`.

The tests prove:

1. A complete Ross setup maps entry model, stop model, target model text, time-in-force, rationale, and invalidation metadata into `TradeIntent`.
2. A setup with trigger/stop/rationale but no target evidence is dropped as `missing_target`.
3. A long setup with stop/invalidation not below trigger is dropped as `invalid_risk_geometry`.
4. ABCD measured-move projection can supply explicit target-model mapping.
5. Risk-off/exhaustion evidence cannot create a long-entry intent.
6. PR6 positive certification cases expose simulated stop, target, and exit-signal capture evidence.

The tests do not prove:

1. Numeric target price for every setup.
2. Target above entry for every long setup.
3. Reward/risk ratio computation for every setup.
4. Minimum R:R policy enforcement.
5. Partial profit scaling, sell-half behavior, breakeven stop movement, or trailing stop lifecycle handoff.
6. Real lifecycle execution/management behavior.
7. Runtime storage persistence of complete trade-plan metadata.

CI follow-up note: the first PR1030 Actions run exposed the certified flat-top positive path as targetless under the new mapping guard. The flat-top detector now emits deterministic target-model evidence, preserving the stricter guard rather than relaxing it.

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
- Complete trade-plan mapping evidence from PR1030 is present in runtime artifacts, without overclaiming numeric R:R or lifecycle behavior that is not proven.
- `PAPER_READY` remains `NO` unless every objective gate passes.

Tests required:

- Runtime configuration safety tests.
- READ_ONLY trace verification tests.
- Execution-disabled/order-submission-negative tests.
- Analytics/storage completeness tests.
- PAPER readiness verdict test.
- Optional later tests for numeric target geometry, R:R computation, partial exits, breakeven movement, and trailing lifecycle handoff if those are required before PAPER.

PAPER-readiness contribution: final pre-PAPER evidence gate, still requiring no overclaim beyond observed runtime proof.

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1030_entry_stop_target_exit_mapping.py
python -m pytest tests/test_ross_pr1029_pattern_detection_certification.py tests/test_ross_pr6_end_to_end_certification.py tests/test_ross_pr5_setup_decision_fidelity.py
```

Local execution may be unavailable in this Codex desktop session if the Windows command sandbox blocks repository access or if the local Python environment lacks pytest. GitHub Actions is the authoritative verification surface if local pytest is unavailable.

## Final Certification Answer

PR1030 partially certifies deterministic entry/stop/target-model mapping and adds small production guards for missing target evidence and invalid long entry/stop geometry. It does not certify numeric target geometry, reward/risk policy, partial exits, breakeven/trailing lifecycle behavior, real production lifecycle management, or full runtime storage persistence. Ross Momentum remains not PAPER-ready until PR1031 completes a full-session READ_ONLY runtime dry run and PAPER readiness gate, with any remaining numeric R:R or lifecycle proof handled explicitly rather than implied.
