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
