# PR1027 Ross Strategy Fidelity Audit

## Scope

This audit covers Ross Momentum strategy fidelity across scanner selection, catalyst handling, setup detection, decision policy, and the risk/execution boundary on current `main` after PR1025.

This is an evidence and certification PR. It does not tune thresholds, weaken selection gates, enable PAPER or LIVE trading, create fake trades, add fallback trade authority, or bypass risk/execution controls.

## Executive Verdict

```text
PAPER_READY: NO
ROSS_STRATEGY_FIDELITY: PARTIAL
MAIN_BLOCKERS:
1. Autonomous scanner/catalyst runtime proof is not certified.
2. Broader Ross pattern-family positive/negative detection is not fully certified.
3. Production PAPER/READ_ONLY dry-run behavior is not certified against real runtime data.
NEXT_REQUIRED_PR: PR1028 Ross autonomous scanner and catalyst runtime certification.
DO_NOT_GO_PAPER_REASON: Current proof is deterministic fixture/harness evidence, not autonomous runtime proof from live scanner/news/catalyst feeds.
```

Ross Momentum now has deterministic fixture evidence for the full scanner-to-decision path:

- scanner gates can pass Ross-like low-float momentum candidates;
- catalyst absence is blocked explicitly instead of ignored;
- pattern inputs are built only after watchlist/focus acceptance;
- positive fixtures require real setup detection, trigger, stop, and rationale;
- malformed setups, missing inputs, missing trigger/stop, exhaustion, and no-setup cases do not create trade intent;
- risk is called only after a trade intent exists;
- execution remains simulated safe non-live evidence only.

PAPER readiness is not certified by this PR. The system is closer to PAPER, but still needs autonomous scanner/catalyst runtime proof and broader pattern-family certification before a PAPER dry run is justified.

## Readiness By Area

| Area | Current Readiness | Audit Verdict |
| --- | ---: | --- |
| Scanner selection | 75% | Deterministic gates prove price, percent change, RVOL, float, spread/liquidity, and volume rejection/pass behavior. Live autonomous discovery and ranking evidence still needed. |
| Watchlist/focus | 85% | PR1025 closed the explicit focus handoff gap. PR1027 confirms setup/decision are reached only after accepted focus. |
| Catalyst/news | 60% | Catalyst absence blocks before setup and decision. Real news-provider freshness, source quality, and degradation metadata still need runtime proof. |
| Pattern inputs | 80% | Fixture path carries 10s, 1m, 5m, EMA, VWAP, MACD, levels, liquidity, float, RVOL, and catalyst context. Live missing-field coverage remains incomplete. |
| Pattern detection | 70% | Micro pullback, flat top, premarket high break, stale-input rejection, missing-stop/trigger, exhaustion, and no-setup negatives are covered. Remaining Ross setup families need deterministic positive/negative certification. |
| Decision policy | 80% | No valid setup, no trigger, no stop, risk-off, and scanner/catalyst rejections do not create intent. PAPER/LIVE policy still needs dry-run runtime certification. |
| Entry/exit mapping | 65% | Positive fixtures produce stop/target/management evidence for simulated non-live execution. Broker-facing lifecycle proof is out of scope. |
| PAPER readiness | 55% | Safe for more certification work, not yet safe to claim PAPER-ready. |

## Module Fidelity Table

| Module Surface | Evidence Present | Remaining Gap |
| --- | --- | --- |
| Scanner gates | PR6 harness evaluates Ross policy thresholds for price, gap/percent change, RVOL, float, spread, volume, catalyst, halts, and SSR. | Need real scanner cycles proving it can autonomously find and rank the best 3-5 Ross-like symbols without manual focus. |
| Catalyst authority | `negative_no_catalyst` reaches watchlist but fails focus with `DROP_NO_CATALYST`. | Need real news/catalyst source provenance and stale/unavailable classifications in runtime logs. |
| Watchlist/focus handoff | PR1025 runner guard prevents explicit focus metadata from forwarding broad watchlist rows into Ross V1 processing. | Need continued READ_ONLY runtime log review after the guard is merged. |
| Pattern input builder | Positive cases build 10s, 1m, 5m candles with EMA/VWAP/MACD, levels, liquidity, float, RVOL, and news context. | Need runtime missing-field inventory for live IBKR/news data. |
| Setup detection | Positive fixtures detect micro pullback, flat top, and premarket high break. Negative fixtures cover stale 10s, missing stop, indicator-only trigger absence, exhaustion, and no setup. | Need full deterministic positive/negative fixtures for the remaining tradeable Ross setup families. |
| Decision policy | Only entry-ready setups with trigger, stop, rationale, and valid session can become intents. | Need PAPER dry-run proof that production policy state and environment flags are configured safely. |
| Risk/execution | Risk simulation is called only after intent; safe non-live execution is simulated only for positives. | Real broker submission remains intentionally out of scope. PAPER/LIVE remain blocked until later certification. |
| Analytics/certification | All PR1027 matrix results assert analytics capture is available. | Need runtime storage review during READ_ONLY/PAPER dry runs. |

## Pattern Fidelity Matrix

| Pattern / Rule | Required Ross evidence | Current code evidence | Missing evidence | Decision behavior | Status | Required PR/fix |
| --- | --- | --- | --- | --- | --- | --- |
| Micro pullback | Front-side momentum pullback with fresh 10s/1m data, reclaim trigger, stop, and rationale. | `positive_micro_pullback_a_quality`; stale 10s negative; PR5 micro pullback input-scope tests. | Live scanner-driven micro-pullback runtime proof and more negative variants. | Valid fixture can create safe non-live intent; stale input blocks before intent. | PASS | PR1029 for broader variants; PR1031 for runtime proof. |
| Flat-top breakout | Real resistance shelf, volume expansion, trigger above level, stop, and rationale. | `positive_flat_top_volume_expansion`; PR5 weak-volume flat-top rejection. | Live level quality and multi-symbol runtime proof. | Valid fixture can create safe non-live intent; weak volume rejects. | PASS | PR1029 and PR1031. |
| High-of-day breakout | Valid HOD source, breakout trigger, volume/liquidity support, and stop. | PR5 HOD missing-level rejection proves missing HOD is not accepted. | Deterministic positive HOD breakout fixture and runtime HOD source proof. | Missing HOD rejects; positive HOD path not fully certified in PR1027. | PARTIAL | PR1029. |
| Premarket-high break | Valid premarket high, level break, volume confirmation, catalyst, trigger, and stop. | `positive_pmh_break_valid_level_volume_stop_catalyst`; PR5 missing PMH rejection. | Live PMH level provenance and news/catalyst runtime proof. | Valid fixture can create safe non-live intent; missing PMH rejects. | PASS | PR1028 for catalyst/runtime; PR1029 for more fixtures. |
| Reversal risk / extended move rejection | Extended/parabolic move should become risk-off evidence, not a long entry. | `negative_exhaustion_risk_off`; PR5 exhaustion test logs risk-off and selects no long setup. | More exhaustion/failed-breakout variants across sessions. | Does not create trade intent or call risk when treated as non-entry. | PASS | PR1029. |
| Volume confirmation | Breakouts need volume expansion and weak volume must reject. | Flat-top weak-volume rejection and positive volume-expansion fixture. | Live volume-quality provenance and HOD/PMH volume variants. | Weak volume rejects before intent for covered fixture. | PARTIAL | PR1029; PR1031 runtime volume trace. |
| VWAP context | VWAP should be present for context/support decisions where required. | PR6/PR1027 fixture inputs include VWAP in `LevelSet`/`IndicatorSet`. | Dedicated VWAP-support positive/negative fixtures and runtime source proof. | Context is available in fixture path, but dedicated gating is not fully certified here. | PARTIAL | PR1029. |
| EMA context | EMA9/EMA20/EMA200 should support continuation or degrade/block by setup policy. | PR6/PR1027 fixture inputs include EMA values; PR5 verifies indicators do not create indicator-only trades. | Dedicated EMA-support and EMA-failure fixtures. | Indicator-only setup cannot create intent. | PARTIAL | PR1029. |
| MACD context | MACD should be context/degradation input, not standalone trade authority. | PR5 missing MACD degrades ABCD without blocking micro pullback; indicator-only MACD/EMA signal creates no intent. | Dedicated MACD policy matrix for all MACD-dependent setups. | MACD-only evidence does not create trade intent. | PARTIAL | PR1029. |
| Stop placement | Every tradeable setup needs defensible stop/invalidation. | Positive PR6 cases assert stop exists; `negative_missing_stop` blocks intent. | Full stop model mapping into lifecycle modules. | Missing stop prevents trade intent and risk call. | PASS | PR1030. |
| Target mapping | Intent should carry target/management evidence for exits. | PR6 positive `exit_evidence` captures simulated management readiness and `target_model`. | Full target/partial/trailing mapping against lifecycle and broker-facing modules. | Simulated non-live only; no PAPER/LIVE authority. | PARTIAL | PR1030. |
| Catalyst confirmation | A-quality Ross candidate should have real catalyst or explicit degradation/block. | `negative_no_catalyst` fails focus with `DROP_NO_CATALYST`; positives carry `PRESENT`. | Real news-provider provenance, freshness, and unavailable-source classification. | Missing catalyst stops before inputs/setup/intent. | PARTIAL | PR1028. |
| Float discipline | Low-float preference; unknown/high float must not normalize as core Ross. | `negative_unknown_float` and `negative_float_above_limit` stop before inputs and intent. | Live float-provider source/freshness proof. | Unknown/high float rejects in certified harness. | PARTIAL | PR1028. |
| Risk/reward validation | Trigger, stop, target, and risk/reward should be validated before PAPER. | Risk is called only after intent; missing stop blocks. | Explicit risk/reward ratio certification and production risk-engine dry run. | Current proof is boundary gating, not full risk/reward certification. | UNKNOWN | PR1030; PR1031. |

## Failure Trace Table

| Stage | Expected Ross behavior | Current observed behavior | Gap | Severity | Required fix | Proposed PR |
| --- | --- | --- | --- | --- | --- | --- |
| Scanner | Autonomously identify Ross-like low-float, high-RVOL, strong-gap candidates. | Deterministic harness proves gate pass/fail behavior only. | No full autonomous runtime scanner proof. | HIGH | Capture live READ_ONLY scanner cycles with top 3-5 explainable ranks. | PR1028 |
| Catalyst/news | Require real catalyst for A-quality or explicit block/degrade. | Missing catalyst blocks as `DROP_NO_CATALYST`; positives use fixture `PRESENT`. | Real news provider provenance and freshness not certified. | HIGH | Add runtime catalyst source/freshness audit and tests. | PR1028 |
| Watchlist K | Build watchlist from scanner candidates without fake broad fallback. | Harness produces watchlist when gates pass; PR1025 focus guard prevents broad handoff drift. | Need live watchlist ranking proof. | MEDIUM | Runtime trace for K selection and rejected candidates. | PR1028 |
| Focus M | Narrow watchlist to best execution candidates with catalyst/RVOL quality. | Harness focus rejects no catalyst/weak quality; positives reach focus. | Need live focus ranking and no-manual-focus proof. | HIGH | Runtime focus trace and ranking acceptance criteria. | PR1028 |
| Pattern inputs | Build fresh 10s/1m/5m, indicators, levels, liquidity, float, RVOL, catalyst context. | Fixture path builds all required fields for certified cases; stale 10s blocks. | Live missing-field inventory incomplete. | HIGH | Runtime input trace with missing/stale/unavailable classifications. | PR1028/PR1029 |
| Micro pullback | Detect controlled front-side pullback with trigger and stop. | Positive fixture passes; stale 10s rejects. | More variants and live proof needed. | MEDIUM | Expand deterministic fixture matrix. | PR1029 |
| Flat-top breakout | Detect resistance shelf break with volume confirmation. | Positive fixture passes; weak volume rejects. | Runtime level/volume proof needed. | MEDIUM | Add live-like fixtures and runtime trace. | PR1029 |
| HOD/PMH breakout | Require valid HOD/PMH levels and breakout confirmation. | PMH positive exists; missing HOD/PMH rejects. | HOD positive fixture and runtime level provenance missing. | MEDIUM | Add HOD positive/negative matrix and level-source audit. | PR1029 |
| Decision policy | Create intent only for valid setup, trigger, stop, rationale, session policy. | No setup, no trigger, missing stop, risk-off, and scanner rejects create no intent. | Production env/override behavior not dry-run certified. | HIGH | READ_ONLY/PAPER policy-state audit. | PR1031 |
| Entry mapping | Entry model should map to real trigger authority. | Positive fixtures provide entry model/trigger; indicator-only signal blocks. | Runtime trigger source proof and broker-facing mapping incomplete. | HIGH | Entry mapping certification against decision/lifecycle modules. | PR1030 |
| Stop placement | Stop/invalidation is required before intent/risk. | Missing stop prevents intent; positives have stops. | Lifecycle stop-controller integration proof remains incomplete. | HIGH | Map Ross stop model into stop/lifecycle modules. | PR1030 |
| Target mapping | Targets/partials/trailing rules should be explicit before PAPER. | Simulated exit evidence captures target readiness. | Full target/partial/trailing behavior not certified. | HIGH | Target/exit lifecycle certification. | PR1030 |
| Risk gate | Risk should be called only after valid intent and should block unsafe state. | Harness calls risk only after intent; negative cases do not call risk. | Real risk-engine dry-run proof not included. | HIGH | Risk-engine integration dry run with Ross intents. | PR1031 |
| Execution mode gate | READ_ONLY must not submit orders; PAPER must be enabled only after certification. | Harness simulates safe non-live execution; LIVE negative blocks. | Production READ_ONLY/PAPER mode trace not certified. | CRITICAL | Full-session READ_ONLY dry run and explicit PAPER gate. | PR1031 |
| Analytics/storage | Outcomes, no-trade reasons, traces, and intent counts should be stored. | PR1027 asserts storage capture availability in harness analytics records. | Runtime storage completeness not certified. | MEDIUM | Verify persisted runtime artifacts and trace completeness. | PR1031 |
| PAPER readiness | PAPER only after scanner/catalyst/runtime/prod gates are proven. | This PR is fixture/harness proof only. | No autonomous runtime or production dry-run certification. | CRITICAL | Complete PR1028-PR1031. | PR1031 |

## New Executable Evidence

This PR adds `tests/test_ross_pr1027_strategy_fidelity_audit.py`.

The test suite proves:

1. Positive Ross fixture candidates preserve the full scanner -> watchlist -> focus -> inputs -> setup -> decision -> risk -> safe non-live execution chain.
2. Scanner and catalyst rejection cases stop before pattern inputs, setup detection, trade intent, risk, and execution.
3. Missing catalyst is not silently ignored: it is preserved in diagnostics and rejected as `DROP_NO_CATALYST`.
4. Setup/decision failures never escape to risk or execution when inputs are stale, stop is missing, trigger is missing, exhaustion is detected, or no valid setup exists.
5. The full PR6 matrix contains only the three certified safe non-live successes and the ten certified negative cases.

## Fallback / Bypass Inventory

| Flag/path | File/function | Current effect | Can affect PAPER/LIVE? | Risk | Required action |
| --- | --- | --- | --- | --- | --- |
| Explicit focus fallback | `src/strategies/ross_momentum/runner.py::_filter_watchlist_for_explicit_focus`; orchestrator Ross focus handoff | Explicit `focus_list`, `focus_symbols`, or `focus_m_symbols` filters broad watchlist rows before Ross V1 processing. | Yes, as a safety guard; it reduces PAPER/LIVE candidate scope. | LOW | Keep guard; add READ_ONLY runtime proof that non-focus rows stay execution-ineligible. |
| Synthetic/fake trade fallback | `src/strategies/ross_momentum/policy/runtime_safety.py::synthetic_intent_allowed`; `log_fallback_intent_blocked` | Synthetic intent allowance delegates to validation override and is live-like blocked by policy helpers. | PAPER can be affected if explicitly requested; LIVE/READ_ONLY should not be allowed. | MEDIUM | Assert synthetic/validation flags are disabled for certification runs; test live-like block. |
| PAPER forced intent path | `src/strategies/ross_momentum/decision_policy.py::build_trade_intents` | PAPER returns an intent only when `valid_trade` is true, which requires selected setup plus `trigger_ready_now is True`. | Yes, PAPER only. | MEDIUM | PR1031 must prove PAPER mode is gated by real setup/trigger evidence and correct env flags. |
| `debug_force_execution` | `IntentPolicyConfig.debug_force_execution`; `build_trade_intents` | Can bypass data-quality flags when explicitly configured. PR1027 does not enable it. | Yes if passed into PAPER/LIVE-like wiring. | HIGH | Require disabled config in READ_ONLY/PAPER certification; add guard assertion before PAPER. |
| Validation/session overrides | `IntentPolicyConfig.validation_session_override`; env `VALIDATION_SESSION_OVERRIDE`; env `ALLOW_PAPER_AFTER_HOURS_INTENTS` | Can permit validation-session or PAPER after-hours behavior under configured conditions. | PAPER yes; LIVE should be blocked by normal session policy. | HIGH | Inventory env state and assert overrides disabled unless a validation test explicitly scopes them. |
| Manual focus | `src/core/orchestrator.py::load_manual_focus_config`; strategy handoff | Provides watch/focus candidates only; PR1025/PR1027 evidence says it must not bypass setup/risk/execution. | Yes, it can affect candidate set, not trade authority. | MEDIUM | Keep manual focus as watch authority only; prove no setup/risk bypass in runtime dry run. |
| Additional heuristic patterns | `src/strategies/ross_momentum/patterns/pattern_registry.py::build_additional_heuristic_patterns`; `ROSS_ENABLE_ADDITIONAL_HEURISTIC_PATTERNS` | Optional experimental hook is empty by default and config-gated. | Could affect PAPER/LIVE if future heuristics are added and enabled. | MEDIUM | Keep disabled for certification; require fixtures before adding any heuristic pattern. |
| `trigger_ready` / `trigger_ready_now` | `decision_policy.build_trade_intents`; `e2e_harness.run_ross_e2e_case` | Intent creation requires trigger readiness after setup, trigger, stop, and rationale checks. | Yes, especially PAPER intent creation. | MEDIUM | PR1030/PR1031 must prove runtime trigger source, not fixture-only readiness. |
| `TRADE_READY` | `src/strategies/ross_momentum/runner.py::RossMomentumRunner.run` | Counts intents whose `decision` is `TRADE_READY`, defaulting missing `decision` to `TRADE_READY` for count reporting. | Could affect reporting/readiness counts; not direct order authority in PR1027 evidence. | MEDIUM | Audit decision attribute semantics before PAPER; avoid using count alone as trade authority. |
| `EXECUTION_ENABLED` | Not found in targeted PR1027 file pass. | No PR1027 evidence of this exact flag. | Unknown. | MEDIUM | PR1031 must inventory runtime execution env/config flags and prove order submission remains disabled until approved. |
| `ROSS_VALIDATION_OVERRIDE` | Exact flag not found in targeted PR1027 file pass; validation override equivalents are present. | Equivalent behavior appears through `VALIDATION_SESSION_OVERRIDE` and validation override policy helpers. | PAPER yes if enabled through equivalent paths. | HIGH | Standardize/verify override flag names before PAPER; assert disabled in dry run. |
| `synthetic_intent_allowed` | `src/strategies/ross_momentum/policy/runtime_safety.py::synthetic_intent_allowed` | Allows synthetic intent only through `validation_override_allowed(mode, requested)`, i.e., requested validation mode. | PAPER/SIM can be affected; LIVE/READ_ONLY should be blocked. | MEDIUM | Add explicit certification test for mode/request matrix before PAPER. |

## Pattern Input Gaps vs Pattern Detection Gaps

Pattern-input gaps are no longer the larger blocker for the certified fixture path. The PR6/PR1027 evidence shows 10s, 1m, 5m, indicators, levels, liquidity, float, RVOL, and catalyst context can support valid Ross setup decisions.

The larger blockers are now:

1. live autonomous scanner and catalyst quality evidence;
2. deterministic detection coverage for all remaining Ross tradeable setup families;
3. PAPER dry-run proof that production risk/execution boundaries behave like the certified fixture harness.

## PR1028 to PR1031 Staged Plan

### PR1028 — Ross Autonomous Scanner and Catalyst Runtime Certification

Purpose: prove the live scanner and catalyst/news path can autonomously produce Ross-like candidates and explainable top 3-5 focus symbols without depending on manual focus.

Files likely touched:

- `src/scanner/`
- `src/scanner/scanner_runner.py`
- `src/strategies/ross_momentum/policy/`
- `src/core/orchestrator.py`
- catalyst/news provider adapters and trace/log modules
- `tests/` scanner/catalyst certification files
- `docs/certification/PR1028_*`

Acceptance criteria:

- READ_ONLY scanner cycle produces ranked watchlist K and focus M candidates with reason codes.
- Catalyst source, freshness, status, and unavailable/degraded behavior are logged.
- Unknown/high float, weak gap, low RVOL, weak liquidity, and missing catalyst do not reach setup evaluation.
- Manual focus is not required for candidate discovery proof.

Tests required:

- Deterministic scanner ranking positive/negative tests.
- Catalyst present/missing/stale/unavailable tests.
- READ_ONLY runtime trace test or replayed fixture proving watchlist/focus ranking.

PAPER-readiness contribution: closes the largest current blocker by proving autonomous candidate quality before setup detection.

### PR1029 — Remaining Ross Pattern Detection Certification

Purpose: complete deterministic positive and negative certification for the remaining Ross tradeable pattern families.

Files likely touched:

- `src/setup_engine/setup_families/`
- `src/strategies/ross_momentum/patterns/`
- `src/strategies/ross_momentum/patterns/pattern_registry.py`
- `src/strategies/ross_momentum/policy/pattern_input_policy.py`
- `tests/test_ross_*pattern*`
- `docs/certification/PR1029_*`

Acceptance criteria:

- Every enabled Ross tradeable family has at least one positive fixture and multiple targeted negatives.
- HOD breakout positive certification is added.
- VWAP/EMA/MACD context is covered as context/degrade/block evidence, not standalone trade authority.
- Reversal/failed-breakout/exhaustion signals cannot become long-entry intents.

Tests required:

- Pattern-family positive/negative matrix.
- Missing/stale input policy tests by setup family.
- Registry invocation/no-placeholder certification tests.

PAPER-readiness contribution: reduces strategy-fidelity uncertainty after scanner/catalyst candidates reach setup evaluation.

### PR1030 — Entry/Stop/Target/Exit Mapping Certification

Purpose: prove Ross entry, stop, target, partial, trailing, and exit evidence maps cleanly into existing lifecycle/risk/management modules.

Files likely touched:

- `src/strategies/ross_momentum/decision_policy.py`
- `src/strategies/strategy_contracts.py`
- `src/core/engines/trade_lifecycle_engine.py`
- `src/core/engines/position_management_engine.py`
- `src/core/stop_controller.py`
- `src/execution/trade_exit_engine.py`
- `tests/test_ross_*entry*`, `tests/test_ross_*exit*`
- `docs/certification/PR1030_*`

Acceptance criteria:

- Every trade intent has explicit entry, stop/invalidation, target, and management metadata.
- Missing stop/target where required blocks or degrades exactly as policy says.
- Risk/reward validation is explicit and tested.
- Lifecycle modules can consume Ross intent metadata without broker submission.

Tests required:

- Entry model mapping tests.
- Stop/invalidation mapping tests.
- Target/partial/trailing mapping tests.
- Risk/reward acceptance/rejection tests.

PAPER-readiness contribution: proves a valid Ross setup becomes a manageable trade plan, not just an intent.

### PR1031 — READ_ONLY Full-Session Dry Run and PAPER Readiness Gate

Purpose: run a production-shaped READ_ONLY full-session certification and decide whether PAPER can be enabled in a later controlled step.

Files likely touched:

- `src/core/orchestrator.py`
- `src/config/runtime_config.py`
- `src/execution/`
- `src/storage/`
- verification scripts under `verification_scripts/`
- runtime trace/log capture helpers
- `docs/certification/PR1031_*`

Acceptance criteria:

- Full-session READ_ONLY run shows no order submission, no probe/fake trade, and no unapproved execution path.
- Scanner/catalyst/focus/setup/decision/risk/execution/storage traces are complete.
- Overrides (`debug_force_execution`, validation/session overrides, synthetic intent) are disabled or explicitly blocked.
- PAPER_READY remains `NO` unless all objective gates pass; if gates pass, the report states the exact PAPER enablement checklist.

Tests required:

- Runtime configuration safety tests.
- READ_ONLY dry-run trace verification.
- Execution-disabled/order-submission-negative tests.
- Analytics/storage completeness tests.

PAPER-readiness contribution: final pre-PAPER evidence gate. It can recommend PAPER only if scanner, catalyst, setup, decision, risk, execution, and storage traces all pass.

## Smallest Safe PR Sequence From Here

1. PR1028 — Ross Autonomous Scanner and Catalyst Runtime Certification.
2. PR1029 — Remaining Ross Pattern Detection Certification.
3. PR1030 — Entry/Stop/Target/Exit Mapping Certification.
4. PR1031 — READ_ONLY Full-Session Dry Run and PAPER Readiness Gate.
5. PR1032 - PAPER dry-run certification with broker submission boundaries explicitly controlled, only if PR1031 recommends it.
6. PR1033 - LIVE_MICRO readiness gate only after PAPER is clean.

## Recommended Next Implementation PR

The next implementation PR should be PR1028: autonomous scanner and catalyst runtime certification.

Reason: PR1027 shows the strategy path can behave faithfully once a candidate and valid setup fixture exist. The biggest remaining uncertainty is whether the live scanner/news path can autonomously produce the right candidate quality and explainable top 3-5 focus symbols without manual focus.

## Verification

Local verification could not be run in this Codex session because the Windows command sandbox fails before command startup with:

```text
windows sandbox failed: helper_unknown_error: apply deny-read ACLs
```

Required verification on the PR branch:

```powershell
python -m pytest tests/test_ross_pr1027_strategy_fidelity_audit.py
python -m pytest tests/test_ross_pr6_end_to_end_certification.py tests/test_ross_pr5_setup_decision_fidelity.py
```

## Final Audit Answer

Ross Momentum is materially closer to PAPER readiness, but not PAPER-ready. No unsafe fallback/debug path was added by this PR. The certified fixture path proves scanner/catalyst/setup/decision fidelity for a narrow but meaningful Ross subset. The next safe move is autonomous scanner and catalyst runtime certification, followed by broader pattern detection certification and then PAPER dry-run proof.
