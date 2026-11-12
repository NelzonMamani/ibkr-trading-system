# P01_ROSS_MOMENTUM — STRATEGY GOVERNANCE (E19/M7 aligned)
Date: 2026-02-08

## 1) Scope
Ross Momentum is a **LONG-biased** momentum continuation strategy for U.S. small-cap gappers/runners.

## 2) Authority
- Core epochs E0–E21 are treated as implemented/certified.
- Metadata epochs M0–M10 govern canon, contracts, verification, and change control.
- Canon registries (SF_*, XL_*, C_*, K_*, SCP_*, MCP_*, levels/zones) are the only valid identifiers.

## 3) Safety and No-Trade contexts (E16)
Ross MUST emit NO TRADE when any of:
- data quality invalid / stale / missing reference price
- spreads/liquidity violate policy
- risk engine denies (daily loss, consecutive loss cap, position limits)
- halts not allowed (unless allow_halts=True and stability confirm passes)
- parabolic exhaustion / climax top guard triggers (policy-defined)
- topping risk HALT triggers

## 4) Tunable Parameter Authority (locked)
All thresholds that affect behaviour MUST live in `strategy_policy.py`:
- stock selection thresholds (price/gap/%change/rvol/float/volume/spread/catalyst)
- setup specs (micro pullback ratios, flag thresholds, ORB range definition)
- topping risk ratios
- mode/time boundaries
- risk/permitted re-entries caps (if used)

No hidden constants elsewhere.

## 5) Traceability (E1/E14/M4)
Every emitted TradeIntent MUST include:
- SF_* id
- XL_* id
- required C_* snapshot
- required K_* snapshot
- key levels used (e.g., VWAP, HOD, ORB)
- numeric values and thresholds used in decision

## 6) Change control (M8)
Any behavioural change requires:
- explicit change log in governance pack
- parameter diff summary
- re-run certification verification suite (E21)

END


## Change control — 11 November 2026 bounded Bull protection

NEW delegated project policy STANDALONE_BULL_POST_PARTIAL_COST_TIGHTENING_V1 is separate default-off synthetic standalone Bull only. Accepted actual2R/floor-half partial remains unchanged; terminal accounted gross-profit, independently reconciled/protected remainder, fresh retained completed execution bar after last partial fill, strict close/executable bid above qualified decimal E0 ceiling, existing immutable expiry and once-only same-ID/TOTAL1 final-write guards are required. OriginalS0/invalidation/TPNone remain distinct. Bull structural failure has priority; no Micro cost-failure or generic trailing/add/relationship/resumption enrollment. Exact source attribution, automation choices, parameter diff, scoped failures/validation and required review/CI/integration are maintained in SAME checkpoint/handoff records. No certification or operational-readiness upgrade is claimed.


## Change control — 11 November 2026 full-Core retained-state quarantine

ExecutionEngine inspects existing PAPER native persisted state before generic startup recovery/capital projection; its existing restart-reconciliation refusal remains latched. StorageEngine distinguishes an absent snapshot from stored non-object JSON. Both repairs follow causal full-Core failures; no policy parameters/defaults/admission thresholds changed. Genuine all33 Bull/Micro retained transitions, actual fresh Core constructors/cycles, storage effects and bounded process/transport controls are maintained in SAME checkpoint/handoff records with failures and overlapping counts. Certification runtime smokes involving real providers/brokers are outside this synthetic-only instruction; required automatic offline CI remains mandatory. No recovery clearing, cold permission reconstruction, operational enrollment or readiness upgrade.


## Change control — 11 November 2026 native canonical daily-risk feedback

Existing maximum-loss/entry-only uncertainty policy now receives actual bound native fill DELTAs through existing ExecutionEngine, canonical lifecycle, SQLite and governor owners. Strict native persistence validates quantities/identity/time and one canonical snapshot/event transaction; separate native progress uncertainty cannot become success or new-entry permission. Factual fills/protection/authorized exits retain their existing authority. Real partial PnL, final counts and mixed-history/day/net identity semantics are proved without a new governor/ledger/stream or legacy activation. Parameter diff: NO loss/admission/default/size/target/management threshold changed; originalS0/invalidation/TPNone and all transport/truth/five-position/capital guards persist. Scoped failures, overlapping validation, independent review/required CI/integration and limitations live in SAME checkpoint/handoff/ONEqueue. Local full development failure and corrected focused checks are retained; final frozen-head automatic offline verification remains required. No real-provider runtime certification smoke, operational enrollment, recovery clearing or readiness upgrade is authorized or claimed.


## Change control — 11 November 2026 source-bound snapshot quality

CHANGE_REQUEST: repair reproduced actual native snapshot scope/cache omissions and ACTIVE Core's incorrect per-symbol quality-map consumption. IMPACT_ANALYSIS: existing raw/domain/manager provenance and optional strict existing-client seam; actual client/epoch cache isolation and two existing profit/cost consumers; legacy APIs retain defaults. CERTIFICATION_DELTA: factual scope/component controls and actual manager/Core quality proof are distinct; helper supplies quality/completeness only, existing freshness/LIVE/session/milestone/final-write gates remain. Parameter diff: NO strategy/management/risk/admission/size/target/quote-age/budget default or threshold changed; E0/S0/invalidation/TPNone and all protections persist. CHANGE_DECISION_RECORD: standing existing-owner causal-repair authority, no new project trading policy or generic fallback; independent P2 prequote check repaired before final exact-head review/automatic offline CI/integration. Immutable causal failures and overlapping focused evidence are maintained in SAME checkpoint/handoff/ONEqueue. No real-provider runtime smoke, operational enrollment, recovery clearing or readiness upgrade. Fresh canonical valuation remains a separate dependency, not implicitly certified by this prerequisite.


## Change control — 11 November 2026 PR1216 Windows quality fixture correction

Required first Windows CI failed seven new raw-quote-script quality fixtures because an unused MarketDataClient constructor bootstrapped a Proactor loop whose loopback socketpair correctly met the hard guard. Existing NS external adapter replaces only that unused constructor; real manager/Core/native owners and all assertions remain, with an explicit narrow no-SDK-bootstrap guard. Production source/parameters/transport protections/CI budgets unchanged. First failed CI/local correction alias failure, overlapping passes and mandatory final-head review/CI/integration are retained in SAME records. No readiness or policy grant.


## Change control — 11 November 2026 strict fresh native valuation

CHANGE_REQUEST: enforce existing configured include-unrealized loss policy through actual source-bound fresh native quotes and durable canonical marks after reproduced absent ACTIVE valuation/swallowed legacy mark persistence. IMPACT_ANALYSIS: existing Core, lifecycle, SQLite pair, governor and execution entry guards; demonstrated cold-worker/Windows optional-loop dependency repaired in the same qualification owner by native ibapi.Contract for an already-bound actual EClient; async branch retained. CERTIFICATION_DELTA: actual full33 native callbacks/Core known-loss/eligible/absence/partial-quantity/uncertainty controls and separate owner persistence/CAS/source checks; source guard component proof remains distinct from new dispatch and natural/broker/cold recovery. Parameter diff: NO daily loss/comparator/default/size/target/management/quote-age or CI budget/gate changed; E0/S0/invalidation/TPNone and protections remain. CHANGE_DECISION_RECORD: existing loss/entry-only uncertainty authority supplies bounded repair, not new trading policy, FX or fee allocation. Immutable causal failures/overlapping checks, independent review/required CI/integration and precise fee-intake continuation live in SAME checkpoint/handoff/ONEqueue. No new manager/ledger/table, real-provider runtime smoke, operational enrollment/recovery clearing or readiness upgrade.


## Change control — 11 November 2026 complete positive native roundtrip fees

CHANGE_REQUEST: consume complete authoritative positive native fee facts under EXISTING round-trip gross-minus-commission/known-NET risk convention after source-loss probe. IMPACT_ANALYSIS: same native request/cache owner supplies strict currency/copied fee facts; existing Exec/Core selects fully terminal standalone exact coverage; existing lifecycle snapshot/event journal and governor NET overlap receive truthful costs. No new service/table/manager/ledger/outcome stream or capital/exit/management behavior. CERTIFICATION_DELTA: genuine full33/native callbacks/Core known-.28 limit feedback, preserved gross/count/flat/capital/replay, source/ownership/currency/day and persistence-uncertainty controls, with exact proof limits. Parameter diff: NO loss comparator/budget/default sizing/quality/caps/target/management/CI gate/budget changed; Factory gross2/fees4/NET2 preserved. CHANGE_DECISION_RECORD: existing-policy terminal same-day same-currency known-POSITIVE standalone subset only; pre-enrollment unsupported data retains established GROSS, selected uncertainty closes entries without suppressing factual fills/erasing confirmed charges. Zero wire-presence/rebates/FX/partial/multi-day/relationship/finality remain excluded; First own post-partial unadopted. Causal failures/overlap/independent exact-head review/required CI/integration and exact continuation in SAME checkpoint/handoff/ONEqueue; no operational enrollment/recovery clearing/readiness upgrade.


## Change control — 11 November 2026 completed literal-zero native fee corroboration

CHANGE_REQUEST: distinguish a narrowly corroborated literal native wire-zero commission from missing/empty/direct SDK default0, then consume complete terminal fee coverage through existing canonical NET feedback. Existing Factory gross2/commission4/NET2 and governor NET/inclusive-loss policy supply arithmetic authority; no new project trading/rate policy or legacy-default source authority.

IMPACT_ANALYSIS: existing IbkrClient first-attempt per-decoder raw-frame proxy delegates the unchanged pinned SDK handler and publishes known-zero witness authority only after normal return/current ownership/one-use corroboration; observed loss is irreversible and unsupported capability leaves positive legacy behavior available. Exact literal0/0.0/raw identity facts, not unforgeable object-call origin or a cloned parser. Existing Exec/TLE/Gov require zero-only witness metadata, SAME snapshot/event journal, nonempty exact execution coverage, strict terminal/currency/day/native scope and durable entry-only uncertainty. Positive normalized records/defaults and factual-fill/protection priority unchanged; no extra ledger/table/manager/outcome or recovery permission.

PARAMETER_DIFF: NO rates, loss comparator/threshold, rounding convention, quote/currency freshness rule, sizing/quality/caps/default1, originalE0/S0/invalidation/TPNone, family/target/management policy or Linux30/Windows60/downstream gate/budget changed. Other zero spellings/negative rebate/FX/partial-multiday/relationship/finality/reconnect/cold scope remains excluded. First own post-partial policy unadopted; operational BE/trailing/adds/resumption OFF.

CERTIFICATION_DELTA: actual first SDK connection/decoder/reader/queue/thread and full33 Core all-zero/mixed NET coverage, durable uncertainty/replay and contradictory-history controls, with all causal source/fixture failures and overlapping exact-source validation in SAME checkpoint/handoff/ONEqueue. Restored ORIGINAL config fixture151PASS then final fallback152PASS; earlier combined485/SIXCore1636 remain pre-fallback source3de evidence, final13Core focused validates the last change. Independent scoped SDK/consumer reviews are complete; final parent/records/head review and required automatic offline certification/CI/checkout-tree verification/integration remain PENDING. No real-provider runtime smoke or operational-readiness certificate.

CHANGE_DECISION_RECORD: standing existing-owner implementation authority, factual known-zero arithmetic only after the complete source/financial contract. Unsupported preselection remains established GROSS/no-NET; selected uncertainty closes entries without erasing confirmed evidence or suppressing factual fills. No natural/broker/atomicity/continuous-protection/fullboot/cold-recovery/operational enrollment, real trading or recovery clearing. Full programme remains unfinished. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


## Change control — 11 November 2026 offline-child inheritance prerequisite

CHANGE_REQUEST: repair a demonstrated test-child native-curl containment gap before offline certification. IMPACT_ANALYSIS: one existing test helper/environment and fake-backend control only; no production/default/policy/CI-budget change. CERTIFICATION_DELTA: independent guard review and7 focused helper controls with all stated measurement limits; failed Yahoo401 probe excluded, unfinished positive/forced-kill proof excluded. Exact identities, causal failures and next action in SAME checkpoint/handoff/ONE queue. No operational readiness, broker/atomicity/cold-recovery grant.


## Change control — 11 November 2026 complete-fee consolidation

Completed positive/literal-zero fee and required offline-child guard source are consolidated without source rewrites after the positive-only mandatory upload failure left CI unaccepted. Existing arithmetic/policy/protections unchanged; exact reviewed81656033 source reused. Full new-head CI/tree/review/expected-head integration is required; old run preserved, no gate/budget/approval waiver.


## Change control — 11 November 2026 PR1218 Windows child launcher

CHANGE_REQUEST/IMPACT_ANALYSIS: resolve23 actual D66 Windows pre-child CreateProcess WinError206 failures by changing ONLY existing supervised test launcher from oversized inline -c source to the EXACT unchanged UTF8 child emitted in its existing private evidence directory. Child AST/string constant32777characters is unchanged; old Windows argv sample32827>32767/new file sample70 are measurements, not local Windows app validation. No production/fee/strategy/risk/startup/recovery/management owner, environment/cwd, transport/SDK/implicit-connect/atomic-enrollment guard,20s supervision/kill/reap/cleanup, Linux30/Windows60 budget or required downstream gate changes.

CERTIFICATION_DELTA: D66 CI43098819844 terminal FAILURE preserves Linux7003 and Windows23FAILED/6981passed; downstream SKIPPED/uploadSUCCESS, actual33bd/ordered8275+D66/tree17bd proof and artifact13893811864 are in SAME checkpoint/handoff. Old89 artifact-service failure and Yahoo401 escaped-provider/forced-kill incident remain distinct historical failures, never passing evidence. Existing argv/source causal1FAILED0.52s then1passed0.40s; frozen affected26passed46.09s covers22 of23 failed cases; the omitted corrupt-null case separately1passed/4warnings2.68s, not included in26. Counts overlap all prior scopes and supply no Windows/CI acceptance. Final changed head/tree/review and complete required automatic Linux/Windows/downstream checks/tree/protected integration remain PENDING. No waiver/docs-only PR/repeated applicability audit.

PARAMETER_DIFF/DECISION: no fee rate/rounding/comparator/threshold/default1/quality/cap/entry/stop/invalidation/TPNone/management policy changed. Strict raw0/0.0/original SDK normal return/current first-attempt/terminal execution/currency/day eligibility, established GROSS fallback/uncertainty, factual-fill/protection priority and all truth/five-position/capital/final-write safeguards remain. Final fee seal carries ONCE into already frozen source8f0 phase/pristine READ_ONLY batch; shared launcher/guard ancestry must be retained. First own post-partial unadopted; operational BE/trailing/adds/resumption OFF/full programme unfinished. No natural/broker/full-boot/cold-recovery/atomicity/operational readiness grant. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


## Change control — PR1218 complete-fee integration seal, 11 November 2026

CHANGE_REQUEST/DECISION: accept existing positive/literal-zero native complete-roundtrip fee feedback plus the required offline-child inheritance guard after exact-head review/full required CI and controlled merge45f7ac82ffba976657ecf03ce1b5de9e397fca84; reviewed/tested/accepted tree2881921c039ecceb65473985270f48b3776f1b1e, ordered8275923c0f5a04f7e4b65989ee5554650d72e13c/719995fde5c4e149ad7aa867caa3a84f85546497. This seals an existing source repair, not new strategy/rate/FX/rounding/threshold/management policy. PARAMETER_DIFF: none beyond already reviewed source behavior; all sizing/default1/quality/truth/five-position/protection/accounting/capital/final-write/uncertainty gates and Linux30/Windows60 budgets remain.

CERTIFICATION_DELTA: required PRCI43107435260 actual complete-success receipt and actual ordered merge/tree/checkouts verified; Automatic accepted-main PUSH https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/43114612680 is IN_PROGRESS, observed2026-11-11 22:47:15 UTC; complete accepted-main success is PENDING, NOT a pass. No Linux/Windows/downstream/artifact outcome or runtime is inferred. The complete PR receipt is not a substitute for this separate main run. Old89/oldCI43089170485 remains terminal mandatory artifact-upload HTML-not-JSON failure with no artifact, despite functional passes. Separate D66/43098819844 failed the Windows full suite/downstream SKIPPED despite upload success; actual cause is FileNotFoundError: [WinError 206] The filename or extension is too long; Windows _winapi.CreateProcess; the child did not start; Root independently measured 32777 inline script characters, exceeding Windows32767 before other arguments/escaping; minimal existing-launcher correction will use same UTF8 script on disk. Not a watcher source change., not assumed to be the old service issue. Neither is relabelled final-head acceptance. No test defect, timeout or new-head acceptance is invented. All local/CI counts overlap; original failures and limits stay in SAME checkpoint/handoff/ONE queue. Raw0/0.0/current first SDK-attempt/original-handler normal-return/terminal/currency/day/exact coverage limits and unavailable preselection GROSS fallback remain; no unforgeable-origin, cold, FX, partial/multi-day/relationship grant. Actual Yahoo401 child escape remains failed/excluded; existing guard repair and failed forced-kill limits are inherited once, never erased by acceptance.

This seal is carried ONCE into the frozen/source-reviewed combined successor164f2cc807f80de78706f72162e50be10f6e7bae/treee18d97d1146ca022824aeab6c9c14f3eca5d60ba, containing reviewed8f0→8a514→164 READ_ONLY/PAPER/GROSS source lineage, for combined validation/final parent/records/head review/full required CI/actual tree verification/expected-head integration. That successor is unaccepted and not part of this financial CI; its detailed proof remains in its own SAME-record chapter. No source copies/new module/docs-only PR/repeated applicability audit or separate phase/PAPER CI cycles. First own post-partial policy unadopted, full programme unfinished and operational BE/trailing/adds/resumption OFF. No broker/provider/trading/holdings/operational capital/recovery clearing or natural/broker/atomicity/continuous-protection/full-boot/cold-recovery/readiness certificate. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


## Change control — 11 November 2026 combined fresh-Core handoff

CHANGE_REQUEST/IMPACT: ONE existing-owner successor batch phase8f0→PAPER8a514a1e→GROSS164f2cc807f80de78706f72162e50be10f6e7bae/treee18d97d1146ca022824aeab6c9c14f3eca5d60ba. Repair existing emitted regular aliases and existing Ross PAPER/SIM cache-only news handoff; prove actual fresh constructor/READ_ONLY denial/PAPER ACK-fill-original protection/protective fill canonical daily GROSS feedback. No new session/news/Governor/management policy, ledger/module/manager or generic fallback; MORNING OpeningDrive denied, LIVE/non-Ross PAPER unchanged, valid cached positive qualification remains separate from acquisition health.

PARAMETER_DIFF: original measured10.30/invalidation10.30/actualfill10.53/S010.2897/objective/TPNone/cadence/quality/default1/caps/truth/five-position/capital/final-write/uncertainty unchanged. Existing synthetic HARD daily limit.20 is explicitly configured (default10 unchanged), not a new budget. No feeNET/currency/zero-first-SDK/broker/cold/operational enrollment authority inferred. Resource cleanup preserves PAPER state, no force-flat.

CERTIFICATION_DELTA: original source5 owner/delta reviews and exact overlapping phase/PAPER96/GROSS142/focused/pure evidence/failures live in SAME checkpoint/handoff. Actual accepted fee M45f7ac82ffba976657ecf03ce1b5de9e397fca84/seal Se556eb559ed19f40f745395d9907b70912e105ae/complete PRCI43107435260; Accepted fee automatic-main CI 43114612680 is RUNNING, observed 2026-11-11 22:57:42 UTC. It is NOT a complete accepted-main success; no Windows/downstream outcome is inferred. Actual combined helpere89122e2a2a88d36e7c2058b1a73e4e88601b3cf, root ancestry469cdfd3/tree22eafb6f ordered164/e556; accepted45f and seal e556 ancestors verified; six other blobs exact; independent launcher and profiler relocation review clear, exact two-line profiler relocation/combined-and-normalized child hashes and three actual positive endpoints PLUS launcher guard4 passed, 6 warnings, 7.23s; three endpoints plus launcher/offline regression; /workspace/pristine-core-combined-accepted-parent-positives-20261111.log remain distinct from old8f0/8a/164 source receipts. Final head/records review/full required CI/actual checkout/ordered-parent/tree verification/protected integration remain pending, no acceptance-by-local-pass or two successor CI cycles. Parent owns Yahoo/Windows-failure incident chapters, retained without duplication or retrospective offline claim.

ONE next:Prove fresh-constructor native PMH positive-fee NET-.28/configured.26 actual Core veto using real CommissionReport .01 entry+.02 exit on the exact USD executions, plus actual owned ACCOUNT_CURRENCY_STRICT SDK62/63 All/$LEDGER/USD/accountSummaryEnd/owned query cancellation. Reuse existing TradeOutcomeFactory, TradeLifecycleEngine/storage/ExecutionEngine/Core/DailyRiskGovernor policy and current synthetic child; no prepared AccountCurrencyResult or NET fields. Preserve exactly two financial events plus one fee auxiliary event/coverage2/count1, flat truth and replay safety. This is missing fresh-process fixture evidence, not a demonstrated production defect or new policy; no zero-first-SDK, broker/cold/operational claim. First own post-partial policy remains unadopted. First own post-partial unadopted/full programme unfinished; operational BE/trailing/adds/resumption OFF and all parked/truth/accounting/protection/replay safeguards remain. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


## PR1219 Windows redirected-stdio repair — 12 November 2026 candidate

CHANGE_REQUEST/IMPACT/PARAMETER_DIFF: TEST helper UTF8 child stdio and matching parent decoding ONLY; original embedded child, production/policy/lifecycle/guards/budgets unchanged. CERTIFICATION_DELTA: PR1219 failed3c/review5866481696/CI43116688092 remains unaccepted: actual4a58 ordered45f/3c/tree6b correct, Linux7153passed, Windows3FAILED/7151passed; serial/cache/PS-exit/harness/parser SKIPPED/uploadSUCCESS. Existing helper8c0d23e0 independently clears explicit child/Popen UTF8 after cp1252 Unicode logging caused SKIP_STAGE/cycleFalse and secondary PAPER LEG. Embedded child4c3cc9dd unchanged; all owners/assertions/guards/20s/CI budgets preserved. Causal READ_ONLY1FAIL2.52s/two PAPER2FAIL7.82s/guard1FAIL0.38s remain failures; local adverse4PASS7.79s, final guard1PASS0.37s(overlap4), cold23PASS43.07s remain overlapping Linux encoding controls, not Windows/CI acceptance. Exact counts/artifact/logs/history are in SAME checkpoint; final new-head review/full automatic CI/tree verification/protected integration pending. No new policy/readiness or repeated proof chapter; First own post-partial unadopted/all protections/off/parked work unchanged. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

PR1218 automatic-main43114612680 COMPLETE SUCCESS, FIRST attempt: BOTH actual checkouts45f7ac82ffba976657ecf03ce1b5de9e397fca84/tree2881921c039ecceb65473985270f48b3776f1b1e; Linux7003/3skipped/664.56s and Windows7004/2skipped/2435.18s, all required gates, artifact13900601552/727388bytes/SHA2569cdff450f96e107752ef8fadee395df2a24dda7df2e22637a472f79dd7373b34. Carried ONCE here; earlier point-in-time pending paragraphs remain, no separate parent-main docs PR/CI cycle.


## PR1219 controlled integration receipt — 12 November 2026

CHANGE_DECISION/CERTIFICATION_DELTA: PR1219 controlled merge5fdc23384e8085e31c23a673d239b598fd3c3a55, ordered45f7ac82ffba976657ecf03ce1b5de9e397fca84/44bcaf6a8a3ad851bcadb9d37c2d7e43d980ea8e, reviewed/tested/accepted tree85f3f2f11f9b90311804aa671e88ca0616e4ab11; exact review5867050466 and complete required PRCI43125252706: attempt1; linux7153passed/3skipped/4warnings/820.28s; windows7154passed/2skipped/5992warnings/2312.61s; artifact13905400776/727620bytes/SHA25624307b7d286088369a3e0128d07358247aab2acc544f5a780c2f5b4dd92bb0cc. Previously carried PR1218 automatic-main43114612680 is COMPLETE SUCCESS at45f7ac82ffba976657ecf03ce1b5de9e397fca84/tree2881921c039ecceb65473985270f48b3776f1b1e; its actual complete receipt is reverified, not re-appended as new completion evidence. Failed old3c/review5866481696/CI43116688092 and the corrected UTF8 fixture diagnosis stay in the existing chapters. Automatic M2 main https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/43130952687 IN_PROGRESS, observed2026-11-12 00:56:50 UTC; complete main success remains PENDING, NOT a pass. No Windows/gate/artifact result is inferred. Detailed failures/proof limits stay in SAME checkpoint/handoff. Actual successor18df1875b6462129091ef6bdd7c6ec57dc2be24a/tree881a13136d63443a3ab6593d9cae397a4b99e068: Fresh positive NET, native shutdown ownership repair, and fresh open valuation; local reviewed source with required final-head CI pending; ONE next:Prove the separate fresh literal-zero SDK-first-attempt NET route under existing policy after this batch integrates.. No source-progress/local-count substitution for CI, new policy or natural/broker/cold/operational claim. First own post-partial unadopted/all protections/off/parked work preserved. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## Change control — Fresh native NET, truthful shutdown and open valuation — 12 November 2026 candidate

Accepted-parent input: 5fdc23384e8085e31c23a673d239b598fd3c3a55/tree85f3f2f11f9b90311804aa671e88ca0616e4ab11; actual acceptance evidence: PR1219 review5867050466 CI43125252706 complete success; main43130952687 in_progress at00:56:50UTC. Pre-record source HEAD: 18df1875b6462129091ef6bdd7c6ec57dc2be24a/tree881a13136d63443a3ab6593d9cae397a4b99e068. Provided actual head status: Local source reviewed and validated; final-head PR CI pending. Local source receipts below do not establish a future final-head CI/main result.

CHANGE_REQUEST/IMPACT: source03c6754d completes fresh positive-NET and open-valuation evidence and repairs reproduced native shutdown registry mutation in existing Core/TradeExit owners. Capture stable mode/provider/ownership before disconnect; native/unknown/pending ownership remains incomplete, known simulator teaching scope remains, verify_empty/other resource hooks unchanged. No NameError-only flatten or new exit/cancel/recovery owner/policy.

PARAMETER_DIFF: No strategy/risk/size/target/recurring-management policy, TTL, clock, CI-budget or default change; the production delta is the bounded shutdown ownership fence. E0/S0/invalidation/TPNone/default1/truth/capital/final-write safeguards persist; scenario.20/.22/option-off reuses existing risk policy. CERTIFICATION_DELTA: exact source/definition scoped reviews and local overlapping241/291/16/3 plus focused1/2/1, original failed3.50s/pure1.51s and review corrections are attributed in SAME records; local evidence is not final required CI/integration or native-flat/broker/cold/atomicity/readiness acceptance. First own post-partial remains unadopted; next is separately bounded fresh literal-zero genuine SDK-first-attempt fixture evidence under EXISTING zero policy. All off/parked work persists. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


## PR1220 shutdown-hook test-double correction — 12 November 2026 candidate

CHANGE_REQUEST/CERTIFICATION_DELTA: PR1220 old7ba/review5867429317/run43131346377 has actual Linux1FAIL/7377PASS/3skip/1015.52s on fb091 ordered5fdc/7ba/tree117e; old Windows/full outcome pending. RecordingEngine test double rejected Core's required execution_context keyword. Only its existing shutdown signature/observation is repaired; original assertions remain and actual unknown context/no storage context are checked. Production/guards unchanged. Import-path precollection error is not a test result; correctly scoped original1FAIL0.79s→complete module4PASS0.80s, scopes overlap. Exact test-blob de9eb041 source delta clear; final new-head review/full CI/tree/protected integration pending. Preserve all old failures/CI limits and First pending policy/veto. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
