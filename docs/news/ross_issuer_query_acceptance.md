# Ross issuer-query acquisition (acceptance pending)

`ROSS_ISSUER_QUERY_ENABLED=false` is the default. Set the registered boolean
`ROSS_ISSUER_QUERY_ENABLED=true` to enable the actual Ross consumer's
`_enrich_news_context` -> canonical news service -> batch RSS adapter -> existing
RSS scheduler/store path. This does not enable trading, select candidates, bypass
mandatory catalyst policy, or upgrade readiness. Research records stay research.

The existing Google News RSS search contract encodes full names/aliases, `$TICKER`
and supported exchange notation. The primary tier schedules at most four distinct
Google query URLs first (explicit scanner priority, otherwise existing context
order; ticker breaks ties); identical URLs
share a fetch. Fixed feeds remain one fetch per distinct feed across the batch.
The unchanged eight-second stage reserves 5.2 seconds for primary acquisition and
2.8 seconds for PREP fallback. Queries are not appended to the fallback reserve.
Queries use at most the existing five-second timeout in one four-worker wave;
fixed feeds then use existing adaptive deadlines. No source is retried within a
lookup. Yahoo ticker queries are deliberately not scheduled operationally after
the recorded HTTP429 results; research capability and its failure evidence remain.

At most four issuers usually receive queries per acquisition. Extra queries and
invalid issuer identities are explicitly unattempted in per-issuer coverage;
this is partial company coverage, not evidence of no news. There is no claim of
fair rotation across a larger ranked batch. Source deadlines, HTTP failures,
processing truncation, dates, missing dates and publication ranges remain visible.
Operational feeds are byte-bounded to 512 KiB each. Late workers never contribute
articles after retrieval deadlines. The scanner only snapshots owned cleanup;
it never waits ten extra seconds on the news stage. The diagnostic verifier waits
up to ten seconds after the consumer returns, separately from acquisition.
The verification subprocess also has a wall deadline and records forced exits.

Canonical acquisition metadata, including failed and empty results, obeys the
existing RTH refresh interval (registry default 120 seconds). The full query URL
plan, policy/profile and effective issuer identity fingerprint cache coverage.
Changing quotes/volume alone cannot defeat cadence. Research coverage is
incompatible with this operational acquisition fingerprint, and research articles
cannot qualify. No second cache or refresh authority is introduced.

The latest-five limit previously applied before qualification. With this setting,
retention streams through entries under the same processing deadlines and keeps
five presentation items plus one semantic policy witness. A fresh dilution veto
has priority over a qualifying event witness. The witness is re-evaluated from
text, issuer identity, publication time and provenance at every read/merge, never
from stored classification flags. This is a bounded qualification/presentation
split, not an arbitrary increase to the headline cap. Truncated scans remain
incomplete. Disabled acquisition keeps the old five-item routing contract.

The existing Ross policy vocabulary remains authoritative. Qualification now also
requires conservative subject/event attribution: requested issuer at the start
of the relevant clause, an asserted direct event, no ambiguous coordinated subject
or speculative/preview wording. Another issuer's earnings with a co-mention does
not bind to the requested ticker. Unknown grammar fails closed. This deliberately
misses some genuine events, including many agency-led headlines. Update-only
timestamps are labelled and cannot establish fresh publication. Freshness remains
six hours; mandatory catalyst policy and dilution veto remain. An unavailable
current retrieval fails closed even when an old positive item remains in cache.

Google article links are intermediary links, not resolved publisher article URLs.
Publisher labels, original link, original timestamp/date basis and source-provided
publisher URL remain separate. Exact headline equality is not proof of identical
events, and repeated coverage is conditional on observed articles.

## Broker-free verification

Use `scripts/verify_ross_operational_news.py --candidates-file <identities.json>
--output-directory <new-directory> --enable-issuer-query`. It invokes the actual
Ross news consumer with a new canonical cache and no operational prep hydration,
records canonical results, decisions, diagnostics, source hashes, bounded raw
responses, cleanup and process outcomes. It never starts a scanner cycle, broker,
market-data provider or trading runtime. Default without the flag is cache-only.
Upload the entire output directory (ZIP), including raw responses and manifests;
a timeout/failure is evidence and must not be discarded. Offline fixture success
is contract verification; captured-response replay is regression, not a claim of
current network availability or live operational eligibility. Windows acceptance
within eight seconds is still required before considering this setting's default.


## Windows bottleneck repair (operational acceptance still pending)

The 2026-10-14 Windows run at `0a4bfce95b` completed all three Google
queries, but query response completion was not completion of the whole required
primary acquisition. The adapter passed the original full unresolved issuer set
to PREP even after primary deadlines, and propagated global exhaustion to every
issuer. Eight seconds measures the acquisition deadline, not a hard total for
cache/profile work, classification, persistence and logging. The old verifier's
`consumer_elapsed_seconds` additionally included diagnostic result assembly.

Operational scheduling contract `ross_primary_completion_v3` preserves the
5.2/2.8 allocations and the eight-second ceiling. Incomplete required primary
acquisition remains unavailable; PREP cannot repair that missing dependency, so
it is explicitly deferred instead of launching another pool. This scheduling
optimization remains, but the universal availability dependency introduced with
it was an implementation defect; the acquisition/coverage correction below
supersedes that dependency. Complete primary exploration still sends only
policy-unresolved issuers to fallback. A fresh policy witness or safety veto
remains terminal. A completed peer does not inherit another peer's deadline.

Compatible canonical acquisition metadata is reused for positive, negative and
unavailable outcomes within existing cadence. A current negative cache hit now
returns after one canonical read, rather than rereading the same cache/prep and
reconstructing all diagnostics. Fresh prep articles still use existing identity,
time and policy checks; prep hydration alone cannot certify missing query/source
coverage or clear a failed acquisition. No second cache authority is introduced.
Old scheduling fingerprints cannot certify the repaired completion contract.

The verifier now separates the actual news consumer call from report assembly.
Canonical diagnostics measure cache reads, acquisition profile/refresh planning,
provider time, acquisition metadata/cache write, merge/summary work, diagnostic
emission, and Ross policy-context processing. Per-source coordinator processing
is separate from worker request/parse latency. Cleanup remains outside the
consumer call. Process exit zero means diagnostic completion, not acceptance or
trading readiness. Every dependency-deferred source and incomplete outcome stays
visible. Live fixed-source latency may still prevent cold acquisition completion;
no coverage, freshness or catalyst rule is relaxed to hide that limit.

The earlier repair at `929084c64c` treated every selected primary URL as a
required availability dependency. That was adapter logic, not an explicit Ross
policy requirement. It is superseded by the acquisition/coverage correction below;
HTTP errors still remain real coverage failures and are never erased.

The `ross_issuer_event_v9` qualification fingerprint also rejects unverified
post-event ownership (for example, JPM reporting earnings of another company).
Verified same-issuer ownership and ordinary earnings-period complements remain
supported. This fingerprint invalidates older compressed witness-selection
coverage, rather than treating an old retained cohort as proof of the new rule.

Short dilution abbreviations (ATM, S1, S-1) require token boundaries; ordinary
words such as treatment cannot occupy the priority veto witness slot. Longer
existing offering/dilution terms retain their established matching forms.
Degradation is derived from each result's recorded acquisition policy, so a
later dynamic setting change cannot relabel an operational failure as healthy.

Ownership/complement checks apply across catalyst classes, not just earnings.
For example, an issuer announcing FDA approval for an unverified rival cannot
qualify that rival's event. Unknown product/beneficiary relationships also fail
closed; this deliberately limits recall rather than guessing event ownership.

The v5 grammar preserves fully dated `quarter ended September 30, 2026`
reporting periods (validated calendar dates, with no trailing owner). Explicit
bounded product/purpose complements such as `for its lead drug AX-101`, `for
lead therapy`, `for cloud services`, and `for hospitals` do not imply another
issuer owns the event. Arbitrary corporate names, invalid dates and appended
foreign ownership remain rejected. These are labelled contract fixtures, not
observed positive trading evidence.

The v6 attribution grammar handles ordinary complements case-insensitively
and protects a verified leading issuer identity from clause-word splitting
(e.g. AS / Amer Sports). Later co-mention clauses remain independent. Explicit
lowercase/title-case and separator-ticker fixtures verify both acceptance of
direct assertions and rejection of rival-event inheritance.

Passive `granted/awarded/issued/assigned/licensed/given to` event recipients
require the same verified issuer ownership as other owner complements. Ordinary
purpose infinitives (`to improve hospitals`) are not recipients. Unknown or
foreign recipients fail closed; v7 invalidates prior compressed witness proof.

A verified same-issuer recipient can be followed by the same fully anchored
ordinary product/purpose grammar. This reuses the original complement rule;
trailing foreign ownership and unknown beneficiaries remain rejected. The v8
fingerprint invalidates previously compressed witness-selection coverage.

The same comma/whitespace separators accepted before verified-owner earnings
periods are accepted before its fully anchored ordinary complement. Unknown or
foreign suffixes remain rejected; v9 invalidates earlier witness proof.

## Acquisition versus source coverage: authority correction

The universal dependency came from `batch_rss_adapter.py` at reviewed head
`929084c64ca66ccef58792b6feb3667953873c54`: `primary_complete` requires every
selected primary URL to be attempted, available and untruncated; the
`required_primary_unavailable` branch then forces every issuer unavailable.
The earlier tests and repair notes mirrored that implementation assumption;
they were not an independent Ross policy requirement.

Actual authority:

- `strategy_policy.py:1022` (`StockSelectionSpec.require_catalyst=True`) and
  `policy/ross_policy.py:68-70` delegate mandatory catalyst policy.
- `policy/catalyst_policy.py:42-64` requires a confirmed catalyst, and fails
  missing/unavailable/unknown evidence closed. It contains no publisher quorum.
- `docs/architecture/NEWS_INTELLIGENCE_CONTRACT.md`, Ownership Boundary and
  Separate Dimensions, keep objective retrieval separate from strategy policy.
  Its Ross Runtime Migration forbids treating unavailability/budget exhaustion
  as catalyst absence. This correction preserves those negative decisions.
- `source_groups.py` defines memberships/order/purposes, not an availability AND
  across publishers. The accepted canonical adapter `_retrieval_status` and
  `_provider_available` support `partial_request_failure` as partial acquisition;
  `tests/test_pr1067_batch_rss_adapter.py::test_pr1067_partial_failure_mapping`
  verifies that established contract.
- `_news_retrieval_state_for_symbol` already isolates successful per-issuer
  `available`/`partial` summaries from unrelated batch exhaustion. The existing
  successful-peer/fallback-deadline regression exercises that distinction.

No Ross thresholds, event vocabulary, attribution grammar, freshness, source
membership, publisher quorum, dilution veto, budgets or default setting change.
This corrects an accidental adapter-wide dependency, not an adopted policy.

The explicit operational acquisition contract is now:

| Dimension | Contract |
| --- | --- |
| Issuer acquisition | A selected issuer-query response fully processed before the coordinator deadline, or a matched entry already accepted by the canonical bounded fetcher, establishes a bounded acquisition. HTTP success alone or another issuer's empty query does not. |
| Selected-source coverage | Complete only when every URL in the planned source scope, including deferred/capped work, was attempted, available and fully processed. Otherwise partial; individual failures, unattempted rows, processing cuts and deadlines remain visible. |
| Search completeness | Always unestablished. Even complete selected-source coverage is not an exhaustive company-news search. `issuer_query_requests_completed` names query-request completion, not general coverage. |
| Qualification | Existing Ross publication freshness, issuer-to-event attribution, uncertainty rejection and dilution veto decide every retained article. Valid acquired evidence can qualify under partial source coverage. Neither acquisition success nor HTTP200 manufactures a catalyst. |
| Partial negative | Without a qualifying witness, partial coverage cannot prove catalyst absence. Keep mandatory DATA_UNAVAILABLE, including when a dilution veto is observed; retain the veto flag and explicit `partial_coverage_dilution_veto` rejection reason. |
| Deadline | Late worker results never enter canonical evidence. A coverage deadline is retained separately from a completed issuer acquisition; no budget increase or new fallback work. |
| Cache | Persist the same acquisition/coverage facts in the canonical store. Scheduling fingerprint `ross_issuer_acquisition_v4` rejects earlier universal-dependency outcomes. No second authority. |

Contract-positive cases are labelled fixtures, not natural catalyst evidence.
The attached Windows timing acceptance is preserved separately; no new Windows
lookup is requested by this diagnostic correction.
