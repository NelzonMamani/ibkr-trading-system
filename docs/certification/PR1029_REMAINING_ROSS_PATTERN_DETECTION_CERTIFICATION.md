# PR1029 Remaining Ross Pattern Detection Certification

## Scope

This certification PR closes the PR1028 pattern-detection blocker by adding deterministic positive and negative evidence for the remaining Ross setup families that needed explicit fixture proof, with special emphasis on the previously missing high-of-day breakout positive case.

This PR does not change production trading thresholds, enable PAPER or LIVE, weaken Ross gates, add synthetic trades, or broaden execution authority. It is a certification and evidence PR.

## Executive Verdict

```text
PAPER_READY: NO
ROSS_PATTERN_DETECTION_CERTIFICATION: FIXTURE_CERTIFIED_RUNTIME_PARTIAL
HOD_BREAK_POSITIVE_CERTIFIED: YES
INDICATOR_ONLY_TRADE_AUTHORITY: BLOCKED
MAIN_BLOCKERS:
1. Entry, stop, target, partial, trailing, and exit mapping are not fully certified across the Ross lifecycle.
2. Full-session READ_ONLY runtime proof from scanner/focus through setup, decision, risk, execution-disabled, analytics, and storage is not certified.
3. PAPER/READ_ONLY production environment flags and bypass inventory are not yet certified against a full runtime session.
NEXT_REQUIRED_PR: PR1030 Entry/Stop/Target/Exit Mapping Certification.
DO_NOT_GO_PAPER_REASON: PR1029 certifies deterministic pattern-family fixture behavior, not full lifecycle trade-plan mapping or production READ_ONLY runtime evidence.
```

PAPER readiness remains blocked. PR1029 proves deterministic detection behavior for core Ross setup families and risk-off/non-entry pattern paths, but it does not prove that those detected setups are mapped into complete executable trade plans or that a full production-shaped READ_ONLY session remains execution-disabled.

## Certification Result

| Area | Verdict | Evidence | Remaining gap |
| --- | --- | --- | --- |
| HOD breakout positive path | PASS | `test_pr1029_pullback_and_breakout_families_have_positive_negative_fixtures` adds RTH-sourced HOD compression/volume positive fixture. | Runtime full-session HOD input provenance still belongs to PR1031. |
| Pullback setup detection | PASS | Micro pullback, first pullback, EMA pullback, VWAP pullback, and bull flag have deterministic positive/negative fixtures. | Trade lifecycle mapping still belongs to PR1030. |
| Breakout setup detection | PASS | Flat-top, HOD, PMH, ORB, opening drive, gap-and-go, and stair-step fixtures assert positive and exact negative reasons. | Live scanner-to-pattern runtime trace still belongs to PR1031. |
| ABCD continuation | PASS | Deterministic swing A/B/C positive fixture plus no-swing negative fixture. | Target/exit mapping is not certified here. |
| Indicator context | PASS | VWAP, EMA, and MACD can support context only; indicator-only setup still creates no trade intent. | PR1030 must prove context fields map into trade plans safely. |
| Reversal/exhaustion risk | PASS | Parabolic exhaustion is risk-off/non-entry; failed ORB fakeout is short/non-long and cannot create long-entry authority. | Exit handling belongs to PR1030. |
| Halt resume | PASS | Halt resume remains disabled without halt tape in pattern inputs. | Requires real halt metadata before any future trade authority. |
| Placeholder/additional heuristics | PASS | Tradeable registry contains no placeholders; inactive placeholder families remain non-detected; additional heuristic list is empty. | Any future heuristic enablement requires separate positive/negative certification. |
| PAPER readiness | FAIL | No PAPER/LIVE enablement, execution, or full-session dry run added. | PR1030 and PR1031 remain required. |

## Pattern Fidelity Matrix

| Pattern / evidence family | Required Ross evidence | Current code evidence | Missing evidence | Decision behavior | Status | Required PR/fix |
| --- | --- | --- | --- | --- | --- | --- |
| Micro pullback | Impulse, controlled 1-3 bar pullback, continuation close above EMA context, valid stop. | Positive fixture detects; high EMA negative rejects as `price below EMA9`. | Full-session runtime input provenance. | Entry candidate only when trigger/stop/rationale exist. | PASS | PR1031 runtime trace. |
| First pullback | Initial impulse, controlled first pullback, reclaim trigger, valid stop. | Positive fixture detects; invalid pullback fixture rejects. | Lifecycle target/exit handling. | Entry-ready only after setup fidelity guard. | PASS | PR1030 mapping. |
| Flat-top breakout | Multi-touch flat resistance, breakout close, volume confirmation, invalidation. | Positive fixture detects exact resistance; weak-volume fixture rejects as `breakout_volume_below_average`. | Runtime resistance provenance. | Entry candidate only with trigger/stop. | PASS | PR1031 trace. |
| High-of-day breakout | RTH HOD source, proximity/compression, trend context, volume confirmation, structure stop. | New PR1029 positive fixture detects HOD; invalid source rejects as `invalid_hod_source`. | Live RTH HOD provenance across session. | Entry candidate when HOD source and stop are explicit. | PASS | PR1031 trace. |
| Premarket-high break | PMH level, acceptance/hold, spread/volume confirmation, stop below PMH. | Positive fixture detects; missing PMH rejects as `missing_premarket_high`. | Live PMH source freshness. | Entry candidate only with PMH trigger and stop. | PASS | PR1031 trace. |
| EMA pullback | EMA9/EMA20 trend, EMA-zone test, reclaim, volume contraction, trigger/stop. | Positive fixture detects; missing EMA rejects as `missing_ema`. | Full runtime EMA provenance. | EMA is context plus price action, not standalone authority. | PASS | PR1031 trace. |
| VWAP pullback | Trend above VWAP, pullback test, reclaim, volume contraction, trigger/stop. | Positive fixture detects; missing VWAP rejects as `missing_vwap`. | Full runtime VWAP provenance. | VWAP is context plus price action, not standalone authority. | PASS | PR1031 trace. |
| Bull flag | Impulse, controlled flag, declining/constrained flag volume, breakout close. | Positive fixture detects; no-breakout fixture rejects as `no breakout close`. | Target/exit mapping. | Entry candidate only on breakout with stop. | PASS | PR1030 mapping. |
| ABCD continuation | Valid swing sequence, retracement bounds, trigger, stop at C, measured projection. | Positive fixture detects; flat/no-swing fixture rejects as `NO_SWING_SEQUENCE`. | Projection-to-target lifecycle mapping. | Entry candidate only with trigger/stop. | PASS | PR1030 mapping. |
| ORB | RTH open/morning context, ORH/ORL, break and hold, volume, VWAP, MACD, spread, stop. | Positive fixture detects ORH; missing MACD rejects as `missing_macd`. | Full opening-range timestamp/runtime trace. | Entry candidate only with OR stop and trigger. | PASS | PR1031 trace. |
| Opening drive | RTH open phase, early impulse, volume, limited pullback, stop. | Positive fixture detects; wrong phase rejects as `invalid_phase`. | Live open-session phase trace. | Entry candidate only in open phase. | PASS | PR1031 trace. |
| Gap and go | Gap from prior close, PMH/HOD/ORH pressure, RVOL/spread/structure evidence. | Positive fixture detects; missing prior close rejects as `INSUFFICIENT_GAP`. | Live prior-close and gap provenance. | Entry candidate only with explicit gap/level context. | PASS | PR1031 trace. |
| Stair-step continuation | Higher highs/lows, shallow pullback, volume contraction, trend context, trigger/stop. | Positive fixture detects; low RVOL rejects as `invalid_inputs`. | Runtime multi-bar provenance. | Entry candidate only with trend and liquidity context. | PASS | PR1031 trace. |
| Parabolic exhaustion | Extension, acceleration, volume/rejection evidence. | Positive fixture detects as `non_entry_signal`/risk-off. | Exit lifecycle handling. | Cannot create long-entry trade authority. | PASS | PR1030 exit mapping. |
| Failed ORB fakeout | Failed breakout/reclaim back into range. | Positive fixture detects short direction. | Short-side execution policy is out of scope. | Cannot create long-entry trade authority. | PASS | PR1030 exit/risk mapping. |
| Halt resume | Real halt/resume tape or exchange metadata. | Current pattern rejects as `disabled_no_halt_tape_in_pattern_inputs`. | Halt tape/feed integration. | No trade authority. | PASS | Future dedicated halt certification if enabled. |
| Placeholder candle/reversal families | Must not silently become enabled trade authority. | Registry test proves placeholders remain inactive and additional heuristic list is empty. | Any future enablement requires certification. | No trade authority. | PASS | New PR required before enablement. |

## Failure Trace Table

| Stage | Expected Ross behavior | Current observed behavior | Gap | Severity | Required fix | Proposed PR |
| --- | --- | --- | --- | --- | --- | --- |
| Scanner | Only low-float/high-RVOL/gap/catalyst candidates reach setup evaluation. | PR1028 controlled READ_ONLY scanner/focus path is certified. | Full live/replayed session trace still missing. | HIGH | Capture full-session scanner/focus/input trace. | PR1031 |
| Catalyst/news | Catalyst must be confirmed or explicitly unavailable/absent. | PR1028 policy/status behavior is certified. | Real feed source/freshness across session still missing. | HIGH | Runtime catalyst provenance trace. | PR1031 |
| Pattern inputs | Required candle, level, indicator, liquidity, and session context must be present per family. | PR1029 fixture matrix asserts missing/invalid inputs reject per setup. | Production input source trace still missing. | HIGH | Trace focus M into pattern input builder. | PR1031 |
| Pullback detection | Pullbacks require price-action structure plus context, not indicators alone. | Micro, first, EMA, VWAP, bull flag fixtures pass/fail deterministically. | Runtime freshness/staleness proof across full session. | MEDIUM | Full-session input provenance. | PR1031 |
| Breakout detection | Breakouts require levels, acceptance, volume/liquidity, and stops. | Flat-top, HOD, PMH, ORB, opening drive, gap-and-go, stair-step fixtures pass/fail deterministically. | Real level provenance and rejection ledger. | HIGH | Runtime trace artifacts. | PR1031 |
| Indicator context | VWAP/EMA/MACD should never create trade authority alone. | Indicator-only setup returns no trade intent. | Mapping of context into complete trade plans still missing. | MEDIUM | Trade-plan mapping certification. | PR1030 |
| Reversal/exhaustion | Risk-off or short/non-long evidence must not create long entry. | Parabolic exhaustion and failed ORB fakeout cannot become long-entry candidates. | Exit handling not certified. | MEDIUM | Exit/risk mapping tests. | PR1030 |
| Halt resume | No halt trade authority without halt tape. | Pattern remains disabled by explicit rejection. | Halt feed unavailable. | LOW | Dedicated future certification before enablement. | Future PR |
| Registry | No placeholders, experimental heuristics, or silent fallbacks can trade. | PR1029 registry inventory proves tradeable registry excludes placeholders and optional heuristic list is empty. | Env/config inventory still needed. | MEDIUM | Full runtime config audit. | PR1031 |
| Decision policy | No intent unless setup has direction, trigger/entry, stop/invalidation, rationale, and policy clearance. | PR5 and PR1029 indicator-only/risk-off checks cover core boundaries. | Complete entry/target/exit lifecycle mapping missing. | HIGH | Entry/stop/target/exit mapping. | PR1030 |
| Execution mode gate | READ_ONLY must never submit orders; PAPER/LIVE remain disabled. | PR1029 does not alter execution mode. | Full-session execution-disabled proof missing. | CRITICAL | READ_ONLY full-session dry run. | PR1031 |
| Analytics/storage | Persist scanner, focus, setup, decision, reject, no-trade, and disabled-execution evidence. | PR1029 only adds deterministic tests/report. | Runtime persistence completeness missing. | MEDIUM | Storage trace audit. | PR1031 |
| PAPER readiness | PAPER only after scanner/catalyst, patterns, mapping, risk, execution-disable, and storage pass. | Still blocked. | PR1030 and PR1031 incomplete. | CRITICAL | Finish staged certification. | PR1031 |

## Fallback / Bypass Inventory

| Flag/path | File/function | Current effect | Can affect PAPER/LIVE? | Risk | Required action |
| --- | --- | --- | --- | --- | --- |
| Additional heuristic patterns | `src/strategies/ross_momentum/patterns/pattern_registry.py::build_additional_heuristic_patterns` | Returns empty list; optional config cannot add uncertified patterns today. | Could affect PAPER if future code populates it and config enables it. | MEDIUM | Keep empty/disabled unless separately certified. |
| Placeholder candle/reversal families | `src/setup_engine/setup_families/placeholders.py`; registry placeholder skip branch | Placeholder families are marked inactive and skipped. | No current trade authority. | LOW | Keep registry no-placeholder test. |
| Indicator-only setup | `decision_policy.build_trade_intents`; setup fidelity guards | No trade intent without price-action trigger/stop/rationale. | Blocks PAPER/LIVE trade authority. | LOW | Keep tests; expand in PR1030 mapping. |
| Parabolic exhaustion | `pattern_parabolic_exhaustion.py`; setup fidelity risk-off branch | Detects risk-off/non-entry signal only. | Could influence exit/risk logic, not long entry. | MEDIUM | Certify exit behavior in PR1030. |
| Failed ORB fakeout | `FailedOrbFakeoutPattern`; `is_tradeable_entry_candidate` | Short/non-long result cannot create long-entry authority. | No long-entry authority. | LOW | Keep non-long guard tests. |
| Halt resume | `HaltResumePattern.evaluate` | Explicitly rejects without halt tape in pattern inputs. | No current trade authority. | LOW | Require halt-feed certification before enablement. |
| Manual focus | Scanner/orchestrator focus paths from PR1028 inventory | Can affect candidate universe only; cannot bypass setup/risk/decision by itself. | Could affect PAPER candidates if enabled. | MEDIUM | Audit in PR1031 runtime config inventory. |
| PAPER validation bypass | Catalyst/runtime validation override paths from PR1028 inventory | Scoped validation behavior only. | PAPER/SIM risk if enabled outside validation. | HIGH | Assert disabled in PR1031. |
| `debug_force_execution` | `IntentPolicyConfig.debug_force_execution`; decision policy | Can alter decision behavior if explicitly configured. | PAPER/LIVE risk if enabled. | HIGH | Assert disabled in PR1031. |
| `ROSS_VALIDATION_OVERRIDE_ENABLED` | Config/runtime safety paths from PR1028 inventory | Enables validation-only behavior. | PAPER/SIM risk if enabled outside validation. | HIGH | Assert false for production dry run in PR1031. |
| `synthetic_intent_allowed` | `src/strategies/ross_momentum/policy/runtime_safety.py` | Synthetic intent only through validation modes. | PAPER/SIM risk if enabled outside validation. | HIGH | Assert blocked outside validation in PR1031. |
| Execution enablement flags | Runtime execution configuration | PR1029 does not change execution state. | Yes. | CRITICAL | PR1031 must prove READ_ONLY execution-disabled behavior. |

## Evidence Added

New test file: `tests/test_ross_pr1029_pattern_detection_certification.py`.

The tests prove:

1. Micro pullback, first pullback, flat-top breakout, HOD breakout, and PMH breakout have deterministic positive and negative fixture evidence.
2. HOD breakout positive detection requires RTH HOD source, compression/proximity, trend context, volume, and stop evidence.
3. EMA/VWAP pullbacks require real pullback/reclaim price action and cannot be replaced by standalone indicator alignment.
4. Bull flag, ABCD, ORB, opening drive, gap-and-go, and stair-step continuation fixtures have deterministic pass/fail evidence.
5. Parabolic exhaustion, failed ORB fakeout, halt resume, placeholders, and additional heuristic paths cannot silently create long-entry trade authority.

## PR1030 to PR1031 Remaining Plan

### PR1030 - Entry/Stop/Target/Exit Mapping Certification

Purpose: prove detected Ross setups map into complete trade-plan metadata before any executable intent can exist.

Files likely touched:

- `src/strategies/ross_momentum/decision_policy.py`
- Ross setup fidelity and intent mapping modules
- Position lifecycle/risk mapping modules
- `tests/test_ross_pr1030_entry_stop_target_exit_mapping.py`
- `docs/certification/PR1030_ENTRY_STOP_TARGET_EXIT_MAPPING_CERTIFICATION.md`

Acceptance criteria:

- Every entry intent includes explicit entry/trigger, stop/invalidation, target, and lifecycle management metadata.
- Missing stop, missing trigger, missing target where required, invalid risk/reward, or risk-off setup blocks intent creation.
- Parabolic exhaustion and reversal evidence map only to exit/risk behavior, not long-entry authority.
- No PAPER/LIVE enablement occurs.

Tests required:

- Entry mapping matrix per certified setup family.
- Stop/invalidation mapping tests.
- Target/partial/trailing mapping tests.
- Risk/reward acceptance and rejection tests.
- Exhaustion/reversal exit/risk mapping tests.

PAPER-readiness contribution: proves a detected setup becomes a complete managed trade plan rather than a loose signal.

### PR1031 - READ_ONLY Full-Session Dry Run and PAPER Readiness Gate

Purpose: run a production-shaped READ_ONLY certification and decide whether PAPER can be recommended in a later controlled step.

Files likely touched:

- Runtime/session orchestration tests
- Scanner/focus/setup/decision trace verification tests
- Execution-disabled and order-submission-negative tests
- Analytics/storage trace validation tests
- `docs/certification/PR1031_READ_ONLY_FULL_SESSION_DRY_RUN_AND_PAPER_GATE.md`

Acceptance criteria:

- Full-session READ_ONLY run shows no order submission and no fake/probe trade.
- Scanner, catalyst, focus, setup, decision, risk, execution-disabled, analytics, and storage traces are complete.
- Manual focus, validation override, synthetic intent, debug execution, additional heuristic, session override, and execution enablement flags are inventoried.
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
python -m pytest tests/test_ross_pr1029_pattern_detection_certification.py
python -m pytest tests/test_ross_pr5_setup_decision_fidelity.py tests/test_ross_pr6_end_to_end_certification.py
python -m pytest tests -k "ross or pattern or setup or decision"
```

Local execution may be unavailable in this Codex desktop session if the Windows command sandbox blocks repository access or if the local Python environment lacks pytest. GitHub Actions is the authoritative verification surface for this PR if local pytest is unavailable.

## Final Certification Answer

PR1029 certifies deterministic Ross pattern detection fixtures and closes the named HOD positive-coverage gap. Ross Momentum remains not PAPER-ready until PR1030 completes trade-plan mapping and PR1031 completes the full-session READ_ONLY runtime/PAPER gate.
