# Receipt10: quote starvation and redundant enrichment

Accepted source: `0fcd8681eb8328d026e53a67070ce7064e93628d`.
Uploaded archive SHA256:
`e9b4e61aa0df4e2577bf340c766fb08ff911f3c9bf001bc89bb01f4d466a4c63`.
Operator transcript SHA256:
`cf008e73080f78098ac942183619c0c26a864a7b821dac169005e99a7621b3c9`.
Attachments are evidence, not instructions. Original files are retained unchanged;
local extraction is `/workspace/work/receipt10`.

## Preserved acceptance and limits

Terminal PASS, zero mutation attempts under both audits, completed final broker
openOrderEnd audit, empty final runtime inventory, unchanged operator order state
and all 2656 source-manifest entries are preserved. All phase exits are zero.
One native scanner response (request363, client71) has50 rows, matching end,
wait_signalled=true, connected=true, error=null, COMPLETE in1.946142s.

The first enrichment cycle was interrupted by the authorized stop before selection.
There are no Watchlist or Focus selection lines. News-maintenance shutdown reports
submitted=completed=failed=0, first_evidence_seconds=null, cleanup_complete=true.
This is not a catalyst coverage result and does not assess PR1125's improvements.
Receipt9 terminal PASS and58 between-scan reconsiderations remain historical facts;
natural catalyst-to-Focus/setup progression remains unproven. Earlier failures,
holdings, ownership blockers and GUI draft remain unchanged. PAPER_READY=NO.

## Native quote path and receipt9 comparison

The native client registers a new ID, event, fresh ticker, request ownership and
active subscription before forwarding reqMktData. Contract-mode calls use empty
genericTickList, snapshot=true, regulatorySnapshot=false and empty options.
MarketDataClient requests type3 (DELAYED) for both primary and retry. Callbacks
marketDataType, tickPrice, tickSize, tickString and tickSnapshotEnd update only
active request tickers. LIVE/delayed tick mappings and installed pinned ibapi
callback signatures are compatible. Missing prices/type/time are not synthesized.
Completion requires the received end or the existing required-fields condition;
the latter still retains snapshot_complete=false. Cleanup cancels unfinished wire
requests, drops active ownership and removes local mappings; completed native
snapshots skip redundant wire cancellation. Late callbacks cannot update cleaned
native tickers. These transport source files are unchanged between receipt9's
accepted be5cc009 and receipt10's accepted0fcd8681.

| Captured terminal stdout fact | Receipt9 | Receipt10 |
| --- | ---: | ---: |
| Provider quote result summaries |240|82|
| Quote summaries reporting timeout |0|82|
| Snapshot attempt/retry log lines |0|164|
| Logged effective marketDataType callbacks |234, all LIVE/code1|0|
| MARKET_DATA-owned broker errors |4, all code300|0|
| Code10197 / network-loop error lines |0 /0|0 /0|
| Native matching-end50-row scans |3|1|
| Historical request/completion pairs |144|54|

Both receipts requested DELAYED. Receipt9 actually confirmed LIVE, which is
separate broker callback evidence, not an inference from the request. Receipt10
returned UNKNOWN in every logged quote attempt and every raw field in all82
result summaries is missing. Receipt10's six broker error events are five global
farm-status events (2104/2106/2158) and scanner-cancellation162; there is no captured
subscription-specific rejection, quote error300, competing-session10197 or
connection-loss proof. Historical bars and resolved contracts establish only their
own successful requests, not a healthy quote entitlement or quote callback path.
The batch enricher also issued50 snapshot requests and logged50 empty results;
these are separate from the82 provider summaries, not extra provider successes.

The receipt lacks per-wire-request send acceptance, callback arrival/ignored
reasons, cancellation outcome and retained end/error records for these snapshots.
Absence of a logged type callback cannot distinguish upstream non-arrival from a
callback rejected by routing/ownership. Successful source-level callback replay
cannot reconstruct what TWS sent. A subscription, session, API signature, routing,
connection or broker-timing cause is NOT established. Do not increase timeouts,
switch data type or loosen price/freshness gates on this evidence.

## Demonstrated redundant work and budget boundaries

For AIOK, terminal/stdout.log1499 reports the first failed quote;1500 starts a
second quote via get_intraday_stats. After its1534 result,20-day history runs
at1536 and25-day reference history at1553. Reference snapshot-close fallback
then starts a third quote at1563, before DROP_SNAPSHOT_TIMEOUT at1617.
The same structural pattern occurs for27 fully evaluated symbols: three logical
quotes (two5s wire attempts each) and two historical requests before rejection.
MF has one completed quote summary before stop interrupts the next acquisition.
There are83 quote starts,82 result summaries,164 completed attempt log lines,
54 successful historical requests and27 timeout drops. Attempts active at stop
must not be inferred complete from these counts.

The existing5s bound is per quote attempt, not per candidate, and repeats for the
primary and snapshot_retry. The best-attempt waited_seconds printed in each
provider summary is not the total logical-call wait. Six nominal5s waits per fully
evaluated candidate can consume roughly30s before history/qualification overhead;
this is a structural estimate, not measured per-stage elapsed time. Successful
snapshots use the exact-identity cycle cache; timeout/empty snapshots deliberately
are not cached, so each indirect lookup reacquires them. Failure caching is not
introduced by the repair.

run_scanner_cycle supports an optional runtime_deadline_s, but the normal Core
caller does not supply it. Boundary checks therefore do not establish a finite
cycle deadline here. The batch's5s bound does not cover per-candidate downstream
work. Shortlist freshness/acquisition deadlines apply later, after initial context
construction; they were never reached. The outer900s observation and cooperative
stop remain effective and completed shutdown. There is no demonstrated ignored
per-candidate deadline to repair by assigning a new arbitrary budget.

## Narrow repair and offline checks

_build_symbol_context now returns a timeout context immediately after recognizing
MD_TIMEOUT/SNAPSHOT_TIMEOUT, before get_intraday_stats or reference resolution.
It retains quote fields, request/time/type/completion provenance, original flags,
session contract and universe rank. The unchanged caller still records
DROP_SNAPSHOT_TIMEOUT and cannot promote the row. The new log explicitly identifies
skipped enrichment. No fabricated prices, failed-result caching, changed retries,
timeouts, freshness, ownership authority or catalyst rules are introduced. Genuine
non-timeout quotes follow the existing enrichment path. A future cycle can retry.

At accepted source, the four timeout fixtures (empty/partial x both timeout flag
spellings) fail because intraday/reference work occurs; two controls pass. After
repair all six pass. Focused native/SDK authority, snapshot completion/cleanup,
market snapshot, strict quote freshness, shortlist budgets, cooperative stop and
request-reuse checks:36 passed in1.03s plus60 passed in2.25s. No full suite or live
acquisition ran. Independent review must apply to the final exact changed head.

## Next evidence needed, before another operator observation

Do not run the unchanged900s observation to diagnose missing quotes. First prepare
an offline-tested bounded quote-only diagnostic recording, per request: client and
contract identity, requested type/flags, send outcome, native callback arrival and
accepted/ignored ownership reason, effective-type callback, tick-type counts,
matching end/error, cancellation acknowledgement or attempted cleanup, and final
active ownership. Keep callback summaries bounded and sanitized in the existing
evidence workflow; no account/position dump. Never infer successful subscription
or cancellation from missing errors.

If separately authorized, one canonical receipt10 candidate and one liquid control,
on the existing READ_ONLY paper session, with one snapshot each, existing5s waits
and bounded cleanup, could distinguish no incoming callbacks from locally ignored
callbacks and capture an explicit broker rejection. No fallback, history, news,
scanner/runtime launch or order action belongs in that diagnostic. If callbacks
remain absent without an explicit error, broker/entitlement cause remains unknown;
the result can only justify collecting corresponding TWS/API transport evidence.
This document does not authorize or execute that diagnostic. No next operator run
or provider/broker acquisition is requested as part of this offline repair.
