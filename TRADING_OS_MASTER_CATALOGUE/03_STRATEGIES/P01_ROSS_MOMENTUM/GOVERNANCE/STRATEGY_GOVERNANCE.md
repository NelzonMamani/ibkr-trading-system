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
