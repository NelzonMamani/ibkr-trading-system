# Ross issuer-query acquisition (acceptance pending)

`ROSS_ISSUER_QUERY_ENABLED=false` is the default. Set the registered boolean
`ROSS_ISSUER_QUERY_ENABLED=true` to enable the actual Ross consumer's
`_enrich_news_context` -> canonical news service -> batch RSS adapter -> existing
RSS scheduler/store path. This does not enable trading, select candidates, bypass
mandatory catalyst policy, or upgrade readiness. Research records stay research.

The existing Google News RSS search contract encodes full names/aliases, `$TICKER`
and supported exchange notation. The primary tier schedules at most four distinct
Google query URLs first (candidate priority rank, then ticker); identical URLs
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
