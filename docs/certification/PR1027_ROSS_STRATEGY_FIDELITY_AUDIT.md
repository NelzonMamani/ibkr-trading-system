# PR1027 Ross Strategy Fidelity Audit

## Scope

This audit covers Ross Momentum strategy fidelity across scanner selection, catalyst handling, setup detection, decision policy, and the risk/execution boundary on current `main` after PR1025.

This is an evidence and certification PR. It does not tune thresholds, weaken selection gates, enable PAPER or LIVE trading, create fake trades, add fallback trade authority, or bypass risk/execution controls.

## Executive Verdict

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

## New Executable Evidence

This PR adds `tests/test_ross_pr1027_strategy_fidelity_audit.py`.

The test suite proves:

1. Positive Ross fixture candidates preserve the full scanner -> watchlist -> focus -> inputs -> setup -> decision -> risk -> safe non-live execution chain.
2. Scanner and catalyst rejection cases stop before pattern inputs, setup detection, trade intent, risk, and execution.
3. Missing catalyst is not silently ignored: it is preserved in diagnostics and rejected as `DROP_NO_CATALYST`.
4. Setup/decision failures never escape to risk or execution when inputs are stale, stop is missing, trigger is missing, exhaustion is detected, or no valid setup exists.
5. The full PR6 matrix contains only the three certified safe non-live successes and the ten certified negative cases.

## Unsafe Fallback And Debug Path Review

| Path | Status | Notes |
| --- | --- | --- |
| Explicit focus fallback into broad watchlist | Closed by PR1025 | Runner guard now filters explicit focus metadata before Ross V1 processing. |
| Synthetic/fake trade fallback | Not introduced | PR1027 adds tests/docs only and creates no intent path. |
| PAPER mode forced intent log path | Conditional, not PAPER-ready proof | Existing decision policy can create a PAPER intent only after a valid setup and trigger-ready signal. PR1027 treats this as fixture/simulation evidence, not broker readiness. |
| `debug_force_execution` | Review before PAPER | The audit does not enable it. It should remain disabled for certification and live-like runs. |
| Validation/session overrides | Review before PAPER | The audit does not enable validation or after-hours overrides. They need explicit dry-run policy coverage before PAPER. |
| Additional heuristic patterns | Config-gated and empty by default | `build_additional_heuristic_patterns()` remains empty unless future code adds experimental families. |

## Pattern Input Gaps vs Pattern Detection Gaps

Pattern-input gaps are no longer the larger blocker for the certified fixture path. The PR6/PR1027 evidence shows 10s, 1m, 5m, indicators, levels, liquidity, float, RVOL, and catalyst context can support valid Ross setup decisions.

The larger blockers are now:

1. live autonomous scanner and catalyst quality evidence;
2. deterministic detection coverage for all remaining Ross tradeable setup families;
3. PAPER dry-run proof that production risk/execution boundaries behave like the certified fixture harness.

## Smallest Safe PR Sequence From Here

1. PR1028 - Ross autonomous scanner and catalyst runtime certification.
2. PR1029 - Remaining Ross pattern detection positive/negative certification.
3. PR1030 - Ross entry, stop, target, partial, trailing, and exit mapping audit against lifecycle modules.
4. PR1031 - READ_ONLY full-session dry run with scanner-driven candidates and no manual focus dependency.
5. PR1032 - PAPER dry-run certification with broker submission boundaries explicitly controlled.
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
