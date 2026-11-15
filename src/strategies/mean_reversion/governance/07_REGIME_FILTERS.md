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
