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


### 2026-11-14 — PR1231 Windows aggregate budget failure and scoped correction

Original reviewed candidate d7c171aac3a7b0fda87a83f55cad5cb9b3725efb/tree3e60bf62
remains historical evidence. Independent exact-head review5906997378 cleared ATR
source and29focused controls; local182passes overlap and are not additive.
Automatic CI43638331204 attempt1 was CANCELLED, not accepted: Linux132580038763
passed7970/3skipped/4warnings in1202.99s. Windows132580038753 completed full
7971passed/2skipped/6156warnings in3375.69s, then serial46passed in32.88s, but hit
the unchanged60-minute JOB limit during cache diagnostics. Both actual checkout
logs identify353dcead26f9df5e0c081a8c71a339f7e0bc7c6f, ordered parents881e47ff
then d7c171aa, candidate tree3e60bf62. Full-suite passes do not substitute for
complete CI. PR1231 remains draft/unmerged pending corrected required CI.

Causal diagnosis: full Windows suite ran20:38:02–21:34:19UTC. Cache checks began
21:34:54; cancellation21:36:11 left77seconds. Existing verify_cache_probe.py has
THREE intentional blocked-child cases with startup30s/cleanup5s; their startup
budgets alone require about90s. Later actualPS5 exit/harness/parser checks never
ran. Focused95/news37/float9 had passed before the full suite. No failing test or
production defect was demonstrated; quiet progress logs cannot identify a causal
slow individual test. Full Windows was17–25percent slower than PR1230's cited
2708.68/2878.89s runs. Preserve the cancellation and unrun gates as limits.
The729-byte partial artifact14132683319 (service-reported SHA256
309d7f1330639943f766ebc345217a4c75569175f5fd4415339d5ff459936a89) contains
only earlier focused evidence, not missing downstream proof; archive bytes were
not independently downloaded/hashed.

The minimal correction separates the existing Windows full-suite and controlled
process gates into bounded jobs, preserving60minutes per Windows job, Linux30,
every test/child timeout, dependency/environment branch, inherited-order-state
guard and evidence upload. The existing required windows-offline name becomes
an explicit always-run aggregate that requires both upstream successes; suite
skip is allowed ONLY under authoritative harness_only=true. A skipped/cancelled/
failed mandatory upstream cannot become aggregate success. Focused suite logs
retain a separate unique artifact; the controlled harness artifact name stays.
No optional bypass, threshold change, suite exclusion, retry or widening.

ATR feature/test bytes stay unchanged; their passing focused evidence and review
are reused. Independent exact-head workflow delta review and required automatic
CI for the CHANGED head remain mandatory; no already-successful unchanged-head
suite was manually rerun. This is scoped completion of demonstrated CI budget
exhaustion, not another observer/source policy or documentation-only cycle.
Default-off cooldown work continues independently; old UNKNOWN observations,
ATR numerical-bounds/native-entry/management vetoes and all five ownership
protections remain. Observation distribution3f48bf3f/sourcec65/calendar unchanged.
No observer/provider/broker or operational recovery/readiness activity.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

Workflow correctionc3422219f92e01aa3a43682bfe1b5ffdd2eb8461 focused validation:
4checks passed, including actual embedded aggregate execution across128 causal
scope/suite/controlled status combinations plus missing/malformed/ambiguous
inputs. Parsed YAML confirms all15original Windows steps retained exactly across
the split, and original scope/Linux blocks semantically unchanged. Required
windows-offline aggregate rejects failed/cancelled/skipped mandatory jobs; only
authoritative harness-only permits the full-suite job skip. No production ATR/
context/test fixture bytes were changed or focused source suites rerun. These
workflow checks do not replace required automatic corrected-head CI.


### 2026-11-14 — PR1231 accepted measurement-only ATR; complete CI receipt

[PR1231](https://github.com/NelzonMamani/ibkr-trading-system/pull/1231) integrated
from base881e47ff791e6c2bafc8fdb1a6249a12a95b1388, reviewed final head
29e9c4ac9a5ab0f15320062f2a29ea182ea929d6, candidate tree
c2e77a3be5f8cc339012ae46eb9fb900b203cd9c. Independent original ATR review
5906997378 and exact correction review5907288495 are preserved; corrected source/
test ATR bytes equal the original reviewed d7c171aa. Tested PR checkout
dfba9283418e6da883432c36ff228e64706ef31c has ordered parents881e47ff then29e9c4ac.
Authorized expected-head mergeabfc822d804ab966e9abd8638ed052e842393d75 has those
SAME ordered parents and treec2e77a3b; reviewed/candidate/tested/accepted trees
match. Main was verified after integration; no source candidate was changed to
append acceptance receipts.

[Corrected PR CI43644351093](https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/43644351093)
attempt1 SUCCESS: scope132598669821; Linux job132598752257:7974passed/3skipped/
4warnings/804.71s; Windows suite job132598752304:7975passed/2skipped/6156warnings/
3205.34s; controlled132598752229 and required aggregate132613943724 SUCCESS.
All original focused95/news37/float9/serial46/cache6/actualPS5exit13/stub-only
harness48/quote-parser/evidence-upload gates passed. Both actual test checkouts
and controlled checkout identify dfba9283; original required windows-offline
strictly required both Windows results. Only authoritative conditional
harness-only/dependency-only alternatives skipped, no mandatory gate skipped.
Linux30/Windows60 budgets and all child timeouts are unchanged.

[Automatic main CI43649428902](https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/43649428902):
attempt1 SUCCESS at acceptedabfc822d: scope132614364986; Linux132614409609
7974passed/3skipped/4warnings/805.10s; Windows suite132614409564
7975passed/2skipped/6156warnings/2750.41s; controlled132614409595 and required
aggregate132627068361 SUCCESS. Every original mandatory downstream gate passed.
Actual Linux/Windows/controlled git-log checkouts identifyabfc822d; treec2e77a3b
and ordered parents881e47ff then29e9c4ac equal reviewed/PR-tested integration.
Remote main remainedabfc822d after COMPLETE main CI verification.

Archive figures below are GitHub service metadata, NOT independent downloaded-
byte hash claims. PR focused14135216586,727bytes,SHA256
53b2f41fb92b628eb731fe89b398005f41ec98d54ec21c7ceec1dd27fc8c1d82; PR controlled
14133765339,745245bytes,SHA256
3d9a4a01431bb42e7856aadf16ddb0344f306d9cc74a1e8098ee5f2d2fe18836.
Main focused14137225972,727bytes,SHA256
9504732041bee208f40651afd4e29df0d2b346734199b1dbec80a72d3d92a6bb; main controlled
14135022614,744934bytes,SHA256
ebae55e323d0546fee5ff0670070ac08dbab6c90e432e38e78fde69d8a128881.

Preserved failure: original CI43638331204 at d7c171aa/tree3e60bf62 was CANCELLED
at the60-minute Windows job limit AFTER7971passed/2skipped/6156warnings/3375.69s
and serial46; cache had77seconds for three intentional30-second children, later
gates unrun. Its Linux7970passed/3skipped/4warnings/1202.99s and full Windows
passes are historical partial evidence, NOT complete CI acceptance. The old
729-byte artifact is only earlier focused evidence. Diagnosis/failed budget and
all earlier causal fixture failures remain in preceding entries. No production
defect or causal individual slow test was demonstrated. No blind unchanged-head
retry occurred: the reviewed workflow correction changed the head and required
automatic full CI. Main automatic CI is likewise not a manual successful-suite
rerun. Counts overlap focused review and prior runs, not additive inventory.

Accepted behavior: Wilder14 on original validated completed current-session
stream, seed bars2..15/update16+, no overnight predecessor, USD/share and each
step's completed-close percent; raw input/hash/source/request/calendar/member/
completion provenance retained. Immutable bounded offline input/report tooling
rejects invalid/missing/conflicting facts; retrospective replay is explicit and
grants no live permission. No approved representative P02 market dataset was
identified; original DBs were not opened/initialized. Quote availability is
explicit, costs remain UNAVAILABLE, no zero-cost fallback/calibration/profit labels.
Measurement-only adoption supplies NO numerical ATR bounds: admissionUNKNOWN/
eligibleFalse and native-entry/management vetoes remain.

ONE next bounded task is the separately reviewed local-observation/fencing
foundation [PR1232](https://github.com/NelzonMamani/ibkr-trading-system/pull/1232),
through its own complete required CI/expected-head integration. It must retain
its precise unsupported stages and old UNKNOWN observations; this receipt does
not count unmerged B source as accepted ATR scope. Observation distribution
3f48bf3f/sourcec65/reviewed calendar untouched; no observer/provider/broker,
operational capital/recovery, native ownership or readiness upgrade. All five
ownership vetoes and parked work remain. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
