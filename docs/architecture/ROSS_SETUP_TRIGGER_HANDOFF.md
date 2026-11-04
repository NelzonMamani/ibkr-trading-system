# Ross selected setup to intent contract

The production owner is `RossMomentumStrategyV1.process_watchlist`: canonical registry result, DecisionEngine selection, same-family execution-timeframe TriggerEngine, structural price mapping, existing permission/tradeability gates, then intent/cycle selection. `decision_policy.build_trade_intents` is a separate consumer; passing its tests alone does not prove this production boundary.

The original authorities 06 section 8 and 09 section 9 name ORB/premarket-high, micro pullback, bull flag and consolidation breakout as initial families. Failed breakout is caution/exit, with VWAP context. The 68-item reference vocabulary is not blanket entry activation. Accepted flat-top and three-bar/second-pullback extensions retain their existing session, input and trigger policies. Candle-only, disabled halt and risk-off signals do not authorize long entries.

A selected entry must retain its own numeric trigger and structural stop, rationale and approved target model. Entry completeness is now checked before candidate ranking on the local repair branch described below; the defensive selected-use check remains. The generic optional target field does not override Ross's PR1030 target-presence guard. The production intent now retains `target_model`; this descriptive model is not a fabricated numeric take-profit. A missing target or missing canonical selected contract blocks intent with an explicit terminal reason even if the trigger fired. Currently target-less detectors (including ORB and three-bar/second-pullback) remain unavailable for intent until their setup-specific target policy is supplied through the canonical result. This change does not invent that policy.

Core canonical contracts supersede contextual trigger guesses for the same family. PRE/RTH_OPEN use the existing genuine 10s execution stream; steady sessions use the existing 1m stream. Missing/stale execution provenance stays non-actionable. Micro pullback exports its detected pullback high/low; consolidation exports its own range and uses the existing range-break primitive with same-stream volume confirmation. Explicit structural stop and acceptance invalidation remain separate trigger facts; trade geometry uses the structural stop when supplied.

Tests in `test_ross_selected_setup_handoff.py` include real consolidation registry-to-intent checks and explicitly synthetic pre-produced contract handoffs through production functions. They do not certify natural Focus selection, news coverage, Paper order lifecycle or trading readiness. No risk/execution/session/catalyst/volume thresholds are changed.

## Accepted-main setup-family audit — 3 November 2026

Audit source pin `a66b43f2b44d98405d1dc30bc62f8c359a5f3fbc`, tree
`04a58818e178764c28e0fecab472fe1dbbbc0154`. This section preserves the baseline
counterexample and recommendation; the local pre-ranking repair/update below
supersedes its selection-gap status without changing the family target inventory. This updates the existing handoff
audit, not another setup catalogue. The isolated optional-import repair changes
neither strategy, pattern, trigger, management, risk nor execution source.
Original authorities/specifications remain the [strategy contract](../strategy/ROSS_MOMENTUM_STRATEGY_CONTRACT.md),
[PR1029 detection report](../certification/PR1029_REMAINING_ROSS_PATTERN_DETECTION_CERTIFICATION.md),
[PR1030 mapping report](../certification/PR1030_ENTRY_STOP_TARGET_EXIT_MAPPING_CERTIFICATION.md)
and [Bull Flag/Micro relationship policy](ROSS_BULL_FLAG_MICRO_PULLBACK.md).
Old reports describe the layers they actually tested; later accepted source is the
current invocation authority. No registry label is a certification of raw intent.

### Shared real invocation, provenance and downstream boundary

`RossMomentumStrategyV1.process_watchlist` in
`src/strategies/ross_momentum_strategy_v1.py` builds authoritative runtime inputs,
runs Level/Structure/Setup/Trigger engines, then `RossPatternRegistry.run`, then
canonical-result trigger enrichment, `DecisionEngine.compute_decision`, same-family
trigger selection, confirmation, selected-contract/geometry/target checks,
tradeability and per-cycle selection. It does not simply call the standalone
`decision_policy.build_trade_intents` helper. The pre-registry contextual
`SetupEngine` emits PMH, ORB, First/Micro Pullback, Bull Flag, Flat Top, HOD,
VWAP_RECLAIM_CONTINUATION and Consolidation candidates; this is distinct from
calling every canonical detector.

Runtime `patterns/pattern_trace.py::_fetch_runtime_timeframe_bars` requests existing
10s/1m/5m streams. `patterns/pattern_inputs.py::build_authoritative_pattern_inputs` normalizes
original aware bar times, records timeframe/indicator/level provenance, and uses
`policy/pattern_input_policy.py`. PRE/RTH_OPEN primary=1m, execution=10s, context=5m;
RTH_MID/RTH_LATE primary=1m, execution=1m, context=5m. Required/preferred family
checks are applied to the active session plan; a blanket all-day 10s requirement
would misstate the policy. Existing freshness bounds are10s60s/1m180s/5m900s.
Provided indicator values are labelled PRESENT; missing values are computed only
from usable primary candles where supported (EMA9/20, sufficient-history EMA200,
VWAP, MACD), otherwise MISSING/UNAVAILABLE. PRESENT is a provenance label, not an
independent audit of a caller's indicator claim. Optional EMA200/MACD handling
varies by family; no indicator alone creates entry authority.

`setup_fidelity.py::blocking_input_reason` and `apply_detected_setup_fidelity`
enforce scoped BLOCK/non-long/risk-off/missing trigger-stop-rationale rules. The
numeric defaults in `PatternBase._detected` infer trigger/stop from supplied level
context; those are NOT proof of each family's own structural anchors. Runtime
selected-contract review must distinguish them from explicit detector numeric
fields. No target is supplied by that base. `_target_model_from_setup` requires
existing `target_suggestion` or an ABCD projection; it does not manufacture one.
A descriptive target model is not a numeric take-profit/R:R certification.

For eleven families (ORB/PMH/Micro/Bull/Flat Top/Consolidation/Three-bar/Second/Key Level/First Pullback/ABCD),
`_canonical_pattern_trigger_candidates` replaces same-family contextual triggers
with explicit numeric canonical contracts and a genuine execution-stream receipt.
Other registry families do NOT automatically gain this bridge because they have
an isolated trigger evaluator. Contextual setup aliases are normalized separately;
for example Momentum Reclaim normalizes to VWAP_RECLAIM_CONTINUATION, while the
trigger registry has MOMENTUM_RECLAIM. Do not equate those routes without checking
actual emitted setup identity.

After raw formation, `StrategyRunner.process` forwards intents. Core's ACTIVE
manager path in `core/orchestrator.py` preserves arbitration, execution integrity,
position-truth and fresh-quote checks. In READ_ONLY only eligible post-guard intents
receive the existing canonical `build_decision_artifact` ID and actual
`RiskEngine.evaluate_trade_intent`; a real READ_ONLY execution denial is expected.
Five unmatched positions globally block NEW entries AFTER raw formation and BEFORE
canonical artifact/risk admission, so no downstream risk input is expected under
that veto. A later unreachable legacy risk block is not a proof of this path.
PAPER/LIVE canonical risk integration is not certified by the bounded READ_ONLY
repair. No runtime/broker operation is part of this audit.

### Bull Flag / Micro Pullback first

`setup_engine/setup_families/bull_flag.py::BullFlagPattern` is the canonical owner:
standalone breakout uses9 candles (3 impulse, up to5 flag, breakout), EMA9>EMA20,
VWAP/trend, flag depth/width/declining volume and breakout-close checks. Its numeric
flag-high/flag-low trigger/stop/invalidation and descriptive measured-move target
are explicit. `evaluate_formation` uses8 closed structural candles and returns
CONTEXT/non-entry. `micro_pullback.py::MicroPullbackPattern.evaluate` requires at
least5 candles, initial impulse,1-3 controlled bars, <=65% retracement, continuation
close above pullback high and EMA9; it exports its own high/low and Prior high/HOD
target. `evaluate_readiness` is an explicit separate armed mode, not confirmation.

Core wires the existing TradeManagementEngine onto the live Ross strategy.
`compose_bull_flag` therefore governs the normal composed Bull Flag route: positive
conId, eligible session, PRESENT streams, closed parent bars, parent security/
session/origin validity, eligible later same-security Micro child, no reused child,
and child stop respecting parent invalidation. Missing parent/child/security is
rejection, never unpaired standalone fallback. Bull trigger delegates to Micro
confirmation at the recorded child event; standalone trigger crossing/wick/spread/
volume controls are a different supported use. Existing consumed-child persistence
and `prepare_relationship_intent` prevent repeated child use. A repeated unchanged
signal is not a new opportunity.

Management profile BULL_FLAG_MICRO_2R_V1 freezes actual reconciled E0/S0/R0 only
after terminal initial fill; the2R once-only floor-half reduction, floor-quarter
adds, positive confirmed quantities, pending reservations, max logical adds,
reconciliation, stop protection and restore rules belong to the existing management/
risk/execution owners. A target description alone does not activate this profile
on another family. Standalone families retain existing generic management controls;
no new partial/R:R policy is inferred from PR1030.

Existing tests: `test_bull_flag_trigger.py` (armed/fired/shape/liquidity),
`test_micro_pullback_execution_refinement.py` (detection, missing levels, armed/fired,
refinement), `test_ross_bullflag_micro_management.py` (real registry+composed child ->
actual strategy -> risk/in-memory execution; missing/stale/cross-security/parent/
child/duplicate/restart/fill/stop boundaries), `test_bull_flag_pipeline_end_to_end.py`
(standalone detector/trigger/decision layer), `test_ross_selected_setup_handoff.py`
(real Micro numeric contract and synthetic selected handoffs).
`test_readonly_manager_risk_handoff.py` replaces the strategy after Core wiring,
uses standalone real BullFlag detection and synthetic supported-news/cached Focus,
and proves actual manager artifact/risk/ownership boundaries. It does NOT by itself
prove the composed relationship/news/Core combination; the composed test and Core
test are separate proofs, neither natural market proof. Preserve that gap.

### Every registered enabled family: current coverage map

Scope:28 registry entries (26 TRADE_READY,2 PROBATIONARY),27 unique detector IDs;
Ross also contains6 inactive candle placeholders. The map includes registered
families that are currently blocked; it does not activate them. Every row shares
above session/input/catalyst/quote/ownership/risk gates. Minimum bars below are
local detector minima, not sufficient runtime data requirements.

Source abbreviations: **RF**=`src/setup_engine/setup_families/ross_families.py`;
**PB**=`.../pullbacks.py`; **BR**=`.../breakouts.py`; **CP**=`src/strategies/common/patterns/`;
**TR**=`src/strategies/common/triggers/trigger_registry.py`. All canonical detectors
are instantiated by `setup_engine/registry.py::build_tradeable_patterns` and invoked
by Ross registry except explicit placeholder skips. **C**=explicit canonical-result
execution bridge above; **X**=only contextual setup route; **G**=no complete actual
Ross trigger production route established. Existing tests are under `tests/`.
**D** means deterministic detection evidence, **H** a tested synthetic handoff;
neither is natural evidence. No natural positive formation is established for ANY row.

| Registry family / detector | Required structure, candles, indicators/levels | Trigger vs detection; stop/invalidation and target policy | Existing test evidence / actual production limit |
| --- | --- | --- | --- |
| BULL_FLAG / `bull_flag.BullFlagPattern` P_BULL_FLAG | 9 standalone/8 parent;1m plus genuine session refinement; EMA9/20,VWAP; parent/child details above | C; standalone breakout distinct from composed Micro confirmation; explicit flag or child stop; measured move / composed2R profile | Bull/Micro tests above; D/H, separate actual Core READ_ONLY proof; natural UNPROVEN |
| MICRO_PULLBACK / `micro_pullback.MicroPullbackPattern` P_MICRO_PULLBACK | >=5, impulse+1-3 bars+continuation; EMA9; active-plan1m/10s requirements | C; armed vs break trigger separate; explicit pullback low stop/invalidation; Prior high/HOD model | `test_micro_pullback_execution_refinement`, `test_ross_selected_setup_handoff`, PR1029 positive/negative; D/H |
| FIRST_PULLBACK / RF.FirstPullbackPattern P_FIRST_PULLBACK | >=6,3-bar impulse+2-bar controlled first pullback+reclaim; EMA9/20 scoped policy | C after local repair below; own pullback-high trigger, pullback-low structural stop/invalidation, unchanged descriptive impulse-high/extension target; existing registered evaluator | `test_first_pullback_production_handoff`: actual RF registry/V1 on synthetic fresh streams, no target completion; PR1029 controls retained. Natural progression and numeric management remain unproven; common detector remains a distinct owner |
| GAP_GO / RF.GapGoPattern P_GAP_GO | >=4, prior-close gap, level pressure, spread/RVOL, VWAP/EMA context; ORB_GAP_GO policy1m/5m | G in current actual setup producer; TriggerEngine has explicit GapGo special evaluator, but SetupEngine does not emit GAP_GO and C omits it. Inferred anchors; HOD-extension model | `test_gap_go_pipeline_activation`, PR1029 D and engine unit controls; no complete actual strategy invocation proof |
| GAP_CONTINUATION / RF.GapGoPattern P_GAP_GO | Exact same implementation/input as GAP_GO | Registered alias causes SECOND same-ID evaluation; not independent signal/confirmation | Registry inventory proves duplicate; no independent family entry or natural proof |
| ORB / BR.OpeningRangeBreakoutPattern -> CP.detect_orb P_ORB | >=6, REGULAR/open phase; ORH/ORL, volume, VWAP/EMA/MACD/context; ORB policy1m/5m | C; registered ORB confirmation; numeric ORH/structural OR-low stop/invalidation; NO target model | `test_orb_pattern`, PR1029 D; selected-handoff tests supply synthetic target or assert missing_target. Real detector remains target-blocked |
| PREMARKET_HIGH_BREAK / BR.PremarketHighBreakPattern -> CP.detect_premarket_high_break | >=2, original PMH, hold/acceptance/volume/spread; PMH policy1m, preferred5m/10s | C; registered PMH break/hold; explicit stop distinct from PMH acceptance invalidation; HOD/next-resistance target | `test_ross_selected_setup_handoff` H; PR1029 D; PR1082 structural invalidation/missing/stale boundaries |
| CONSOLIDATION_BREAKOUT / BR.ConsolidationBreakoutPattern P_CONSOLIDATION_BREAK | >=8, own compressed range and volume; genuine execution stream | C; range-break evaluator, explicit range high/low stop/invalidation; Range expansion model | `test_ross_selected_setup_handoff::test_real_consolidation_registry_to_production_intent` D->H with session/execution boundaries; no natural proof |
| FLAT_TOP_BREAKOUT / PB.FlatTopBreakoutPattern -> CP.detect_flat_top_breakout | >=5, >=3 flat-resistance touches, volume/spread/RVOL; VWAP scoped DEGRADE | C; dedicated flat-top confirmation; explicit resistance/consolidation-low stop; measured range model | `test_flat_top_breakout_pattern` +/-; PR1029 D; selected-handoff H; natural UNPROVEN |
| HOD_BREAK / PB.HODBreakPattern -> CP.detect_hod_break | >=6, RTH-sourced HOD/compression, volume, spread; scoped HOD requirement | X; TR HOD trigger; explicit structural stop/invalidation; NO target model | `test_hod_break_pattern` +/-; `test_setup_family_pipeline_certification` manually builds intent, NOT actual V1 target admission. Target remains missing |
| OPENING_DRIVE / PB.OpeningDrivePattern -> CP.detect_opening_drive | >=5, RTH opening phase/impulse/volume/limited pullback | G; dedicated TR evaluator but actual contextual producer has no OPENING_DRIVE and C omits it; explicit trigger/stop; NO target model | `test_opening_drive_pattern` and PR1029 +/- D; no complete actual V1 raw-intent proof |
| KEY_LEVEL_BREAK / RF.KeyLevelBreakPattern P_KEY_LEVEL_BREAK | >=2, specific prior-known key level, continuation/liquidity acceptance | C after local bridge repair below; existing registered TR evaluator; explicit selected level and structural stop/invalidation; next-overhead-key descriptive model | `test_key_level_break_pattern` detection/trigger controls and `test_key_level_break_production_handoff` actual unmodified registry/V1 raw-intent proof on synthetic fresh streams; natural progression and numeric target/management certification remain unproven |
| ABCD / RF.ABCDPattern P_ABCD | >=7 observed bars, confirmed swing sequence A/B/C from completed primary prefix, bounded60/retracement; scoped MACD DEGRADE | C after local bridge/review below; own trigger/C stop/invalidation and D facts; right-hand swing witness must have completed; no automatic numeric take-profit | `test_abcd_production_handoff` actual registry/V1 raw intent on synthetic streams, completion/window/malformed/future/duplicate/snapshot controls. Numeric management/intrabar/natural progression NOT certified |
| CUP_HANDLE / RF.CupHandlePattern -> CP.detect_cup_handle | >=14, rounded cup/rim, tight handle, contraction/volume/continuation | G; dedicated TR evaluator but no contextual producer/C; explicit handle-low stop; NO target model | `test_cup_handle_pattern` +/- D; missing production bridge and target |
| EMA_PULLBACK / PB.EmaPullbackPattern -> CP.detect_ema_pullback | >=6, impulse, EMA9/20-zone/reclaim, contraction/RVOL/spread; optional VWAP | G; TR evaluator exists, no EMA contextual producer/C; explicit structural stop/invalidation; NO target | `test_ema_pullback_pattern`, `test_ema_pullback_trigger`, `test_ema_pullback_pipeline_certification` are D/engine-layer proofs, not actual V1 target admission |
| VWAP_PULLBACK / PB.VwapPullbackPattern -> CP.detect_vwap_pullback | >=6, VWAP support/test/reclaim, contraction, trend/liquidity | G for SAME canonical VWAP_PULLBACK identity; contextual VWAP_RECLAIM_CONTINUATION is a distinct normalized route. Explicit stop/invalidation; NO target | VWAP pattern/trigger/pipeline tests D/engine-layer; do not claim equivalent canonical route or raw intent |
| MOMENTUM_RECLAIM / RF.MomentumReclaimPattern | >=4, shakeout then VWAP/EMA reclaim; price action, not indicator alone | X alias VWAP_RECLAIM_CONTINUATION; dedicated TR named MOMENTUM_RECLAIM differs from emitted alias. Stop partly inferred; Prior swing high model | Existing binding/PR5 helper coverage; actual same-family source/trigger authority is partial, not a proven full positive V1 lifecycle |
| THREE_BAR_PULLBACK / PB.ThreeBarPullbackPattern | >=5 armed window: impulse+3 controlled contracting bars; active1m/10s requirements | C; family-specific armed/ready/invalidated trigger; own pullback stop/invalidation; NO target | `test_pr1082_trigger_to_intent_terminal_semantics` +/- boundaries; synthetic supplied-target H explicitly NOT detector target policy |
| SECOND_PULLBACK / PB.SecondPullbackPattern | >=5 distinct first-pullback/recovery/second-pullback structure; active5m/1m/10s policy | C; distinct second-pullback trigger; own structural stop/invalidation; NO target | PR1082 natural-shape unit controls and selected-handoff H; real target absent |
| TREND_CONTINUATION_STAIR_STEP / PB -> CP.detect_trend_continuation_stair_step | >=5, stair-step higher-low/impulse/shallow pullback; scoped1m/5m and EMA9/20 | G; TR stair-step evaluator exists, no contextual producer/C; own stop/invalidation; NO target | stair_step pattern/trigger/pipeline tests +/- D/engine layer; not complete actual V1 proof |
| RANGE_BREAK / PB.RangeBreakoutPattern | >=5 and last close > previous close: only inherited simple-continuation heuristic, NOT a range-specific validated detector | G; no TR mapping/C/contextual route; numeric anchors inferred by base; NO target | binding test conditional-fields assertion is not dedicated positive/negative range certification; new offline audit confirms target/mapping limits |
| ASCENDING_TRIANGLE / PB.AscendingTriangleBreakoutPattern | Same >=5 simple-continuation implementation; no own triangle geometry checks | G; no TR mapping/C/contextual route; base-inferred stop; NO target | Same conditional binding limitation; not proved triangle or entry authority |
| PENNANT / PB.PennantBreakPattern | Same >=5 simple-continuation implementation; no own pennant geometry checks | G; no TR mapping/C/contextual route; base-inferred stop; NO target | Same conditional binding limitation; not proved pennant or entry authority |
| GAP_FILL / RF.GapFillReversalPattern | >=5, gap vs prior close, fill test and rebound confirmation | G; no family TR mapping/contextual/C; anchors inferred; VWAP/opening-range-reclaim model | Conditional binding only located for this registry path; complete actual V1 confirmation/intent unproven. Do not add generic breakout as substitute |
| OPENING_FAKEOUT / RF.OpeningFakeoutPattern | >=6, opening wick rejection/failure | SHORT; fidelity rejects non-long before entry arbitration; no long target activation. Above-wick stop, midpoint/OR-low description | Existing registry/binding/non-long guards; no long-entry authorization or new short policy |
| FAILED_ORB_FAKEOUT / RF.FailedOrbFakeoutPattern | >=7, REGULAR failed OR-high probe/reentry | SHORT; non-long rejection intentional; no long-entry authority. Above-wick stop/OR-mid-low description | PR1029 positive risk/caution then non-long exclusion; opposed-direction DecisionEngine tests are separate synthetic contract controls |
| PARABOLIC_EXHAUSTION / RF -> CP.detect_parabolic_exhaustion | PROBATIONARY, >=5 extension/acceleration/rejection/volume | RISK_OFF/non-entry; suppresses new-entry candidate pool; missing stop/target does NOT authorize filtering away the warning | PR1029, setup-family pipeline risk-off interaction; management exit policy separate; no long-entry proof expected |
| HALT_RESUME / RF.HaltResumePattern | PROBATIONARY; real halt/tape metadata unavailable | Explicit disabled_no_halt_tape_in_pattern_inputs; no entry and no target invented | PR1029 halt-disabled negative; no positive permission |

Six placeholder candle patterns are present in registry iteration but explicitly
skipped `inactive_placeholder`; additional heuristics list is empty. Standalone
common candle/context functions must not be counted as enabled Ross entries.
The older vocabulary contains additional names; it is not runtime enablement.
`test_strategy_runtime_setup_binding::test_all_setups_produce_actionable_fields`
only checks trigger/stop fields IF a supplied fixture detects; it neither proves
positive detection for every family nor checks target or actual V1 handoff.

### Simultaneous families, duplicates and demonstrated selection gap

`DecisionEngine` rejects inactive/non-entry/risk-off candidates, suppresses entries
when parabolic risk is present and rejects opposing-direction conflicts. Compatible
long candidates are ranked deterministically by execution/session compatibility,
contextual setup compatibility, trigger/invalidation availability, non-fallback,
score/confidence and pattern ID. Lower-ranked compatible candidates are explicitly
recorded `dropped_lower_priority_compatible_candidate`; this one-winner behavior
is intentional arbitration, NOT silent deletion or independent confirmation.
It does NOT rank target completeness or trigger readiness. A higher-ranked setup
waiting for its own trigger cannot borrow a different family's ready trigger.

The selected family gets its own trigger; after confirmation the actual V1 code
checks its selected target contract. On failure it continues to the NEXT SYMBOL,
not the next same-symbol family. A controlled counterexample uses an actual Micro
positive detector result (existing Prior high/HOD model), and a synthetic high-score
Three-bar result restoring its real missing target. Micro alone produces one
READ_ONLY raw intent; together, in either input order, Three-bar wins, fires then
fails `missing_target`, and Micro is logged lower-priority and never reconsidered.
This proves a selection/eligibility ORDERING GAP under simultaneous inputs; it
does NOT prove such a combination occurred naturally or invalidate deliberate
one-winner/risk-off/capacity policy. The failed winner and lower loss are visible.

Per-cycle strategy selection ranks only ready candidates by trigger quality,
spread/extension and existing one-submission/capacity limits; explicit terminal
outcomes distinguish lower rank/capacity/no-intent. Relationship child IDs are
consumed/reserved through existing lifecycle authority. GAP_GO/GAP_CONTINUATION
are a duplicate detector invocation (28 objects/27 IDs;34 total registry objects/
33 IDs including placeholders), not two independent opportunities. No loop-level
dedup removes the duplicate evaluation; single selected pattern prevents two
same-symbol strategy outputs in this path. The legacy
`StrategyRunner._apply_one_setup_per_symbol` helper is NOT called by current
`StrategyRunner.process`; do not cite it as the runtime suppression authority.
Core arbitration/integrity/ownership remains a separate post-formation boundary.

### Target gaps, recommendation and evidence limits

NO target model is supplied by the actual ORB, HOD, Opening Drive, Cup Handle,
EMA/VWAP Pullback, Three-bar, Second Pullback, Stair-step, Range, Ascending Triangle
or Pennant detector. Some are blocked earlier by missing actual trigger production.
Existing models for Bull/Micro/Flat Top/Consolidation/First Pullback/PMH/ABCD/GapGo/
KeyLevel/MomentumReclaim/GapFill are not blanket numeric take-profit or lifecycle
certification. Not every model-bearing family has a complete current V1 route.

Highest-priority demonstrated repair recommendation: enforce the ALREADY mandatory
selected-entry target/contract eligibility BEFORE ranking entry candidates, through
the existing selected-setup/DecisionEngine authority; retain explicit missing-target
reasons and one-winner policy, and keep risk-off/conflict signals intact. Do not
add a target, enable a family, choose around ownership/freshness/session/capacity
vetoes, or broaden a trigger bridge as part of that change. Validate a complete
candidate winning over a known target-less one, all-target-less rejecting, no
cross-family target borrowing, opposing/risk-off suppression, deterministic ties
and no change to post-guard admission. This is a recommendation, NOT implemented
or a claim that all nonselected signals should trade. Separate missing family
bridges/structural anchors and policy decisions remain explicitly outstanding.

Ten disposable guarded offline controls reproduced the above selection gap
(two orderings), four missing registered trigger mappings, duplicate registry alias,
and three simple-continuation missing-target paths:10passed0.63s in
`/workspace/scratch/ross-family-audit-controls.log`. Test source retained at
`/workspace/scratch/test_ross_family_audit_controls.py`; synthetic pre-produced
high-score arbitration inputs are labelled. No acquisition, real broker connection,
mutation or execution permitted. Existing certification suites were inspected and
carried forward, not repeated. No strategy repair/target activation is part of the
isolated dependency patch.

Natural evidence remains separate: archived successful safety receipts establish
zero mutations, cleanup/source/operator equality, not positive setup-to-intent.
No naturally qualifying supported catalyst -> Focus -> fresh inputs -> real setup/
trigger -> raw intent has been established, for any family. The saved corporate
branch retains later3November receipt/RDAC and366-test details; none were copied
as production corporate changes into this audit baseline. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL. Five unmatched positions remain untouched and blocked.

## Local pre-ranking entry-completeness repair — 3 November 2026

Separate branch `fix/ross-entry-contract-selection` starts at reviewed
`89f57a01045d5c158a68eac94c9e9e9258f07b0f` /
`4b7d1402d2aa19cca3a4cc4c97ce86cdc2a4215b`. Dependency repair remains in its
separate ancestor commit; corporate/source/SEC work remains excluded/parked.
Implementation commit `b6d8c611004055047be2cccd9028bbe9f2e91c97`, tree
`dea9f788a0103e460ae0482aa3915e1a93a4f421`. Local only, not merged/CI/natural proof.

`decision_policy.validate_entry_contract` composes the ALREADY existing canonical
`is_tradeable_entry_candidate`, risk-geometry predicate and target-model resolver
in their existing policy owner. The standalone intent policy and V1's defensive
selected-use check reuse that same composition instead of duplicated rules.
No target, numerical R:R threshold, trigger authority, source or family is added.
The basic detection validator is unchanged: incomplete detection/context remains
visible, not rewritten into a detector failure just to prune the candidate pool.

The actual V1 invokes the existing DecisionEngine with this explicit Ross entry
validator in BOTH existing arbitration calls. Generic engine callers that omit it
retain their previous behavior. Engine preserves original source objects only
inside the bounded current call; no source object is exported/serialized as part
of its result. It first retains inactive/non-entry/risk-off suppression and original
opposing-direction conflict rejection. It then validates intrinsic entry contracts
before compatibility ranking. Every excluded candidate receives the validator's
actual reason in existing `rejected_candidates` plus the structured rejection log.
Ranking key, scores among eligible candidates and one-winner policy are unchanged.
An incomplete warning or opposing candidate is not filtered away to permit entry.

Before: higher-ranked target-less Three-bar won, later failed `missing_target`,
viable Micro was never selected. After: Three-bar is recorded `missing_target`
before ranking; the real Micro positive result wins in BOTH input orders and
retains its own setup ID/family, numeric entry, structural stop, target model and
rationale through actual `process_watchlist` raw intent. Its descriptive target is
not converted into a fabricated numeric take-profit. Synthetic high-score controls
are explicitly labelled, not market opportunities.

All-incomplete inputs use the existing
`CANDIDATE_REJECTED_INSUFFICIENT_QUALITY` / `all_detected_candidates_rejected`
no-entry decision; candidate-specific reasons are retained. V1 emits the existing
decision-stage blocked terminal, not a selected fired-trigger/no-intent success.
Target-less rows in the baseline family map still have NO target policy: they are
now excluded from the entry ranking pool, not enabled or assigned targets.
Context-only setup candidates without their own complete entry fields likewise
reject before ranking, with actual missing-stop/trigger reasons. A late missing
selected contract remains defensively blocked; no canonical contract is created
from a contextual guess.

The selected eligible winner still must pass its own trigger, confirmation,
source/quote/timeframe freshness, session, geometry, tradeability and capacity gates.
No next-family fallback was added after an unconfirmed trigger, risk denial,
submission failure or unknown broker outcome. Core's ownership veto remains after
raw formation and before canonical artifact/real risk admission. Existing actual
Core READ_ONLY handoff/mode/ownership regressions were included in affected checks.

Focused tests added in existing `test_ross_selected_setup_handoff.py`: both input
orders; multiple intrinsic failures; all-invalid inputs; unchanged valid ranking;
risk-off/context/opposing conflict preservation; no fall-through after a complete
winner's unconfirmed trigger; original selected stop/target/rationale identity;
shared validator field failures; mapping input/no private-source export; unexpected
validator failure propagates without selecting another candidate. Broker connection,
requests and order methods are forbidden, with existing hard offline network guards.
Existing selected-target tests now assert earlier decision rejection; the three
contextual fallback tests assert exact missing-stop/trigger logs rather than the
former late missing-selected-contract stage. No assertions were skipped/weakened.

Failing-before:5 new integration cases failed1.12s. Affected selected-handoff,
PR1030 intent mapping, PR1082 terminal semantics, contextual fallback, future-quote
and actual Core READ_ONLY risk-handoff run:181passed/3old-stage assertions failed,
4.14s,26existing utcnow warnings. Updated only those3 semantic stage assertions;
reran them plus2additional mapping/fault controls:5passed0.51s. Thus186distinct
focused cases are covered across receipts, NOT a single186-pass run or CI result.
No unrelated dependency/full/setup suites repeated. Baseline audit's10 passing
counterexample controls remain a historical receipt, not an expectation to rerun
unchanged after correcting their demonstrated starvation behavior.

Remaining family gaps (own target/bridge/structural policy, GAP_GO alias duplicate,
combined composed-news-Core positive proof and all natural progression) are
unchanged. Next action is review of this exact local repair; no runtime retry or
new family activation follows these tests. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL. All five unmatched-position protections remain intact.

## Exact-candidate review and occurrence binding — 3 November 2026

Verified clean input `9322e0c3fab3f38337040778aa2e9df73f8b4dba`, tree
`a0555f25321c6a4bc53ccd606a0858be53ac2479`. Reviewed arbitration commit
`b6d8c611004055047be2cccd9028bbe9f2e91c97` separately from inherited optional
imports/configuration and baseline audit documentation. Canonical validation is a
composition of existing predicates, reads candidate fields only, and does not
query services, refresh data, evaluate risk or grant a session/ownership override.
Risk-off/context and direction-conflict precedence, ranking key and one-winner
policy were correctly retained. No target was invented. The late defensive
validation and post-selection risk/ownership/execution boundaries remain necessary.

BLOCKER FOUND: selection validated a specific result, but subsequent lookup used
only pattern ID/family. A rejected same-ID occurrence could supply the first trace,
contract or trigger; a later non-detected trace could also overwrite the real
candidate's detected state in normalization. New controls reproduced3failures/
1pass0.57s (missing-target and not-detected occurrences in both orders). A separate
control reproduced confidence contamination when a detector error emits a trace
without a result: positional trace/result zip shifted the next rejected result's
confidence onto the actual selected Micro trace. That failed0.50s after correcting
required fixture constructor fields (the constructor error is not defect evidence).

Minimal fix within existing owners, commit
`9b35e96a5647a5d0094fb927f03da9da2eeab616`, tree
`3d8b3b3d4522a7db61732efeec56c9c791ff902b`:

- Ross-opted-in DecisionEngine preserves original per-call result ordinal and
  returns `selected_candidate_index`; ambiguous same-ID traces cannot override
  canonical result facts. No arbitrary decision IDs or source objects are exported.
  Generic engine callers without the entry validator retain previous output schema.
- Existing canonical trigger candidates carry `canonical_result_index`, copied
  by TriggerEngine. V1 selects the exact chosen occurrence's trigger, contract and
  matching trace, not the first member of a family/ID. Source contract remains the
  owner for its own stop/target/rationale/metadata. Result indices preserve gaps
  from non-detected candidates; they are local list bindings, not persistent trust.
- Trace confidence is assigned through the same identity-bound correspondence,
  not positional zip across possible error-only traces. Invalid/noninteger/bool/
  out-of-range ordinals, wrong identity or ambiguous trace/result correspondence
  cannot substitute another source. Unknown binding gives explicit
  `selected_contract_binding_unavailable` and no entry. Legacy lookup without an
  ordinal permits only one unambiguous match.

This does NOT deduplicate GAP_GO invocation or enable other families. Default
scores/order among eligible candidates are unchanged; the additional ordinal is
binding metadata only. No fallback after risk rejection, execution failure or
unknown broker outcome was added. Existing dependency, canonical predicates,
Core/position truth, RiskEngine and execution sources were unchanged by review fixes.

Receipt clarification: the prior186-case evidence was181passes with3old contextual
stage assertions failing, then5passes: those3corrected stage expectations PLUS
2NEW mapping/fault controls. The5-pass receipt is not five weakened expectations.
Two intermediate new assertions used the wrong terminal field name (`stage` rather
than `terminal_stage`); fixing the fixture assertions did not change production.
The changed existing target expectations assert earlier decision-stage blocking,
no selected entry/trigger evaluation, no raw intent, and actual candidate rejection
reasons. Exact contextual missing-stop/trigger logs strengthen the no-canonical-
contract checks. Historical late-rejection receipts remain historical.

Review validation:9 focused binding/ranking/suppression controls passed0.60s;
changed-owner six-module run197passed/1exact-schema expectation failed4.04s,
26existing utcnow warnings. That expectation retained EVERY existing trigger field
and added required ordinal0, rather than loosening dictionary equality. It and
the two error-trace correspondence variants then passed3cases0.66s. Additionally,
3existing composed BullFlag/Micro controls passed0.79s: actual registry/strategy
intent -> synthetic risk/in-memory execution, no unpaired fallback, and duplicate
child/restart rejection. These test the changed metadata path, not a repeated
management suite. Across the six-module receipts199distinct affected cases have
passed, plus3composed controls; no single202-pass run/CI/Windows claim. Review adds
13new parametrized binding controls; no tests skipped. Logs are retained locally
under `/workspace/scratch/ross-entry-review-*` and
`ross-entry-selection-review-affected.log`.

Result: original candidate had blockers; corrected exact source reviewed with no
remaining local publication blocker. Recommend draft publication for independent
review and repository-required CI when authorized, NOT merge/runtime/PAPER approval.
Missing target/trigger policies, natural positive progression, composed-news-Core
combined proof and five-position ownership veto remain as recorded above. No
provider/broker call, observation, push or merge. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL.

## PR1148 publication and exact-head acceptance receipts — 3 November 2026

Draft [PR1148](https://github.com/NelzonMamani/ibkr-trading-system/pull/1148)
publishes the isolated optional-import and Ross entry-selection work. Candidate
`9dee39476de02dc4b2153657afac9cfba6cda32e`, tree
`6dc3335b580379b358fd928a3488f1d9085eb001`; accepted/fetched main
`a66b43f2b44d98405d1dc30bc62f8c359a5f3fbc`, tree
`04a58818e178764c28e0fecab472fe1dbbbc0154`, unchanged at publication. No rebase.
GitHub test merge `39d0b70a5cde4e337ffa4e83acca0d40e8ea7458` has EXACTLY the
candidate tree and parents accepted main + candidate. Scope checks exclude parked
corporate/news/SEC production changes and private contact literals. The three
audit/config/checkpoint documents are documentation, not runtime enablement.

Independent agent review [5759973276](https://github.com/NelzonMamani/ibkr-trading-system/pull/1148#pullrequestreview-5759973276)
anchors the exact candidate: no blocking findings. Separate reviewer inspected
canonical predicate reuse, occurrence/duplicate/ambiguity/trace-error binding,
warning/conflict precedence, valid ranking/one-winner, missing targets, unchanged
post-guard risk/ownership and dependency isolation. No redundant suite rerun or
source edits by reviewer. Posted as COMMENT, not human/formal approval or CI proof.

Initial CI [41724915655](https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/41724915655) FAILED: Linux17 failed/3697 passed/3 skipped; Windows17 failed/3699 passed/1 skipped. All17 matching failures were inspected, including by the independent reviewer: expected earlier contract rejection and incomplete downstream fixtures, with no demonstrated new production defect. Later Windows cache/PowerShell steps were skipped and cannot count as acceptance.

Corrective test-only commit `8970953b96aaa8f5f813d4384c57756cbfdc810a`, tree `b8eebc29f9f9b591fcbf9b05738fefea32d59c0d`, changes six test modules; all production/workflow bytes remain unchanged. Labelled synthetic target completeness enables actual downstream detector controls; two unmodified detector controls retain missing_target rejection. Negative cases require actual gate reasons; positive/multi-symbol cases require actual raw intent. Context/diagnostic fixtures retain strict earlier rejection and correctly spaced timestamps. No test skipped, target invented in production, or safety assertion relaxed. Local focused corrections:65 passed and35 passed; after strengthening exact negative reasons16 passed. These are local offline receipts.

Independent exact-head delta [review5760117413](https://github.com/NelzonMamani/ibkr-trading-system/pull/1148#pullrequestreview-5760117413) found no blockers. COMMENT records independent agent review, not human approval. Earlier review5759973276 remains tied to its original head. GitHub merge `97c8c493c636fdfbf1208ec081c8dc89afc650eb` has EXACTLY final candidate tree b8eebc29f9f9b591fcbf9b05738fefea32d59c0d, parents accepted main +8970953b.

Changed-head [CI41726801425](https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/41726801425) completed SUCCESS. Existing unchanged workflow selected full checks (HARNESS_ONLY=False). Linux3716 passed/3 skipped/4 warnings (230.12s); Windows3718 passed/1 skipped/268 warnings (602.40s). Both checked out merge97c8c493, whose tree equals the reviewed final candidate. Windows focused diagnostic95, news maintenance37, native float-cache9 and serial admission40 tests passed. Six cache subprocess fixtures passed; actual PowerShell exit propagation13 controlled checks, observation harness46 checks (including12 package/5 preflight synthetic cases), and PowerShell5.1 diagnostic parser passed. Intentional failing-child output is part of the successful exit-propagation negative controls, not a failed CI step. Evidence upload succeeded. Harness-only alternatives/install step were conditionally skipped because full-suite mode ran; previously skipped required cache/PowerShell controls actually executed successfully here. Optional-dependency guarded controls ran in the full suites. No unchanged-head retry or unrelated local full-suite rerun.

Final PR metadata: accepted base remains a66b43f2b44d98405d1dc30bc62f8c359a5f3fbc; final head8970953b/treeb8eebc29; mergeable, draft/open/unmerged, no review threads. No blocking agent findings. Agent COMMENT is not formal human approval; any repository-required approval must still be satisfied at controlled integration. Recommendation: exact-candidate integration review, with fresh ref/check/protection verification and explicit merge authorization. No runtime/PAPER acceptance.

Receipt documentation is saved on separate local docs/pr1148-ci-acceptance so the
final published reviewed/tested candidate remains unchanged by receipt updates.
The original9dee candidate was superseded only by the six-module test correction
documented above. No second PR or workflow
change. PR remains DRAFT/unmerged. Any later integration must reverify exact base,
head, tree, checks, threads and required approvals; this task does not authorize it.
Natural supported-event-to-raw-intent, missing family target/bridge policies,
composed-news-Core combined proof, five-position veto and readiness limits remain.
No provider/broker call, observation or holdings action. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL.

## PR1148 accepted; next bounded family repair — 3 November 2026

PR1148 merged under explicit user authorization with expected-head guard at
8970953b96aaa8f5f813d4384c57756cbfdc810a. Accepted main
`e21e8eb365d53dccb61107cea8a4cda054e514d8`, tree
`b8eebc29f9f9b591fcbf9b05738fefea32d59c0d` equals reviewed/tested tree.
Independent review5760117413 and CI41726801425 reverified; original failed
CI41724915655 preserved above. No suite rerun. Full integration/protection receipt
is in the SAME NATURAL_READONLY_CHECKPOINT.md, section PR1148 controlled integration.

Next recommendation is one KEY_LEVEL_BREAK canonical trigger bridge: existing
strategy_policy.py lines121/185 define the family/entry condition; RF KeyLevelBreakPattern
supplies selected-level provenance, explicit trigger/stop/invalidation and next-
overhead-level descriptive target. TR already registers its own armed/fired
evaluator. Actual V1 `_canonical_pattern_trigger_candidates` (2232ff) excludes the
family and contextual SetupEngine has no producer. The existing runtime-named
`test_key_level_break_pattern.py` test exercises registry only, not V1 raw intent.
Scope any separately authorized repair to that existing bridge/TriggerEngine path,
canonical occurrence binding, existing evaluator and contract validation. Prove
actual V1 positive/armed/negative/freshness/identity/risk-off/conflict boundaries
with synthetic inputs and preserved own stop/target/metadata. Do not invent target,
R:R or management policy or claim numeric execution certification. If existing
contracts are insufficient, report the policy blocker. No implementation here.
GAP_GO duplicate invocation and other family target/bridge gaps remain unchanged.
Natural proof, five-position veto and PARKED corporate/SEC/listing state remain.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## KEY_LEVEL_BREAK production bridge — 3 November 2026

The previously recorded bridge recommendation is implemented locally: one
KEY_LEVEL_BREAK addition to V1's canonical trigger-family allowlist. Existing
TriggerEngine dispatch and the registered evaluator were already sufficient.
No new detector/trigger/target logic or owner was added. Family map above now marks
this route C; prior G/next-repair entries remain historical findings.

Before: six new controls failed, five passed; actual V1 lacked its own trigger.
After:13 new controls pass with real detector/registry/evaluator and synthetic
fresh streams, including actual raw intent without synthetic target completion,
precise missing/stale rejection, invalid contracts and both-order same-ID binding.
Affected existing controls:122 passed with18existing warnings, including other
families, suppression/conflict and actual Core ownership/mode boundaries.
The SAME checkpoint's matching section records baseline, saved receipt carry-
forward, exact owners, detailed controls, durations and local log locations.

The existing next-overhead-level target is descriptive: numeric take-profit/R:R,
management lifecycle and natural progression are not certified by this bridge.
Other family policies/bridges and GAP_GO duplicate invocation remain unchanged.
One next action: exact local candidate review. No push/merge/runtime activity.
Five-position veto and PARKED corporate/SEC/listing policy remain intact.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## KEY_LEVEL_BREAK review correction and target scope — 3 November 2026

Exact942f2e1c/treeafd8aca7 review found one blocker: canonical acceptance
invalidation survived the trigger but generic raw-intent construction replaced it
with the different structural stop. Actual-V1 and both-order duplicate assertions
failed3/7 before correction. The scoped V1 correction preserves the selected
KEY_LEVEL_BREAK trigger's invalidation on raw intent; stop remains independent,
other-family construction unchanged. Corrected affected92cases passed; three new
malformed-contract cases passed. Prior13/122 receipts remain historical local
results, not repeated CI claims. Full evidence is in the SAME checkpoint's
KEY_LEVEL_BREAK exact-candidate review section.

Existing contract accepts the detector's nonempty descriptive next-overhead-level
target; no synthetic target was supplied. Raw target_model is retained with
numeric take_profit_price=None. Risk does not translate the prose into a price.
Selected-protection post-fill handling retains stop/no numeric target;
TradeManagementEngine records DESCRIPTIVE_ONLY. Generic exit-plan R-multiple
fallbacks elsewhere are not KEY_LEVEL_BREAK target/management certification.
Ownership veto prevents artifact/risk admission after formation; READ_ONLY remains
an independent execution denial. No universal missing-numeric-target block or
family execution certification is claimed. Family row C denotes tested synthetic
raw handoff only. Natural progression and numeric management remain unproven.

Corrected candidate recommended for authorized draft publication and independent
exact-head review/CI; no push/merge/provider/broker/observation. No other family
repair, corporate/SEC or parked listing work. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL.

## PR1149 published candidate — 3 November 2026

Draft PR1149 publishes exact3608d6cf9a1da4016bf9e1dd0aba47b0b53750c8 /
b58b2db9d0c977569d20dadefb28e684d6e49704 against unchanged accepted basee21e8eb3.
Test mergefe44059444ef31326933503e1fbe2404aeae9fac has the identical tree.
Independent agent COMMENT review5760597105: no blockers; not human approval.
Reviewed canonical occurrence binding, separate acceptance invalidation/stop,
unchanged other-family/safety boundaries, negative controls and descriptive target
scope. Prior failing-before/13/122/92+3 local receipts remain preserved.

CI41734010206 SUCCESS on exact matching merge tree: Linux3732passed/3skipped;
Windows3734passed/1skipped. Native cache, serial admission, six cache subprocess
fixtures, actual PowerShell exit propagation13checks/observation46checks and parser
passed. No code changes after publication or redundant suite reruns. No scoped
blocker remains; recommend separately authorized controlled integration review,
with fresh requirements/ref/check verification. Agent COMMENT is not human approval.

The SAME checkpoint contains full external receipts. Receipt-only edits live on
separate LOCAL docs/pr1149-ci-acceptance; they do not replace the tested PR head.
No family target/management policy added: C still means synthetic actual V1 raw
handoff, not natural progression, numeric management or PAPER readiness.
Five-position veto and PARKED corporate/SEC/listing provenance unchanged. PR draft,
no merge/provider/broker/observation. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## PR1149 accepted; next FIRST_PULLBACK handoff recommendation — 3 November 2026

Accepted main6eca86a2be1ef6570c8a2e2b0e3fd2422c6a6579, tree
b58b2db9d0c977569d20dadefb28e684d6e49704, exactly reviewed/tested candidate.
Expected-head-guarded merge followed review5760597105, successful CI41734010206,
matching test tree and repository requirement checks; no protection bypass or
suite rerun. Receipt: PR1149 issuecomment-6617899746. Saved0ca17591 checkpoint/map
receipts carried forward unchanged. Complete integration evidence is in the SAME
checkpoint's PR1149 controlled integration section.

KEY_LEVEL_BREAK handoff and separate structural stop/acceptance invalidation are
integrated. Numeric management and natural progression remain NOT certified.

Next priority: FIRST_PULLBACK own structural-contract -> canonical trigger bridge.
Existing policy family118/entry193 specifies controlled pullback and pullback-high
reclaim, not a new target law. RF.FirstPullbackPattern measures pullback low/high
but does not export those numeric anchors; generic PatternBase context inference
is not own structure. Existing descriptive retest-impulse-high/extension target
and registered trigger_first_pullback evaluator already exist. V1 bridge omits it.
Named first_pullback tests target common detector, not actual registered RF owner.
Bound a separately authorized repair to RF contract export + existing V1/TriggerEngine
handoff, exact occurrence binding and actual positive/negative/raw-intent controls.
No detector substitution, changed detection/trigger semantics, target/management
invention or other-family activation. Stop on an unresolved policy boundary.
No implementation during this task. Five-position veto intact; corporate/SEC/listing
work PARKED. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## FIRST_PULLBACK own anchors and canonical bridge — 3 November 2026

Local repair resolves the previously recorded X/generic-anchor handoff gap in
actual RF.FirstPullbackPattern, not common.detect_first_pullback. Existing policy
family118/entry193 and detector entry/stop text supply measured pullback high/low;
existing structural stop law invalidates below the low. Stop and invalidation
remain separate concepts with the SAME numeric boundary here; no new reclaimed-
high invalidation rule or offset. Existing detection/retrace/strict reclaim and
descriptive impulse-high target unchanged. RF exports own fields/metadata; V1
adds FIRST_PULLBACK to canonical bridge. Registered evaluator/TriggerEngine,
occurrence binding and all selection/safety owners reused unchanged.

Before:9fail/9pass new controls show generic10.3 vs own10.42 and missing canonical
trigger. Final new module25passed0.73s on actual registry/V1 with synthetic fresh
streams; no target completion. Both-order duplicate, malformed/missing/stale,
required1m, actual10s/steady1m, strict high/low and exact45% retrace boundaries.
Affected existing99passed plus1 PR1029 case (separate runs), including neighboring
families and actual Core ownership/mode gates. Full receipts and test-assertion
corrections are in SAME checkpoint matching section; no CI/Windows claim.

Updated row C means synthetic actual raw-intent handoff, NOT natural formation,
numeric management, positive risk admission or PAPER readiness. Five-position
veto remains after formation before risk. No other-family/target-policy work,
provider/broker calls, observation, push or merge. Next: exact local candidate
review. Corporate/SEC/listing remains PARKED/fail closed.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## FIRST_PULLBACK window/confirmation review — 3 November 2026

Exact00dbd69d/tree4675fbd7 review: no production blocker. Anchors derive solely
from candles[-3:-1]; impulse[-6:-3], confirming[-1] and earlier prefix cannot
supply/move them. Per-evaluation source inputs/timestamps unchanged. Existing RF
primary-reclaim detection remains separate from registered execution high-break
confirmation; it was not changed to common-detector pre-break readiness.
Execution high alone is insufficient: close must exceed measured high; close at/
below measured low remains invalidated. No newly claimed intrabar ordering,
stateful cross-cycle invalidation or stop-fill/management proof.

10new guarded boundary controls passed0.63s,25deselected: confirming high/low
independence, prefix/impulse exclusion, each pullback-bar extreme, actual V1
wick-touch/equal/below/above close and low invalidation. Original25/99/1 receipts
inspected/carried forward, not rerun; production unchanged by review. Occurrence
binding and existing safety/ranking/ownership/READ_ONLY owners reviewed intact.
Full evidence and target handling are in SAME checkpoint matching review section.

Descriptive target permits raw intent with numeric take-profitNone; selected
protection retains stop/no numeric target. No numeric-management or natural
certification. Advice: authorized draft publication and independent exact-head
review/CI; no push/merge/provider/broker/observation. Corporate/SEC/listing parked;
five-position veto intact. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## PR1150 independent malformed-window correction — 3 November 2026

Initial publishedec4551f4 review5761032145 demonstrated NaN structural low producing
raw stop/invalidationNaN. Earlier provisional no-blocker statement superseded.
Original CI41740527836 does not settle that independent blocker. Scoped RF-only
numeric OHLC validation over six relevant bars now precedes anchor derivation;
rejects malformed_candles, no coercion/substitution/target or other-family change.
Six actual-V1 numeric and two direct-owner nonnumeric variants added. Corrected
43+99+1 focused run143passed3.53s (18existing warnings); old25/99/1/ten-control and
failing-before receipts preserved in SAME checkpoint. Changed-head independent
review and required CI pending. Descriptive target/raw intent is still not numeric
management, intrabar ordering, natural progression or PAPER readiness.
PR draft/unmerged, five-position veto and parked corporate/SEC/listing unchanged.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## PR1150 published exact-head review and CI — 3 November 2026

PR1150 initialec4551f4 review5761032145 found NaN numeric-authority blocker;
original receipts retained. Correctede2de4179110c4d757c910935f08eec2b4183e6ab /
9a5b15b8946c0758c5e31af87f251b41706516c6 adds bounded actual RF six-bar OHLC
rejection before derivation; no valid semantic or other-family change. Matching
merge0d2b9ebd827133cae3d33c3e385ad551508b1af4, unchanged base6eca86a2.
Independent agent COMMENT review5761052907: no blockers, not human approval.
Prior25/99/1/ten controls and new143-pass changed-source receipt preserved.

Corrected-head CI41740948445 SUCCESS: Linux3775passed/3skipped, Windows3777passed/
1skipped, matching reviewed merge tree. Windows native cache/serial admission,
six cache subprocess fixtures, actual PowerShell exit13/observation46 checks and
parser passed. No remaining scoped blocker; recommend separately authorized
controlled integration review with fresh ref/check/requirements verification.
Initial blocked review/old-head CI remain historical, not retrospectively cleared.

Complete receipts in SAME checkpoint. Separate local docs/pr1150-ci-acceptance
keeps final PR head stable; no competing checklist/PR. Descriptive raw target is
not numeric management/intrabar/natural certification. Five-position veto intact;
corporate/SEC/listing parked. Draft/unmerged, no provider/broker/observation.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## PR1150 integrated; next ABCD canonical handoff — 4 November 2026

Accepted main2a31eb07ac7fa7985fb2f78f2f495603f813193c, tree
9a5b15b8946c0758c5e31af87f251b41706516c6, EXACT corrected reviewed/tested tree.
Review5761052907, CI41740948445/all jobs, no blockers/threads and repository
requirements reverified before ready/expected-head-guarded merge. No protection
bypass or suite repetition. PR1150 issuecomment-6618777171 records integration.
Savedc0e20e7c checkpoint/map receipts carried forward on local docs/pr1150-integration.
Original NaN finding/review5761032145 and failing/repair controls preserved;
superseded CI41740527836 now all-job SUCCESS does not accept its blocked source.

FIRST_PULLBACK own structural anchors, canonical trigger handoff and RF-only
malformed-OHLC rejection are integrated. Numeric management, intrabar ordering and
natural progression remain uncertified. No numeric target policy added.

Next recommendation is ONE ABCD canonical trigger bridge: existing policy122/195,
RF.ABCDPattern own A/B/C+indices, pullback-high trigger, C structural stop and D=C+AB
projection, registered trigger_abcd_continuation evaluator all exist. Actual V1
canonical bridge omits ABCD; existing trace/detector tests do not prove actual V1
raw intent. Bound separate repair to existing canonical bridge/dispatch and
required fact carriage, exact occurrence/anchor/timeframe provenance, guarded
positive/negative/invalidated/malformed/duplicate controls. Do not turn D into an
approved numeric order target, alter swing/detection/trigger rules or implement
management/other-family policies. Report a policy blocker instead of inventing it.
No ABCD implementation in this task. SAME checkpoint holds full evidence/owners.
Five-position veto intact; corporate/SEC/listing parked. No provider/broker,
preflight, observation or trading. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## ABCD actual canonical bridge and geometry evidence — 4 November 2026

Local repair resolves the audited G handoff: existing RF detector/registered
ABCD evaluator reused, V1 canonical bridge adds ABCD and preserves original
A/B/C/indices, trigger, C stop/invalidation, D and metadata through exact ordinal
selection and serialized raw intent. No numeric target instruction: original
projection description remains target_model and take_profit_priceNone.

Guarded controls demonstrated malformed/future admission after a bridge-only
change. One shared ABCD helper in the existing evaluator module now validates RF
source and operational execution candles; valid swing/retrace/break rules remain.
Existing builder observation clock is carried on optional PatternInputs field,
not resampled/substituted; ABCD alone enforces finite coherent OHLCV and aware
ordered timestamps<=clock. Source lookback remains60; original dates/provenance
and bounded-window-relative indices preserved. Declared optional TradeIntent
setup_metadata carries facts, not new trading authority; deep snapshot prevents
later source mutation changing formed intent. Other-family gates unchanged.

New27cases pass0.81s; affected159passed/1malformed-fixture failure, then corrected
fixture's unchanged retracement rejection passed, plus1PR1029 case. The fixture
fix changes only open10.8 to10.85 to respect low10.84, retaining highs/lows/closes/
swing/retrace; no weakened assertion. Full passing/failing receipts and exact
owners are in SAME checkpoint section. No CI/Windows or natural proof claim.

C now denotes actual raw handoff on synthetic fresh streams, including geometry/
serialization, strict close/touch, invalidation, missing/stale/malformed/future and
duplicate isolation. Last confirming candle is not measured into A/B/C or B..C;
future-dated observations reject. No numeric management/intrabar/natural
certification or target policy invented. Five-position veto/READ_ONLY intact;
corporate/SEC/listing parked. Next: exact local review. No push/merge/acquisition/
broker/observation. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## ABCD review: completed swing witness and retained evidence — 4 November 2026

Review verified exacta039a25a/treeac8ab2a0 and prior27/160/PR1029 receipts.
The shallow-retrace fixture open correction preserves every swing/retrace input
and its original negative assertion. No weakening or synthetic target completion.

Found one blocker: the latest still-forming primary bar could be C's right-hand
swing witness. Actual V1 control emitted raw intent before witness completion
(1failed0.55s). RF now searches existing swing algorithm only over bars whose
original start+primary interval<=original observation clock, so witness must also
be complete. Entire malformed/future source still rejects before this boundary;
source dates and bounded-window indices not substituted. Unknown interval/no
completed sequence fail closed. Metadata records completed count; no trigger,
retracement, D, target policy or other-family rule changed.

After correction:31updated controls passed0.75s;22existing ABCD controls passed
0.33s. Additional1lookback case passed0.47s (31deselected), verifying60-bar bound,
offset18/local indices53/55/57 and exact original timestamp. New module32distinct
cases across receipts, not one32-pass run or CI/Windows proof. Input/result/receipt
mutation cannot rewrite serialized raw intent. SAME checkpoint has full findings
and retained failing-before/snapshot receipts. Prior Core/neighbor safety evidence
carried forward; no redundant unaffected suites.

Corrected candidate suitable for authorized draft publication/independent review/
CI. D remains a projection fact, not executable target. Numeric management,
intrabar ordering and natural progression uncertified. Five-position veto and
READ_ONLY remain; corporate/SEC/listing parked. No provider/broker/observation/
push/merge. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## PR1151 exact-head publication/review/CI — 4 November 2026

Published ONE draft PR1151 at3c08a337176fae78b6683e40e61b5149fe9e2a70 /
9cd60e0b89ec2b589748973f6357608ad00db60f against unchanged accepted2a31eb07.
Matching mergef174a998cef541270d2a7337858301c297359dc5 has exact candidate tree.
Independent agent COMMENT review5761516164 found no blockers; not human approval.
Reviewed actual wiring, completed-witness timing, bounded indices/source times,
exact occurrence, deep raw serialization and unchanged safety boundaries.
Original27/160/PR1029 and31/22/1 review receipts/failures retained, not rerun for
status. Scope excludes corporate/SEC implementation/private contact literals.

CI41747724577 SUCCESS, all three jobs on exact matching merge tree:
Linux3807passed/3skipped, Windows3809passed/1skipped. Native cache, serial admission,
six cache subprocess fixtures, actual PowerShell exit13/observation46 controls and
parser passed. No source changes/retries/redundant local suite runs. Recommend
separately authorized controlled integration review with fresh ref/check/protection
verification. Agent COMMENT is not human approval; no scoped blocker remains.

Complete external receipts in SAME checkpoint; separate LOCAL docs/pr1151-ci-acceptance
keeps exact reviewed/tested PR stable without another PR/checklist/receipt-only
suite run. D is evidence, not executable target; numeric management/intrabar/
natural certification remains unproven. Five-position veto/READ_ONLY intact;
corporate/SEC/listing parked. Draft/unmerged; no provider/broker/observation.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

### PR1151 controlled integration — 4 November 2026

Explicit user authorization applied only to head `3c08a337176fae78b6683e40e61b5149fe9e2a70`, tree `9cd60e0b89ec2b589748973f6357608ad00db60f`, base `2a31eb07ac7fa7985fb2f78f2f495603f813193c`. Fresh GitHub verification found unchanged refs, independent agent review [5761516164](https://github.com/NelzonMamani/ibkr-trading-system/pull/1151#pullrequestreview-5761516164) bound to this head with no blockers (COMMENT, not human approval), successful [CI41747724577](https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/41747724577), no review threads and clean mergeability. Tested merge `f174a998cef541270d2a7337858301c297359dc5` has the candidate tree and authorized base/head parents. Main was unprotected, required contexts empty, rulesets empty and merge commits enabled; no protection bypass occurred. No completed suite was repeated.

Marked ready and merged with expected-head guard using merge commit. Accepted runtime/main is **`f55c0225fc55adc379d766ba7ebfeac88a322f1f`**, tree **`9cd60e0b89ec2b589748973f6357608ad00db60f`**. Fetch verified exact tree equality and both parents. [Integration receipt6628182592](https://github.com/NelzonMamani/ibkr-trading-system/pull/1151#issuecomment-6628182592). Saved documentation `c82c2b663758d7559e0dcbbe65659cc895915e9c` was carried forward on separate `docs/pr1151-integration`; documentation does not substitute another runtime pin. Existing incomplete-swing-witness and snapshot-isolation failing-before/passing-after receipts remain above.

ABCD canonical trigger handoff, selected-anchor serialization/isolation and completed swing-witness handling are repaired. D remains a measured projection, never executable take-profit. Numeric management, intrabar ordering and natural progression remain uncertified. Five unmatched positions still globally veto new-entry admission AFTER raw formation and BEFORE canonical artifact/risk admission. Corporate/SEC work and listing provenance remain PARKED/fail closed. Historical observations, failures, UNKNOWNs, GUI draft and separate cache/callback uncertainties remain preserved. No provider/broker/preflight/observation/trading occurred.

**One next action (recommendation only):** undertake a separately authorized bounded repair of duplicate GAP_GO/GAP_CONTINUATION detector invocation. Existing specification `strategy_policy.py:116,129` describes Gap & Go and gap continuation separately, but `src/setup_engine/registry.py:61,84` maps both to `GapGoPattern`; `build_tradeable_patterns:102` creates both instances and `RossPatternRegistry.run` evaluates both. The existing audit records 28 active objects/27 IDs (34/33 including placeholders). Reuse these owners to evaluate the existing identical implementation once with explicit alias provenance; do not globally collapse arbitrary duplicate result IDs/occurrences or treat two aliases as independent confirmation. Acceptance must preserve registered membership/status, canonical occurrence binding, existing selection/suppression and one-winner policy while proving one invocation for this alias pair. Do not invent a distinct continuation detector, anchors, targets or management policy. This is a duplicate-work correction, not full GAP_GO activation or natural acceptance. No further repair was implemented in this integration task.

PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

### GAP_GO implementation-alias evaluation repair — local, 4 November 2026

Baseline verified locally: accepted main `f55c0225fc55adc379d766ba7ebfeac88a322f1f`, tree `9cd60e0b89ec2b589748973f6357608ad00db60f`. Separate branch `fix/gap-go-alias-evaluation` preserves the original checkout and carries saved PR1151 receipts from `283af85e0e4a0c71ea1a6263e946f8fa541c02aa` (including its preceding receipt commit). Applicable instructions and DEPRECATION_LEDGER read; no owner/module retirement or new configuration system.

Confirmed before editing: `CANONICAL_SETUP_REGISTRY` instantiated both GAP_GO and GAP_CONTINUATION as `GapGoPattern`; `build_tradeable_patterns` returned 28 active objects and RossPatternRegistry.run evaluated each. The existing policy descriptions (strategy_policy.py GAP_GO and GAP_CONTINUATION) remain distinct concepts, but actual shared implementation emits P_GAP_GO/GAP_GO. This change declares the existing implementation alias, not policy equivalence or a new continuation detector.

Production/test commit **`f938d8a04d7fba603b348ff4aaaac86cb9b09a21`**, tree **`6e22d0400d3949ba1abe4337f5a7dd90a7305498`**: existing SetupFamilyImplementation gains optional canonical_setup_id; only GAP_CONTINUATION declares GAP_GO. Existing factory groups explicit aliases only after per-entry enablement filtering and verifies identical detector class/canonical authority. Nonalias entries using the same class remain separate. Registry ordering is retained; caller-request order is normalized through membership selection. Optional requested_setup_ids is a factory selection argument, not a new runtime configuration store. Default still includes every enabled family; alias-only selection and disabled-canonical/enabled-alias remain supported. No result/input cache, time/security/context deduplication or second evaluation owner exists.

One canonical result and one trace retain the enabled requested names, including rejection/error traces. Existing result setup_metadata preserves canonical_setup_id/requested_setup_ids without changing trigger/stop/target facts; trace schema adds requested_setup_ids. Canonical GAP_GO trace provenance now remains available on rejection as well as detection. Other-family contracts/results, occurrence ordinals and selection/trigger owners are unchanged. Removing the second physical evaluation naturally removes its redundant result/trace; it does not create competing copies or globally collapse matching result IDs. Active factory count is now 27, Ross total including six placeholders 33; old 28/34 counts above are historical observations.

Guarded synthetic comparison through the accepted factory implementation and actual Ross loop confirmed before: 2 GapGo instances/evaluations/results/traces; after: 1 of each for the same input, with actual positive detection and no invented target. Focused validation: initial 10 alias controls plus existing canonical trace, PR1029 detector certification, selected-setup handoff and live failure-trace modules **108 passed in 2.61s**. Added a concrete mixed-neighbor occurrence/registered-trigger control: final alias module **11 passed in 0.38s**. This is not a summed 119-case distinct suite: ten alias cases overlap. One earlier test-selection command referenced a nonexistent test path and collected no tests; corrected selection produced the 108-case receipt. No assertions were weakened. git diff --check passed.

Controls cover both names/both request orders/either name alone; fresh repeated/security/changed-snapshot contexts; actual detected contract equality; single rejection/error; trace/requested aliases; default/neighbor order and enabled status; unrelated same-class entries not collapsed; invalid alias configuration fails closed. Mixed GAP_GO plus actual consolidation result retains consolidation index1, its own trace/contract/stop/metadata and dispatches its registered ready trigger. Existing affected selection controls retain suppression/ranking and READ_ONLY behavior. Network/broker connection/query/order guards applied through the reused offline fixture; synthetic comparison also forbade connections/orders. No provider/broker collection, observation, push or merge occurred. These are local Linux/offline receipts, not Windows/CI/independent approval or natural acceptance.

Remaining limits: GAP_GO's missing canonical trigger bridge/structural-contract certification is NOT repaired. Alias deduplication does not establish a distinct GAP_CONTINUATION detector, target/management policy, numeric take-profit, intrabar ordering or natural progression. Five-position global veto remains after raw formation before canonical artifact/risk admission. Corporate/SEC and listing provenance remain PARKED, all historical receipts/UNKNOWNs and GUI draft preserved. One next action: review this exact local candidate and its alias/occurrence controls before any publication decision.

PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

### GAP_GO alias candidate local review — 4 November 2026

Verified requested local review input `e6333aec7a0d91b67629aa8210afd02e1a1d2958`, tree `0fe8ab5b85f78c5bf695f411edfb5a0fc246b0ca`, clean worktree and accepted ancestor `f55c0225fc55adc379d766ba7ebfeac88a322f1f`. Reviewed production separately from carried PR1151 documentation. Existing strategy descriptions remain separate; only the explicitly declared shared implementation alias is coalesced. No class-/pattern-ID-wide deduplication exists. Per-entry enablement precedes grouping, including canonical-disabled/alias-enabled, and canonical registry order is independent of request-list order. Results are evaluated afresh on every run; no persistent cache or input suppression.

**Findings: no blocking production defect found.** One canonical instance/result/trace retains both requested names, or only the selected enabled name. Rejection metadata and error traces retain aliases. Exact levels/contract fields remain detector-owned; alias projection changes metadata only. Undeclared same-class entries remain distinct. Default registry order and neighboring families are unchanged apart from removal of the redundant alias evaluation. Acquisition, qualification, selection/risk-off/conflict policy, one-winner execution rules and ownership owners are not changed. Existing five-position veto remains after raw formation before artifact/risk. No target or family activation was added.

Concrete uncovered review gaps were timeframe-specific context reuse and occurrence lookup after a neighboring exception emits a trace without a result. Added five guarded synthetic controls, test-only commit **`8328e34f80a6926feb994cbbebcc6a3a11c50cab`**, tree **`aed6d4f5de5d6efc1b0f8caa5fb725f3ded0a47b`**. Result: **5 passed, 11 deselected in 0.42s**. One test confirms fresh calls for 1m/5m/10s/1m; four combinations cover error versus rejection and neighbor before versus after. Actual registry output passes existing V1 selected-contract/selected-trace lookup, canonical bridge and registered consolidation trigger; selected result ordinal, trigger/stop/metadata and trace identity remain exact despite unequal trace/result counts. GAP_GO still has no canonical bridge; the test explicitly uses the neighboring supported family rather than inventing a GAP_GO trigger/target.

Production diff from the original reviewed input is empty. Existing 108-case and overlapping 11-control receipts are retained without rerunning them or claiming 119 distinct cases. The five added cases are new, not a full-suite/Windows/CI receipt. git diff --check passed. This is a local review, not independent external approval. No AGENTS file found in applicable checkout/parents; existing ledger reviewed, unchanged because no owner/module retirement occurred.

**Publication recommendation:** suitable for separately authorized draft publication, independent exact-head review and required Linux/Windows CI. No push or merge was performed. Remaining GAP_GO trigger bridge/structural contract and management gaps stay open; deduplication alone proves neither raw intent nor natural progression. Corporate/SEC/listing work remains PARKED, successful observations and historical UNKNOWNs/failed receipts/GUI draft preserved. No provider/broker calls, acquisition, observation or trading.

PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

### PR1152 publication, independent review and CI acceptance — 4 November 2026

Published one draft [PR1152](https://github.com/NelzonMamani/ibkr-trading-system/pull/1152) from `fix/gap-go-alias-evaluation` at exact candidate **`a629a7cb8d86d90a253503fd943f54a1685c9f0d`**, tree **`a4d4ced00b3b407e37bf01b29a52ad5c47f69eba`**. Clean local state verified before push. Fetch confirmed accepted main/base **`f55c0225fc55adc379d766ba7ebfeac88a322f1f`**, tree `9cd60e0b89ec2b589748973f6357608ad00db60f`; no delta, rebase or baseline substitution. Production diff is confined to the existing setup factory/alias declaration, registry projection and trace field; tests and two existing documentation files are separate. Inherited PR1151 documentation receipts remain preserved, with corporate/SEC implementation absent.

Independent agent [review5767413761](https://github.com/NelzonMamani/ibkr-trading-system/pull/1152#pullrequestreview-5767413761) is explicitly bound to candidate head a629a7cb and found no blockers. COMMENT, not human approval. Reviewed declared-only grouping, enabled-name provenance, independent securities/timeframes/snapshots/repeated calls, undeclared same-class independence, deterministic ordering, rejection/error traces, selected contract/trigger/trace occurrence identity and unchanged safety owners. No new defect or additional test need arose; no source changes after review/publication.

[CI41820198272](https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/41820198272), pytest run1387, completed SUCCESS on first attempt. All three jobs passed:
- verification-scope `126541160043`: HARNESS_ONLY=False, existing workflow unchanged.
- Linux/test `126541232893`: **3823 passed, 3 skipped, 4 warnings in224.56s**.
- windows-offline `126541232524`: **3825 passed, 1 skipped, 268 warnings in532.62s**; focused diagnostics95, maintenance/news37 and native float-cache9 passed; serial manifest/single-use admission40 passed; all six offline cache subprocess fixtures passed; actual Windows PowerShell5.1 exit propagation13 and observation harness46 checks passed, parser and artifact upload passed. Expected deliberately failing child controls validate failure propagation and are not failed workflow steps. Only alternative harness-only installation/identity steps were conditionally skipped; required cache/PowerShell checks executed.

Both full-suite checkout logs identify tested merge **`307fc275d7415629677daca86e08e893817bb9d3`**. Fetched Git object has tree **`a4d4ced00b3b407e37bf01b29a52ad5c47f69eba`**, exactly the candidate, and parents f55c0225/a629a7cb. Fresh final PR verification: same base/head, draft=true, merged=false, mergeable=true/clean; no review threads. No CI retries or completed local-suite repetitions. Historical 108-case/overlapping11-control and five additional control receipts remain separate; never summed as119 distinct tests.

**Recommendation:** exact candidate is suitable for separately authorized controlled integration review; keep draft/unmerged pending that authorization and fresh requirements verification. This receipt is saved on separate `docs/pr1152-ci-acceptance` so reviewed/CI head remains unchanged. One next action is controlled integration review of PR1152 at the literal candidate head/tree, not another repair or observation.

Completion remains only declared-alias single evaluation/result/trace per input context, alias-only support and requested-name/occurrence provenance. GAP_GO canonical trigger-bridge/structural-contract and management gaps remain OPEN. No new target policy, independent GAP_CONTINUATION detector, numeric management, intrabar ordering or natural progression is certified. Five-position post-formation/pre-artifact/risk veto, GUI draft, historical UNKNOWNs/receipts and PARKED corporate/SEC/listing work preserved. No merge, provider/broker collection, preflight, observation or trading.

PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
