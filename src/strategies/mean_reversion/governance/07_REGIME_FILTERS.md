# Regime Filters (Clause 7)

## Stand-down regimes
- Index trend day (SPY/QQQ trending strongly up/down)
- Fresh news regime (if configured to forbid)
- Halts
- Macro event window
- VWAP slope veto (trend proxy)

## Time-of-day gating
- Avoid first minutes after open
- Avoid late-session illiquidity

## 2026-11-15 — Source-producing contract proposal; implementation remains blocked

Status: **DRAFT, not adopted, not a complete source contract.** PR1233's veto
repair remains accepted. This inspection does not repeat its foundation tests
or create an UNKNOWN-only handoff and call the dependency closed. No numerical
strong-trend or macro-window policy is adopted by this proposal.

### Existing authority and the exact missing inputs

The immutable contract clause7 and this file require stand-down on strong
SPY/QQQ index trends and major macro-event windows. They do not define a trend
formula, completed timeframe/lookback, calibrated strength boundary, event
classes, schedule source or before/after release window. The source-local
`MeanReversionPolicyConfig.max_abs_vwap_slope_atr_per_min` is a separate
candidate VWAP-slope veto, not authority to classify broad-index trend.

Existing reusable owners, inspected offline:

- `src/market_data/candidate_identity.py:CandidateIdentity` retains qualified
  security identity. A ticker string or scanner rank cannot replace the
  separately qualified SPY and QQQ identities.
- `src/ibkr/market_data_client.py:HistoricalDataResult` and
  `HistoricalRequestSpec` retain actual request/end/completion, dispatched and
  returned security identities, original raw bars and normalization facts.
  `history_ownership_guard` retains current connection/request-conflict
  authority. A list, count, return from SDK, or completion counter cannot
  manufacture this metadata.
- `src/adapters/data/historical_data_provider.py:get_intraday_bars` normalizes
  supported completed historical results and retains rejected/source counts.
  Its current function acquires data: it must not be called in this offline
  batch. A future source adapter must consume already supplied qualified facts
  or use an explicitly authorized existing acquisition path.
- `src/market_data/session_pct_change.py:covered_opening_window` binds an
  explicit finite reviewed market-session receipt and original calendar facts.
  Its present usable scope is PRE/RTH_OPEN; it is not an all-day authority.
  `resolve_market_session_context` labels all phases but does not manufacture
  finite calendar coverage. No new calendar engine is proposed.
- `src/domain/quote_freshness.py` preserves original LAST_TRADE clocks, maximum
  age and historical vetoes. Acquisition/callback/assessment time are distinct.
- PR1230's `CompletedSignalContext` demonstrates detached source/derived
  fingerprints and revalidation. Its current context is P02-specific, requires
  its own reference/quote contract and at least16 opening one-minute bars.
  Neither its trading policy nor its fixed lookback/session scope may be
  silently imported as P03 index-trend authority.

No approved current-session SPY/QQQ historical-and-quote evidence pair or
P03-specific positive source producer exists in the active Core handoff.
`_prep_symbols_from_config` falling back to [SPY, QQQ] is symbol preparation,
not qualified index coverage. The active manager pipeline invokes StrategyRunner
before its optional post-strategy aggregate observer; that observer supplies no
pre-assessment facts. The other adaptive stage after the unconditional return
in `_select_watchlist_for_policy` is unreachable and must remain unused.

No scheduled-economic-event owner, vetted finite schedule receipt, approved
release-class registry or schedule-revision/coverage authority was found in
tracked source, configuration, tests or maintained P03 governance. The existing
exchange calendar receipt declares trading sessions only. Generic RSS/news
hits and absence of news are not a scheduled-calendar completeness source.
The illustrative `major_macro_event_window=False` value is not source evidence.

Source candidates for later review, **not approved, fetched or present datasets**:
Federal Reserve FOMC calendars
(https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), BLS release
schedule (https://www.bls.gov/schedule/), and BEA release schedule
(https://www.bea.gov/news/schedule). Candidate classes are FOMC decision/press
conference, BLS Employment Situation/CPI and BEA GDP/Personal Income and Outlays.
This is a proposed source/class review list, not an exhaustive event universe,
verified schedule, adopted window or evidence that an event-free interval is
covered. Original publisher bytes, timezone, version/revision and finite
class/interval completeness review would still be required.

`src/regime/observers.py` observes the selected scanner universe; its
news_density_proxy is zero with MISSING_NEWS. `classifier.py` uses watchlist
momentum/range/spread baseline scores, not separately qualified SPY/QQQ streams
or economic-release coverage. Its TRENDING/CHOP/NEWS_DRIVEN labels cannot prove
four directional booleans or absence of a macro window. Enabling this adaptive
layer or changing weights would not supply the missing facts.

### Proposed bounded source contract for independent review

The following are proposed NEW project requirements, not historical doctrine.
They are necessary shape/ownership constraints; unresolved parameters below
mean this is not yet an adoptable complete measurement contract.

1. Each index needs its own exact qualified CandidateIdentity, original
   HistoricalDataResult request/completion/connection binding and immutable
   source OHLCV. The eventual selected timeframe and lookback must consist
   only of completed, ordered, contiguous, same-session bars; no overnight
   carry, forming bar, reconstructed metadata, foreign identity or rejected
   normalization. The source calendar must explicitly cover the assessment
   session; restrict enrollment to its proven phase rather than claiming MID
   or LATE from the existing opening-only receipt.
2. A versioned formula must publish exact units, seed/window, inclusion and
   equality rules and feature values. Compute each index independently.
   Never infer either direction from another index or an aggregate label.
   Contradictory directions within one index, conflicting same-version facts
   or disagreement between source identity/period and derived evidence make
   that index UNKNOWN. Independently valid SPY-up and QQQ-down are not a source
   conflict: either strong direction still vetoes P03. Both direction flags
   may be False only after the complete required measurement window is valid
   and the adopted formula evaluates neither direction as strong.
3. Scheduled event evidence needs an approved authoritative publisher/source
   registry and an immutable original publication/revision receipt covering
   the exact adopted classes and assessment interval. Specify scheduled times,
   source timezone/DST, cancellations/reschedules, revision version, original
   publication and retrieval clocks, canonical event IDs and content hash.
   Conflicting revisions, an unapproved URL, a caller's coverage=True, an
   empty fetch, cache age or uptime cannot prove coverage. A reviewed finite
   no-event declaration may mean covered absence only when backed by the same
   authoritative class/interval manifest, not by an empty article collection.
4. True means a covered scheduled event intersects its adopted window;
   False requires complete reviewed coverage of every adopted relevant class
   over the whole assessment-window interval. Unknown disables permission.
   The result means only absence/presence of the covered scheduled event
   risk, never absence of unforeseen macroeconomic or geopolitical risk.
   Unforeseen news and existing individual-symbol news/truth/risk vetoes remain
   separate and active; scheduled clearance cannot override them.
5. The eventual immutable handoff must retain both complete index source
   bundles plus schedule source bytes/manifests; original clocks and session
   boundaries; explicit coverage/reasons per required fact; source and derived
   fingerprints; policy/schema versions; assessment time and validity end;
   cycle/security/connection/source-owner identity and configuration version.
   Mutable source aliases or a dict of booleans are not authoritative evidence.
6. Active Core must take a coherent already-owned source snapshot before
   assessment, then pass the same immutable occurrence-bound handoff through
   StrategyRunner -> MeanReversionRunner -> P03 consumer. Revalidate source,
   configuration, session, fingerprints and original clocks at each stage
   using current assessment time; no renewed publication/bar timestamps or
   recomputed hashes over silently corrected facts. Callback corrections,
   new completed windows, schedule revision, source/connection/identity change,
   calendar/policy change or expiry invalidates a prior positive observation.
   Unsupported/missing handoff stays vetoed. No adaptive weighting, new manager,
   private source acquisition or legacy-tail resurrection is authorized.

### Decisions/data required before implementation

- Select and justify a P03-specific strong-trend formula, timeframe, lookback,
  numerical strength boundary, equality/flat rule and bar/quote validity end.
  Existing qualitative stand-down rules and P02 scoring/ATR measurements do not
  supply this calibration. Specify rationale independently of desired fixtures;
  no numerical choice is made merely to manufacture a covered nontrend pass.
- Name and approve the exact scheduled-release publishers, covered classes,
  completeness attestation/revision mechanism and a finite original offline
  dataset. Define the before/after window, endpoints and bounded publication/
  revision freshness. No such approved input is currently available. Official
  source selection alone would still not establish an actually supplied
  complete receipt, original times or current revision coverage.
- Decide initial actual-session scope consistent with existing explicit
  coverage, source-owner mutation/version fences and authorized runtime intake.
  A broader session contract must extend existing ownership deliberately.

Only after independent review and explicit NEW project-policy adoption of
these decisions may an implementation be claimed. Its offline causal proof
must include actual source adapter -> active Core -> runners -> consumer with
covered nontrend/outside-window and separate trend/event vetoes; incomplete,
stale, future, foreign, contradictory and between-stage mutation cases must
refuse. Synthetic source fixtures must be labelled synthetic and cannot attest
an approved market/calendar dataset or natural positive Core admission.

Current outcome: exact source/calibration dependencies remain unresolved;
P03 regime vetoes remain intact. Continue the independent ready programme batch.
No provider/broker acquisition, observer, order, operational action or readiness
upgrade. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## 2026-11-15 — Concrete bounded measurement/schedule proposal for review

Status: **PROPOSED NEW PROJECT POLICY, NOT ADOPTED OR IMPLEMENTED.** This makes
specific choices for review instead of claiming the earlier missing-input
inventory was a complete contract. No P03 permission is opened by this text.
No market outcome, profit label or desired fixture was used to choose it.

### P03_REGIME_SOURCE_V1: finite opening-phase scope

Initial applicability is actual RTH_OPEN under the existing finite reviewed
market-session owner, after fifteen completed current-session minutes and
strictly before its opening_end/current_close. PRE, MID, LATE, an unknown
calendar, holiday, override or identity/source conflict remains UNKNOWN.
This intentionally does not extend the current opening-only calendar owner or
P03's native/management authority. Ordinary P03 min/max-time, spread, risk,
news and ownership gates remain independently necessary.

**Measurement definition, not calibrated predictive strength.** For each
separately qualified SPY and QQQ, use the most recent three fully completed
five-minute blocks aligned to the covered 09:30 New York RTH open. Derive those
blocks solely from their same-security completed one-minute OHLCV stream.
Let their OHLC values in increasing time order be O[i],H[i],L[i],C[i], i=0..2.
The proposed operational directional-structure veto is:

- UP: C[i] > O[i] for all three blocks, and H[0] < H[1] < H[2],
  L[0] < L[1] < L[2], C[0] < C[1] < C[2].
- DOWN: C[i] < O[i] for all three blocks, and H[0] > H[1] > H[2],
  L[0] > L[1] > L[2], C[0] > C[1] > C[2].
- Neither: both direction flags False, only if every required input is valid
  and the complete formula has been evaluated. Equality breaks the relevant
  strict structure condition; no epsilon, percentage-strength threshold or
  minimum net-return calibration is introduced. A flat valid window can be
  neither. This is not a claim that no other form of market trend exists.

Rationale: three complete aligned blocks distinguish a sustained sequence of
bodies and progressing entire ranges from a single-bar impulse. Requiring
both high/low and close progression avoids making candle color alone the
stand-down definition. Fifteen minutes is the explicit structure horizon,
not a backtested optimum. Strict inequalities are deterministic geometry,
not a probability estimate. Tiny but valid progression can conservatively
veto; this proposal makes no claim of calibrated signal quality. A different
broader meaning of strong trend would require a separately reviewed policy.

UP and DOWN cannot both be true for a single coherent window; supplied or
derived contradictory flags are invalid evidence, not an arbitration choice.
Valid SPY-UP with valid QQQ-DOWN is not a source conflict: either individual
strong direction vetoes P03 as before. No direction or absence is inferred
from the other ETF, the selected-stock universe or an aggregate regime label.

**Completion/freshness.** Let E be the most recent aligned five-minute end at
or before the current assessment. The three blocks exactly cover [E-15m,E).
Require that interval to lie inside the current covered RTH session. Source
one-minute bars cover that interval and every completed minute through the
latest completed minute, ordered with no gaps/duplicates; no forming bar,
prior-session carry or reconstructed bar is permitted. Each block needs all
five members with finite positive coherent OHLC and finite nonnegative
volume. A zero-volume member is retained, never fabricated or dropped.
The latest one-minute end has age in [0,60s); E has age in [0,300s). Equality
at either stale boundary requires a newer completed window. The one-minute
rule is the natural completion cadence, not a widened quote tolerance.
Original request dispatch <= completion <= current assessment; every used
bar end <= authoritative completion. Preserve all raw/normalized membership,
rejections, request spec, IDs and actual historical ownership guards. Require
an independently qualified same-security LIVE quote under the existing
quote-time/market-data/quality owners and unchanged quote max-age/history
rules; a history close is not a current quote. No missing ownership metadata
may be inferred from historical completion counters.

### Scheduled-event classes, publishers and operational windows

The following exact publisher endpoints/classes are proposed for explicit
source approval. They are reference candidates, not an already acquired or
reviewed finite event dataset:

| Publisher/source | Covered class identifiers | Proposed closed window around explicit scheduled start |
| --- | --- | --- |
| Federal Reserve, https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm | FED_FOMC_RATE_STATEMENT; FED_FOMC_CHAIR_PRESS_CONFERENCE | [start-30m,start+90m] for each event |
| BLS, https://www.bls.gov/schedule/ | BLS_EMPLOYMENT_SITUATION; BLS_CONSUMER_PRICE_INDEX | [start-15m,start+30m] |
| BEA, https://www.bea.gov/news/schedule | BEA_GDP_ADVANCE; BEA_GDP_SECOND; BEA_GDP_THIRD; BEA_PERSONAL_INCOME_AND_OUTLAYS | [start-15m,start+30m] |

These are NEW operational stand-down choices, not publisher recommendations,
Ross doctrine or calibrated impact estimates. The statistical-release embargo
includes the immediate pre-release interval and the next half hour; the wider
FOMC interval covers overlapping statement/press-conference scheduling and
longer communication. Overlapping windows are unioned; each event retains its
own identity. All listed GDP estimates are covered so an estimate revision is
not silently treated as an unrelated harmless update. Minutes, speeches,
auctions, PPI and other releases are explicitly outside this finite class
universe; its False result cannot assert those risks absent. An unforeseen
or unscheduled event is not certified absent by scheduled-calendar clearance.
Existing news, safety and risk vetoes remain separate and cannot be overridden.

**No default release clocks.** Each event must retain its actual publisher
class/name, scheduled local date/time, explicit source timezone, canonical
UTC instant and original source literal. A date-only FOMC calendar entry
cannot be assigned a conventional 14:00/14:30 time by inference. If a linked
publisher release page is necessary to establish the clock, its exact URL
and bytes must be included and independently approved with the parent receipt.
Only explicit Eastern/New York scheduling may use America/New_York; preserve
DST conversion and refuse naive, ambiguous, nonexistent or conflicting times.
Do not invent midnight events or refresh original publication/revision time.

**Finite observable coverage.** An approved immutable receipt covers the
entire target New York calendar date for EVERY listed class, with explicit
per-class rows including reviewed no-event declarations. It contains exact
original publisher bytes/content hashes, retrieval/completion times, original
publication/revision times if supplied, final official URLs, event identities,
canonical clocks, class intervals, source version, reviewer/adoption reference
and a declared valid-through. A local hash is content identity, not a publisher
revision number or completeness proof. Where the publisher supplies no
revision timestamp/version, record that absence; approval must identify the
exact reviewed bytes and the last successful source verification, never mint
a publisher version. Cancellations/reschedules require explicit new evidence;
conflicting or incomplete revisions make the affected coverage UNKNOWN.

The proposed receipt source verification age is [0,15m), with valid-through
no later than verification+15m or target-date end, whichever comes first.
This is a bounded operational refresh choice, not a guarantee the publisher
cannot change within fifteen minutes. No refresh is implemented here. A new
read can renew verification of the same bytes but cannot renew an event's
publication or scheduled time; failed reads and cache reuse cannot renew it.
An immutable static receipt naturally expires; no local flag extends it.
Historical and synthetic receipts may be replayed only with explicitly
labelled retrospective assessments, never as contemporaneous clearance.

True requires a valid covered event with assessment in its class's closed
window, including both endpoints. False requires every adopted class's
reviewed coverage over all event starts that could intersect assessment:
[start_of_relevant_interval = assessment-post_window,
 end_of_relevant_interval = assessment+pre_window], inclusive. The initial
opening-phase scope places these intervals within the covered target date;
any cross-date interval outside the receipt is UNKNOWN. Empty HTTP/ICS/JSON,
missing class, unavailable source, a caller coverage=True, a changed/unapproved
source or a stale receipt is UNKNOWN. This is only **observed scheduled-event
coverage as of the approved verification**, not a guarantee against an unseen
late schedule revision, unscheduled event or unforeseen macroeconomic risk.

### Immutable active handoff, revision fencing and evidence still missing

Reuse existing CandidateIdentity, HistoricalDataResult/RequestSpec, history
ownership guard, MarketSnapshot/quote-time and covered-session owners. The
future P03 owner may project these completed supplied inputs; it must not
construct another acquisition manager or borrow P02 trading calibration.
One detached immutable evidence bundle must retain separate SPY and QQQ raw
source facts/membership and derived geometry, schedule source bytes/coverage,
original times and validity ends, qualified identities, cycle/session,
connection/source-owner versions, policy/config/schema versions and canonical
source/derived SHA256 fingerprints. The bundle is not four caller-supplied
booleans plus a claimed coverage flag.

Before assessment, actual Core supplies that bundle through StrategyRunner ->
MeanReversionRunner -> P03 consumer. At every boundary use current assessment
time and the same original source bundle, checking expiry, actual phase,
identity, live request/connection guard, source/policy/config version and both
fingerprints. The mutation/version owner must expose corrections, replacement
quotes/history, disconnect/reconnect, calendar change, schedule revision or
persistence failure; any such change invalidates prior positive observations.
No recalculated hash over silently changed facts, new receipt clock or legacy
adaptive label may repair a failed revalidation. The concrete existing seams
are `CoreOrchestrator._run_manager_pipeline` before its strategy call,
`StrategyRunner.process`'s existing per-runner context,
`MeanReversionRunner.run`, `MeanReversionStrategy.process_watchlist` and the
existing `build_market_regime_facts` consumer (currently given None). Any new
optional handoff argument must be P03-specific and default absent; other
strategies and their ordinary defaults must not inherit these facts or rules.
This prerequisite must be implemented through existing owners deliberately;
it is not supplied by this policy draft. Current native structural/risk/short/
management vetoes remain.

Reference research on 2026-11-15 attempted the three HTTPS publisher pages;
each was refused by the environment proxy with HTTP tunnel403 before page
retrieval. No publisher bytes, current release times, calendar dataset or
completeness certificate was acquired or approved. Therefore the source
endpoints/classes/windows and structural formula above are concrete review
proposals ONLY. Independent contract review must precede any adoption and
implementation. Missing inputs remain: approved finite original official
schedule receipts with per-class coverage and revision/freshness authority;
qualified contemporaneous SPY/QQQ complete history/quotes; and existing-owner
version fences at the actual active handoff. A bounded READ_ONLY capture can
preserve benchmark source facts, but cannot fabricate schedule coverage or
make this measurement a calibrated/profitable strategy. No alwaysUNKNOWN
carrier is counted as closing the source-producing dependency.
