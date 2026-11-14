# P02 — Statistical Intraday Momentum — STRATEGY GOVERNANCE
**Catalogue path:** `03_STRATEGIES/P02_STATISTICAL_INTRADAY_MOMENTUM/GOVERNANCE/STRATEGY_GOVERNANCE.md`  
**Timestamp:** 2026-02-08T00:52:50Z

## 1) Strategy boundaries (non-negotiable)
- This strategy is **continuation momentum**, not mean reversion.
- Stock selection is **eligibility + ranking**, not entry/trigger logic.
- Entries are executed only via canonical `XL_*` primitives.
- No strategy code may bypass OS risk engine, execution authority, or no-trade contexts.

## 2) Invariants
- **No partial coverage:** all canonical IDs are classified.
- **Traceability:** every decision produces an auditable artifact (E14/M4).
- **Mode parity:** strategy must behave consistently in SIM/PAPER/READ_ONLY/LIVE (E7).
- **Data provenance:** every feature has provenance (M10).

## 3) No-trade contexts (E16)
Strategy must not emit entry intents when:
- market closed or session phase disallowed
- stale/invalid reference prices
- spread/liquidity outside bounds
- max consecutive losses reached
- risk engine veto
- symbol cooldown active
- regime explicitly disallowed (if enabled)

## 4) Change control (M8)
Any parameter change must:
- occur only in `strategy_policy.py` knobs
- be accompanied by a verification run (E21)
- record a change note (what changed, why, expected impact)

## 5) Safety
- Default direction: LONG-only, unless explicitly certified for shorts.
- Event/halts: denied until specialised handling is certified.


## 2026-11-14 — DRAFT bounded native Template A bridge (not adopted or enabled)

This proposal is a new project calibration for a synthetic-only prerequisite,
not historical Ross doctrine and not a claim that the existing adapter is
complete. Root coordinator adoption after independent contract review is required
before implementing this proposal. The ordinary policy remains unchanged/off.

Existing authority: ALGORITHM execution law §0 requires conditions,
confirmations, a genuine SF, one XL and invalidation; Template A §10 permits
SF_OPENING_RANGE_BREAKOUT / 01_XL_ORB_BREAK / INV_LEVEL_LOSS. The existing P02
strategy_policy_v2.py T_OPENING_BREAK_HOLD requires a full structure-bar hold and
RVOL>=2. Its structural invalidation law uses level loss. Existing
strategy_policy.py supplies unchanged bar-score threshold .7, 30..360-minute
activation interval, .005..05 volatility band, liquidity/spread rules and explicit
2R numeric target construction. The proposed route must not substitute the
current adapter's gap/RVOL score for the native bar-based decision.

Proposed bounded definitions:

- Default off. A separate in-process TEST/PAPER/SMALL enrollment can exercise
  Template A only. The normal strategy enable flag does not imply enrollment;
  environment input, session overrides and SIM activation shortcuts cannot grant
  native admission. No additional strategy is enabled by default.
- Use the existing completed HistoricalDataResult, CandidateIdentity, session and
  reference owners. Require current-session, end-confirmed, security-bound STK/USD
  history with an identical positive con_id, finite valid OHLCV, aware timestamps,
  unique ordered contiguous one-minute bars and authoritative session boundaries.
  Unknown coverage, unresolved identity, gaps, stale/future/forming bars or missing
  required reference/quality facts block the route. No snapshot-to-bar fallback,
  internal level injection or renewal of old observations is permitted.
- NEW calibration proposal: measure the opening range from the first thirty
  completed one-minute bars after the actual RTH open. This aligns the native
  measurement with the existing P02 earliest activation minute30; it is not the
  Ross native ORB window. Aggregate five-minute structure bars only from complete
  blocks of that same one-minute stream aligned to the actual open.
- Require a whole completed five-minute structure bar, starting at or after range
  completion, whose low and close are strictly above measured OR high. Keep the
  canonical common SF detector and registered ORB trigger exercised with real
  measured inputs, plus the unchanged P02 native signal/regime/time thresholds.
  Equality, wick-only breakout, forming hold, missing source and weak bar score
  remain blocked. Retain V2 RVOL>=2 participation confirmation, all canonical C/K
  requirements, own occurrence identity and original quote/history provenance.
- NEW numeric mapping proposal: current executable long quote must be strictly
  above measured OR high; that level is the retained INV_LEVEL_LOSS structural
  stop. It is not the Ross OR-low stop. Keep the existing explicit P02 2R target
  authority, calculated from actual proposed quote entry and this structural stop
  through TakeProfitAuthority, subject to ordinary risk/target validation. Do not
  import Ross numeric-TP=None or invent a descriptive objective. This grants no
  trailing, reduction, adds, re-entry or recurring-management enrollment.
- Bar-score values are heuristic scores, not probabilities. Retain original
  features, weights and threshold. A finite raw score already in [0,1] may
  be carried as heuristic intent confidence; otherwise retain a veto, without
  clipping, constant uplift or gap/RVOL substitution to satisfy shared admission.
- Strategy output is a provisional proposal for the existing Core risk stage;
  C_RISK_ENGINE_APPROVED/K_RISK_ENGINE_GREEN_CONFIRM cannot be asserted until the
  actual shared risk decision. The admitted order remains contingent on all
  existing position-truth, recovery, daily-risk, ownership, inventory, capital,
  reservation and final-write guards. Unknown safety facts must veto admission.

Concrete implementation dependencies remain to be reviewed: the active adapter
has no native completed-context provider, policy activation is not wired to an
explicit native test opt-in, P02 V2 is not registered in the active V2 registry,
and active Core applies the Ross integrity triple to every strategy. The current
adapter genuinely lacks SF/XL/INV, so its PATTERN_INVALID rejection is a valid
contract veto, not evidence that removing that guard is safe. Existing E22/P9/
portfolio calls below the active manager return are unreachable; a positive
integration proof must use those existing owners in the active call graph, never
copy or activate the legacy tail. This draft neither removes a veto nor claims a
positive Core fill/accounting proof.

### Required C/K evidence map and exact unresolved prerequisites

This table is a proposed ownership map, not a declaration that the producer is
implemented or its UNKNOWN facts passed. Every listed required condition must
receive a bound, inspectable source fact; absence/conflict means veto.

| Canonical requirement | Existing evidence / owner and remaining dependency |
| --- | --- |
| C_TIME_OF_DAY_ALLOWED, C_SESSION_PHASE_ALLOWED | P02 ActivationSpec 30..360 minutes plus actual covered RTH boundaries. The proposed first bridge is restricted to the existing session_pct_change.covered_opening_window: RTH_OPEN extends from09:30 until10:30 New York (minute60). The proposed thirty-minute OR plus a completed five-minute hold can therefore qualify from10:05 until10:30, subject to actual receipt coverage and all other gates. No calendar extraction is needed for that bounded interval. Later-session enrollment would need a separately reviewed general-RTH coverage owner. Do not call the opening validator with a forged earlier assessment time. |
| C_HALT_STATE_ALLOWED, C_SSR_STATE_ALLOWED | CandidateMetrics halted/ssr with known boolean source facts; stock_selection_spec.allow_halts=False / allow_ssr=True. Unknown halt/SSR provenance cannot become false by default; no halt-resumption enrollment. |
| C_DATA_QUALITY_OK, K_DATA_QUALITY_CONFIRM | Existing candidate quality/resolution flags, completed HistoricalDataResult, matching qualified CandidateIdentity and real quote snapshot. No cached positive flags or externally supplied detected setup. |
| C_REFERENCE_PRICE_VALID | Existing reference_resolved, reference_quality_tier and prior-completed-session reference provenance, bound to the same security; missing/nonpositive/nonfinite reference vetoes. |
| C_HAS_BID_ASK, C_SPREAD_WITHIN_LIMIT, K_SPREAD_CONFIRM | Original complete MarketSnapshot positive bid<=ask, quote_time_rejection and historical rejection flags; unchanged P02 25bps maximum, not the looser V2 narrative .60% threshold. Revalidate at proposal/risk/dispatch without replacing quote time by receipt time. |
| C_LIQUIDITY_WITHIN_MIN, K_LIQUIDITY_CONFIRM | P02 UniverseSpec minimum dollar volume20M, source-bound day volume and price; V1/V2 disagreement does not lower this threshold. |
| C_STALE_DATA_REJECT | Existing quote_time_rejection LAST_TRADE age limit and historical veto retention; newest fully completed 1m bar must belong to the current expected one-minute completion interval (proposed NEW interval-completeness calibration), with no gaps/future bars. Exact observation/assessment times stay distinct. |
| C_FLOAT_KNOWN_OR_ALLOWED | Existing statistical_stock_selection_spec float_max_millions200; proposed enrollment requires known finite positive float within that maximum, rather than treating unknown as permission. |
| C_LEVELS_BUILT_OK, C_INVALIDATION_DEFINED, C_SETUP_FAMILY_ACTIVE, K_INVALIDATION_PRESENT_CONFIRM | Security/session-bound measured OR from complete history; common SF detector; own Template A occurrence; independently retained stop/invalidation below executable proposed entry. No Ross detector policy or assumed OR-low anchor. |
| C_VOLATILITY_STATE_ALLOWED | Native P02 evaluate_regime / realized-return standard deviation .005..05; preserved independently of ATR. |
| C_ATR_WITHIN_BOUNDS | **UNRESOLVED POLICY.** ALGORITHM §4 and CAPABILITY_MAP require this condition, but no P02 ATR definition, lookback, unit, numerical lower/upper bounds or evaluator is present. The V1 return-stdev band is not ATR; risk_policy StopModelSpec atr_multiple1.5 is a placeholder stop multiplier, not admission bounds. This condition remains UNKNOWN and blocks native admission. |
| C_RELATIVE_VOLUME_OK, K_RELATIVE_VOLUME_CONFIRM | Existing source/resolution provenance for candidate RVOL plus P02 T_OPENING_BREAK_HOLD RVOL>=2. Missing usable execution RVOL does not pass. |
| C_ABSOLUTE_VOLUME_OK, K_VOLUME_CONFIRM | Existing statistical_stock_selection_spec min_volume500000 plus same-stream completed volume, independent of dollar-volume and bar-score evidence. |
| C_RISK_ENGINE_APPROVED, K_RISK_ENGINE_GREEN_CONFIRM | Actual shared RiskEngine, position truth, recovery/daily-risk/capital/reservation/final-write owners. NEW staged proposal/admission split requires explicit adoption; never mark this true before the risk decision or use a test ALLOW substitute. |
| C_STRATEGY_PERMISSION_OK | Existing strategy enable flag plus separate explicit default-off native test enrollment; no flag implies another. |
| C_MAX_CONSECUTIVE_LOSSES_NOT_REACHED | Actual DailyRiskGovernor source facts and configured limits; V2 separate two-/three-loss behavior is not implemented by enabling the adapter and cannot be called certified. Unknown durable accounting/loss facts veto; reuse the concurrent committed-accounting prerequisite. |
| C_SYMBOL_COOLDOWN_EXPIRED | ActivationSpec120-second cooldown needs a bound authoritative prior-entry/fill-history read through existing lifecycle/storage owners. Current P02 adapter does not implement it. A current-run empty result is not proof that prior-run durable history is empty. Missing/conflicting history must veto; no new parallel cooldown ledger. |
| C_NO_TRADE_CONTEXT_FALSE | Existing stop/breaker, daily-risk/recovery, position truth, portfolio and risk no-trade decisions; missing or uncertain authority remains blocking. |
| K_BREAK_AND_HOLD_CONFIRM (Template A) | Proposed whole completed 5m hold plus real registered ORB evaluator, with retained source/occurrence identity and one permitted XL; optional retest is outside this initial bridge. |

Exact next policy decision: define P02 ATR measurement (true-range/ATR formula,
completed timeframe and lookback), units and finite admissible bounds, with
source/evidence rationale independent of the desired positive fixture. This is
not another permission to flip activation and cannot be resolved by renaming the
existing return-volatility gate. Completed-context, existing covered-opening-window binding and cooldown read
guarantees, plus complete C/K mapping, must also be implemented and reviewed
before admission.
Until then this document remains DRAFT/not adopted; native P02 PAPER admission
and a claimed positive Core accounting proof remain blocked.

V2 mandatory partials, stop migration and time-stop laws are not waived or
superseded by a possible future entry/fill/initial-protection proof. Such a bounded
proof would terminate before claiming managed continuation, full P02 deployment
or operational enrollment. Existing one-share/default behavior, all five ownership
vetoes and PAPER_READY=NO; PAPER_READINESS_GATE=FAIL remain.


## 2026-11-14 — Separate ATR measurement/calibration proposal (NOT ADOPTED)

This is a concrete proposal for the unresolved C_ATR_WITHIN_BOUNDS prerequisite,
not adoption of the native-entry draft, an admission bound, stop model or exit
policy. ATR admission remains UNKNOWN/fail-closed. The existing .005..05
population standard deviation of one-minute returns in signal_engine/features.py
is a separate measurement. risk_policy.py's atr_multiple1.5 is a placeholder
stop multiplier and supplies no admission bounds.

Measurement candidate, explicitly NEW project choices where specified:

- Use Wilder true range and Wilder smoothing, as defined in J. Welles Wilder Jr.,
  *New Concepts in Technical Trading Systems* (1978), the original ATR reference.
  This bibliographic formula attribution is not a claim of a new online source
  retrieval or empirical P02 calibration. Canonical P02 ALGORITHM and
  STRATEGY_CAPABILITY_MAP require ATR but supply no numerical bounds.
- Propose fourteen completed one-minute true ranges, computed from the same
  validated current-session stream as the completed-context prerequisite. For
  bar i, TR_i=max(H_i-L_i, abs(H_i-C_(i-1)), abs(L_i-C_(i-1))). Need fifteen
  contiguous completed current-session bars to obtain fourteen true ranges.
  Exclude the first bar's opening gap: its predecessor must be an actual
  completed bar from this session, not a fabricated close or prior-day reference.
  Session reset and this exclusion are NEW project measurement choices, not a
  quotation from Wilder or Ross. No overnight carry or forming-bar update.
- Seed ATR_14 with the arithmetic mean of the first fourteen TRs; then update
  ATR_i=(13*ATR_(i-1)+TR_i)/14 over every subsequent completed current-session bar.
  The lookback14 is a smoothing period, not permission to discard earlier seed
  history and reseed from an arbitrary rolling suffix. Contiguous open-aligned
  context makes the seed/reproduction deterministic. Preserve all input/member
  timestamps, identity, source request and completion provenance.
- Publish ATR in USD/share and ATR_pct=100*ATR/C_latest_completed for comparison
  across prices. Use the latest completed close as denominator, not a newly
  received quote or proposed fill. Reject unknown identity, currency, timestamp,
  nonfinite/nonpositive price, invalid OHLC, incomplete/gapped/foreign/stale/future
  context and insufficient warmup; never substitute zero or return volatility.
- Independent arithmetic oracle: fourteen TRs of1 seed ATR1; next TR2 produces
  ATR15/14 (about1.0714285714), and at completed close100 yields the same numeric
  percent. A gap from prior close100 to H102/L101 has TR2, not its intrabar range1.
  These synthetic examples test formula correctness only; they justify no gate.

Admissible-bound contract proposed: a separately adopted finite lower/upper pair
in ATR_pct units with 0<=lower<upper, inclusive endpoints. The actual lower and
upper values are UNRESOLVED, represented as unavailable, not zero/infinity or an
unbounded pass. Even a correctly measured ATR cannot establish admission while
bounds or their authority are missing. No OR/RVOL exception is introduced to
bypass the canonical required ATR condition.

Calibration rationale and required evidence: the repository's synthetic signal
and execution fixtures establish mechanics, not representative market
performance. No approved representative, independently held-out P02 historical
sample with costs/coverage and outcome definitions has been established here.
Therefore numerical bounds cannot presently be justified. Do not choose them to
admit the positive fixture or copy the return-stdev band/stop multiplier.
Before numerical adoption, define the approved historical source/provenance,
security/session/price/liquidity universe and missing/halts/corporate-action rules;
separate development from validation by dates and securities; freeze the bound
selection procedure before held-out evaluation; report sample/coverage limits,
low/high/adverse cases, sensitivity and uncertainty against unchanged P02 signal,
risk and target/management rules. This is a calibration prerequisite, not
permission to acquire provider data in this batch. Reuse only separately approved
available offline data; no observer/provider/broker collection is authorized.

Context/cooldown work can proceed independently after its bounded contracts are
reviewed and adopted. This ATR proposal does not grant activation, risk ALLOW,
a TradeIntent, native SF/XL/invalidation adoption, management enrollment or a
positive Core proof. P02's own existing target/management contracts and all five
ownership vetoes remain. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


## 2026-11-14 — ADOPTED bounded completed-context prerequisite (NEW project policy)

After independent contract review by next_session_contract_review, adopt ONLY the
following completed-market-context prerequisite under the user's delegated
authority. This supersedes the insufficient self-declared synthetic-frame
proposal; it does NOT adopt Template A/native entry, ATR calibration, risk ALLOW,
activation or target/management changes.

Existing HistoricalDataResult gains additive optional request ownership facts,
unknown by default. A frozen HistoricalRequestSpec in its existing module retains
actual normalized transmitted barSizeSetting, whatToShow, useRTH, formatDate,
endDateTime, durationStr and keepUpToDate. Existing native and ib_insync request
owners capture these plus detached dispatched contract identity at actual SDK
dispatch, original aware UTC dispatch clock, and actual matching end-callback
clock/raw start/end facts. Timeout/error/no end cannot manufacture completion.
Existing cache, reuse, fallback, slicing and normalized-provider wrappers must
preserve these facts without renewing their clocks or overwriting conflicts.
UTC_BAR_START semantics are granted only by the supported actual intraday
formatDate2 request owner; daily/custom/ambiguous/unknown semantics are ineligible.
No global history request default changes to force qualification.

P02 consumes exact completed nonstreaming one-minute TRADES facts through the
existing history/identity/session/quote/reference owners. Require matching
positive integer con_id and canonical symbol; accepted/history/reference
identities must be STK/USD. Quote binding uses only its exposed symbol/con_id,
not invented fields. Require known request/completion identity, finite valid
positive OHLC/nonnegative volume, aware bar-start times, strictly ordered unique
contiguous current-session bars from actual covered RTH open through the latest
completed minute. No sorting, gap filling, dropping forming tails, snapshot
fallback or foreign/prior-session substitution. Preserve original raw timestamps,
request/cache/acquisition provenance and normalized UTC interval bounds.

NEW interval-quality choice: newest completed end age is [0,60)seconds at actual
assessment; equality60 is stale. Require original dispatch<=original completion
<=current assessment and EVERY bar end<=original completion: a bar forming at
retrieval cannot become eligible by waiting or cache reuse. Require at least16
completed one-minute bars for the existing fifteen-minute return and at least
three complete five-minute blocks. Derive five-minute bars solely from complete
five-member blocks aligned to actual open; retain the members, never use a
second independent history or partial block.

Use covered_opening_window at the real current assessment, requiring RTH_OPEN
and its original coverage fingerprint/boundaries; no forged earlier clock,
phase override or new calendar engine. Existing quote_time_rejection and
historical evidence vetoes remain; original positive bid<=ask, quote/volume
facts and acquisition/market times stay distinct. Require qualified resolved
execution-usable, nondegraded/non-synthetic positive canonical reference for the
same security and covered previous completed session, preserving provenance.

The producer detaches nested input facts and fingerprints raw plus derived
content. A new explicit consumer in existing signal_decision.py revalidates
these facts, current calendar/configuration and freshness before delegating to
unchanged decide_intent. No mutable cached positive authority or default
activation follows. The native bar decision is a component proposal only;
ATR remains UNKNOWN and actual Core structural veto remains intact. All five
ownership vetoes and ordinary defaults remain. The separate ATR proposal above
was independently cleared as an accurate NOT-ADOPTED proposal; no numerical
admission bounds or stop/management rule are adopted.


## 2026-11-14 — ADOPTED bounded durable cooldown observation (NEW project policy)

Independent next_session_contract_review cleared this bounded read contract;
under delegated authority adopt it BEFORE implementation. Existing120 seconds
remains unchanged. This adopts observed timing and fail-closed unknown-history
behavior only, not the native-entry draft or a negative-clearance capability.

Every distinct positive, durably accounted P02 ENTRY_FILL, including partial
entry fills, contributes its ORIGINAL authoritative execution timestamp. The
anchor is the maximum validated original timestamp. Later distinct executions
reset that anchor; late older events/duplicates do not reset from receipt or
registration time. Proposals, reservations, risk decisions, acknowledgement-only,
cancellation/rejection, exits/reductions and process/session/day changes neither
start nor clear cooldown. Generic lifecycle register-time or receipt-time
fallbacks do not establish an authoritative entry timestamp and remain UNKNOWN.

Bind exact P02 policy/execution identity (statistical_intraday_momentum /
StatisticalIntradayMomentum), actual account, qualified positive con_id with
consistent symbol/STK/currency and actual effective mode. No trader_type guess,
symbol-only alias, configured-default account or foreign strategy/mode sharing.
Read the existing canonical lifecycle/storage authority coherently across current
AND prior same-mode runs; PR1229's filtered financial projection is not a complete
cooldown history source. Target-independent entry observation must not rewrite
P02's own numeric2R or management contracts. Validate positive accounted entry,
original timestamp/source, execution identity and durable journal binding;
conflicting versions of the anchor invalidate it. Independently validated recent
facts survive other missing/conflicting/unavailable evidence where available.

At aware current UTC assessment, negative age is UNKNOWN; observed timing is
ACTIVE for age[0,120) and ELAPSED at EXACT equality120 and above. This is a timing
classification only. Missing/unavailable/unmarked/conflicting history, incomplete
prior-run scope or pending/uncertain intake cannot become proof cooldown is clear.
EMPTY/EXPIRED eligibility requires authoritative complete capture of the entire
preceding120-second interval and its boundary across all intersecting runs and
owned request/intake states. Existing execution_snapshot explicitly supplies
REQUEST_ONLY completion, not a no-late-fill/interval guarantee; neither
execDetailsEnd nor fill-stall telemetry nor new run timestamps/120s uptime fills
that gap. Therefore coverage remains UNKNOWN and eligibility=False for every
currently supported read outcome, including ELAPSED/no-known-entry.

Do NOT add capture-complete flags, a synthetic certificate, timer, capture ledger
or run/genesis timestamps claiming this missing guarantee. The exact unresolved
capability is authoritative finite interval intake plus owned-request completeness,
including pending/uncertain and late-fill ordering, through existing owners. No
positive negative-clearance test can be manufactured from prepared flags.
Implement the honest observational read and causal current/prior-run/fresh-process
controls; retain native admission veto until a separately justified guarantee is
established. No order replay, ownership restoration, fence restoration, quarantine
clearing, operational enrollment or resumption follows. Actual Core structural
veto and ATR UNKNOWN remain; all five ownership vetoes are intact.


### Implementation checkpoint (offline candidate; final review/CI pending)

Completed-context implementationd889f7d4 and bounded cooldown observatione435f218
follow their separately reviewed/adopted contracts above. Source owner and
consumer tests177pass; independent context136pass subset. Cooldown42new cases
independently pass with coverageUNKNOWN/eligibleFalse in all outcomes. Actual Core
still rejects incomplete native P02 entry; no complete cooldown clearance or
positive Core admission is claimed. Full source, failure, evidence and remaining
guarantee details are in SAME3's latest bounded-prerequisite entry. ATR proposal
remains NOT ADOPTED with numerical bounds unresolved; original entry, target and
management draft scope is not implicitly adopted by these prerequisites.


### Independent ATR authority/data audit (read-only; no numerical adoption)

Bounded review at b17e7a93 confirms bounds cannot presently be justified:
strategy_assumptions.md3–8 is qualitative; ALGORITHM104–106 supplies no values;
strategy_policy_v2.py546/560/565/594/607 says pending replay calibration.
V1 strategy_policy48–49/features45–48,82–83 measures return population stdev;
risk_policy15/34 is a placeholder stop multiplier, not admission authority.
Test_scoring_determinism9–10 and test_completed_context61–76 are authored
synthetic streams/callbacks, not representative security/session/cost outcomes.
Existing src/core/replay_engine.py19–24,52–73 replays recorded events; it does
not supply a calibrated dataset. src/learning/models.py8–24 has trade records
without enforced held-out/provenance/cost contracts, and policy_proposal.py7
imports RossMomentumPolicy. It cannot authorize P02 calibration. Fixed
src/execution/slippage_model.py16–21 and commission_model.py10–13 are simulation
assumptions, not observed P02 costs. Tracked news-source evidence CSVs are not
P02 OHLCV training samples; no approved P02 dataset manifest was identified.
Retained databases/logs were not opened or treated as calibration authority.

Smallest separate calibration prerequisite: approved already-available immutable
offline OHLCV/quote manifest with security/session/time/adjustment/missing/halts
and cost provenance; freeze chronological/security development versus held-out
splits and P02 outcome/bound-selection procedure before validation. Report
sensitivity/adverse regimes/coverage uncertainty. No provider acquisition,
fixture-tuned bounds, new engine or activation is authorized here. ATR admission
remains UNKNOWN/fail-closed. Full cooldown clearance also remains blocked by the
separate native intake/request-history guarantee documented above. The SAME3
acceptance receipt carries exact integration/review/CI identities and limits.


## 2026-11-14 — ADOPTED measurement-only ATR contract (NEW project policy)

Under delegated authority, after independent next_session_contract_review CLEAR,
adopt ONLY the preceding recorded ATR measurement proposal: Wilder TR, fourteen
completed current-session one-minute TRs (bars2..15), arithmetic seed atbar15,
then Wilder recurrence frombar16. Exclude opening gap/overnight carry; reset each
actual covered session. Report USD/share and percent of each step's own completed
close. All derived arithmetic must remain finite. Existing completed-context
minimum16, original completion clocks, security, calendar, quote/reference and
all rejection rules remain unchanged. No return-volatility substitution.

The pure offline feature-owner API accepts immutable UTF8 JSON bytes (<=16MiB)
with a required expected SHA256, unique keys, no nonfinite literals, exact
P02_ATR_OFFLINE_V1 schema, dataset identity, SYNTHETIC or MARKET_UNVERIFIED
classification and1..512 unique security/session records. Each record contains
original source_facts, recorded assessed_at and expected source/derived canonical
SHA256 fingerprints. Datetime wrappers use exact datetime/fold fields; no inferred
OHLCV/identity or counter reconstruction. Existing context validation at that
original assessment is HISTORICAL_REPLAY_ONLY; effective covered calendar/config
must match the expected derived fingerprint. Input metadata grants no dataset
approval. No environment override, acquisition, storage constructor or live replay.

Canonical immutable reports retain input hash, source/derived hashes, security,
calendar/configuration, request/completion and original member timestamps, TRs,
seed/update values, coverage and explicit validated context-quote availability.
Costs are UNAVAILABLE: this API does not validate cost evidence or infer zero.
Invalid/incomplete input refuses report; original source bytes are never changed.
Numerical bounds remain null/unavailable, ATR admission UNKNOWN, eligibleFalse.
This adoption supplies no numerical calibration, native entry, stop/management,
activation, positive Core proof or readiness upgrade. Independent review cleared
the full bytes/report contract before implementation.


### 2026-11-14 — P02 measurement-only ATR and immutable offline validation

Accepted base881e47ff/tree540a6bd9 and receipt698e12ef are preserved once.
Independent next_session_contract_review cleared the complete measurement/bytes/
report contract; adoptionac0c117d precedes implementation. This adopts only the
recorded measurement, not its unresolved numeric bounds or native-entry draft.
Existing features.py now measures Wilder14 TR from the revalidated PR1230
completed context: bars2..15 seed, then every subsequent completed bar, session
reset/no overnight predecessor, USD/share and each step's own completed-close
percent. Immutable result retains member timestamps, TRs/seed/updates and context
hashes. Nonfinite derived arithmetic refuses. No decision/scoring/risk change.

The same feature owner validates bounded immutable UTF8 bytes with exact expected
SHA256, exact schema, duplicate/nonfinite/depth/size controls and expected source/
derived fingerprints. Existing source validation at recorded assessment is marked
HISTORICAL_REPLAY_ONLY; effective covered calendar/configuration must reproduce
the expected derived hash. No configuration is installed from input. Reports are
deterministic canonical bytes, retain original source facts and request/member/
completion provenance, complete1m/5m/TR coverage and explicit context-quote
availability. CostsUNAVAILABLE, boundsnull, admissionUNKNOWN/eligibleFalse; no
dataset approval or performance claim. Missing data is refused, never rebuilt
from completion counters. MARKET_UNVERIFIED and SYNTHETIC are labels only.

Focused causal validation:182passed/2warnings/4.76s across existing P02 tests,
historical completion owners and actual-Core dependency veto. This includes29
new ATR checks (overlap, not additive): independent Fraction recurrence and gap
oracle; seed/update boundaries; no cross-call carry; zero-range measurement
without admission; async aware/raw timestamp serialization; immutable/report
repeatability; source/derived/hash mismatch, stale/forming/foreign/missing inputs,
unknown schema/classification/cost claims, malformed datetime, duplicate keys/
sessions, invalid/deep/oversized bytes and finite-input arithmetic overflow.
Original47context controls and actual Core structural veto remain passing.
No failed test invocation occurred in this implementation prefix; earlier PR1230
failures remain history in preceding entries. Required exact-head review and CI
remain pending; focused passes are not CI acceptance.

Read-only metadata inventory identified no explicitly approved immutable P02
calibration dataset. Across repeated workspace checkouts:166CSV (W02/W03 evidence
matrices),1206DB/SQLite files,249JSONL and3Ross uploadZIPs; no Parquet/Feather/Arrow/
HDF5/Pickle/NumPy files. Original databases/ZIPs were not opened; filenames are
not a completeness claim about their contents or independent market samples.
No schema-writing constructor, acquisition or provider was invoked.

Concrete calibration plan: approve an exact immutable available input manifest
and intended reuse first; if DB examination is needed, use an isolated snapshot,
never a schema-initializing original. Validate qualified security/session/
adjustment/gap/halts provenance and original completed OHLCV; separately establish
quote/cost availability. Freeze chronological/security development and held-out
splits and bound-selection procedure before evaluation. While management/outcome
semantics remain unresolved, publish measurement distributions/coverage only, no
profit labels, expectancy or net-performance claims. Generic STATISTICAL zero
slippage/commission fallback is not observed P02 cost. Numerical bounds remain
unavailable and C_ATR_WITHIN_BOUNDS UNKNOWN.

Cooldown PR1230 observations remain unchanged: every old outcome retains
coverageUNKNOWN/eligibleFalse. A separate observable-local-state versioned
policy is under contract investigation/review; no broker-history completeness
certificate is fabricated from execDetailsEnd, uptime, terminal orders or flags.
Native entry/ATR/management vetoes and all five ownership safeguards remain.
Frozen observation distribution3f48bf3f/sourcec65/calendar unchanged. No observer,
broker/provider, operational recovery or readiness upgrade.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


## 2026-11-14 — Batch B PROPOSAL: observable local-state cooldown (NOT ADOPTED)

This proposes NEW project policy, separate from the adopted historical-entry
observation above. It is default-off and is not implemented or enrolled. It
requires independent contract review and delegated adoption before source work.
It proposes an explicitly named alternative local basis for the P02 cooldown
condition; it does not reinterpret the old API as complete history. Existing
`p02_entry_cooldown_snapshot` must retain coverage UNKNOWN / eligible False.

The proposed contract is `P02_OBSERVABLE_LOCAL_COOLDOWN_V1`. Any future opt-in
selects this policy basis, not a capture-complete flag. Initial proof/enrollment
is restricted to explicitly synthetic TEST/PAPER scope; operational defaults and
other modes remain off. Adopting this component contract would not adopt the
native entry bridge, numerical ATR admission bounds, SF/XL/invalidation mapping,
management or operational permission. All five ownership vetoes remain.

### Predicate and scope

Keep `ActivationSpec.cooldown_seconds=120` as the sole duration owner. Each
distinct validated, durably accounted positive P02 ENTRY_FILL, including an
entry partial, contributes its ORIGINAL authoritative execution timestamp. Use
the maximum such timestamp. Replayed duplicates and late older fills do not
renew from callback, registration, accounting, query or read time. Proposals,
reservations, acknowledgement-only, rejection/cancellation, exits/reductions,
session/day transitions and restart neither trigger nor clear cooldown. P02's
own numeric2R/independent stop remain unrelated to this entry-timing predicate.

Bind exact policy/execution aliases `statistical_intraday_momentum` /
`StatisticalIntradayMomentum`, actual account, qualified positive conId with
consistent symbol/STK/currency, actual effective PAPER mode and current owner
instances. Never infer an account from configuration, a strategy from trader
type, or a security from symbol alone. Missing/ambiguous binding is unavailable.

The proposed local predicate is true AS OF a coherent owner/journal read only
when every observed relevant local record is classifiable and settled, and
either no validated local entry is present or its age is at least120 seconds.
Age below120 is ACTIVE; exact equality120 is locally elapsed. A future timestamp,
invalid assessment clock, missing/unknown run scope, malformed or contradictory
relevant entry, persistence uncertainty, pending/in-flight/uncommitted factual
intake or unresolved owned request makes the local predicate unavailable/false.
An independently valid recent entry can still be reported as a known ACTIVE
veto despite other uncertainty. Fully bound foreign scopes may be excluded;
ambiguous rows must not be silently classified as foreign or empty.

This deliberately narrower local choice says nothing about uncaptured broker
executions, finite broker history, late unseen messages or lifetime request
completeness. `execution_snapshot` / `execDetailsEnd` remain REQUEST_ONLY. Empty
local state is not claimed to prove an empty broker interval. No capture flag,
genesis/uptime clock, second fill ledger or inferred broker guarantee is added.

### Existing owners and proposed immutable evidence

Use the existing lifecycle/storage/execution/callback owners; no new manager,
scheduler, database or cooldown ledger. A future composable read/guard must
detach and fingerprint the relevant current/prior-run canonical events and
snapshots, run provenance, durable native/relationship ownership and progress,
and corresponding current pending/uncertain accounting/callback state. Generic
registration-time or best-effort rows without authoritative entry binding cannot
become valid anchors or proof that all observed local records are settled.
Restored raw native state remains inspection-only and quarantine stays active.

An immutable local evidence token must identify the policy/version/configuration,
account/security/mode, source-context/occurrence fingerprint, original entry IDs
and timestamps, assessment, owning ExecutionEngine/TLE/StorageEngine and actual
SQLite connection generation, existing native client OBJECT, client ID and
connection epoch. Later consumption also binds the actual canonical decision
and exact prospective order/contract/quantity/entry/stop/target. Object/generation
witnesses are process-local, not serialized permissions. A same-ID/epoch client
replacement, reopened/replaced storage owner, restart or account/mode change
invalidates the token. A path or numeric client ID alone is insufficient.

`PRAGMA data_version`, row counts, maximum event time, callback diagnostic counts
or a content hash alone are NOT a version protocol: own-connection writes and
unpublished callbacks can escape them, and a read transaction can remain pinned
to an old snapshot. Durable content must be re-read through the existing owner;
any database version is supplemental to actual owner identity and participating
mutation revisions. The fingerprint is audit evidence, not source completeness.

### Exact participating revisions and mutation APIs (proposed, not implemented)

The ExecutionEngine owns one process-local local-cooldown authority, bound once
to its actual NativeClient, TLE, StorageEngine and SQLiteStore instances. This is
a small guard inside those existing owners, not a manager, source-history flag
or second ledger. An owner without the following participation is unsupported
and cannot issue a positive token. Its initial state is dirty, never known empty.
The proposed owner APIs and revisions are explicit:

- NativeClient `begin_local_intake(kind)` / `finish_local_intake(ticket, outcome)`
  change ingress revision I and the in-flight set. Begin runs at the FIRST owned
  callback operation, before argument parsing, account registration, diagnostic
  counters, request filtering, cache publication or listener invocation. Include
  `execDetails`, `execDetailsEnd`, `orderStatus`, `openOrder`/End, error and
  connection lifecycle/account-ownership callbacks, including ignored, malformed
  and conflicting intake. Connect/disconnect/rebind also invalidate before
  changing ownership. Finish runs in finally; an exception, ignored relevant
  fact, correction or listener failure remains dirty rather than disappearing
  when an in-flight counter reaches0. The current post-publication listener is
  insufficient and its swallowed exception cannot settle intake.
- ExecutionEngine `begin_local_mutation(kind, binding, parent_frame=None)` /
  `finish_local_mutation(frame, outcome)` change owner revision E, in-flight
  frames and dirty/uncertain state BEFORE changing native scope, retained native
  or relationship requests, reservations, accounting/progress/quarantine, native
  order ID or initial callback cache. `_retain_native_request`, native state
  save/load, native-result preparation/drain, request result/terminal updates,
  relationship updates and scope binding participate. Foreign scope is excluded
  only after complete binding; unknown identity invalidates globally for this
  authority. Existing capital/allocation reservation receipts are observed and
  bound; this contract neither replaces their owners nor changes their policy.
- TLE entry/exit/generic `apply_event`, `apply_entry_fill`, `apply_exit_fill`,
  reconciliation/recovery, native feedback require/complete/uncertain, adapter
  replacement and financial auxiliary mutations join the same frame BEFORE any
  observable change; nested calls pass the SAME issuer-private frame. Revision
  L and dirty state extend through durable acknowledgement/readback. Existing
  `_persist_*_best_effort` catches must report failure to this authority before
  retaining their existing behavior. A swallowed generic event/snapshot failure
  therefore makes local eligibility unavailable; it is never accepted merely
  because strict-native feedback happens to be complete.
- StorageEngine/SQLiteStore lifecycle event/snapshot/native-state/run-scope and
  relationship writers join revision S BEFORE relevant mutation and finish only
  after their real commit/readback. This includes generic/best-effort writer
  paths, not only `persist_native_lifecycle_feedback`. Store close/reopen/adapter
  replacement invalidates. The enrolled connection AND its owned Cursor wrap
  external execute/executemany/executescript at OPERATION ENTRY before execution,
  including already-prepared cached statements; conservatively any external SQL
  operation advances S/invalidates old evidence, even a read. Only the exact
  issuer-owned read/mutation frame admits internal operations. Attribute/config
  setter entry participates likewise. Authorizer prepare callbacks alone never
  certify that outside-lease cached SQL/PRAGMA/config changes advanced S. A raw
  OTHER-connection writer has no invented owner revision: its committed contents
  are in the fresh read and SQLite exclusion prevents its intervening write.
  Unknown/unclassifiable raw rows fail closed.
  Relevant in-memory mutations must still use the participating owner frame;
  exposing a mutable authoritative record to an unparticipating writer is an
  unsupported configuration, not permission to trust a content hash.

`settle_local_intake(ticket, committed_binding)` is issued only by the existing
actual Core accounting/owned-request collector AFTER cache classification,
canonical accounting, progress persistence and required truth/reconciliation
settle that exact intake generation. It verifies actual owner records; it is not
an input boolean. Identical duplicates can settle through those real owners and
permit a NEW read, retaining original fill time. Contradictory corrections,
unknown writes and listener failures retain the existing unresolved latches.
A source intake whose relevant identity cannot be classified cannot settle as a
foreign event. Current AND prior-run unresolved durable request/frame records
are inspected; a restart/empty runtime map never clears them or quarantine.

### Deterministic synchronization and SQLite fence

There are two synchronization domains, with this fixed order and no inversion:

1. I is a NativeClient-owned short lock around ingress revision/in-flight/dirty
   bookkeeping ONLY. While holding I, never acquire the engine guard, native
   cache lock, lifecycle lock, SQLite connection/transaction or SDK transport
   lock, and never invoke a listener or arbitrary callback. It is released before
   callback parsing/publication. Finish also uses I only. A guard acquisition
   uses nonblocking I acquisition; busy means unavailable, with no retry loop.
2. G is the ExecutionEngine-owned nonreentrant authorization/mutation gate.
   Read/authorization acquisition is nonblocking. Normal owned mutations enter
   G before touching relevant owner state and release in finally. Legitimate
   nested owner work receives the same private mutation frame rather than
   reacquiring G; a thread ID or RLock reentrancy grants no authority. Unrelated
   reentrant mutation is rejected and invalidates the evidence. Callback ingress
   NEVER waits for G: actual raw facts remain in the existing NativeClient cache,
   I remains dirty, and the existing next collector cycle processes them. No
   callback fact is discarded or marked accounted to make entry validation pass.
3. Under G, copy required native cache facts with a nonblocking cache-lock
   acquisition and release that cache lock immediately. Bookend the copy with I
   observations; any intervening ingress/in-flight/dirty intake refuses the read.
   Only then acquire the SQLite fence below; never hold the cache lock with SQL.
   Read participating in-memory state only under G, using detached immutable
   values. Caller-owned/cached mutable references cannot be token authority.
4. The SQLite fence uses the SAME already-open original SQLiteStore connection;
   no second connection, reopen, database creation or path-based same-file
   attestation. Stdlib sqlite3 cannot attest an original backing file handle.
   Explicit default-off TEST/PAPER opt-in creates an OPAQUE connection facade
   from the existing SQLiteStore's first normal connection creation. The raw
   original sqlite3.Connection stays issuer-private and is NEVER publicly exposed.
   The facade is NOT a sqlite3.Connection subtype: plain external
   `source.backup(store.connection)` therefore refuses TypeError before target
   dispatch. This closes the proven PREEXISTING-backup bypass: a raw target can
   accept BEGIN IMMEDIATE inside a backup progress callback, then the old backup
   can continue writing past query_only/authorizer. A new-backup-into-an-already-
   fenced-target refusal alone does not establish safety.
   Default-off paths retain the normal raw connection and behavior. Preexisting
   raw connections/escaped aliases are unsupported, never converted or reopened.
   Keep check_same_threadTrue, actual creator identity, source owner and
   generation. No lease constructs a store, inserts schema/run state, changes
   journal mode, checkpoints or VACUUMs. SQLite sidecars are not another ledger.
5. The facade has a strict supported API allowlist, no raw __getattr__ forwarding
   or returned bound raw methods. execute/executemany/executescript/cursor return
   ONLY issuer-owned cursor facades. cursor.connection and __enter__ return the
   same connection facade; cursor operations/context/iteration return only
   facade/detached values. Reject custom cursor factories BEFORE raw creation.
   All raw cursors/handles stay private. Custom row factories are refused from
   initial opt-in: SQLite passes the RAW Cursor to such callbacks, so recording
   a flag after invocation is too late. Only builtin sqlite3.Row/default row
   conversion is supported. No caller can acquire a positive 'now clean' witness
   after prior raw exposure; unknown provenance stays unsupported.
   Track outstanding public cursor/VM operations. Lease acquisition refuses a
   pending/not-exhausted operation, including INSERT RETURNING or an unfinished
   SELECT; no false in_transaction certificate stands in for completed stepping.
   Actual owner materialization uses fresh trusted private cursors and fully
   consumes/closes them under the issuer frame. No external cursor is reused.
   The owner retains a permanent tracked internal authorizer router. Public
   authorizer replacement/removal, custom functions/aggregates/window functions/
   collations/progress/trace hooks, extension loading and custom factories refuse
   before exposing/invoking an underlying raw API. Their attempt invalidates;
   ordinary supported default behavior stays unchanged. blobopen, deserialize
   and backup are forbidden, sticky-unsupported attempts in every phase; no raw
   Blob/backup handle is ever issued. The facade's target type refusal also
   covers a backup invoked on an arbitrary OTHER/plain source connection.
   Track supported transaction/autocommit/isolation/setconfig/setlimit and
   row/text configuration at operation entry; during a lease refuse BEFORE
   invoking any underlying setter/API. Setters can mutate even when their
   implicit COMMIT is denied; autocommitFalse/setconfig/setlimit may bypass the
   authorizer. A failed setter invalidates rather than certifying unchanged
   state. Close/replacement/interrupt invalidate; an interrupt can cancel a read
   but never grant permission. serialize/getconfig/getlimit are read-only and
   cannot confer authority; unsupported callbacks/actions still refuse.
   This is a scoped owner facade, not a global SQLite interceptor or protection
   from hostile private-attribute extraction outside supported source ownership.
6. Under G, require creator-thread/exact connection ownership, no active caller
   transaction, no pending cursor/VM/writer/mutation and no unsupported callback/
   configuration or attempted forbidden API.
   Read and retain the actual `busy_timeout`, `query_only` and authorizer/router
   generation. Set busy_timeout0 BEFORE `BEGIN IMMEDIATE`, then enable query_only
   and the restrictive authorizer phase before any final materialization. The
   already-required pre-send native uncertain record must have COMMITTED before
   acquisition; never move it into this transaction. The original connection's
   `BEGIN IMMEDIATE` excludes writers on other connections to that database.
7. During the fence, query_only prohibits writes even for already-prepared cached
   statements. Re-register the owner router at the phase change to invalidate
   cached preparation authorization as well. The active authorizer allows only
   the required SELECT/READ/builtin FUNCTION/RECURSIVE read actions; it denies
   write/DDL/transaction/savepoint/ATTACH/DETACH/PRAGMA mutations and all unneeded
   opcodes. COMMIT, ROLLBACK and executescript's implicit transaction change are
   refused except the exact private finally-release operation. No arbitrary
   user SQL function, row factory or callback is invoked during materialization.
   Source-owned facade API guards additionally refuse authorizer removal,
   deserialize, close and transaction/config replacement during the lease.
   Cursor/direct/generic/best-effort SQL cannot write past these same-connection
   guards; best-effort exceptions still mark the owner dirty. Existing generic
   writes outside the lease remain in the fresh read and source revisions.
8. Reuse the existing coherent SELECT/materialization owner on this exact owned
   transaction, without nested BEGIN/commit/rollback. Read current/prior-run
   lifecycle events/snapshots, provenance and native/relationship progress fresh.
   Validate detached local predicate, planned diff and E/L/S. Bookend with I
   checks. An ambiguity/change/read error/interruption issues no lease. A failed
   query never returns a fabricated empty success. A raw other-connection write
   is either already visible in this fresh transaction or excluded until release.

All guard/SQLite lock acquisition is fail-fast; normal connection timeout5s must
not remain active for BEGIN. There is no lock backoff/retry or invented disk-I/O
bound. In finally, the exact issuer enables only its own ROLLBACK, rolls back
ONLY its transaction, restores query_only, busy_timeout and authorizer/router
state exactly and verifies no active transaction and unchanged ownership. Then
release G. Never commit or rollback caller work. Partial acquisition and cleanup
failure invalidate; inability to verify restoration keeps the authority dirty
and unavailable. No transaction is held for history queries, reconnect, ACK,
arbitrary hooks or SDK send. No global SQL interceptor, new database/ledger,
file-handle/VFS mechanism or SDK lock replacement is introduced.

### Proposal, risk and exact own-request transition

At proposal, process actual factual callbacks/accounting/reconciliation/protection
first. `read_local_cooldown(scope, context, assessed_at)` acquires G and the above
coherent fence, checks I/E/L/S and returns detached evidence only. It does not
assert risk green. Its token has one private call-chain nonce and these phases:
ISSUED -> RISK_BOUND -> PREPARED -> LEASED -> CONSUMED, or ABORTED. No phase or
nonce is serialized, reusable, copyable or reconstructed after restart.

At actual shared risk evaluation, `bind_local_cooldown_risk(token, decision)`
performs another fresh coherent read at the real assessment time and binds the
exact canonical decision/occurrence/context and immutable order specification.
Any unrelated revision/content/source change aborts; this API cannot refresh a
stale token to whichever state now happens to pass. A new proposal must start
with ordinary factual processing. Other risk/truth/admission gates remain
independent and can reject a locally elapsed/no-entry observation.

Preparation intentionally changes state. `prepare_local_entry_transition`
issues a private planned-mutation capability for THIS absent new client request
only. It is valid in this single live call chain and records exact before/after
records, issuer owner instances, generations and receipts for these edges:

- No own reservation -> the actual capital/allocation owners' known-unsubmitted
  reservation receipts, bound to exact decision/request/quantity and scope.
- No retained native request -> the real newly retained DISPATCH_UNCERTAIN row,
  original immutable request and progress, durably COMMITTED/acknowledged through
  `_retain_native_request` / existing native-state owner BEFORE any final lease.
- No native broker ID/cache facts -> the actual client's newly reserved unused
  ID and its first empty event/execution cache. Before resetting a slot, prove
  no prior cache/request/order identity exists. ID collision or existing facts
  abort; never erase callbacks to fit the planned transition.

Each owner transition advances its real revision and is admitted only while
carrying this exact capability; the authority records that exact delta in the
nonce. No arbitrary revision subtraction, pending-list exception or later hash
refresh is allowed. Any callback ingress, unrelated owner mutation, different
receipt/request/quantity/decision, extra row or unknown outcome aborts. The final
coherent read must equal the original validated state PLUS those exact planned
changes. The one own DISPATCH_UNCERTAIN row is permissible only via the live
never-consumed capability, not because its durable text says uncertain. All other
pending/uncertain/uncommitted requests remain blockers. None of these preparation
steps is an ENTRY_FILL or changes the original120-second clock.

Failure before dispatch preserves existing known-unsubmitted release semantics
only where the real owners prove them. A nonce never authorizes clearing a
failsafe/quarantine/uncertain record, replay, retry, rearm or broker ownership.

### Final native-entry linearization and one-shot consumption

After actual client resolution, propagate the private bound guard through the
existing provider/broker/submitter to NativeClient's ordinary entry
`before_submit(order_id, contract, order)` seam. Resolution may not implicitly
connect or replace a client for this proof. Reconnection/replacement aborts.
The hook calls `acquire_local_entry_lease` AFTER the required uncertain native
record has committed and AFTER the real ID/cache preparation. It acquires G and
the same-original-connection SQLite fence, reads/validates fresh state, exact
order and scope, and records LEASED. Failure issues no lease. The existing hook alone is insufficient:
returning ready and later calling an unguarded SDK method has a race. The lexical
`submit_order` try/finally owns abandonment from hook invocation through guarded
native entry: if the hook acquired LEASED but an exception, validation, wrapper
or READ_ONLY refusal prevents `placeOrder` entry, it changes the nonce to ABORTED
and releases that exact lease. The hook itself releases on partial acquisition
failure before return. Entry cleanup and outer abandonment are issuer-bound and
idempotent, so no branch leaks G/SQL or rearms a consumed/aborted nonce.

The proposed NativeClient `placeOrder` ENTRY adapter therefore consumes the
issuer-private lease, bound to that exact client/ID/call chain. Existing mutation
audit and READ_ONLY guards remain active; unsupported/unguarded P02 calls refuse.
The adapter uses invocation-private detached native Contract/Order descriptors
matching the risk-bound immutable specification (including native defaults),
never shared caller objects that another thread can mutate. With G/SQLite held,
it obtains I nonblocking and compares current object/epoch/account, I in-flight
and dirty state, I/E/L/S generations, exact prepared nonce and actual arguments.
On equality it atomically changes LEASED -> CONSUMED at THIS actual immutable
native mutation invocation entry; this is the authorization linearization point.
A callback admitted BEFORE this point invalidates/blocks the invocation. A
callback admitted AFTER it is a factual post-boundary operation: it invalidates
future permissions and receives ordinary accounting priority, but does not
retroactively authorize a cancellation/retry or claim the send did not happen.
This boundary does not claim network-arrival ordering or broker atomicity.

Immediately after consume, release I, then perform the exact owner ROLLBACK/
configuration-restoration operation and release G in finally, BEFORE delegating
to the existing audited EClient SDK body. Never close the original connection.
Cleanup failure aborts without delegation; the nonce is already spent and safety state stays uncertain. No user hook, listener, parser, query,
logging callback or SDK call occurs between compare-and-consume operations while
I is held. No issuer may reuse the lease following rejection/exception. Existing
SDK errors/unknown ACK/partial fills remain factual outcomes and never rearm it.

The lease lifetime is thus `before_submit` acquisition THROUGH actual guarded
`placeOrder` ENTRY and immediate fence cleanup, not through socket send/return
or broker ACK. This is a deliberate precise replacement of the earlier draft's
unsafe through-send wording. Pinned SDK Connection has a nonreentrant lock;
`disconnect` invokes connectionClosed while holding it, and `sendMsg` acquires it
without a bounded lock timeout. Holding G/I/cache/SQL through that SDK body risks
lock inversion or unbounded fence retention. Do not replace SDK locks, duplicate
transport or claim a timeout1s socket bounds that lock. Source participation must
ensure callbacks never wait for G while holding SDK/native locks. An actual P02
bridge must bind this exact entry adapter; a lease-only component/pure test is
NOT enforcement of proposal/risk/final-write integration. That bridge remains
separately vetoed until its other authority and wiring are adopted/proved.

### Grounded feasibility and acceptance limits

Existing reusable seams at accepted881e47ff:

- `SQLiteStore.fetch_committed_lifecycle_accounting` (~1557) owns a coherent
  all-run read; it currently has no combined local mutation/dispatch token.
- `NativeClient.cached_native_executions` (~516) copies callback facts and
  detects execution conflicts when read; diagnostic counters are not revisions.
  `orderStatus`/`execDetails` and `_emit_execution_callback` (~677) do not yet
  provide the required pre-publication, error-preserving ingress boundary.
- Native lifecycle feedback establishes PENDING and latches UNCERTAIN around
  strict writes; generic best-effort persistence is not an equivalent guarantee.
  `ExecutionEngine._native_callback_lock` (~3736) serializes collectors only.
- Active Core evaluates risk (~4917) then calls execute_trade (~4966).
  `_route_order` (~1588) rechecks before provider dispatch; request retention
  (~1703), client resolution and native cache initialization happen afterwards.
- `IbkrOrderSubmitter.submit_once` (~85,144) does not pass an ordinary entry
  guard to `NativeClient.submit_order` (~1056), whose existing optional hook
  (~1090) precedes `placeOrder`. That propagation and serialized consumption are
  concrete missing implementation prerequisites, not an existing guarantee.

Before proposing source acceptance, prove real-owner journal reads and every
invalidation boundary with deterministic offline controls: exact120 boundaries;
partial/duplicate/late entries; foreign/ambiguous scopes; prior-run pending state;
callback entry/ignored/conflicting/corrected/completion/error before journal
commit; interrupted/lost-ACK persistence; database/client/epoch replacement;
changes between proposal/risk/route/native hook; expected own-request transition
versus unrelated mutation; single consumption; no dispatch on stale/unavailable
evidence; and bounded cleanup without leaked workers or deadlocks. Preserve
existing default-off/unsupported-scope refusals and all prior safety assertions.

This draft changes no source or flags. Adoption would authorize development of
these bounded components, not claim they already exist. Actual P02 proposal/risk/
final-write integration remains separately blocked by its native bridge and
remaining admission/management requirements. No positive P02 Core trading,
broker-history completeness, restored cold ownership, continuous protection,
operational capital/recovery action, resumption or readiness is claimed.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


### 2026-11-14 — ADOPTED separate observable-local cooldown policy V1

Under user-delegated project authority, root adopts the complete independently
reviewed1aa6b65f8a03cd88fe865e91644ecb7e0eea76c4 contract (tree329c1594)
BEFORE source implementation, as NEW project policy. This is
P02_OBSERVABLE_LOCAL_COOLDOWN_V1, default-off and synthetic TEST/PAPER only.
It is AS-OF validated committed local facts with pending/uncertain/uncommitted
intake blocked; it is NOT broker-history completeness or a guarantee against
unseen late fills. PR1230's original complete-capture predicate remains UNKNOWN
and its original API remains eligibleFalse. Original execution-time120s anchors
and all original admission/truth/quarantine gates remain.

Final independent next_session_contract_review CLEAR supersedes the earlier
conditional private-connection design: original-handle identity is unavailable
through stdlib sqlite3. Adopt SAME-original-owned-connection fencing with tracked
default-off subtype/creator thread, nonblocking G/I/cache order, BEGIN IMMEDIATE
after pre-send commit, query_only/authorizer and source-owned public API controls.
Cached operations must participate in revisions; trusted fresh cursors only.
Blob usage is sticky unsupported; custom hooks/unknown ownership/configuration
remain unavailable. Exact own-request nonce transitions, actual immutable native
ENTRY consume and lexical abandonment cleanup are mandatory; guards release
before SDK body/ACK. No global SQLite/SDK monkeypatch or second accounting ledger.

Source development remains conditional on implementing every participating owner
and validating these guarantees. Unsupported participation/fence/cleanup cannot
grant local permission. Pure mechanism probes on new temporary/in-memory SQLite
databases confirmed the specified read/write/transaction/cached/cursor/backup
controls and exposed the Blob/configuration limits; these are NOT production
owner or pipeline proofs. Original repository databases were not opened.

This adoption does not adopt the native-entry draft, numerical ATR admission
bounds, management semantics or operational enrollment. Actual Core P02 entry
remains structurally vetoed; no positive Core proof is claimed. Observation
distribution3f48bf3f/sourcec65/calendar and all five ownership vetoes unchanged.
No observer, broker/provider, operational recovery or readiness upgrade.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


### 2026-11-14 — Adopt reviewed original-connection ownership amendment

Independent exact contract review CLEAR at5e57f03570ca74711882336a749e5f9170bd1577
(treecd45901d) supersedes earlier conditional private-connection/public-raw-subtype
mechanism designs. Root adopts this bounded amendment before source work, under
the same delegated authority. The original raw SQLite connection/cursors remain
issuer-private from FIRST explicit synthetic TEST/PAPER opt-in creation; public
connection/cursor facades have a strict allowlist, return facades only and reject
custom factories before invocation. No generic raw forwarding or late wrapping.
Default-off storage keeps its existing raw connection and behavior.

External SQL/cursor operations including cached execution invalidate source
revision; only exact issuer-private internal frames are exempt. Existing active
statements/VMs must be exhausted or closed before acquisition. Lease acquisition
requires source-owned nonescape and all participation; unsupported ownership
stays unavailable. This is not a parallel ledger, new database or global SQLite
interceptor. Actual original-connection BEGIN IMMEDIATE writer exclusion,
query_only/authorizer/API guards, exact timeout/config restoration and one-shot
native ENTRY/abandonment rules remain mandatory.

Failures/limits preserved: stdlib cannot attest the original open file handle
from path stat, so the second-connection scheme is unsupported. Writable blobs
opened before a query_only/authorizer fence can still write. A backup ALREADY in
progress can acquire a target fence from its progress callback and then mutate
the target; rejecting only newly-started backups is insufficient. A pending
WITH UPDATE RETURNING VM can likewise outlive preparation authorization. These
are failed mechanism assumptions reproduced in isolated scratch databases, NOT
passing source guarantees. Opaque initial ownership, forbidden blob/backup APIs
and no-active-VM preconditions address those findings. Setter/config/cursor
controls are required before delegation, not after an authorizer refusal.

The completed contract is adopted for bounded implementation; source correctness
and actual proposal/risk/final native ENTRY enforcement remain unproved until
independent exact-head review and required CI. Old PR1230 coverageUNKNOWN/
eligibleFalse remains unchanged; new default-off local basis never certifies
broker history, unseen late fills, SDK send success or cold ownership. ATR
numerical bounds, native entry and management vetoes remain. No observer or
broker/provider/operational action; observation release3f48bf3f/sourcec65/calendar
and all five ownership safeguards unchanged. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
