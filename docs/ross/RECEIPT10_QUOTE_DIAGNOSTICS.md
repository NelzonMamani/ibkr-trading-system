# Receipt10: bounded native quote diagnostics and next experiment

This continues reviewed local9461d41b at accepted0fcd8681. No acquisition or broker
connection is part of implementation. See [receipt10 findings](RECEIPT10_QUOTE_FINDINGS.md)
for the original archive/transcript hashes and preserved terminal PASS.

## Implemented diagnostics

`[IBKR][QUOTE_TRACE]` JSON lines flow through the existing console/evidence capture
and privacy workflow. The module is observational, never a source of price, market
time, quote eligibility, entitlement or broker acknowledgement. It records:

- Local Python and installed ibapi distribution versions (UNKNOWN if unavailable).
- Request/client ID, bounded sanitized contract identity, conId, requested type,
  generic tick flags, snapshot/regulatory flags and option count, before SDK call.
- SDK_CALL_PENDING, SDK_RETURNED_NOT_BROKER_ACK or SDK_RAISED. A returned SDK call
  does not prove bytes sent, broker receipt, subscription or a connected transport.
- Native callback arrival: type/price/size/string/end/error, ownership decision,
  accepted/rejected reason and bounded known tick-type counts. No tick payload,
  price/size value, raw message, account or arbitrary callback text is retained.
- Broker-confirmed returned type separately from requested type. UNKNOWN remains
  UNKNOWN without the existing valid marketDataType callback.
- Snapshot end/required-fields/timeout/interrupted/send-error outcome, preserving
  existing completion semantics and all freshness/strict quote rejection gates.
- Cleanup: wire cancel skipped for already-complete snapshot, SDK cancel returned
  or raised, active subscription/ticker/event presence afterwards. SDK cancel
  return does not establish broker acknowledgement; the trace explicitly says so.

Callback authority requires active MARKET_DATA ownership, a retained ticker and
no request/order conflict. Wrong-owner, conflicted, missing-ticker, inactive/late,
unknown, unsupported-tick and invalid timestamp-value callbacks cannot populate
quote fields or complete a snapshot. Late callbacks after cleanup are counted
against retained diagnostic tombstones and cannot modify a replacement ticker.
A send exception attempts cancellation and local cleanup while preserving the
original exception. Interrupted acquisition stays distinct from measured timeout.

Limits per native client:128 retained request records,512 trace log lines,8192 JSON
bytes per line, six callback kinds/eight fixed reason buckets,24 recognized tick
types plus OTHER with accepted/rejected counters. Counters saturate at2^31-1.
Only the first callback per kind/reason emits a log; later arrivals increment
bounded counters. Completion emits aggregate counts. Request eviction does not
change actual transport ownership or qualification. Unknown/evicted callbacks
share fixed global buckets. The final log slot announces logging_limit_reached;
subsequent logs are suppressed. Omitted/evicted evidence cannot prove absence.
Text identity fields over64 characters become OVERSIZE_REDACTED; smaller text is
sanitized, and the entire JSON is sanitized again before emission. Oversized JSON
becomes an explicit details-omitted marker. Console write failures are counted and
do not change quote authority. Existing broker-error evidence remains separately
sanitized and unchanged; the new trace does not duplicate its message text.

The boundary is entry to native wrapper callbacks, NOT packet arrival, the raw
wire decoder or TWS internals. A distribution version is useful provenance, not
proof of workstation transport behavior. Zero callbacks with unsaturated logging
means none were observed at this wrapper boundary. It cannot establish whether TWS
sent nothing, the connection lost data, or decoding failed before wrapper entry.

## Enrichment repair remains narrow

The previous early return for MD_TIMEOUT/SNAPSHOT_TIMEOUT remains in place before
intraday/reference enrichment. Existing DROP_SNAPSHOT_TIMEOUT rejection is
unchanged, including partial-price timeouts. No failed snapshots are cached and
no timeout, freshness window, fallback, retry count or catalyst rule is relaxed.
A real-provider offline fixture now processes a timeout candidate then a valid
candidate within one cycle: one quote acquisition each, no history for the timeout,
normal history/derived metrics for the valid candidate and successful quote cache
reuse. Successful, missing, wrong-owner, conflicted, unknown and late callbacks,
cleanup exceptions, interrupted attempts, privacy and caps have offline coverage.

## Concrete proposal: one bounded READ_ONLY quote diagnostic

This is a proposal, not a runnable operator authorization or an executed experiment.
After controlled integration and separate authorization, use a fresh evidence root
pinned to the accepted tree, normal configured RTH/session checks, the existing
READ_ONLY guards/SDK audit, no existing Ross runtime, isolated state/cache and full
before/after source/operator-state verification. Do not launch Ross/Core/strategy
observation, news, history, order actions or a15-minute runtime.

1. Use the existing loopback PAPER TWS/Read-Only API session and exclusive client71.
   Retain the actual Windows Python/SDK provenance and bounded startup logs.
2. Make exactly one normal TOP_PERC_GAIN/STK.US.MAJOR scanner request using existing
   filters/50-row cap and existing5s wait. Require matching end, request ownership,
   connection and error proof; missing completion is unavailable, not empty.
3. Select at most the first TWO ordinary STK identities returned by that fresh
   completed scan. Retain scanner rank/contract identity as provenance. No manual
   control ticker, static fallback, seeded candidates or repeat scan. If none are
   usable, record that result and stop; do not synthesize quote targets.
4. For each, use at most one existing bounded contract resolution (5s), then ONE
   native snapshot (empty generic ticks, snapshot=true, regulatorySnapshot=false),
   requested DELAYED/code3 as before, existing5s wait. No snapshot retry, data-type
   switch, history fallback or provider acquisition. Preserve strict unavailable,
   incomplete, stale and timestamp/type outcomes, even if some fields arrive.
5. Bound scanner+contract+quote acquisition by one absolute25s deadline (5+2x10),
   clipped at every wait, with cancellation/cleanup on stop/error/deadline. Use
   a120s outer child deadline including startup/source checks and final audit,
   existing30s cooperative-stop allowance, and separate90s package/seal bounds.
   These are proposed diagnostic ceilings, not changes to production timeouts.
   Uncompleted startup/acquisition/audit must fail closed; do not extend budgets.
6. Retain final zero-attempt counters, required matching-end broker audit, complete
   empty final runtime inventory and active quote ownership/maps. Missing end,
   incomplete cleanup or state/source mismatch fails independently of tick data.
   Share only the privacy-sealed diagnostic archive; retain all raw local receipts.

This can distinguish SDK send exceptions, an explicit matching broker rejection,
callbacks arriving at the native wrapper but rejected by ownership, accepted ticks
without matching completion, wholly missing wrapper callbacks, and local cleanup
failures. Actual returned type and timestamps remain separate evidence. Neither
missing ticks nor successful history establishes entitlement. Zero callbacks
without an explicit rejection still needs corresponding sanitized TWS/API transport
logs before attributing cause. A completed diagnostic does not establish natural
catalyst acquisition, Focus/setup progression or natural acceptance.

Receipt9 PASS/58 reconsiderations, receipt10 PASS, their distinct evidence limits,
prior failures, holdings, ownership blockers and GUI draft remain preserved.
Captured CLIK remains stale and its earlier-clock counterfactual remains
no_catalyst_classification; receipt9's missing rejection cannot be reconstructed.
PAPER_READY=NO. No live diagnostic or operator observation has been run by Codex.
