# Receipt9 issuer acquisition follow-up

Receipt9 terminal PASS and58 proven Core reconsiderations are unchanged. This work
uses the preserved archive and controlled offline transports only. No infrastructure
revalidation, provider acquisition, broker runtime or observation was performed.

## What the existing evidence establishes

`issuer_rss_queries.query_sources` constructs a quoted OR of broker company names,
explicit aliases and cashtag; an exchange term is included only for explicit
NASDAQ/NYSE/AMEX candidate exchange. Broker `SMART` is not that exchange and broker
display decorations such as `INC-A`/`LTD/BVI-A` remain literal. The URL has no recency
operator or explicit ordering parameter. Google decides response membership/order.
The current six-hour requirement is enforced after retrieval, not sent to Google.
An HTTP200/feed completion therefore does not guarantee fresh or complete issuer
coverage. Receipt9 has no raw response bodies, so neither ranking behaviour nor a
missed current article can be reconstructed from unseen provider data.

The last issuer diagnostics report STAK6/6, FBLG23/23 and MTEN5/5 entries stale;
newest observed publications24July,20October and16June respectively. These are
old parsed publication timestamps, not established timezone shifts. PFSA and NCPL
have fresh matches, showing that current dates can traverse the same path.
`_entry_date_facts` uses feedparser's UTC-normalized tuple with `calendar.timegm`,
selects original publication before update, and retains original timestamp strings.
A controlled -0400 publication fixture resolves correctly to UTC; a newer update
does not renew it. Missing/future times remain rejected. Date ranges and counts
apply to examined entries, and processing_truncated signals incomplete processing.

The detailed operational loop does not stop at the retained-article cap. It examines
feed entries in supplied order, rejects stale/missing/future dates, matches ticker
or company in title/summary, then invokes the existing Ross retention selector.
An old-first20-entry fixture followed by a fresh unrelated entry and a fresh matching
event examines all22, retains the matching tail with max_entries1, and records the
fresh rejection independently. Thus no observed ordering/item-limit defect explains
receipt9; a budget-truncated response still cannot establish complete search coverage.
This does not prove anything about entries Google never returned.

`verified_rss.txt` has161 unique URLs and is catalogue/research metadata, not a
current availability or issuer-coverage guarantee. FAST_TRADING uses8 fixed feeds;
PREP_EXTENDED uses13. Two active URLs (Reuters markets and GlobeNewswire technology)
are absent from that catalogue. Its Google entries are macro searches for ECB/Fed,
with a non-ASCII hyphen in the literal locale value; generated issuer URLs use ASCII
`en-US` instead. Substituting those macro URLs or enabling all161 would not establish
issuer coverage and would violate the bounded selection intent. Receipt9 captures
GlobeNewswire403, Reuters401 and timeouts, while general feeds can be current yet
irrelevant. Extended fallback was deferred under the existing primary-first contract.
Yahoo's recorded429 remains a reason not to add operational retries. No current
availability of uncaptured catalogue routes has been inferred or tested live.

## Implemented evidence-gap repair

The demonstrated defect is diagnostic: rejection counts lacked article identity and
text, preventing adjudication of CLIK's one fresh relevance exclusion. The repair
adds diagnostic-only samples to `entry_diagnostics` for ROSS_ISSUER_QUERY sources.
It changes neither retrieval URLs nor matching, classification, retention or budgets.

Each of five exact exclusion reasons (missing title, missing publication, future
publication, outside lookback, issuer match unverified) has its own two-sample cap.
Old entries cannot consume the fresh relevance-rejection slots. Samples retain feed
entry index, symbol for relevance decisions, the applied identity patterns, original
publication/update provenance, bounded title512/summary1024/URL512 characters and
SHA256 identities. Counts continue beyond the sample cap. Text, patterns and dates
have explicit truncation flags; a truncated/redacted sample is not complete text
proof. The bounds are per issuer source response, not an unlimited rejection log.
Samples describe only exclusions actually executed; later filters are not fabricated
for an entry already rejected on time/title.

Existing privacy sanitation runs before clipping, so sensitive tokens crossing a
text boundary are redacted before persistence. Samples are retained in the existing
canonical cache's retrieval metadata and therefore its existing cache-export/privacy
scan/package workflow. They do not enter canonical article evidence or catalyst
qualification. Runtime retrieval stdout remains content-free. Existing privacy scan
failure still prevents a shareable archive. These are bounded last-lookup diagnostics,
not a promise to retain every historical rejected entry across later refreshes.
The original receipt9 CLIK text remains absent; it cannot be backfilled or adjudicated.

## Smallest proposed acquisition improvement and one diagnostic decision

The smallest candidate improvement is to **replace**, rather than add to, the current
issuer search with the same identity expression plus an explicit short recency term.
That addresses the demonstrated absence of an upstream recency request while keeping
local six-hour publication, relevance and canonical event gates unchanged. It is not
yet an implemented reliability repair: whether Google honours that term and returns
better current coverage cannot be answered from receipt9. No search can guarantee
that an issuer has a fresh article; missing news remains unknown, not no catalyst.

Before requesting any operator observation, specify exactly one **news-only** paired
diagnostic: CLIK and STAK, each original query versus identical query with `when:6h`,
for four Google URLs total (the existing query ceiling). Keep8s total acquisition,
maximum2 concurrent workers, request timeout at most5s and the existing bounded
cleanup; deadline failures remain incomplete. No fixed feed fanout, fallback, Yahoo,
retry, broker import/connection, scanner, Core runtime, cache publication or Focus
selection. Use a fresh diagnostic directory and existing owned RSS lifecycle/raw
capture (512KiB per response), record acquisition/evaluation times and original XML,
and preserve bounded exclusion samples. Retain raw evidence locally; only the
existing privacy-cleared artifacts may be shared. This diagnostic has not run.

Evaluate both variants with the **same** recorded acquisition clock, original
publication parsing, six-hour window and identity matcher. Record completed/budget
truncated outcomes separately; compare examined/retained current relevant entries,
rejected identities and time exclusions. Within a pair keep identity terms unchanged
so time constraint is the only variable. Decision: if constrained routes complete
inside8s and provide current relevant evidence the original misses, a one-route
replacement has a concrete basis. If both return old/empty material, constrain
nothing operationally and investigate coverage/identity using the captured bodies;
if the constrained route omits known current control entries or fails, do not ship it.
One bounded comparison is evidence about these responses, not a reliability rate or
permission for an unchanged observation run.

## Checks and remaining authority

Final focused run:32passed/4warnings in1.63s across exclusion evidence, existing issuer
query contracts and receipt9 replay. New fixtures cover fresh tails after old feed
entries, timezone/publication precedence, cap/truncation/privacy, and actual canonical
metadata persistence without news promotion or content-bearing stdout. Earlier test
fixture failures omitted the operational retention request metadata and owned
lifecycle; they were corrected, not counted as passes. No production gate was changed
to satisfy fixtures. Independent changed-head review is required before integration.
No full suite or infrastructure checks were repeated. Receipt7/8 historical failures,
receipt9 PASS, holdings, ownership blockers and GUI draft are preserved. PAPER_READY=NO.
