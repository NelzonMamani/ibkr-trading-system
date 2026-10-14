# Explicit issuer-query RSS research

`scripts/verify_news_discovery.py --profile issuer_query_rss_research_v1`
accepts one ticker with `--company-name` and repeatable `--alias`, or a
`--candidates-file` batch of full identities. This is opt-in research through
the canonical service, RSS provider, four-worker scheduler and canonical store.
It does not enable Ross trading or qualify catalysts.

## Recovered source contracts and callers

The archived `troubleshooting/stock_selection/stock_selection_scanner_25_jan_2026.py`
defines `fetch_latest_news_headline`, called by that script's scanner loop.
The dated `ross_stock_selection_scanner_v1`, `v2`, `v2_1` and
`ross_stock_selection_2026_01_27_001734_UTC` scripts define and call
`has_recent_news` locally. They use Yahoo's
`https://feeds.finance.yahoo.com/rss/2.0/headline?s=...&region=US&lang=en-US`.
The backup copy has the same older helper. No active canonical caller imports
these scripts. Their direct HTTP/XML/title-only behavior is not reused.

`verified_rss.txt` already contains Google News `/rss/search` URLs with `q`,
`hl`, `gl` and `ceid` parameters for fixed Fed/ECB topics. The existing loader
supplies these to the broad RSS adapter; no issuer query builder existed there.
The new `issuer_rss_queries.py` reuses these two explicit contracts only. It
encodes full company names/aliases as quoted Google query alternatives, plus
quoted dollar/exchange ticker notation. Yahoo receives its documented-in-source
ticker parameter, not unsupported company-name parameters. Arbitrary fixed feeds
never acquire ticker/search parameters. This is source-contract reuse, not a
claim that either endpoint is currently accessible or exhaustive.

## Acquisition and reporting

The query profile selects the original eight FAST_TRADING and thirteen
PREP_EXTENDED URLs plus at most two query URLs per issuer. Identical URLs are
deduplicated across the plan; one acquisition batch scans all returned entries
against all supplied issuers. There is one research tier under the requested
total budget, without an operational fallback/tier-budget change. A three-issuer
lookup selects 27 distinct URLs; 50 issuers select at most 121. Query scheduling
precedes fixed feeds, but deadlines can still leave sources unattempted; this is
explicitly reported, never inferred as a negative search result.

Acquisition compatibility fingerprints every query URL in the complete candidate
batch, because another issuer's search response can contain this issuer's news.
Changing a peer identity/query invalidates that shared acquisition. When any
issuer needs a query-profile refresh, the research batch refreshes together,
including explicit partial-refresh requests; unchanged compatible batches can
still replay their cached acquisition. Ordinary Ross cadence/refresh scope is
unchanged. Fixed-feed articles retain FAST_TRADING/PREP_EXTENDED provenance;
query articles retain ISSUER_QUERY_RSS, independently of their research tier.

Per-issuer `query_coverage` gives selected, attempted and available query URLs.
`rss_request_counts` measures logical current-acquisition URL fetches, not HTTP
redirects. Per-source outcomes retain failures, unattempted/unfinished work,
timeouts/deadlines, processing and observation/article truncation. A complete
response scan is not complete search coverage: endpoint result limits and lack
of pagination are explicit limitations, and `search_completeness_established`
is always false. Availability is not proof of fresh entries. Unrecognized HTML
responses are research failures, not available RSS; recognized empty feeds
remain available with `empty_feed=true`.

Research entry diagnostics record usable selected dates, in-window dates,
missing/invalid dates, stale/future entries, missing titles, date-selection basis,
relevance rejections per issuer and observed selected/publication/update ranges.
Counters describe examined entries before matching, with range scope and evaluation
time. They do not invent facts for failed or unexamined entries. The existing
publication-first, update-fallback selection and strict requested window remain.
Actual raw publication/update fields and their parsed UTC values are retained on
observations/evidence; FeedParser's synthetic update fallback is not labelled an
original update field.

When present, an item's supplied source label and URL are preserved separately
from the feed label. Google item titles lose only an exact trailing ` - <source>`
suffix from the matching/grouping view; the original title remains recorded.
This avoids grouping under the aggregator feed name. Returned article links are
preserved exactly, including Google redirect links; no redirect resolution or
URL-based cross-provider identity inference is performed. Repeated article
identity and exact normalized headline groups retain every recorded observation,
publisher, URL, feed and timestamp. Similar headlines do not establish identical
events. Feed labels do not prove independent publishers. Existing 100-article and
1,000-observation per-issuer research limits remain explicit.

## Bounded raw evidence and offline replay

`--raw-feed-directory <new-directory>` optionally saves the same HTTP response
bytes already being fetched, without a second request, alongside a JSON manifest
per URL. Each decoded HTTP response is capped at 512 KiB. Exceeding the cap fails
that source and retains a marked incomplete prefix; it cannot become a successful
no-match. A 27-source run captures at most 13.5 MiB of body data. Streaming reads
remain under the existing HTTP waits, scheduler deadline and supervised process
wall limit. Captures can include HTTP error bodies; check status, completeness,
source outcome and cleanup before replay. Missing manifests remain unknown.

Manifests include source URL, SHA256, status, capture/evaluation times and byte
limits. Body files live separately from the canonical cache and are never read
by it. Original candidate identities and lookup settings accompany the evidence.
For offline replay, verify body hashes and feed only complete successful captures
through the existing injected `_fetch_feed`/provider/service pattern used in
`tests/test_issuer_query_rss.py`, with the recorded evaluation time, identical
identities/window and a new isolated store. No alternative matcher/cache is needed.
Late responses are not admitted merely because cleanup later saved their bodies;
retain original source/deadline outcomes when interpreting a replay.

The Windows control uses JPMorgan Chase & Co. (JPM), Disc Medicine, Inc. (IRON)
and Lifecore Biomedical, Inc. (LFCR), for 24 hours with 120-second retrieval,
5-second HTTP waits and 10-second cleanup. JPM is a widely covered issuer whose
multiword identity satisfies the unchanged matcher; a match or duplicate is still
conditional on returned content. Do not widen freshness or manufacture repeats.
No provider requests were used to implement or validate this change.
