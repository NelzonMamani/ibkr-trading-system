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


### 2026-11-14 — Default-off P02 observable-local foundation implemented (bounded)

Sourceb5f4f0f589810ca5796b3053f9a80c04024dfa66 follows reviewed adoptiond427f27b.
Final contract5e57f035/treecd45901d was independently cleared before source work.
Integration3a3cedd5a5f50703896647b346346bce90f67442/tree434a2774 has ordered
parentsb5f4f0f5 then corrected ATR prerequisite29e9c4ac; all9 source/test blobs
were preserved byte-for-byte. Only EOF record conflicts were resolved, retaining
both exact histories once. No source duplication, new database/ledger or manager.

NEW P02_OBSERVABLE_LOCAL_COOLDOWN_V1 is explicit TEST/PAPER keyword opt-in only;
default raw storage/native behavior remains. Actual canonical TLE writes and
current/prior committed journal, actual native bootstrap facts and existing
collect_relationship_updates feed a same-original-connection fenced source read
and immutable context/version-bound AS-OF LOCAL observation. Original authoritative
entry times including partials anchor the existing120s; duplicates and late older
facts never renew by receipt. Empty observed local state or exact120 elapsed can
satisfy ONLY local_condition_satisfied. Every evidence retains coverageUNKNOWN,
broker_history_completeFalse and admission_authorizedFalse. Old PR1230 public
reader still always returns coverageUNKNOWN/eligibleFalse. This is not capture
completeness, broker-history proof or a guarantee against unseen late executions.

Opt-in SQLite ownership uses opaque connection/cursor facades from FIRST creation
with no raw-handle/custom-factory escapes. Operation-entry revisions cover cached
SQL; outstanding statements/RETURNING VMs refuse acquisition. Blob, backup,
deserialize and custom hooks/configuration are unsupported. SAME original
BEGIN IMMEDIATE after pre-send commit, timeout0, query_only/authorizer and actual
finally restoration exclude interfering writers. Fixed issuer SQL has no bound
parameters that could invoke global adapter callbacks. Strict actual source/read
frames are capabilities; RLock/thread identity is not permission. Best-effort
persistence failures become local uncertainty. The existing financial/timestamp/
identity/chain validators are reused; P02 numeric2R and independent stop are not
rewritten. Missing snapshots/events/current known commits, foreign journal changes
and unknown current/prior native-state scope cannot silently become EMPTY_LOCAL.

Native I registration precedes existing account registration/parsing/cache
publication; completion never clears dirty intake. Listener failures preserve
raw facts; actual ticket/thread ownership and callback-registration revisions
are checked. Initial BASELINE settles only via an opaque receipt issued after
actual collector/cache+journal verification. The component G+SQL lease exercises
one-shot, argument/callback race and lexical-abandonment cleanup at immutable
native ENTRY; locks close BEFORE SDK body. No actual SDK send was performed.
The mutation audit counts direct/refused calls, immediate owner-to-base SDK
delegation once, and distinct reentrant/cross-client/before_submit commands
independently; every wrapper still runs read-only guards.

Initial client scope is DEDICATED_SYNTHETIC_ONLY, a REQUIREMENT, not a global
unshared-client/capture certificate. Initial retained native/plans/callback owners
refuse enrollment. Unknown/foreign/unleased BUY remains blocked on that enrolled
client; this is not positive mixed-strategy enrollment. Default/unbound BUY uses
existing SDK guards, and protective SELL without an entry lease preserves them.
Changing a bound BUY lease to SELL refuses rather than escaping comparison.

EXACT LIMIT: positive observations use synthetic ENTRY LifecycleEvents through
REAL canonical accounting and EMPTY native-cache/bootstrap settlement, NOT a
retained-native-fill/protection P02 pipeline. NONEMPTY execution/order/open-order
caches, retained request states and relationship state remain unsupported;
financial/error/ignored/inherited/unknown callback tickets stay dirty. No positive
financial-ticket settlement or new P02 bridge is proved. Actual proposal/risk/
canonical decision/planned reservation nonce/final Core dispatch integration is
CLOSED: stage revalidation except LOCAL_CHECK returnsFalse. This is a foundation,
NOT complete policy enforcement or full Core enrollment. Cold native ownership,
adoption, valuations, resumption and recovery clearing remain ungranted.

Latest implementation receipts: SQLite42passed/.86s; ASOF24passed/26warnings/1.13s;
Native WHOLE30passed/26warnings/1.25s plus ONLY2newscopecontrols passed with30
deselected/3warnings/.69s. Thus98 DISTINCT new controls across scoped batches,
not a claimed whole98 or whole32Native invocation. Earlier33/20/21/24 prefixes
overlap and are not additive. Existing affected checks ran ONCE after relevant
changes: lifecycle/SQLite/schema285passed/246warnings/12.31s; cached-client/
read-only/guard/submitter164passed/1warning/11.85s; exactly4actual-Core cold
accounting variants (gross/positive fee/known-zero fee/partial gross)4passed/
8warnings/21.40s. These453existing checks overlap future CI, not new inventory.
No old1600/full suite was manually repeated. Compile/whitespace checks passed.
Independent assembled exact-head source review and required final-head CI remain
mandatory; no pending or isolated prefix substitutes for them.

Failures remain failures, with overlapping after-passes identified:
1. SQLite first1passed/32SETUPERROR/3.52s: overbroad PRAGMA filter denied readonly
   table_info(table); exact introspection/private-config handling fixed it.
2. First composed run19failed/1passed/21warnings/6.33s: trusted feedback->open_trades
   reacquired nonreentrant G. Exact source/private READ frame fixed it. Separate
   single1failed/.79s hit the constructor PRAGMA issue BEFORE that frame; corrected
   single1passed/.62s overlaps final24, not another full-module result.
3. Missing-all-events control1failed/1warning/.78s: known runtime commit/snapshot
   could falsely become EMPTY_LOCAL. Full verified snapshot chains and exact
   current committed-event durable matches now required; after1pass/.67s overlaps24.
4. Runtime/journal controls3failed/21deselected/4warnings/.75s: PAPER->LIVE, TEST
   departure and coherent other-connection original-time changes revalidated old
   evidence. Fresh actual context/generation+journal fingerprint fixed them;
   after3passed/.72s overlaps24.
5. Native cache control1failed/12deselected/1warning/.70s: callback after ID reserve
   could be erased by cache reset. Enrolled CACHE_OCCUPIED refuses before hook and
   setdefault preserves raw facts; default-off old path unchanged.
6. Initial audit adaptation reentry1failed/20deselected/.61s undercounted2commands
   as1; class-qualified one-use delegation fixed it (after1pass/.76s overlaps30).
7. Callback audit1failed/29deselected/.72s suppressed a distinct before_submit
   command before an exception; immediate caller ORIGINAL CODE identity is now
   also required (after1pass/.80s overlaps30).
These source-development failures and the earlier disproven Blob/backup/activeVM/
second-file assumptions are not baseline passes or production certification.
Detailed offline logs remain in /workspace/p02-local-*-20261114.log; originals
and accepted failure history were not removed.

ONE next bounded prerequisite: establish actual per-occurrence financial callback
settlement through existing retained request/accounting/protection owners before
expanding local observation consumption. Preserve unsupported-stage vetoes until
the native bridge/decision bindings are adopted and implemented; do not invent
P02 admission to demonstrate them. ATR numeric bounds remain a separate unresolved
approved-data/calibration requirement; use the recorded plan, no acquisition or
profit labels while management outcomes/cost evidence remain unresolved. All five
ownership vetoes and native-entry/ATR/management gates stay closed. Observation
distribution3f48bf3f/sourcec65/calendar unchanged. No observer, broker/provider,
operational capital/recovery action or readiness upgrade.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


### 2026-11-14 — Scoped independent review findings repaired; final review pending

Accepted ATR prerequisite PR1231 mergedabfc822d804ab966e9abd8638ed052e842393d75,
treec2e77a3b, after corrected CI43644351093 attempt1 SUCCESS: Linux7974/3skipped/
4warnings/804.71s, Windows7975/2skipped/6156warnings/3205.34s, all original
controlled-process gates and required aggregate SUCCESS. Actual test checkouts
dfba9283 have ordered parents881e47ff then29e9c4ac and reviewed treec2e77a3b;
accepted merge has the same ordered parents/tree. Original cancelled43638331204
remains failure history. Automatic main43649428902 is RUNNING at this entry; do
not infer its result. Receipt publication follows complete CI, without changing
the frozen source merely to append receipts. Observation release3f48bf3f unchanged.

Independent source review at46f457f94541ccbf629f19423ac142f1a9ca0f04/tree3c228986
ran99focused controls (57warnings), which PASSED but MISSED3blocking findings;
that head was NOT CLEAR. Two bounded public-source probes released/joined their
workers: pre-bind Native.orderStatus could be in flight while baseline/read
reported local_conditionTrue; weak facade finalization could remove an active
RETURNING VM from weak tracking before raw finalization, admitting a fence.
The third source defect passed UNBOUND DailyRiskGovernor.trading_day_for to fee
validation, rejecting valid fee-bearing history. None is a passing certification.

Consolidated source correction435d8e55a291777ae9d555d9e7f69c50d1b42d0f
(tree4ca55f43, parent46f457f9) changes only8scoped source/test paths. Constructor-
FIRST bounded actual lifetime-operation/revision bookkeeping and the SAME I lock
now participate before binding. Atomic quiescent bind never resets the witness;
actual negative operation IDs remain visible before ordinary ticket registration
and after ticket finish. Unknown/failure/rebind is sticky unsupported. No callback
history/raw-fingerprint accumulation or inferred capture certificate. Missing
constructor provenance and reinitialization refuse; stable actual stdlib thread
primitives preserve existing history Event fixtures. Default transport/cache
semantics and all operational permissions remain; this bookkeeping supplies no
broker history or global unshared-client guarantee.

SQLite keeps strong RAW active-operation records independently of weak facade
lifetime until verified exhaustion/explicit close. Abandoned active VM refuses
fencing until creator-store shutdown closes the actual operation. Dead weakrefs
never mean settled; no strong facade retention. This exposed actual owned-read
leaks, repaired by finally-closing4schema probes,5strict canonical-pair checks
and the StorageEngine native-state reader. No caller VM auto-clear, rollback of
caller work, capital redesign or relaxed active-VM rule was introduced.

ONLY the new local helper now uses the ACTUAL bound governor day owner, verifying
exact governor/Storage/TLE/provider and bound-method provenance; governor identity
is in the immutable source version. Synthetic positive-fee and known-wire-zero
CHARGE evidence is validated through real canonical auxiliary owners and offline
SDK-summary fixtures. A known-zero wire leg does NOT mean all round-trip fees
are zero. No fallback timezone/fee, empirical-cost or net-performance claim.
Wrong/missing governor ownership refuses. All actual P02 stage/bridge restrictions
from the preceding foundation entry remain unchanged.

Failure chronology (prefixes overlap final checks; not additive inventory):
- Maintained pre-bind regression1failed/32deselected/1warning/.73s ->1passed/.65s.
  A failure before ticket registration was separately1failed/38deselected/
  1warning/.79s; source-minted failed-intake fallback repaired it, targeted2passed
  /.70s including real-threading-alias control. Bound-reinit expectation1failed/
  .96s was a TEST expectation error: existing API correctly raised unavailable,
  rather than returningFalse. Test-only correction1passed/.68s; source unchanged.
- Weak cursor finalizer1failed/.43s ->1passed/.45s. Strong tracking then exposed
  reopened-schema1failed/.48s and strict canonical ENTRY/STOP1failed/1warning/
  .76s; actual owned reads were closed, not silently declared inactive.
- Fee probe first2failed/4warnings/1.37s stopped at the schema VM refusal BEFORE
  the day branch; this is NOT TypeError proof. After reader repair,2failed/
  4warnings/.97s causally REACHED the unbound-day missing-timestamp defect with
  valid synthetic auxiliary facts. Bound-owner repair2passed/.89s, then expanded
  wrong/missing-owner controls2passed/1.12s overlap final26.

Latest defined NEW controls117=SQLite50+ASOF26+Native41; NOT a claimed whole117
invocation. SQLite whole50passed/1warning/1.15s; ASOF whole26passed/30warnings/
1.42s; Native whole38passed/36warnings/1.49s plus ONLY2newfocusedpassed/1warning/
.70s and1newfocusedpassed/1warning/.68s. Earlier42/48/49/24/30/32/38 prefixes
overlap and remain attributed to their actual source.

Affected existing checks ran ONCE after these constructor/default-callback and
owned-reader corrections:285lifecycle/SQLite/schema passed/246warnings/11.36s;
253native/read-only/submitter/history passed/1warning/12.91s (includes89existing
history-completion cases); exactly4actual-Core cold accounting variants passed/
8warnings/16.44s. These542existing nodes overlap earlier453 and future CI; they
are not new inventory. Logs: /workspace/p02-local-review-fixed-*-20261114.log.
No old fullCore/full-suite blind rerun, manual CI retry or observer.

Final assembled exact-head correction review and complete automatic CI remain
mandatory before expected-head integration. Local condition observations and
component lease cleanup are NOT complete policy enforcement: nonempty native
caches/request/relationship states and financial tickets remain unsupported,
actual proposal/risk/planned nonce/final Core stages stay closed. Original
UNKNOWN API, numerical ATR/entry/management vetoes, all five ownership safeguards
and dedicated synthetic-only scope remain. No native ownership restoration,
broker/provider activity, capital/recovery action or readiness upgrade.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


### 2026-11-14 — PR1232 Linux CI audit regression and scoped SDK correction

Initial reviewed376a3d6c/tree88a5e3c5 and review5907620925 remain historical
evidence, not CI acceptance. Required CI43650288835 Linux132617056606 FAILED:
2failed/8089passed/3skipped/4warnings/1060.40s. The failures are EXISTING
test_standalone_pmh_late_fill_protection cases
test_first_confirmed_project_partial_retains_original_stop_then_own_failure_to_flat
and test_first_pending_partial_and_competing_stop_preserve_remainder_without_replay.
Both completed their genuine33-pattern Core/PAPER/accounting/protection/failure/
replay assertions, then rejected extra audit counts: expected place4/modify0 and
place2/modify0, respectively; same commands were additionally counted as modify4/2.
Actual wire counts stayed4/2, not duplicate sends. Keep all original assertions.
The old Windows job was still running at this entry; its result is not inferred.
Controlled-process success does not make this failed required CI acceptable.

Independent diagnosis: FIRST's existing SDK interposition calls a saved audited
SDK function. Its immediate caller is the shim, rather than Native.placeOrder's
original code, so the previous immediate-caller-only predicate counted the same
command twice. Local reproduction exactly2failed/6warnings/2.64s is preserved in
/workspace/p02-ci-first-partial-audit-before-20261114.log. This is a regression
in the new audit adaptation, not a family/stop/quantity/target-policy defect or
a passing baseline.

Scoped source correction4616e111bf729a82802a92a6a00e1bbe90003b00/tree6812b757,
parent376a3d6c, changes ONLY mutation_audit.py,3Native-to-SDK call sites and
10counter controls in the existing Native test module. It creates a one-shot
audit-delegation receipt at the ACTUAL Native SDK body call site, bound to exact
client/order ID/contract object/order object, top Native audit frame, original
saved audited SDK identity and direct helper or exactly selected shim frame.
No arbitrary ancestry/callback borrowing, global registry or SDK monkeypatch.
The receipt is consumed once and revoked in finally; it is NOT order permission.
Submit-to-Native immediate-source checks remain. Every SDK/read-only guard still
runs, even when redundant audit counting is suppressed. No family source, test
assertion, policy, quantity, stop, TP, financial projection or owned-cursor rule
was changed.

After correction: exact2existing failures2passed/6warnings/2.43s, overlapping
selected88real coordination/SDK-interposition/First cases passed/851deselected/
327warnings/36.84s. New Native/audit module WHOLE51passed/38warnings/1.58s
includes10new adversarial receipt variants: selected/direct shim, repeated same
SDK calls, same/different callback commands+abort, reentry, cross-client, changed
descriptor and guard changes. Existing SDK/default/read-only/submitter164passed/
1warning/11.92s. Logs /workspace/p02-ci-*-20261114.log. No First assertions or
price/protection controls were weakened; no unchanged full suite was manually
rerun. Local delta review cleared source; independent assembled exact-head delta
review and complete automatic CHANGED-head CI remain required before merge.

Defined new controls now127=SQLite50+ASOF26+Native51; scoped and independent
counts overlap earlier117/118 and future CI, not additive proof inventory. All
prior review failures remain preserved. Local observations still have
admission_authorizedFalse/coverageUNKNOWN; nonempty native financial intake and
actual P02 admission stages stay unsupported/closed. Observation distribution
3f48bf3f/sourcec65/calendar, all five ownership vetoes, ATR bounds/native-entry/
management restrictions and parked work remain. No observer, broker/provider,
operational capital/recovery action or readiness upgrade.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


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


### 2026-11-15 — PR1232 verified integration and complete automatic main CI

PR1232 https://github.com/NelzonMamani/ibkr-trading-system/pull/1232 is merged
under standing expected-head authorization. Accepted base
abfc822d804ab966e9abd8638ed052e842393d75; final reviewed head
b686d10565d679a0487835d06d2c566a0b155326; candidate/reviewed/tested/merged tree
09f695bfcfcff9f9e6beb63100c5ee3f39defbb5. Independent exact-head SDK delta CLEAR
review5907891308 (https://github.com/NelzonMamani/ibkr-trading-system/pull/1232#pullrequestreview-5907891308)
complements prior review5907620925 for unchanged source. The independent53
Native/First controls passed/44warnings/3.07s; these overlap the local and CI
checks, rather than adding distinct proof inventory.

Required PR CI43653680298 attempt1 is SUCCESS:
https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/43653680298
- scope132627443803 SUCCESS;
- Linux132627513904:8101passed/3skipped/4warnings/1157.84s;
- Windows full132627513926:8102passed/2skipped/6225warnings/2694.73s;
- controlled132627513890 SUCCESS:46serialized quote checks,6cache subprocess
  fixtures,13PowerShell exit checks,48stub harness observations, parser PASS
  and artifact upload;
- required Windows aggregate132639318920 SUCCESS, actual harness_only=false,
  both mandatory Windows owners successful. No omitted downstream gate.
Actual platform/controlled checkout1a4404052f0ebd016e3dbd9cf45bed5fd502b38f has
ordered parents abfc822d804ab966e9abd8638ed052e842393d75 then
b686d10565d679a0487835d06d2c566a0b155326 and tree09f695bf above.

After rechecking unchanged remote base/head, the expected-head merge produced
b479ba17368634a1918278d1cffda2b95554ae02. Its actual ordered parents are the
same abfc822d base then b686d105 head; its tree is exactly09f695bf above.
Automatic push/main CI43657815920 attempt1 is also fully SUCCESS:
https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/43657815920
- scope132640192759 SUCCESS;
- Linux132640241653:8101passed/3skipped/4warnings/1078.80s;
- Windows full132640241627:8102passed/2skipped/6225warnings/3025.30s;
- controlled132640241630 SUCCESS:46serialized checks,6cache subprocess fixtures,
  13PowerShell exit checks,48stub observations, parser PASS and upload;
- required Windows aggregate132653734239 SUCCESS, actual harness_only=false,
  both Windows owners successful. Windows focused95, news37 and float-cache9
  checks also completed successfully before the full suite; counts overlap.
Actual main Linux/Windows/controlled checkouts identify b479ba17368634a1918278d1cffda2b95554ae02.
Run conclusion SUCCESS and remote main b479ba17 were independently re-read after
all jobs completed. No manual unchanged-head rerun or B-run cancellation.

Artifact identities below are GitHub service archive metadata, NOT independent
downloaded-archive hashes. PR final-order14138622738:729bytes,
SHA256 d3397c596bba090390a48dfde43f104d91748dbaaf4de0b8da1f9ce34bf9592a;
PR controlled14137052345:745356bytes,
SHA256 9968308f4181e9d6057d0ed631c42f90bfd8c8bc2798bdc20b6a7e65d6142e13.
Main final-order14140257784:727bytes,
SHA256 84cba70472084324e620ff37c3d3abc130c25711199813017076111f158fade1;
main controlled14138274866:745233bytes,
SHA256 5a71219843fb6d5ef19a2e4533d94e4c5846e3ddc1c42aca07aca6ce4c330c49.

Historical failures remain failures. Initial B CI43650288835 tested
376a3d6c285344772377d300c1650c259a41444e via checkout
ec2fc031bf5d7987db09dabbe6c027df278098ca. Linux132617056606 FAILED with
2failed/8089passed/3skipped/4warnings/1060.40s. Windows132617056578 completed
naturally FAILED with3failed/8089passed/2skipped/6225warnings/2853.21s;
aggregate132630015137 FAILED. Two failures on each platform are the preserved
First SDK audit-double-count regression described above, repaired by4616e111;
wire sends and all prior real33-family financial/protection assertions had
passed. The additional Windows failure is
 tests/test_atomic_capital_owner.py::test_cross_account_and_concurrent_cap:
authorized attempted.wait(10) timed out. Its cause remains UNLOCALIZED; hidden
second-worker construction/ready/close outcomes were not available from that
log. The bounded scratch both-futures diagnostic1passed/.22s does NOT explain
Windows or establish robustness. Its optional diagnostic-only patch stayed
OUTSIDE the repository; current candidate atomic test/storage/raw defaults
were unchanged. Corrected PR/main passes do NOT causally resolve the old wait.
No production atomic-capital defect was demonstrated, and no gate was relaxed.

Scope remains the independently reviewed/adopted NEW default-off synthetic
TEST/PAPER observable-local-state foundation (adoption9df5d0b2, amendment
d427f27b, contract5e57f035). Actual participating canonical journal/collector,
opaque same-original SQLite fence and immutable ASOF observations support only
LOCAL_CHECK. Original120s execution-time semantics, partial/duplicate handling
and known financial facts remain; old coverageUNKNOWN/eligibleFalse API is
unchanged. New observations retain admission_authorized=False,
broker_history_complete=False and coverageUNKNOWN. They do NOT establish
complete broker history. Only a dedicated synthetic client is supported;
mixed/unknown ownership refuses. Nonempty native caches/requests/relationships
and positive financial-ticket settlement remain unsupported. Actual proposal,
risk, planned reservation nonce and final Core consumption remain unsupported;
no positive full P02 admission or native bridge proof is claimed.

Review fixes preserve constructor-owned callback lifetime/quiescent binding,
strong active-VM records and explicit owned-reader cleanup, bound actual
financial trading-day ownership, and the one-use exact-command Native/SDK audit
receipt. Audit suppression supplies no mutation permission; direct/refused,
callback/reentrant/repeated/cross-client attempts and all read-only guards
remain exercised. Defined new127controls and local542affected/88coordination/
164SDK figures overlap prior checks and CI; they are not additive inventory.

Receipt handling: the literal missing PR1231 acceptance suffix from
c297c4e2e1f3c84064df5175d4e3e8e980d426df versus parentabfc822d was appended ONCE
immediately before this receipt in each SAME record (5106bytes each, SHA256
fef576c1efc8f5bb7062d822467e27d44a9f590ab8edd07894c0f3c08dcca6f3).
Accepted B bytes stay an exact prefix; no old code, new tracker or docs-only PR.
This evidence-only branch is based on actual accepted mergeb479ba17; it does
not amend the reviewed source or claim a separately tested source tree.

Continue only the maintained bounded P02 prerequisite queue. Numerical ATR
bounds, native entry/management and actual risk/final-write enrollment remain
unresolved/closed; P02 target/independent-stop contracts and all five ownership
vetoes are unchanged. No native ownership restoration, order replay, quarantine
clearing, broker/provider/observer activity, operational capital/recovery action,
parked-work activation or readiness upgrade. Distribution3f48bf3f/sourcec65 and
calendar remain unchanged. Synthetic evidence is not natural/broker readiness.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


### 2026-11-15 — Batch B financial-callback settlement V1 — ADOPTED

This is a proposed NEW bounded extension to P02_OBSERVABLE_LOCAL_COOLDOWN_V1,
not historical Ross doctrine, broker-history completeness or entry authority.
Independent contract review and delegated adoption MUST precede source changes.
The accepted empty-cache foundation and old UNKNOWN reader are unchanged until
that adoption. This proposal supplies LOCAL_CHECK observations only. Proposal,
risk, canonical decision, planned reservation nonce, final native/Core write,
numerical ATR bounds, P02 native entry and management remain unsupported/closed.
Every observation keeps admission_authorized=False, broker_history_complete=False,
coverage=UNKNOWN; settled means locally accounted AS OF an owned coherent read,
not that no unseen late execution exists.

FIRST SUPPORTED CASE AND EXCLUSIONS
One same-process, same original Native client/account/client-id/epoch, reconciled
standalone long ENTRY -> original selected protective STOP -> flat roundtrip.
The original retained request and exactly its protective child must be terminal,
fully filled, uniquely owned, with no pending entry/stop/remainder liability,
relationship/selected-unit plan, add, amendment, discretionary exit or management
enrollment. Original measured entry/stop/target contracts, quantities and default
one-share operational request stay unchanged. Existing guarded synthetic sizing
can supply adverse partial cases; this policy grants no new sizing or capital.
A real retained Ross standalone fixture may demonstrate this financial boundary;
no positive P02 intent, green RiskDecision or P02 SDK send is required/permitted.
The P02 observation identity still comes from its accepted identity owner; a
foreign strategy fill is not relabelled as a P02 cooldown entry.

Enrollment remains before financial callbacks on the actual fresh opted-in
synthetic owner, after constructor-lifetime/quiescent binding. Do not weaken the
prebind unknown-intake refusal, accept old callback history at enrollment, restore
cold orders, or clear native caches. Controlled tests may invoke the existing
retained-request owner with its genuine source bindings; neither a fake settled
flag nor a caller-created canonical event substitutes for callback consumption.
Actual retained requests created later must pass the existing prospective
decision/native-scope/persistence owner; this is not permission to dispatch BUY.

IMMUTABLE SOURCE OCCURRENCES (EXISTING NATIVE INGRESS OWNER)
Extend the existing LocalIntakeTicket/origin registry, not a parallel order or
financial ledger. For each admitted bound callback preserve the detached exact
builtin/SDK-field value tree ALREADY captured by _local_native_value at outermost
callback ENTRY, plus its existing ticket id, start/end revisions, source object,
client-id/epoch/accounts, failure/finished state and raw hash. The tree is a frozen
semantic payload, not repr of a mutable SDK object retained for future use.
No user callback, arbitrary deepcopy/property or fresh caller payload is invoked
under I. Unknown types/nonfinite or malformed financial values cannot settle.

The actual Native callback body records publication linkage on its OWN active
origin ticket/thread, after the relevant source cache/query owner accepted facts:
exact order/exec/request id, selected source-cache key and source-owned request
context/generation where applicable. Only known original Native source frames
may publish; the helper cannot accept a caller's accounted/complete assertion.
Ignored/rejected/no-publication callbacks remain dirty. Frozen payload is retained
independently of mutable _executions_snapshot/open-order SDK objects. A later
mutation of such an object must fail comparison; it cannot rewrite the occurrence.
Snapshot readers return immutable detached records. Original ticket identity and
issuer registry remain necessary: constructing an equal dataclass is not origin.

CALLBACK MATRIX (EVERY OCCURRENCE IS CLASSIFIED, NONE DISCARDED)
- execDetails: unsolicited existing-owner path only, exactly one retained native
  entry/stop id. Bind account, actual client/id/epoch, positive conId/STK/currency,
  symbol, BOT/SLD side, execId, whole quantity, cumulative interval, price/average
  and authoritative original execution time. Existing cached_native_executions,
  _validate_native_binding and canonical drain perform the financial checks.
  Match exactly one committed canonical execution event and its COMPLETE feedback
  interval. A duplicate occurrence may reference that SAME event; it never creates
  a second financial effect. Changed duplicate/correction, unexpected query/history
  response, fractional/malformed/foreign or unbound execution stays dirty/vetoed.
- orderStatus: freeze ALL original fields, not latest status alone. Validate its
  exact retained order id/client/parent and status/filled/remaining/average/notional
  against that request and the actual execution-prefix intervals. Intermediate
  acknowledged/partial snapshots can be classified as superseded only when their
  exact cumulative financial prefix is complete and the terminal successor belongs
  to this same retained order; no FILLED inference from a later unrelated cache.
  Uncertain acknowledgement, contradictory terminal/quantity/price or unsupported
  status remains dirty. Status alone never proves a fill or monetary completion.
- openOrder: freeze contract/order/state and bind exact retained entry or original
  protective child, orderRef/parent/account/action/quantity/type/stop/target/session
  fields through existing request/protection validation. An old valid acknowledgement
  can be retained as such after terminal fill, not treated as a still-live order or
  deleted. Unknown order, changed stop/quantity/identity or unrelated cache refuses.
- commissionReport: bind exact source-frozen occurrence to its original execution
  via cached_native_execution_fees, including immutable first report, semantic
  conflict state and actual source/currency. A report is never itself NET authority.
  If present, all selected roundtrip execution charges must be covered by the
  existing COMPLETE durable NATIVE_ROUNDTRIP_FEE event and exact fee-owner basis.
  Identical repeated reports reuse that same auxiliary effect; receipt/latest-audit
  timestamps do not create another charge. Explicit zero requires the accepted
  actual pinned-decoder first-wire witness. Direct/default/empty zero is not known
  zero. Conflicting, malformed, negative, unbound, unsupported currency/FX or
  attempted-uncertain fee evidence remains dirty; no financial retry/NET invention.
- accountSummary/accountSummaryEnd: only the existing strict account-currency
  request's exact source-owned request id/context, actual account/client/epoch,
  completed result and verified local cleanup may support the existing fee event.
  Legacy/global summary, unrelated/late/retired request or end-only evidence refuses.
- positionMulti/positionMultiEnd: only the existing position_snapshot's actual
  request-owned context, exact account/client/epoch/security, completed immutable
  result and retired/cleaned request can establish ASOF flat quantity for this
  selected terminal case. Existing BrokerPositionResult.COMPLETE alone is NOT
  cleanup/source authority: before returning, the actual position_snapshot owner
  must issue a separate opt-in immutable completion receipt AFTER its finally has
  verified exact context retirement and local cancellation return. Freeze original
  request id/context identity, source object/client/epoch/account, detached validated
  conId/STK/currency/symbol/whole-quantity rows, completed_at, actual retirement and
  cleanup outcome in that source receipt. Never retain mutable SDK contracts there.
  Cancellation return is local cleanup, NOT broker acknowledgement. A swallowed
  cancellation exception, ownership loss, absent context, late callback or uncertain
  cleanup yields NO valid receipt and remains dirty; preserve legacy default result
  behavior without treating it as positive local authority. Completion must come
  from the original real request owner, never a test completion argument.
  Preserve source completion time and existing freshness
  rule; do not renew it on read. Whole-snapshot completeness and no foreign active
  owned remainder are required. These are local request facts, not lifetime intake
  coverage. Legacy uncorrelated position/positionEnd remain unsupported/dirty.
- Existing BASELINE/managedAccounts/nextValidId bootstrap settlement remains under
  its original exact owner checks. Request-id end markers, openOrderEnd/history,
  error, ignored inherited account callbacks, listener registration/change, unknown
  callback kinds and anything not explicitly mapped above remain dirty/vetoed.
  connect/disconnect/epoch/account/client change invalidates, never settles away.

PARTIALS, ORDERING AND SOURCE-CACHE RETENTION
A partial entry, temporary flat before terminal entry, partial protective exit,
pending cancellation/replacement or unknown remainder cannot satisfy this first
subset, even when its factual prefix is accounted/protected. Factual processing
continues. A later genuinely completed terminal roundtrip may classify historical
partial occurrences ONLY via exact source-frozen prefix-to-committed-execution
mapping; no overwrite of their original values/times. Exec/status/report arrival
orders may differ, but every callback remains dirty until its own required effects
exist. No receipt time substitutes for fill time. Corrected executions are an
explicit first-scope refusal, not a request to repair financial history here.
All nonempty Native exec/status/open-order/legacy execution rows must remain and
map to this same one-root source history; any extra/unclassified/changed row refuses.
No clear/reset/cache rewrite, dedup deletion, callback drop or invented status.

ACTUAL OWNER COMPLETION AND COHERENT LOCAL READ
The existing collect_relationship_updates and canonical drain remain the financial
pipeline. Actual strict TLE apply_event SQL event+snapshot ACK, committed event-id
membership, complete_native_feedback and retained COMPLETE canonical frames are
necessary. Match exact event ids/execution facts, quantities/notional and original
fill day against a coherent read of the existing journal, not just in-memory flags.
The current SAME-process retained native snapshot must match the latest owned
current-run durable native state byte/semantic payload and canonical basis. Prior
run nonempty retained states/cold ownership stay unsupported, as do missing/conflict
rows, unknown mode/run metadata, best-effort persistence failure and quarantine.
The read-only settlement step adds no financial SQL, native-order save or fee write.

Original selected protection must have been created/reconciled through the actual
existing post-fill owner, its exact child/native parent/selected stop preserved,
and the authoritative stop fill must have closed that same owned remainder.
Require canonical CLOSED/0, post-fill filled_qty0/exited_qty=requested, no active
registry position for the selected request and source-owned complete ASOF flat
position facts. A caller protection_confirmed/truth dictionary cannot substitute.
No open/protected-position or partial-stop local permission is introduced.

For this opt-in scope, bind the actual PostFillLifecycleEngine and ActiveTradeRegistry
objects once to the SAME existing ExecutionEngine local authority. Bind only
exact, freshly created EMPTY owners before any trade/leg/input/output handle has
escaped; prepopulated/rebound/custom/unknown lifetime refuses financial enrollment.
Register_trade currently stores caller ActiveTrade directly: under this opt-in,
external accepted exact ActiveTrade data is privately copied before storage so
the caller-retained input cannot mutate an owned record. Every external mutable
post-fill input/output is likewise either copied from an exact supported builtin/
owned dataclass field allowlist or marks the local source unsupported BEFORE
exposure. No arbitrary deepcopy hook/custom SDK property is called for authority.
Public get_trade/snapshot/selected_unit_leg, registry get_trade/snapshot and any
mutation return are detached recursively, including ProtectionOrderMeta stop/target/
stop_legs, pending-exit dictionaries, failure flags, take-profit events and registry
state_history. Internal original source-frame calls retain actual references.
A retained input/output alias is not made safe by a later fingerprint.
Their actual mutating API entries participate in existing G/revision ownership; public reads
that expose mutable trade objects become detached outside a verified original
owner frame, as the accepted TLE already does. Internal existing owner calls keep
actual references. Cover post-fill activation/exposure/fill/callback/reconciliation/
management/transition/close/recovery mutation entry and registry register/unregister/
mark_closed/close_all entry. The participating post-fill entry set is
set_startup_recovery_complete, activate_trade_management_after_fill,
update_selected_exposure, record_exit_fill, handle_broker_callback, reconcile_orders,
evaluate_trade_management, evaluate_trailing, replace_stop, cancel_stop,
execute_exit_intents, mark_exit_pending, mark_exited, startup_safe_state, and actual
transition/stop/target/selected-leg mutation helpers used by these owners. Registry
entries are register_trade, unregister_trade, mark_closed and close_all_trades.
Direct unsupported mutation helpers invalidate before use; no untracked recovery/
management action becomes an enrollment path. Existing default-off behavior is
unchanged. Unbound,
replaced, unsupported/custom/escaped owner or call during local read refuses the
local observation. Never merely hash mutable protection/registry state twice and
call that synchronization. This adds no manager, management action or new truth
policy. Native request/query callback lifetime and SAME I protect source facts;
Core truth/admission holders are not enrolled and remain unsupported.

Keep lock order from adopted foundation: nonblocking G outer owner frame, short I
snapshot/bookkeeping only, release I before Native cache lock or SQL; acquire
same-original SQLite fence only with no active owner write, failfast busy_timeout0,
trusted read/query_only/authorizer, existing finally restoration. No SDK/network/
SQL/cache/G acquisition or arbitrary listener under I. Post-fill/registry mutations
join the existing actual-source frame, not arbitrary thread/RLock nesting. Any busy
or unsupported owner returns unavailable; factual callback intake never waits for G.

ISSUER, CONSUMPTION AND REVOCATION
The actual collector-completion path may attempt settlement only AFTER its factual
fill/accounting/protection effects. Fee-bound tickets also wait for the real fee
owner completion; the early collector-return hook alone cannot certify fees.
Use one existing owner completion hook at that point; do not add a scheduler or
parallel collector. A subsequent actual collector pass may read already committed
fees. No extra fee query/write is performed by settlement.
Inside the source-owned G/read/fence frame, verify ALL selected occurrences and
current retained/canonical/protection/registry/query/fee bindings. Mint an extended
existing opaque _P02LocalSettlement receipt tied to that EXACT original ticket,
frozen occurrence/publication hash, native revision/scope, owner revisions,
retained-state and journal/fee/position basis fingerprints and actual read frame.
Register it in the existing issuer map only for this lexical completion frame.
No public caller API accepts an eligible/settled/accounted flag or prepared result.

Native verifies receipt OUTSIDE I using the actual owner read, then compares exact
current ticket/snapshot/source generation and consumes ONCE inside I. Only that
ticket's dirty marker is removed; original facts/caches/financial records remain.
Before/after each consumption recheck scope and snapshots; a new callback before
consume blocks, and a new callback after consume invalidates every earlier local
observation. Final synchronized version is recorded only when no dirty/inflight
source occurrence remains and all actual-owner/journal predicates still hold.
Receipts are nonserializable/nontransferable, source-issued, exact-frame/thread/
origin checked, single-use and revoked in finally. Failure/exception/abandonment,
callback-registration change, connection/account/client/epoch change, new pending
request, owner mutation, SQL ambiguity or changed fee basis invalidates immediately.
Known fills/fees stay recorded; no uncertainty/quarantine/recovery latch is cleared.
A fully revalidated ordinary duplicate can get a new occurrence receipt only from
another actual completion frame, never by reusing the old receipt or reaccounting.

FEES AND PROOF LIMITS
For this FIRST nonempty terminal-roundtrip subset, COMPLETE existing durable
fee-owner coverage for EVERY selected execution is mandatory before the financial
bundle can settle or make localavailable true. No-report/no-attempt still preserves
authoritative known GROSS with fee coverage UNKNOWN, but is NOT positive settlement
for this subset. Absence is not zero/NET and this narrow local restriction changes
no global financial fallback, fee rule or accepted empty-bootstrap behavior. The
settlement reader performs no query/retry/write to obtain fee coverage. Once
observed fee callbacks require effects or existing fee state is selected/uncertain,
all applicable existing fee-owner vetoes remain. Present valid
known-zero fees require durable accepted source witness just like positive fees.
No fee freshness renewal, fee-event backfill, foreign-currency conversion, timestamp
reclassification or price/quantity/target policy changes. Do not weaken canonical
missing/conflicting accounting to obtain a local condition.

CAUSAL VALIDATION BEFORE SOURCE ACCEPTANCE
Reuse existing Native/retained standalone/canonical/post-fill/strict-currency/fee
fixtures and hard SDK/memory-only guards. First demonstrate the accepted code's
specific nonempty-cache/financial-ticket refusal, not an invented production bug.
Then prove one actual source callback -> retained owner -> canonical durable effect
-> protective stop closure/reconciliation -> fee owner (where present) -> issued
receipt -> LOCAL_CHECK observation with all raw caches retained. Observe the actual
issuer call path, event counts/ids, original timestamps and no duplicate financial,
protection/capital effect. Assert all unsupported P02 stages stillFalse/no dispatch.
Paired controls: status-before-exec/report-before-exec; partial/pending/temporaryflat;
identical duplicates/repeats; corrected/conflicting executions/reports; missing or
conflicting durable event/snapshot/native state; wrong account/security/decision/
root/client/epoch; mutable SDK object after receipt; unsupported/legacy/query-end-only
facts; fee uncertainty/no-assumedzero; callback/connection/owner mutation during
issuance/verification; thrown callback/accounting/read/cleanup; forged/reused/abandoned
receipt. Use bounded synchronization/finally cleanup, no sleeps/hidden retries.
Run focused and newly affected checks, independent exact-head review and required
changed-head CI. Preserve all original failures/count overlap; no unchanged broad
suite repetition or docs-only review loop. No actual broker/provider activity,
observer, capital enrollment/recovery action or readiness upgrade.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.


#### Delegated adoption before implementation

Under the user's standing programme authority, adopt ONLY the independently
reviewed complete financial-callback settlement contract at
5b5bf6914286a0b543f0440c15081fc97c10f74f/tree56910bd0844015724409cce480fef5920ce668bd
(original draft bf44ad9b7b4fb712a7238de691dcfe1101c870e7). Independent review
resolved mandatory COMPLETE fee coverage for every selected execution, actual
position-owner completion/retirement/local-cleanup receipts, and fresh-empty
post-fill/registry binding with private input and detached outward ownership.
This is NEW project policy, not historical doctrine. The proposal wording above
records its review history; this adoption is the authorization boundary for code.

Only one same-process fully closed standalone entry/original selected protective
stop/flat roundtrip is initially supported. Nonempty source caches remain intact.
Financial callback settlement is source-issued, occurrence-bound and dependent on
actual complete durable accounting, protection, position and fee owners. No report
remains GROSS/fee UNKNOWN and cannot settle this nonempty subset. No source
cleanup/cancellation acknowledgment or broker-history completeness is invented.

This adoption supplies LOCAL_CHECK only, still default-off through the accepted
explicit synthetic TEST/PAPER enrollment. Every observation retains coverage
UNKNOWN, broker_history_complete=False and admission_authorized=False. All
proposal/risk/reservation/final-write, numerical ATR bounds, native entry and
management remain closed. A legitimate Ross retained request stays Ross; no
positive P02 SDK send, P02 target rewrite or strategy relabel is authorized.
P03 trend/macro-source proposals are NOT adopted by this decision. All five
ownership vetoes and observation3f48bf3f/sourcec65/calendar remain unchanged.
No actual provider/broker acquisition, observer, operational capital/recovery
action or readiness upgrade. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## Proposed bounded benchmark READ_ONLY capture contract — 2026-11-15

DRAFT pending independent contract review and explicit delegated adoption BEFORE
implementation. This is NEW project capture policy, not P02 entry/calibration or
historical Ross doctrine. One later user-operated attempt, not acquisition now.

- Profile `BENCHMARK_CAPTURE_V1`, default OFF, explicitly selected through the
  maintained operator/process/supervisor owners. No scanner, news, strategy,
  risk-decision, execution, order enrollment or adaptive layer is launched.
  Fixed cohort/order SPY then QQQ, separately qualified STK/USD identities, no
  substitution or extra securities. No representativeness/performance claim.
- Exact existing local PAPER/read-only 127.0.0.1:7497/client71. Native exact-ID
  pin BEFORE connect; no alternate-ID retry. Genuine operator verification covers
  PAPER account, API read-only, disabled submission and account/session scope,
  not guessed vacancy. Existing runtime inventory blocks both capture and Ross
  entrypoints; shared exact client admission refuses conflicts without terminating
  other clients. The frozen 3f48bf3f/c65/calendar caller remains unchanged.
- Use the exact reviewed finite calendar receipt through its existing configuration
  and source-integrity owner. Entire existing180s runtime plus360s supervision/
  finalization envelope must remain in ONE covered actual RTH_OPEN. Admission
  requires at least16 completed minutes since actual RTHopen. No override,
  inferred weekday, old root, resume, root reuse or concurrent observation.
- The normalized historical owner adds an explicit default-off completed-opening
  request. At actual request time obtain the existing covered window, floor actual
  UTC time to a completed minute, transmit explicit UTC endDateTime, duration in
  seconds from actual RTHopen,1min/TRADES/useRTH1/formatDate2/nonstreaming/empty
  chart options. Strict interval/identity/source checks precede dispatch. Ordinary
  last-N/empty-end defaults stay unchanged. ALL returned rows remain evidence:
  no suffix removal, forming-tail removal, gap repair, sorting or metadata repair.
- Fixed finite budget: one qualified identity, one daily-reference history, one
  opening1m history and one live snapshot per benchmark; one original connection.
  No favorable-result retries/fallback or delayed-data retry. Existing native
  deadlines/pacing/cancellation and acquisition stop owner apply. Capture has
  one180s monotonic acquisition envelope; each benchmark at most60s, remaining
  time for initial facts and cleanup; no rollover/retry when budget is exhausted.
  Additional implicit requests must be enumerated or refused before adoption.
- Acquire canonical previous completed RTH reference BEFORE opening history and
  quote; bind actual reference owner and its full original history evidence, with
  no missing-reference synthetic default. Compute the history endpoint separately
  immediately before each benchmark request; capture quote last, then original
  UTC assessment immediately, before persistence or next benchmark. Revalidate
  unchanged client/epoch/identity/calendar at every stage. No rewritten timestamp.
- Retain exact transmitted SDK spec, qualified/dispatched identities, raw bars,
  end callback/completion/dispatched clocks, normalizer choices/rejections, raw
  quote authority and source quality, reference provenance, original assessment,
  acquisition durations and detached source/input fingerprints. Missing/empty/
  partial/stale/future/forming/foreign/malformed results are retained with explicit
  refusal, not favorable retry. Unexpected source scope/callback changes abort.
- Exact existing build_completed_context/measure_completed_atr/offline_atr_report
  owners validate genuine applicable inputs. Write P02_ATR_OFFLINE_V1 canonical
  original bytes and exact report when valid, MARKET_UNVERIFIED, otherwise raw
  facts and specific refusal. Keep original strict16bar/open-aligned/live-quote/
  reference/calendar/age rules, measurement formula and numerical ATR UNKNOWN.
- Raw brokerage/provider and full offline source/report bytes stay PRIVATE under
  the fresh root, outside the shareable evidence subtree/archive. Existing privacy
  owners publish only explicit metadata, counts, status/reasons and SHA256/length
  commitments. No automatic raw redistribution, account/path disclosure or raw
  source/derived facts disguised as a summary. Capture success is not data-quality
  acceptance; neither implies calibration, costs, profit, P03 trend or macro clear.
- Reuse the actual supervisor process handshake, native client, SDK mutation audit,
  owned source/connection/request cleanup and terminal receipt. No new controller,
  scheduler, exporter, external order call, operational capital or recovery action.
  All existing five ownership/trading vetoes remain. P02 stages and unsupported
  P03 permissions remain closed. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

### Capture draft precision: budgets, privacy and terminal scope

The following refinements supersede ambiguous shorthand above, pending the same
independent review. One CAPTURE connection plus the existing independent
post-runtime-exit audit connection are sequential, never concurrent; both use
exact71, local PAPER/read-only, no fallback. Bootstrap nextValidId/managedAccounts
are connection ownership facts. At most ONE reqManagedAccts per connection is
permitted (zero if its original handshake already establishes scope), with no
polling/retry/query fallback. No account balance/position/currency subscription
is added for this data-only profile.
Each asset has one contract-details qualification, one primary25D daily TRADES
useRTH1 request ending explicitly at that actual RTHopen (formatDate1 daily-date
semantics), one1m request, and one live snapshot (including reqMarketDataType and
owned market-data cancellation). Existing terminal audit adds exactly one
reqAllOpenOrders after the capture network thread is confirmed dead; its10s query
and owned disconnect are within the existing finalization allowance. No before/
after _broker_snapshot loop or extra scanner/provider fetch runs. Cancellation of
owned DATA requests is permitted; order cancellation/mutation remains forbidden.
The ordinary supervisor audit's read-only connection request is NOT a capture
retry, ownership restoration or flat-state assumption.

Canonical reference consumes the original one-shot daily result and original
qualified identity through the existing resolver. Its retained-source adapter
must be a bounded actual-source consumption seam: same identity/contract, exact
raw result, original ownership guard, no second qualification, no network on
fallback selectors, no cached positive flags or synthetic fallback_attempted.
Every rejected fallback attempt is recorded as no-dispatch. If this cannot be
established faithfully, retain REFERENCE_UNVERIFIED rather than construct a
passing reference. Actual transmitted specs remain distinct from consumer replay
parameters; original failures and raw primary results are never overwritten.

ALL child stdout/stderr, provider traces, exception details and complete private
source/context/ATR bytes are routed outside root/e before the child starts. Safe
terminal/process receipts contain whitelisted metadata only. Existing console
redaction is necessary but does not authorize publishing OHLC/quotes. The existing
archive/seal must exclude private data structurally, not merely hope a privacy
regex recognizes it. Use a16MiB canonical input ceiling (existing offline schema)
and64MiB whole private-capture ceiling. Over-limit inputs must stop further
requests, retain bounded failure/count/hash/retention-incomplete evidence privately,
explicitly refuse context/ATR qualification and never represent a truncated input
as complete. No favorable retry or silent oldest/negative-evidence eviction.

A genuine capture-only process cannot fabricate full Core cleanup hooks. Extend
ONLY existing shutdown evidence ownership with an explicit profile bound by the
supervisor's selected command AND operator expected profile, not self-declared
payload alone. BENCHMARK_CAPTURE_V1 requires actual capture/request retirement,
manager_disconnect and console_flush evidence; unknown/mismatched profiles refuse.
Legacy REQUIRED_HOOKS and ordinary defaults stay unchanged. Existing exact process
identity, OS exit, ordered shutdown, no-runtime inventory, post-exit broker query,
mutation audits and independent finalization callbacks remain mandatory. No
nonexistent Core/scanner/news/storage cleanup is recorded as having run.

Final draft source/diagnostic precision: all CAPTURE, SUPERVISOR and independent
AUDIT stdout/stderr/provider exceptions/callback traces are private, including
preflight, failed preparation, package and seal paths. Redaction alone does not
make provider quotes/orders safe to distribute. Shared terminal evidence must
allowlist factual safety/process statuses and counts/hashes, not arbitrary broker
error strings, retained order/quote objects or source payloads. Private logging
must preserve existing authoritative OS-exit receipt paths and cleanup ownership.
Bounded size failure must invalidate terminal success without hiding the failure.

The completed-opening opt-in requires the original expected Native client object,
client71, connection epoch and original qualified contract/identity. It never
calls get_client/resolve_contract/reconnect on this bound route. Require a single
complete unambiguous contract-details result before data requests; strict scope
and calendar are rechecked immediately before and after dispatch. The daily
reference uses existing MarketDataClient._history_request with explicit expected
client/epoch, before/after strict ownership checks and NO implicit reconnect.
The same live original historical-attempt/guard context covers reference
consumption; original request-ID conflicts invalidate both daily and minute
facts. Missing original source identity/spec/completion cannot be filled from
caller expectations. Non-dispatched refusals have no fabricated transmitted spec.
The existing snapshot owner adds a strict explicit single-attempt LIVE/fresh
option through its existing manager; primary retry and delayed fallback are
outside this profile. All ordinary call signatures/default behavior stay valid.
