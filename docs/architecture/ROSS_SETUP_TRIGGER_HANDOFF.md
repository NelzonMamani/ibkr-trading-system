# Ross selected setup to intent contract

The production owner is `RossMomentumStrategyV1.process_watchlist`: canonical registry result, DecisionEngine selection, same-family execution-timeframe TriggerEngine, structural price mapping, existing permission/tradeability gates, then intent/cycle selection. `decision_policy.build_trade_intents` is a separate consumer; passing its tests alone does not prove this production boundary.

The original authorities 06 section 8 and 09 section 9 name ORB/premarket-high, micro pullback, bull flag and consolidation breakout as initial families. Failed breakout is caution/exit, with VWAP context. The 68-item reference vocabulary is not blanket entry activation. Accepted flat-top and three-bar/second-pullback extensions retain their existing session, input and trigger policies. Candle-only, disabled halt and risk-off signals do not authorize long entries.

A selected entry must retain its own numeric trigger and structural stop, rationale and approved target model. The generic optional target field does not override Ross's later PR1030 target-presence guard. The production intent now retains `target_model`; this descriptive model is not a fabricated numeric take-profit. A missing target or missing canonical selected contract blocks intent with an explicit terminal reason even if the trigger fired. Currently target-less detectors (including ORB and three-bar/second-pullback) remain unavailable for intent until their setup-specific target policy is supplied through the canonical result. This change does not invent that policy.

Core canonical contracts supersede contextual trigger guesses for the same family. PRE/RTH_OPEN use the existing genuine 10s execution stream; steady sessions use the existing 1m stream. Missing/stale execution provenance stays non-actionable. Micro pullback exports its detected pullback high/low; consolidation exports its own range and uses the existing range-break primitive with same-stream volume confirmation. Explicit structural stop and acceptance invalidation remain separate trigger facts; trade geometry uses the structural stop when supplied.

Tests in `test_ross_selected_setup_handoff.py` include real consolidation registry-to-intent checks and explicitly synthetic pre-produced contract handoffs through production functions. They do not certify natural Focus selection, news coverage, Paper order lifecycle or trading readiness. No risk/execution/session/catalyst/volume thresholds are changed.

## Accepted-main setup-family audit — 3 November 2026

Audit source pin `a66b43f2b44d98405d1dc30bc62f8c359a5f3fbc`, tree
`04a58818e178764c28e0fecab472fe1dbbbc0154`. This updates the existing handoff
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

For eight families only (ORB/PMH/Micro/Bull/Flat Top/Consolidation/Three-bar/Second),
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
| FIRST_PULLBACK / RF.FirstPullbackPattern P_FIRST_PULLBACK | >=6,3-bar impulse+2-bar controlled first pullback+reclaim; EMA9/20 scoped policy | X; dedicated TR first-pullback evaluator; model retest impulse high/extension. Current RF delegates numeric anchors to PatternBase rather than returning its measured local high/low | PR1029 D; `test_strategy_runtime_setup_binding` conditional fields only; common `detect_first_pullback` is NOT this RF runtime owner; full numeric handoff gap |
| GAP_GO / RF.GapGoPattern P_GAP_GO | >=4, prior-close gap, level pressure, spread/RVOL, VWAP/EMA context; ORB_GAP_GO policy1m/5m | G in current actual setup producer; TriggerEngine has explicit GapGo special evaluator, but SetupEngine does not emit GAP_GO and C omits it. Inferred anchors; HOD-extension model | `test_gap_go_pipeline_activation`, PR1029 D and engine unit controls; no complete actual strategy invocation proof |
| GAP_CONTINUATION / RF.GapGoPattern P_GAP_GO | Exact same implementation/input as GAP_GO | Registered alias causes SECOND same-ID evaluation; not independent signal/confirmation | Registry inventory proves duplicate; no independent family entry or natural proof |
| ORB / BR.OpeningRangeBreakoutPattern -> CP.detect_orb P_ORB | >=6, REGULAR/open phase; ORH/ORL, volume, VWAP/EMA/MACD/context; ORB policy1m/5m | C; registered ORB confirmation; numeric ORH/structural OR-low stop/invalidation; NO target model | `test_orb_pattern`, PR1029 D; selected-handoff tests supply synthetic target or assert missing_target. Real detector remains target-blocked |
| PREMARKET_HIGH_BREAK / BR.PremarketHighBreakPattern -> CP.detect_premarket_high_break | >=2, original PMH, hold/acceptance/volume/spread; PMH policy1m, preferred5m/10s | C; registered PMH break/hold; explicit stop distinct from PMH acceptance invalidation; HOD/next-resistance target | `test_ross_selected_setup_handoff` H; PR1029 D; PR1082 structural invalidation/missing/stale boundaries |
| CONSOLIDATION_BREAKOUT / BR.ConsolidationBreakoutPattern P_CONSOLIDATION_BREAK | >=8, own compressed range and volume; genuine execution stream | C; range-break evaluator, explicit range high/low stop/invalidation; Range expansion model | `test_ross_selected_setup_handoff::test_real_consolidation_registry_to_production_intent` D->H with session/execution boundaries; no natural proof |
| FLAT_TOP_BREAKOUT / PB.FlatTopBreakoutPattern -> CP.detect_flat_top_breakout | >=5, >=3 flat-resistance touches, volume/spread/RVOL; VWAP scoped DEGRADE | C; dedicated flat-top confirmation; explicit resistance/consolidation-low stop; measured range model | `test_flat_top_breakout_pattern` +/-; PR1029 D; selected-handoff H; natural UNPROVEN |
| HOD_BREAK / PB.HODBreakPattern -> CP.detect_hod_break | >=6, RTH-sourced HOD/compression, volume, spread; scoped HOD requirement | X; TR HOD trigger; explicit structural stop/invalidation; NO target model | `test_hod_break_pattern` +/-; `test_setup_family_pipeline_certification` manually builds intent, NOT actual V1 target admission. Target remains missing |
| OPENING_DRIVE / PB.OpeningDrivePattern -> CP.detect_opening_drive | >=5, RTH opening phase/impulse/volume/limited pullback | G; dedicated TR evaluator but actual contextual producer has no OPENING_DRIVE and C omits it; explicit trigger/stop; NO target model | `test_opening_drive_pattern` and PR1029 +/- D; no complete actual V1 raw-intent proof |
| KEY_LEVEL_BREAK / RF.KeyLevelBreakPattern P_KEY_LEVEL_BREAK | >=2, specific prior-known key level, continuation/liquidity acceptance | G; dedicated TR evaluator but no contextual producer/C; explicit selected level and structural stop/invalidation; next-overhead-key model | `test_key_level_break_pattern` +/- level/source/boundary controls; no actual V1 same-family handoff proof |
| ABCD / RF.ABCDPattern P_ABCD | >=7, bounded swing sequence A/B/C and retracement; scoped MACD DEGRADE | G; dedicated TR evaluator but no contextual producer/C; explicit C stop and numeric D projection/model | PR1029 +/- D, `test_pr1089_canonical_trace_family`; projection is evidence, not a proven actual V1 trigger/raw-intent route |
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
