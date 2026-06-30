# PR1028 Ross Autonomous Scanner and Catalyst Runtime Certification

## Scope

This certification PR covers the Ross Momentum autonomous scanner path from scanner request through ranked watchlist K and focus M selection, plus catalyst/news status semantics at the scanner/focus boundary.

This is a certification and evidence PR. It does not change trading thresholds, enable PAPER or LIVE, weaken Ross gates, create fake trades, broaden execution authority, or add implementation paths outside the tested scanner/catalyst surface.

## Executive Verdict

```text
PAPER_READY: NO
ROSS_AUTONOMOUS_SCANNER_CATALYST_CERTIFICATION: PARTIAL
SCANNER_RUNTIME_EVIDENCE: CONTROLLED_READ_ONLY_REPLAY_CERTIFIED
CATALYST_RUNTIME_EVIDENCE: POLICY_AND_CONTEXT_CERTIFIED_WITH_LIVE_FEED_GAP
MAIN_BLOCKERS:
1. Real full-session READ_ONLY news/catalyst feed provenance is not yet certified.
2. Remaining Ross pattern-family positive/negative detection is not fully certified.
3. Entry/stop/target/exit mapping and production READ_ONLY dry-run behavior are not yet certified end to end.
NEXT_REQUIRED_PR: PR1029 Remaining Ross Pattern Detection Certification.
DO_NOT_GO_PAPER_REASON: PR1028 proves controlled READ_ONLY scanner/focus and catalyst status behavior, but not full-session production runtime evidence from live scanner/news/catalyst feeds through setup, decision, risk, execution-disable, and storage traces.
```

PAPER readiness remains blocked. PR1028 closes part of the PR1027 scanner/catalyst gap by adding deterministic runtime scanner replay evidence and catalyst policy/status assertions. It does not claim that live market/news feeds have been certified across a full session.

## Certification Result

| Area | Verdict | Evidence | Remaining gap |
| --- | --- | --- | --- |
| Autonomous scanner entry contract | PASS | `test_pr1028_readonly_scanner_cycle_ranks_watchlist_and_focus_without_manual_focus` calls `run_scanner_cycle` with a controlled provider and strategy scanner request. | Live IBKR scanner cycle proof still belongs to full READ_ONLY dry run evidence. |
| Watchlist K ranking | PASS | Controlled READ_ONLY replay produces bounded `watchlist_k_symbols`, scanner contract validity, provider source, and ranking intent. | More real-symbol ranking traces across market sessions. |
| Focus M narrowing | PASS | Focus M is non-empty, bounded by policy, and a subset of Watchlist K. | Full-session focus churn and persistence trace. |
| Manual focus independence | PASS | Watchlist rows are produced from the scanner provider; test asserts no `manual_focus` source and no prep seed. | Runtime operator/manual-focus configuration audit in PR1031. |
| High/unknown float rejection | PASS | PR1028 hard rejection test asserts high float and unknown float do not reach watchlist/focus in READ_ONLY. | External float provider freshness/source audit in live runtime. |
| Weak gap and low RVOL rejection | PASS | PR1028 hard rejection test asserts weak percent gap and low RVOL are dropped before watchlist/focus. | More per-session low-liquidity and degradation traces. |
| Missing catalyst behavior | PASS | PR1028 candidate/context test proves missing catalyst fails selection and focus as `DROP_NO_CATALYST`. | Live RSS/provider missing/stale/unavailable trace in full-session run. |
| Catalyst source/freshness/status fields | PARTIAL | Candidate metrics preserve `news_count`, `fresh_news_count`, `stale_news_count`, `top_news_catalyst_tag`, `news_source_mode`, and `news_asof` from deterministic context. | Real feed source/freshness evidence is not full-session certified. |
| Catalyst override safety | PASS | Catalyst policy matrix proves PAPER validation bypass is explicit and READ_ONLY does not accept the bypass. | PR1031 must assert production env flags are disabled. |
| PAPER readiness | FAIL | No production PAPER or full-session READ_ONLY execution-disable run is added here. | Complete PR1029-PR1031. |

## Evidence Added

New test file: `tests/test_ross_pr1028_autonomous_scanner_catalyst_certification.py`.

The tests prove:

1. A READ_ONLY scanner cycle can produce ranked watchlist K and focus M candidates from a controlled provider without manual focus or prep seeding.
2. Scanner contract diagnostics remain valid and preserve the Ross ranking intent.
3. High float, unknown float, weak gap, and low RVOL candidates do not enter watchlist K or focus M.
4. Catalyst/news context fields are preserved into `CandidateMetrics` and selection rationale.
5. Missing catalyst fails both watchlist selection and focus admission when the policy requires catalyst evidence.
6. Catalyst status semantics distinguish confirmed, absent, unknown, unavailable, PAPER validation bypass, and READ_ONLY bypass rejection.

## Scanner Runtime Trace Matrix

| Stage | Required Ross evidence | Current code/test evidence | Missing evidence | Status | Required PR/fix |
| --- | --- | --- | --- | --- | --- |
| Scanner request | Strategy policy creates scanner request with top N, scan code, instrument, price range, ranking intent. | PR1028 uses `scanner_request_from_policy` and asserts `ROSS_MOMENTUM_STOCK_SELECTION`. | Real broker request/response capture. | PASS | PR1031 runtime trace. |
| Provider universe | Autonomous provider returns ordered top-gainer symbols. | Controlled provider returns ordered `PR28A`-`PR28D`; payload top N preserves order. | Live IBKR returned rows and attribution. | PARTIAL | PR1031 full-session READ_ONLY. |
| Gate enrichment | Quote, percent change, RVOL, float, volume, spread, and reference context are merged before ranking. | Controlled provider supplies deterministic quote, intraday stats, float, ADV, and history hooks. | Live missing-field inventory. | PARTIAL | PR1031 storage/runtime review. |
| Watchlist K | Eligible symbols rank into bounded watchlist. | PR1028 asserts non-empty bounded watchlist and valid scanner contract. | Multi-cycle live churn and rank-decay proof. | PASS | PR1031. |
| Focus M | Best watchlist symbols narrow into bounded focus list. | PR1028 asserts non-empty focus and subset of watchlist. | Live focus persistence and demotion trace. | PASS | PR1031. |
| Manual focus | Manual focus must not be required for discovery proof. | PR1028 asserts no `manual_focus` source and no prep seed. | Runtime configuration inventory. | PASS | PR1031. |
| Hard rejects | High/unknown float, weak gap, low RVOL, weak liquidity, stale/missing critical data must not reach setup. | PR1028 covers high/unknown float, weak gap, low RVOL; PR3/PR1027 cover additional hard-rejection behavior including liquidity/data quality. | Full live reject ledger. | PARTIAL | PR1031. |
| Setup handoff | Only focus M should be eligible for setup evaluation. | PR1028 certifies focus M production; PR1027 certifies scanner/catalyst rejects stop before setup. | Runtime trace from focus M into setup engine. | PARTIAL | PR1029/PR1031. |

## Catalyst Runtime Matrix

| Catalyst state | Expected Ross behavior | Current evidence | Decision behavior | Status | Required PR/fix |
| --- | --- | --- | --- | --- | --- |
| Confirmed fresh catalyst | Candidate may continue if all scanner/focus gates pass. | Deterministic context preserves source/freshness fields and `catalyst_summary`. | `catalyst_ok=True`; selection can include candidate. | PASS | Live feed proof in PR1031. |
| Confirmed but stale/degraded | Candidate should carry freshness/degradation evidence and be blocked/degraded according to policy. | Candidate metrics preserve stale/fresh counts; policy exposes non-confirmed statuses. | Fixture-level preservation only. | PARTIAL | Add real stale-feed replay/full-session trace. |
| No catalyst found | Candidate must not silently continue when catalyst is required. | Missing catalyst candidate has `catalyst_ok=False`; focus returns `DROP_NO_CATALYST`. | Blocks selection/focus. | PASS | PR1031 live trace. |
| News unavailable | Must be explicit, not treated as confirmed catalyst. | Catalyst policy returns `DATA_UNAVAILABLE` with `news_unavailable`. | Not satisfied. | PASS | PR1031 source outage trace. |
| News disabled | Must be explicit and not silently bypassed in READ_ONLY. | Catalyst policy returns `DATA_UNAVAILABLE` with `news_disabled` in READ_ONLY. | Not satisfied. | PASS | PR1031 env audit. |
| PAPER validation bypass | Allowed only as explicit validation behavior, never hidden PAPER readiness. | Catalyst policy returns `DISABLED_FOR_VALIDATION` only when PAPER/SIM validation bypass is requested. | Satisfied for scoped validation only. | PASS | PR1031 must prove disabled in production dry run. |
| READ_ONLY validation bypass request | Must not satisfy catalyst. | Catalyst policy returns `DATA_UNAVAILABLE`, not validation bypass. | Not satisfied. | PASS | PR1031 config gate. |

## Failure Trace Table

| Stage | Expected Ross behavior | Current observed behavior | Gap | Severity | Required fix | Proposed PR |
| --- | --- | --- | --- | --- | --- | --- |
| Scanner | Autonomously discover Ross-like low-float, high-RVOL, strong-gap symbols. | Controlled READ_ONLY replay proves runner contract and ranking path. | Live IBKR full-session discovery is not certified. | HIGH | Capture full-session READ_ONLY scanner trace. | PR1031 |
| Catalyst/news | Require confirmed catalyst or explicit unavailable/absent status. | Policy/status matrix and CandidateMetrics preservation are certified. | Real feed provenance/freshness not full-session certified. | HIGH | Add live/replayed feed trace with source/freshness/outage evidence. | PR1031 |
| Watchlist K | Rank and cap candidates with explainable reason codes. | PR1028 asserts bounded watchlist, valid contract, ranking intent, and provider source. | More real-symbol session traces. | MEDIUM | Store ranked watchlist reason-code artifacts. | PR1031 |
| Focus M | Narrow to best execution candidates and reject missing catalyst/quality gaps. | PR1028 asserts focus subset and catalyst drop. | Full-session focus churn and demotion behavior. | MEDIUM | Runtime focus trace and persistence audit. | PR1031 |
| Pattern inputs | Build setup inputs only after watchlist/focus acceptance. | PR1027 proves scanner/catalyst rejects stop before inputs; PR1028 proves focus generation. | Live focus-to-input trace missing. | HIGH | Runtime setup-input trace from focus M. | PR1029/PR1031 |
| Setup detection | Detect remaining Ross families without false positives. | PR1027 covers a subset; PR1028 does not expand pattern detection. | Remaining pattern families not certified. | HIGH | Complete pattern positive/negative matrix. | PR1029 |
| Decision policy | No intent unless valid setup, trigger, stop, rationale, and session policy pass. | PR1027 covers decision boundary; PR1028 does not change it. | Production dry-run env state not certified. | HIGH | READ_ONLY dry-run decision trace. | PR1031 |
| Risk/execution boundary | READ_ONLY never submits orders; PAPER remains disabled until certified. | PR1028 adds no execution authority. | Full-session execution-disabled trace missing. | CRITICAL | Verify no order submission path during READ_ONLY. | PR1031 |
| Analytics/storage | Persist scanner, focus, rejection, catalyst, and no-trade evidence. | PR1028 tests inspect returned payload; no storage implementation change. | Runtime persistence completeness missing. | MEDIUM | Storage artifact review. | PR1031 |
| PAPER readiness | PAPER only after scanner, catalyst, patterns, mapping, risk, execution-disable, and storage pass. | Still blocked. | PR1029-PR1031 incomplete. | CRITICAL | Finish staged certification. | PR1031 |

## Fallback / Bypass Inventory

| Flag/path | File/function | Current effect | Can affect PAPER/LIVE? | Risk | Required action |
| --- | --- | --- | --- | --- | --- |
| Manual focus | `src/core/orchestrator.py::load_manual_focus_config`; Ross strategy handoff | Can seed operator focus candidates, but PR1028 discovery test does not require it. | Candidate set only; must not grant trade authority. | MEDIUM | PR1031 must prove manual focus cannot bypass setup/risk/execution. |
| Prep seed/backfill | `src/scanner/scanner_runner.py::_seed_watchlist_from_prep`; backfill branch in watchlist build | Can add PRE prep candidates under scoped conditions. | Could affect PAPER candidate universe. | MEDIUM | Keep disabled/out of scope for PR1028 proof; audit during PR1031. |
| Mock provider/news | `MockScannerProvider`; `_enrich_news_context` mock injection path | Mock source can inject mock headlines only for MOCK provider behavior. | Must not affect LIVE; PAPER only under validation discipline. | HIGH | PR1031 must assert real provider or explicit validation mode. |
| PAPER validation bypass | `assess_catalyst`; validation override helpers | PAPER/SIM validation bypass can satisfy catalyst only when explicitly requested. | PAPER yes if enabled. | HIGH | Require disabled production env before PAPER readiness. |
| READ_ONLY bypass request | `assess_catalyst`; `validation_override_allowed` | READ_ONLY bypass request is not accepted; returns unavailable if news disabled/unavailable. | READ_ONLY should not trade. | LOW | Keep test coverage. |
| `ROSS_VALIDATION_OVERRIDE_ENABLED` | config resolver and scanner runtime | Activates validation-only behavior in SIM/PAPER. | PAPER yes. | HIGH | PR1031 config inventory must assert false unless scoped test. |
| `synthetic_intent_allowed` | `src/strategies/ross_momentum/policy/runtime_safety.py` | Allows synthetic intent only through validation override modes. | PAPER/SIM yes; LIVE/READ_ONLY no. | HIGH | Keep blocked outside validation; assert in PR1031. |
| `debug_force_execution` | `IntentPolicyConfig.debug_force_execution`; decision policy | Can bypass some data-quality flags if explicitly configured. | PAPER/LIVE risk if enabled. | HIGH | PR1031 must assert disabled. |
| Additional heuristic patterns | pattern registry optional config | Experimental hook remains config-gated and not used by PR1028. | Could affect PAPER if enabled later. | MEDIUM | Keep disabled until PR1029 fixtures certify any additions. |
| Execution enablement flags | execution/runtime config surface | PR1028 does not alter execution state. | Yes. | CRITICAL | PR1031 must inventory and prove execution disabled in READ_ONLY. |

## PR1029 to PR1031 Remaining Plan

### PR1029 - Remaining Ross Pattern Detection Certification

Purpose: complete deterministic positive and negative coverage for remaining Ross tradeable setup families.

Acceptance criteria:

- Every enabled Ross tradeable setup family has positive and negative fixtures.
- HOD breakout positive certification is added.
- VWAP/EMA/MACD act as context/degrade/block evidence, not standalone trade authority.
- Exhaustion/reversal/failed-breakout evidence cannot become long-entry intent.

Tests required:

- Pattern-family positive/negative matrix.
- Missing/stale input tests per family.
- Registry no-placeholder/no-silent-fallback tests.

PAPER-readiness contribution: proves valid focus candidates are evaluated by certified Ross setup logic.

### PR1030 - Entry/Stop/Target/Exit Mapping Certification

Purpose: prove Ross setup decisions map into explicit entry, stop, target, partial, trailing, and exit-management metadata.

Acceptance criteria:

- Every trade intent has entry, stop/invalidation, target, and management metadata.
- Missing stop/target where required blocks or degrades as policy says.
- Risk/reward validation is explicit and tested.
- Lifecycle modules can consume Ross intent metadata without broker submission.

Tests required:

- Entry mapping tests.
- Stop/invalidation mapping tests.
- Target/partial/trailing mapping tests.
- Risk/reward acceptance/rejection tests.

PAPER-readiness contribution: proves a setup becomes a manageable trade plan, not just a signal.

### PR1031 - READ_ONLY Full-Session Dry Run and PAPER Readiness Gate

Purpose: run a production-shaped READ_ONLY certification and decide whether PAPER can be recommended in a later controlled step.

Acceptance criteria:

- Full-session READ_ONLY run shows no order submission and no fake/probe trade.
- Scanner, catalyst, focus, setup, decision, risk, execution-disabled, analytics, and storage traces are complete.
- Validation, synthetic, manual-focus, debug execution, session override, and execution enablement flags are inventoried.
- `PAPER_READY` remains `NO` unless every objective gate passes.

Tests required:

- Runtime configuration safety tests.
- READ_ONLY trace verification.
- Execution-disabled/order-submission-negative tests.
- Analytics/storage completeness tests.

PAPER-readiness contribution: final pre-PAPER evidence gate.

## Verification

Target commands:

```powershell
python -m pytest tests/test_ross_pr1028_autonomous_scanner_catalyst_certification.py
python -m pytest tests/test_ross_pr1027_strategy_fidelity_audit.py
python -m pytest tests/test_ross_pr6_end_to_end_certification.py tests/test_ross_pr5_setup_decision_fidelity.py
```

Local execution may be unavailable in this Codex desktop session if the Windows command sandbox blocks file access. In that case, GitHub Actions is the authoritative verification surface for this PR.

## Final Certification Answer

PR1028 improves scanner/catalyst readiness, but Ross Momentum is still not PAPER-ready. The branch certifies a controlled READ_ONLY scanner replay and catalyst status semantics without changing runtime trading behavior. The remaining safe path is PR1029 pattern certification, PR1030 mapping certification, and PR1031 full-session READ_ONLY dry-run/PAPER gate.
