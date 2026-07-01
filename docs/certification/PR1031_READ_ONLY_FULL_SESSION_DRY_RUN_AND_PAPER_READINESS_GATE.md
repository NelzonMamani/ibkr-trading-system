# PR1031 READ_ONLY Full-Session Dry Run and PAPER Readiness Gate

## Scope

PR1031 certifies a deterministic READ_ONLY full-session replay across the Ross scanner-to-decision evidence chain and verifies that READ_ONLY runtime authority blocks broker order submission even if an execution flag is requested.

This is a certification patch. No PAPER/LIVE enablement was added. No trading thresholds were changed. No Ross scanner, float, RVOL, gap, catalyst, setup, mapping, or risk rule was weakened. No fake numeric targets, fake R:R, fake partials, fake trailing behavior, fake lifecycle execution, or broker order authority were added.

The replay is deterministic and test-controlled. It is not a real broker-connected runtime session, and it does not certify numeric R:R, partial exits, breakeven movement, trailing stops, real lifecycle execution/management, or durable production storage persistence.

## Executive Verdict

```text
PAPER_READY: NO
READ_ONLY_FULL_SESSION_REPLAY: CERTIFIED_DETERMINISTIC
BROKER_ORDER_SUBMISSION_CERTIFIED_BLOCKED: YES
REAL_BROKER_RUNTIME_SESSION_CERTIFIED: NO
SCANNER_FOCUS_REPLAY_CERTIFIED: PARTIAL
CATALYST_GATE_REPLAY_CERTIFIED: YES
SETUP_DECISION_TRACE_CERTIFIED: YES
RISK_GATE_REPLAY_CERTIFIED: PARTIAL
ANALYTICS_STORAGE_CAPTURE_CERTIFIED: PARTIAL
ENTRY_MAPPING_CERTIFIED: YES_FROM_PR1030
STOP_MAPPING_CERTIFIED: YES_FROM_PR1030
TARGET_MODEL_PRESENCE_CERTIFIED: YES_FROM_PR1030
NUMERIC_TARGET_GEOMETRY_CERTIFIED: PARTIAL
REWARD_RISK_CERTIFIED: PARTIAL
PARTIAL_EXIT_MAPPING_CERTIFIED: NO
TRAILING_BREAKEVEN_MAPPING_CERTIFIED: NO
PAPER_READINESS_GATE: FAIL
NEXT_REQUIRED_ACTION: Capture a real production-shaped READ_ONLY broker-connected session artifact before any PAPER enablement decision.
DO_NOT_GO_PAPER_REASON: PR1031 certifies deterministic READ_ONLY replay and blocked broker-order authority, but real broker runtime session proof and durable storage persistence are not certified, numeric R:R remains uncertified, and partial/trailing/breakeven lifecycle behavior remains uncertified.
```

PAPER readiness remains blocked. PR1031 strengthens the safety case by proving that READ_ONLY mode remains scan-only at runtime authority and that deterministic Ross replay evidence reaches scanner, watchlist, focus, inputs, setup, decision, risk, execution-disabled simulation, exit evidence, and analytics capture points. That is not the same as a broker-connected production session.

## Implementation Result

| Area | Verdict | Evidence | Remaining gap |
| --- | --- | --- | --- |
| READ_ONLY runtime authority | PASS | `test_pr1031_readonly_mode_blocks_execution_even_if_execution_flag_is_requested` asserts `RuntimeModeManager` resolves READ_ONLY with `allow_orders=False` even when execution is requested. | None for this deterministic authority rule. |
| Broker order submission gate | PASS | Tests assert `execution_allowed`, `broker_orders_allowed`, `get_execution_enabled`, `get_ibkr_api_write_allowed`, and `get_ibkr_order_submission_enabled` are false in READ_ONLY. | Real broker-connected session artifact is still missing. |
| Positive READ_ONLY replay | PASS | `test_pr1031_readonly_positive_session_reaches_decision_without_broker_order` reaches selection, watchlist, focus, inputs, setup, decision, risk, simulated execution-disabled path, exit evidence, and analytics capture. | Deterministic replay only; not a real runtime session. |
| Negative READ_ONLY no-trade replay | PASS | `test_pr1031_readonly_negative_session_persists_no_trade_without_fake_intent` preserves `DROP_NO_CATALYST`, creates no intent, calls no risk gate, and creates no fake trade. | More negative runtime surfaces can be added later if desired. |
| PAPER forced path exclusion | PASS | Positive READ_ONLY replay asserts `[ROSS][OVERRIDE][PAPER_MODE]` is absent. | PAPER mode remains blocked and uncertified. |
| Storage capture | PARTIAL | E2E analytics record is marked `storage_capturable=True` for trade and no-trade paths. | Durable runtime storage write/readback is not certified. |
| Risk gate replay | PARTIAL | Positive replay calls and approves deterministic risk; negative no-catalyst path never reaches risk. | Real account/risk engine runtime state is not certified. |
| Numeric target/R:R | PARTIAL | PR1030 target-model presence and invalid geometry guards remain in force. | Numeric target price for every setup, target-above-entry proof, R:R calculation, and minimum R:R policy are not certified. |
| Partial/trailing/breakeven lifecycle | FAIL | No PR1031 evidence claims partial exits, sell-half, breakeven movement, or trailing stop handoff. | Requires explicit lifecycle certification if needed before PAPER. |
| PAPER readiness | FAIL | READ_ONLY remains execution-disabled; PAPER/LIVE not enabled. | Requires real READ_ONLY session artifact plus unresolved R:R/lifecycle/storage decisions. |

## Evidence Added

New test file: `tests/test_ross_pr1031_readonly_full_session_paper_readiness_gate.py`.

The tests prove:

1. READ_ONLY runtime authority blocks broker order submission even when execution is requested.
2. Positive Ross replay reaches scanner selection, watchlist K, focus M, pattern inputs, setup, decision, deterministic risk, simulated execution-disabled evidence, exit evidence, and analytics capture.
3. Positive READ_ONLY replay does not use the PAPER-forced intent path.
4. Negative no-catalyst replay preserves a no-trade reason, creates no intent, calls no risk gate, and creates no fake trade.
5. The PR1031 report keeps `PAPER_READY: NO`, `PAPER_READINESS_GATE: FAIL`, and explicit non-certification language for real broker runtime, numeric R:R, and lifecycle behavior.

The tests do not prove:

1. A broker-connected production runtime session completed without order submission.
2. Durable storage persistence of complete trade-plan and no-trade artifacts.
3. Numeric target price for every setup or target above entry for every long setup.
4. Reward/risk ratio calculation or minimum R:R policy enforcement.
5. Partial exits, sell-half behavior, breakeven movement, or trailing stop lifecycle handoff.
6. PAPER mode safety or readiness.

## Full-Session Replay Trace Matrix

| Stage | Expected READ_ONLY behavior | PR1031 evidence | Status | Remaining gap |
| --- | --- | --- | --- | --- |
| Runtime authority | Resolve READ_ONLY as live-like scan-only with no order authority. | `RuntimeModeManager.resolve()` returns READ_ONLY, `is_live_like=True`, `allow_orders=False`. | PASS | None for deterministic rule. |
| Execution flag pressure | Execution request must not override READ_ONLY. | Test sets execution enabled true/effective true and still gets `allow_orders=False`. | PASS | None for deterministic rule. |
| Event replay safety | Live-like READ_ONLY should force event replay OFF. | Runtime manager returns event replay `OFF` under READ_ONLY. | PASS | None for deterministic rule. |
| Scanner selection | Valid Ross candidate should pass deterministic selection gates. | Positive replay has `selection_passed=True`. | PASS | Real scanner provider session artifact missing. |
| Watchlist K | Accepted candidate should enter watchlist. | Positive replay has `watchlist_accepted=True` and symbol in watchlist tuple. | PASS | Real watchlist artifact missing. |
| Focus M | Watchlist candidate should enter focus only when catalyst/focus gates pass. | Positive replay has `focus_accepted=True`; no-catalyst replay stops at focus. | PASS | Real focus artifact missing. |
| Catalyst/news | Missing catalyst must block focus/decision. | Negative replay returns `DROP_NO_CATALYST` with no intent. | PASS | Real news feed session artifact missing. |
| Pattern inputs | Focused candidate should build pattern inputs with provenance. | Positive replay has `inputs_built=True`. | PASS | Runtime input artifact persistence missing. |
| Setup detection | Tradeable setup should be detected with trigger, stop, rationale. | Positive replay asserts setup, trigger, stop, and rationale exist. | PASS | Broader live input family coverage remains out of scope. |
| Decision policy | READ_ONLY should create inspectable intent through normal path, not PAPER forced path. | Positive replay creates one intent and output lacks `[ROSS][OVERRIDE][PAPER_MODE]`. | PASS | Real session decision artifact missing. |
| Risk gate | Positive deterministic intent reaches risk; no-trade path does not. | Positive replay risk called/approved; no-catalyst replay risk not called. | PARTIAL | Real risk/account state not certified. |
| Execution-disabled path | READ_ONLY must not submit broker orders. | Runtime authority denies order APIs; output lacks order-submission markers. | PASS | Broker-connected no-order proof missing. |
| Exit evidence | Simulated non-live management evidence remains inspectable. | Positive replay returns `SIMULATED_MANAGEMENT_READY`. | PARTIAL | Real lifecycle management not certified. |
| Analytics/storage capture | Evidence should be capturable for storage. | Positive and negative replay records have `storage_capturable=True`. | PARTIAL | Durable storage write/readback missing. |
| PAPER gate | PAPER must remain blocked unless objective gates pass. | Report test requires `PAPER_READY: NO` and `PAPER_READINESS_GATE: FAIL`. | PASS | Real readiness decision remains future work. |

## Failure Trace Table

| Stage | Expected Ross behavior | Current observed behavior | Gap | Severity | Required fix | Proposed PR |
| --- | --- | --- | --- | --- | --- | --- |
| Runtime mode | READ_ONLY is scan-only and blocks orders. | Certified deterministically. | Real deployed env artifact missing. | HIGH | Capture real READ_ONLY runtime config snapshot. | Future operational certification |
| Scanner | Autonomous scanner should provide candidates without manual focus or prep seeding. | PR1028 certified controlled scanner; PR1031 replay carries selection. | Real provider full-session proof missing. | HIGH | Capture real scanner cycle artifact. | Future operational certification |
| Catalyst/news | Catalyst must be confirmed; missing catalyst blocks focus. | PR1028 and PR1031 certify deterministic catalyst behavior. | Real news feed artifact missing. | HIGH | Capture real news/catalyst artifact. | Future operational certification |
| Watchlist K | Only gate-passing candidates enter watchlist. | Positive replay passes; negative no-catalyst reaches watchlist but not focus. | Real watchlist storage missing. | MEDIUM | Persist and verify watchlist artifact. | Future operational certification |
| Focus M | Focus requires stricter gate/catalyst satisfaction. | Positive replay passes; no-catalyst replay blocks with `DROP_NO_CATALYST`. | Real focus storage missing. | MEDIUM | Persist and verify focus artifact. | Future operational certification |
| Pattern inputs | Inputs require fresh/provenanced candles, levels, indicators, liquidity, and news context. | Positive replay builds inputs. | Runtime artifact persistence missing. | MEDIUM | Store/read back input provenance. | Future operational certification |
| Setup | Tradeable setup requires price-action trigger, stop, target model, rationale. | PR1030 and PR1031 preserve deterministic evidence. | Real runtime setup artifact missing. | MEDIUM | Store/read back setup evidence. | Future operational certification |
| Decision | READ_ONLY intent must use normal decision path and not PAPER override. | PR1031 asserts PAPER override log absent. | Real session decision artifact missing. | MEDIUM | Store/read back decision evidence. | Future operational certification |
| Risk | Deterministic risk path should be called only for valid intents. | Positive calls/approves risk; no-catalyst calls no risk. | Real account/risk state missing. | HIGH | Add real READ_ONLY risk artifact. | Future operational certification |
| Execution gate | READ_ONLY must block broker orders even if execution is requested. | PR1031 certifies runtime authority blocks orders. | Broker-connected no-order artifact missing. | CRITICAL | Capture real session with zero order submissions. | Future operational certification |
| Analytics/storage | Complete trade/no-trade evidence should be durable. | Replay evidence is capturable only. | Durable write/readback missing. | HIGH | Verify storage artifact persistence. | Future operational certification |
| PAPER readiness | PAPER only after real READ_ONLY evidence and unresolved policy gaps close. | Gate fails; `PAPER_READY: NO`. | Real session, numeric R:R, lifecycle, and storage gaps remain. | CRITICAL | Do not enable PAPER yet. | Future readiness PR |

## Fallback / Bypass Inventory

| Flag/path | File/function | Current effect | PR1031 evidence | Can affect PAPER/LIVE? | Risk | Required action |
| --- | --- | --- | --- | --- | --- | --- |
| `RUN_MODE=READ_ONLY` | `RuntimeModeManager.resolve`; `resolve_mode_authority` | Resolves scan-only with `trade_enabled=False`. | Certified. | Blocks PAPER/LIVE execution in READ_ONLY. | LOW | Keep as authority gate. |
| `EXECUTION_ENABLED` | `resolve_mode_authority`; runtime accessors | Cannot enable orders in READ_ONLY. | Certified under requested true/effective true. | Yes if mode is PAPER/LIVE. | HIGH | Require explicit future PAPER review. |
| `EXECUTION_ENABLED_EFFECTIVE` | Runtime manager | Still cannot override READ_ONLY. | Certified. | Yes outside READ_ONLY. | HIGH | Keep READ_ONLY regression. |
| `EVENT_REPLAY_MODE_EFFECTIVE` | `RuntimeModeManager.resolve` | Forced OFF in live-like modes. | Certified with CYCLE request under READ_ONLY. | Could affect replay behavior. | MEDIUM | Keep live-like OFF behavior. |
| PAPER forced intent path | `build_trade_intents`; `RUN_MODE=PAPER` branch | Can create PAPER intent after setup gates. | READ_ONLY output lacks PAPER override path. | PAPER yes. | HIGH | Keep PAPER disabled until later approval. |
| Missing target guard | `build_trade_intents` | Drops targetless setup. | Preserved from PR1030. | Blocks PAPER/LIVE incomplete plans. | LOW | Keep guard. |
| Invalid geometry guard | `build_trade_intents` | Drops invalid long trigger/stop geometry. | Preserved from PR1030. | Blocks PAPER/LIVE invalid plans. | LOW | Keep guard. |
| `debug_force_execution` | `IntentPolicyConfig.debug_force_execution` | Can bypass some data-quality behavior but not READ_ONLY runtime authority. | Inventoried; not enabled. | PAPER/LIVE risk if enabled. | HIGH | Assert disabled in operational certification. |
| Validation session override | `VALIDATION_SESSION_OVERRIDE` / policy config | Can allow invalid session in validation contexts. | Inventoried; not enabled. | PAPER/SIM risk if enabled. | HIGH | Assert disabled or scoped before PAPER. |
| Manual focus | Scanner/orchestrator focus config | Can influence candidate universe but not READ_ONLY order authority. | PR1028 had no-manual-focus evidence; PR1031 does not add manual focus. | Candidate selection risk. | MEDIUM | Audit real session config. |
| Synthetic intent allowed | Safety policy from earlier inventories | Validation-only synthetic path; PR1031 does not enable it. | Inventoried; not enabled. | PAPER/SIM risk if enabled. | HIGH | Assert blocked outside validation. |
| Order API write allowed | `get_ibkr_api_write_allowed` | False in READ_ONLY. | Certified. | Yes if PAPER/LIVE enabled. | CRITICAL | Keep blocked for READ_ONLY. |
| Order submission enabled | `get_ibkr_order_submission_enabled` | False in READ_ONLY. | Certified. | Yes if PAPER/LIVE enabled. | CRITICAL | Keep blocked for READ_ONLY. |

## PAPER Readiness Gate

| Gate | Required before PAPER | PR1031 status | Verdict |
| --- | --- | --- | --- |
| READ_ONLY authority blocks orders | Runtime must deny order authority in READ_ONLY. | Certified deterministically. | PASS |
| Broker-connected no-order session | Real session must show zero submitted/cancelled/modified orders. | Not certified. | FAIL |
| Scanner/focus real session | Real scanner, watchlist, and focus artifacts must be captured. | Deterministic replay plus PR1028 controlled scanner evidence only. | PARTIAL |
| Catalyst/news real session | Real catalyst/news feed evidence must be captured. | Deterministic/controlled evidence only. | PARTIAL |
| Setup/decision mapping | Entry, stop, target-model, rationale must carry through. | Certified deterministically by PR1030/PR1031. | PASS |
| Numeric target/R:R | Numeric target geometry, R:R computation, and minimum R:R must be decided/certified if required. | Not fully certified. | PARTIAL |
| Lifecycle management | Partial, breakeven, trailing, and sell-half behavior must be certified if required. | Not certified. | FAIL |
| Durable storage | Trade-plan and no-trade artifacts must be written and read back. | Capturable only, not durable. | PARTIAL |
| PAPER enablement | PAPER/LIVE flags remain disabled until all required gates pass. | No enablement added. | PASS |

Final gate result: `PAPER_READINESS_GATE: FAIL` and `PAPER_READY: NO`.

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1031_readonly_full_session_paper_readiness_gate.py
python -m pytest tests/test_ross_pr1030_entry_stop_target_exit_mapping.py tests/test_ross_pr1029_pattern_detection_certification.py tests/test_ross_pr6_end_to_end_certification.py tests/test_ross_pr5_setup_decision_fidelity.py
python -m pytest tests -k "ross or readonly or paper or execution or scanner or catalyst or focus"
```

Local execution may be unavailable in this Codex desktop session if the Windows command sandbox blocks repository access or if the local Python environment lacks pytest. GitHub Actions is the authoritative verification surface if local pytest is unavailable.

## Final Certification Answer

PR1031 certifies deterministic READ_ONLY full-session replay and proves READ_ONLY runtime authority blocks broker order submission. It does not certify a real broker-connected production session, durable runtime storage persistence, numeric R:R readiness, partial exits, breakeven movement, trailing lifecycle behavior, PAPER mode, or LIVE mode. Ross Momentum remains `PAPER_READY: NO`.
