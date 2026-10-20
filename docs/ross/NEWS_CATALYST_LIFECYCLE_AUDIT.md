# Canonical news and Ross catalyst lifecycle audit — 20 October 2026

Baseline: accepted `ff741ded903522ad25969def38c4588c82ade03a`. Separate worktree
and branch `codex/news-catalyst-lifecycle-audit`; neither PR1116 nor the user's
observation checkout is modified. Sources/fixtures are inspected offline. No
provider, broker, scanner cycle, natural runtime or trading process is launched.
A qualified event means an attributed real catalyst, not a bullish endorsement.

## 1. Premarket facts, later evaluations and the HTTP distinction

The canonical path is
`NewsProvider.get_news_batch` in `src/news/prep_adapter.py` →
`CanonicalNewsIntelligenceService.get_news` → `CanonicalNewsEvidenceStore.read/write`
in `src/news/evidence_store.py`. Serialized preparation uses the same facts through
`evidence_from_prep_entry`; it does not own a second news cache/qualification engine.
`published_at`, issuer/text, evidence IDs and URLs survive persistence. On read,
`evidence_from_mapping`/`refresh_evidence_age` derive age from original publication;
`fetched_at`, bucket.updated_at and last_retrieval.completed_at never renew it.
`dedupe_evidence` deduplicates ID and article identity; issuer relevance is rechecked
by `evidence_issuer_relevance_verified` before reuse. `select_qualification_evidence`
retains latest presentation slots plus one policy witness, veto first, for Ross v9.
Retention is bounded; this is not an archival guarantee that every past event remains.

There are two different answers to "does it need another successful HTTP request?":

- **Evidence existence:** a still-valid positive can survive warm reads, service
  restart and preparation serialization without a new headline or HTTP. Existing
  `test_w02_news_consumer_acceptance::test_historical_positive_batch_survives_prep_serialization_warm_restart_and_explicit_refresh`
  verifies those boundaries. A cache-only legacy/fact-only request can still qualify.
- **Current observation's Ross v9 eligibility:** `_ross_retrieval_policy` requests
  compatible acquisition and cadence. In `get_news`, `_acquisition_profile` compares
  candidate identities/cohort/selected URLs/request profile, and `_symbols_due_refresh`
  checks last acquisition completion. Expired/incompatible coverage with no current
  refresh becomes `coverage_unknown`/unresolved even when a retained positive is
  independently valid. `_news_retrieval_state_for_symbol` and
  `_ross_news_context_from_evidence` then prevent Ross qualification. After a
  successful compatible **empty** refresh, the original retained positive can
  qualify again: a newly published article is not required, but current acquisition
  availability is required by the present contract.

The new offline case publishes at07:00 New York (11:00:00.500000 UTC), stores at
07:05, and reads at09:30. The same article/ID/time remains, age9000seconds. The
legacy fact-cache context qualifies without HTTP; Ross-compatible cache-only
coverage is unknown and blocks. A fixture provider's successful empty refresh
restores qualification using the same publication. This is not a natural news claim.

`_enrich_news_context_impl` first reads cache-only, computes unresolved symbols,
then performs bounded canonical acquisition when needed. Its `not unresolved`
short-circuit does **not** establish a cadence bypass: canonical coverage expiry
itself makes that cohort unresolved. A static reading that ignores this guard is
incorrect. Acquisition occurs when this consumer is called, not on a timer by itself.

## 2. Failure retention and its current qualification policy

`CanonicalNewsEvidenceStore.write` merges existing + incoming evidence. An empty
failed refresh updates last-retrieval diagnostics but does not erase still-retained
positive facts. `CanonicalNewsIntelligenceService.get_news` also merges cached and
fresh results. Failure remains per-symbol; successful peers do not inherit another
issuer's error/budget. Existing W02 tests exercise restart and mixed-batch outcomes.

Nevertheless `_ross_news_context_from_evidence` explicitly requires qualifying IDs,
no dilution, **and not retrieval_unavailable**. A retained positive can have an
independently qualified issuer-event decision while Ross status is DATA_UNAVAILABLE.
`test_unavailable_refresh_retains_evidence_but_fails_closed_for_qualification` in
`tests/test_w02_news_consumer_acceptance.py` explicitly requires this fail-closed
behavior. The new lifecycle case confirms it through the current compatible profile.
An adapter-reported HTTP error/timeout/budget is distinct from an unexpected raised
provider exception, which `get_news` does not generically turn into a cached result.
No policy allowing failed refreshes to qualify was implemented in this audit.

## 3. Publication, cache age, sessions, conflicts, dilution and expiry

| Authority | Verified implementation |
| --- | --- |
| Publication age | `assess_issuer_event` in `src/strategies/ross_momentum/policy/catalyst_policy.py`: aware publication/Headline time, not future, age **0..21600s inclusive**; reject missing/older/update-only, research-only, ambiguous issuer/event assertions. The existing value is now named ISSUER_EVENT_MAX_AGE_SECONDS. |
| General evidence freshness | `evidence_freshness_seconds`/`refresh_evidence_age`: request freshness or NEWS_MAX_AGE_HOURS(default6), independent from fetched/cache time. Generic lookback can be longer; that does not extend Ross qualification. |
| Acquisition age | `_symbols_due_refresh`: elapsed since last_retrieval.completed_at, plus profile compatibility. Registry NEWS_REFRESH_SECONDS_RTH is **120**, not the scanner helper's fallback90. Failure/empty acquisition also has cadence. |
| Preparation/session | `NewsProvider.get_news_batch` uses NEWS_REFRESH_SECONDS_PREP(default1800). Scanner `_ross_retrieval_policy` uses RTH cadence whenever issuer-query mode is enabled, including PRE; registered NEWS_REFRESH_SECONDS_PRE(default300) has no reader in these paths. There is no publication-age reset at PRE→RTH or next session. |
| Conflicting reports | Each retained item is assessed independently. There is no correction/retraction/event-revocation state machine or general conflicting-headline veto. Both "JPM reports earnings beat" and "JPM reports earnings miss" qualify as issuer earnings events in a controlled case; qualification is not a sentiment/direction judgment. |
| Dilution | `_dilution_from_evidence` in scanner_runner examines all retained accepted evidence for offering/dilution facts. `select_qualification_evidence` and `unresolved_issuer_news` bound witness/fallback veto tests by publication freshness, but final dilution_flag currently does **not** age-filter retained items. A retained offering older than6h can still veto a newer positive. Do not infer a six-hour financing-risk expiry from the witness-selection rule. |
| Explicit expiry | No supported NewsEvidence.expires_at/valid_until/correction contract or persisted catalyst-expiry state exists. There are publication-window and acquisition-coverage expiries, not an independently approved event-specific lifetime. Arbitrary raw metadata cannot invent expiry authority. |
| Cached Focus/setup | `_run_manager_pipeline` in `src/core/orchestrator.py` reuses cached_focus_rows within Top-N cadence and refreshes list timestamps. `CandidateMetrics` in `src/scanner/result_models.py` carries catalyst_present/summary/news_asof and coarse age, not a canonical publication-expiry/coverage witness. Setup dispatch does not query/requalify the canonical news service on every cycle. This is a separate revalidation gap; no executable trade bypass or natural setup progression was demonstrated here. |

### Demonstrated implementation defect and narrow repair

`_ross_news_contexts_from_news_intelligence_result` hashed the frozen evidence/
summary plus `int(time.time())`. Reusing the exact same immutable batch at article
age21600.0 and21600.1 within the same integer second returned cached CONFIRMED
past the existing cutoff. Conversely a future article becoming current within
that second reused the previous rejection. Both tests fail on accepted baseline.

The fix adds each evidence item's current publication-boundary state
unknown/future/current/stale to the context cache signature, via
`issuer_event_time_state`. The unchanged six-hour constant is shared with existing
qualification/witness checks. Exact21600 remains valid;21600.1 is stale. Normal
same-second reuse within an unchanged state remains a cache hit. No timestamp,
HTTP, issuer matching, deduplication, rule, limit or provider changes are made.
This fixes qualification authority for that adapter call; it does not make frozen
batch presentation ages live or revalidate already materialized Focus candidates.

## 4. Independent acquisition: existing service, bounded work, store limitations

`CanonicalNewsIntelligenceService.get_news` accepts NewsCandidates/request/policy
without IBKR or scanner inputs. `src/news/standalone_lookup.py::lookup_news` already
builds this same service/store/provider and returns a research-only report.
`LookupSettings.validated` bounds budgets/timeouts/item counts; `research_contracts`
creates acquisition/cache policies; `RssFetchLifecycle.wait_for_cleanup` reports
owned cleanup. An offline test invokes this existing consumer using the same
private canonical store and a fixture service, with no additional retrieval call.

`news_fetcher._fetch_headlines_from_sources` uses up to DEFAULT_RSS_FETCH_WORKERS=4,
a bounded pending-futures set, ordered URL submission, shared stage/tier deadlines,
per-source timeout clipping and explicit budget-skipped diagnostics. The adapter
coordinates fast/extended tiers; Ross v9 caps issuer queries to4 and total budget8s.
`RssFetchLifecycle` tracks owned futures/executors/response closure; workers finishing
later do not amend the already returned deadline-bounded result. Massive's existing
adapter has its own bounded/rate-limited provider contract; no new provider is added.

This pending set is a **per-lookup work queue**, not an installed persistent issuer
refresh daemon. The only explicit Queue worker found in the relevant runtime is
float discovery, which must not be misrepresented as a news queue. Independent
canonical acquisition is architecturally possible now, but there is no approved
runtime-owned news scheduler/subscription handoff maintaining Ross positives and
vetoes between scanner cycles. Default standalone cache is
`output/news_lookup/news_cache.json`, different from runtime NEWS_CACHE_FILE unless
explicitly configured. Research and Ross profiles differ; successful research
coverage is not silently compatible Ross coverage.

`CanonicalNewsEvidenceStore.write` currently does JSON read/merge/write_text without
cross-process transaction/locking or atomic replacement. Concurrent background
writers sharing that file are not proven safe. A separately invoked research
request can also apply its own bounded retention cap to that common namespace.
Do not start a second writer or promise independent continuously shared acquisition
until ownership/serialization, retention and lifecycle shutdown are designed and
tested. No second engine, daemon, provider lookup or shared runtime cache write
was created during this audit.

## 5. What measurements affect Ross decisions

| Measurement | Calculation and actual consumer |
| --- | --- |
| Heat/hotness | `news_normalizer.normalize_headlines` → `news_heat.compute_news_heat_score` combines counts, unique titles, velocity, source/region/credibility, sentiment and freshness. Stored/reported by canonical summaries and Ross presentation. Not a catalyst gate or threshold and not an input to scanner `_score_context`/Ross `select_watchlist`. |
| Novelty | Unique/replicated title-source counts are computed; there is no distinct semantic novelty/event-newness score or novelty lifecycle veto in these Ross paths. Unique count contributes to displayed heat, not direct Ross eligibility. |
| Velocity | 5/10/30/60-minute publication counts and `_attention_tier` are reported. Ross v9 recomputes accepted presentation-cohort velocity; the separate qualification witness is excluded from presentation counts. No direct Focus/catalyst/setup velocity threshold in this path. Generic `scanner/filters.py::passes_news_gates` and `news_heat.compute_fire_indicator` have thresholds, but are not this Ross canonical qualification chain. |
| Reliability | `normalize_headlines` high-credibility source-name heuristic, distinct source count and score feed heat/diagnostics. Not an independent calibrated reliability probability and not an issuer-event acceptance threshold. Fresh publication, conservative issuer-subject attribution, event vocabulary, research exclusion and dilution are actual eligibility rules. |
| Catalyst existence/type | Actually influences eligibility: `_ross_news_context_from_evidence` → `_candidate_from_context`/Focus gates. Also influences ranking through `context_builder._catalyst_quality` (type1.0, generic presence0.5) → `rank_symbol_context` → Focus ordering, and binary has_catalyst in `RossMomentumStrategy.rank_candidates`. These are existence/type signals, not heat/reliability/novelty weights. |

Scanner `_score_context` uses price-change/RVOL/dollar-volume with existing quality
penalties; `select_watchlist` sorts rank_score/pct/dollar volume. Generic
`scanner/field_mapper.py` builds composite news/momentum scores, and strategy-policy
specification text contains catalyst-quality/ranking intentions; neither proves
heat/novelty/reliability gates are enforced in the canonical Ross path.

Canonical stored aggregate fields are snapshot values: `enrich_evidence_metrics`
preserves already populated per-item values, and summaries take maxima. A controlled
case reads an article two hours later: age advances, persisted velocity_10m remains1,
but Ross v9 presentation recomputes0. The fixed qualification cache boundary does
not claim to repair these general research/display metric timestamps. A stale
canonical aggregate is not evidence of live news velocity.

## Evidence, unchanged boundaries and policy proposals

New `tests/test_news_catalyst_lifecycle_audit.py` covers exact expiry, future→current,
normal cache reuse, PRE→RTH with/without compatible coverage, successful empty
refresh, reported failure retention, dilution, conflicting earnings, metric influence,
standalone reuse and frozen metrics. Existing W02 covers preparation serialization,
restart, identity, publication faults, per-issuer failures and deduplication. Existing
Ross operational issuer tests cover witness retention and partial acquisition.
No fabricated current catalyst/provider coverage is inferred from these fixtures.

Proposals **not implemented**:

1. Decide whether a still-valid independently attributed positive may remain
   qualified under degraded/expired acquisition coverage. Evidence: retained event
   remains qualified but current policy blocks after120s/error. Any change needs
   explicit degraded-coverage truth and must not infer absence or hide dilution.
2. Carry canonical witness IDs/publication/qualification expiry and coverage facts
   through cached Focus/setup handoff, revalidating the existing rules before use.
   Define failure behavior and coexistence with current list continuity first.
3. Define correction/retraction/conflict handling and financing-risk invalidation/
   expiry separately from positive-event publication freshness. Evidence: conflicting
   earnings both qualify; retained older offering remains veto. No automatic
   expiry, polarity gate or arbitrary raw flag authority was introduced.
4. If independent maintenance is wanted, use one canonical service with a bounded
   runtime-owned scheduler, serialized store ownership and joinable shutdown, not
   another engine. Establish writer/retention interoperability before deployment.
5. Decide which metrics should be current measurements, with cohort/time attribution;
   any new heat/novelty/reliability ranking/gate requires calibration evidence.

These proposals are not approvals or implemented policy. PAPER_READY=NO. Historical
natural receipts, holdings/ownership blockers and PR1116 source remain unchanged.
