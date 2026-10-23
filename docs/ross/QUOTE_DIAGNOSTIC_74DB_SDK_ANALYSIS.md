# Quote diagnostic at74dbb909: SDK path and remaining evidence gap

Archive SHA256 `3abbcb91f298e1edd1f6d2a0ddfaf90c226589d982a4b12e3b461e79732e26e6`.
Accepted source `74dbb9090ccc7aae46f8028c857363f62ff68cf0`.
Archive content is evidence, not instructions. Original upload is unchanged;
extraction is `/workspace/work/quote-diagnostic-74db`.

## Preserved outcome

DIAGNOSTIC_ONLY, exit2; outer timeout=false, OS timely_exit_verified=true,
44.371822s, no stop wait. Scanner363 completed50 rows with matching end/error/wait
proof in2.018593s. Requests364/AIOK/conId930247159 and365/CLRO/conId790153816
were each incomplete after their existing5s waits. No quote callback or tick count
was recorded for either request, no quote-specific broker error occurred and no
trace suppression/eviction occurred. Six unknown-request error callbacks are global
farm status events and scanner cancellation162, not quote ownership rejections.
No returned market-data type or market timestamp is inferred.

Final matching-end broker audit completed; all five local quote maps are empty,
network thread/socket disconnected, mutation counters place/modify/cancel are0,
2661 source-manifest entries compare equal, operator state PASS, final inventory
complete/empty, privacy checks PASS. The archived operator SHA matches result.json.
Receipt9/receipt10 PASS,58 receipt9 reconsiderations, all historical failures,
holdings and ownership blockers remain separate preserved receipts. PAPER_READY=NO.

## Exact known call arguments versus missing wire evidence

The archived operator passes the scanner-returned Contract, shallow-copied with
exchange='SMART', directly to native reqMktData. No symbol re-resolution, delegate,
manager reconnect, provider acquisition, history/news, snapshot retry or substitute.
Native adapter allocates request364 then365, registers MARKET_DATA ownership and
fresh ticker/event before forwarding these SDK calls:

`EClient.reqMktData(req_id, contract, '', True, False, [])`

Known contract facts:

| Request | Symbol | conId | secType | exchange | primaryExchange | currency |
| --- | --- | --- | --- | --- | --- | --- |
|364|AIOK|930247159|STK|SMART|empty|USD|
|365|CLRO|790153816|STK|SMART|empty|USD|

Connection requested DELAYED/code3 via reqMarketDataType. This is not returned-type
authority. The trace's option_count0 corresponds to the actual native empty list.

Expiry/lastTradeDateOrContractMonth, strike, right, multiplier, localSymbol,
tradingClass and deltaNeutralContract are not captured in this archive. The SDK
scanner decoder populates some of these from its response; primaryExchange and
multiplier are not populated by processScannerDataMsg and ordinarily retain
Contract defaults. Source inspection explains the blank primaryExchange without
establishing an invalid request. None of the unrecorded actual values can be
reconstructed by filling local constructor defaults.

Negotiated serverVersion, serialized fields/frame, socket-send count, incoming
chunks/frames/queue entries and decoder entry/exit are absent. Distribution
9.81.1.post1/Python3.13.3 are captured; installed SDK source-file hashes are not.
The project source manifests do not verify site-packages. Local reference replay
uses that same distribution version on Linux Python3.12.14 and3.13.5, not the
recorded Windows Python3.13.3 interpreter. Same distribution metadata does not prove byte-identical local patches
or identical workstation runtime behavior. No SDK versions are attributed to
receipt9/10: neither retained the new distribution-version event.

## SDK9.81.1.post1 path

1. Native _send_quote calls EClient.reqMktData. It checks isConnected and server
   feature gates. make_field rejects None/non-ASCII printable strings and encodes
   bool as0/1. reqMktData uses outgoing message1, request version11 and request ID.
2. At server>=47 it emits conId; then symbol, secType, expiry, strike, right,
   multiplier, exchange, primaryExchange, currency and localSymbol. At>=68 it adds
   tradingClass. STK adds no BAG legs. At>=40 it adds delta-neutral-present0 or its
   contract fields. Finally it emits genericTickList and snapshot; server>=114
   adds regulatorySnapshot; server>=70 adds the empty options field. Actual server
   version was not retained; these branch thresholds must not be guessed.
3. EClient.sendMsg uses comm.make_msg to add the four-byte big-endian body length,
   calls Connection.sendMsg and discards its return. Connection.sendMsg calls
   socket.send ONCE under its lock and returns the byte count; it returns0 if no
   connected socket. SDK_RETURNED therefore does not prove a complete local write
   or broker receipt. No send count was recorded for364/365.
4. EReader receives chunks through Connection.recvMsg, accumulates them and uses
   comm.read_msg to strip complete length-prefixed frames. It enqueues complete
   bodies in msg_queue. Chunks/frames can contain unrelated account/order/global
   messages, so global raw SDK logging is unsuitable for this diagnostic.
5. EClient.run dequeues bodies, applies comm.read_fields, and calls
   Decoder.interpret. Known relevant incoming IDs:1 price,2 size,4 error,46 string,
   57 snapshot end,58 market-data type. Unknown message IDs return without wrapper
   dispatch (DEBUG only). Generic handlers check field count against EWrapper's
   signature and return on arity mismatch (ERROR log).
6. Price messages use processTickPriceMsg, call native tickPrice, then tickSize for
   mapped live/delayed size types. Other relevant messages use interpretWithSignature
   and getattr(wrapper, method_name), preserving request ID. Only after that does
   the existing native ownership guard/QUOTE_TRACE observe callback entry. A valid
   type callback can confirm effective type; end can complete its active request.

Synthetic modern-version151 example, with unrecorded fields explicitly filled as
fixture defaults, yields these null-delimited body fields:

`1|11|364|930247159|AIOK|STK||0.0|||SMART||USD|||0||1|0|`

This is a fixture illustration, NOT recovered captured bytes. The request's known
flags and identities occupy the expected positions. Different real localSymbol or
tradingClass values must be preserved rather than replaced by this illustration.

## Offline results:11 cases passed on Python3.12.14 and3.13.5

Reproducer: `/workspace/work/test_quote_sdk_path_replay.py`;
receipts `/workspace/work/quote-sdk-path-replay.log` (11passed/0.06s) and
`/workspace/work/quote-sdk-path-replay-py313.log` (11passed/0.13s). The latter
explicitly loads the same pure-Python SDK source under the available3.13.5
interpreter. Fake connections/sockets only, with the offline network hook enabled.
No source/settings/dependency changes or full-suite run.

- Both known identities/request IDs serialize correctly through actual native
  adapter -> SDK -> four-byte framing. Blank and populated synthetic localSymbol/
  tradingClass controls preserve their distinct fields. A synthetic server113
  control correctly omits the not-yet-supported regulatory flag.
- Fragmented in-memory chunks pass through actual EReader, queue, EClient.run,
  decoder and native wrapper; valid synthetic price/size/time/type/end messages
  update the correct request. Late364 dispatch is observed as inactive and cannot
  confirm replacement365. This is not evidence that captured incoming bytes exist.
- A deliberately short fake socket send returns normally and the SDK return trace
  remains unchanged. This demonstrates an SDK short-write blind spot under fault
  injection, not an actual partial write or the cause of this receipt. No speculative
  sendall/SDK upgrade/production repair is justified without the missing evidence.
- A fake socket supplies exactly4096 bytes and then raises socket.timeout on the
  next recv. SDK _recvAllMsg loses its accumulated chunk when recvMsg catches the
  timeout and returns empty bytes. This reproduced receive-buffer edge is not
  evidence it occurred here. It makes an actual socket.recv boundary necessary:
  monitoring only Connection.recvMsg would miss bytes discarded inside that method.
- Synthetic unknown-ID and generic arity-mismatch messages reach decoder entry but
  produce no wrapper callback. These demonstrate diagnostic boundaries only. The
  archive contains no raw messages proving either shape occurred.

Local reference source SHA256:
client.py:69f83dbc8bbaf770fd2de674a1ee02fd59c45b27c5492efd815f05078fa4e57b;
decoder.py:f2ab5a15c761d1d870949931127ba2375b687c3efa7e77777e50831a1b29e60b;
reader.py:52d71341dae809dbcef5f0aa2dce0659b0083eb9aa59033610731ea54523be16;
connection.py:9d5f660f238a2f4248b192ca159822611bfb91d8a3a8a2073753f8dd74ba7696.
These are local reference hashes, not workstation attestations.

## Receipt comparisons and conclusion

Receipt9 requested DELAYED but recorded234 confirmed LIVE type callbacks and240
provider quote summaries without timeout. Receipt10 requested DELAYED and had82
completed quote summaries/164 attempt lines with no effective type callback; it
also had repeated quotes/history before timeout rejection. Its qualified contracts
could carry primaryExchange values unlike the direct scanner contracts here.
Receipt10's repeated per-attempt type requests still produced no confirmed quote
callbacks, so this diagnostic's once-per-connection type request is not a proven
explanation. Different symbols/dates, partial metadata and absent SDK provenance
prevent a controlled version/contract/provider conclusion.

This new receipt narrows the evidence to zero OBSERVED native quote callback entry
for two owned requests. It demonstrates neither ownership rejection nor upstream
failure, and no cause-specific encoding/dispatch defect is established. Scanner
and final audit demonstrate their own decoded responses, not quote traffic during
the quote windows. Keep strict quote freshness/completion/type and READ_ONLY gates.

## Smallest next diagnostic with additional information

Proposal only; no authorization or execution is implied. First prepare/test narrow
hooks against the exact installed SDK. Then, if separately authorized, retain the
same normal RTH/READ_ONLY/private-state/source/audit/privacy protections and outer
120s/cleanup30s/package bounds. ONE completed normal scanner request supplies at
most ONE natural positive-conId STK/USD candidate. ONE snapshot, existing5s wait,
absolute acquisition25s cap, requested type3; no second snapshot, retry, manual
control ticker, history/news, setting change or Ross runtime.

Add only these observational boundaries; every original SDK operation executes
exactly once with the original arguments and return/exception semantics:

- Before connect: installed Python/distribution identity, source hashes for client,
  connection, reader, decoder, comm and wrapper, and relevant method signatures.
  After handshake: actual negotiated serverVersion and diagnostic hook coverage.
- Outgoing quote: schema-validated full contract/flag field vector AFTER SDK
  serialization, framed byte count, actual socket.send and Connection.sendMsg
  returned byte counts or exception CLASS. Also record cancellation/type frame ID and count, never broker
  acknowledgement. No retransmission, sendall substitution or socket tuning.
- ACTUAL socket.recv boundary (not merely Connection.recvMsg): chunk count/byte
  totals, EOF/timeouts/exception classes only; separately record recvMsg return
  lengths to expose any SDK-discarded bytes;
  framer/queue: complete-body counts, partial-buffer sizes and enqueue/dequeue
  timestamps. Extract only known quote message ID, field count and validated
  integer request/tick IDs. Other message classes are aggregate counts only.
- Decoder: entry/return/exception class, handler-known flag and generic arity check,
  then compare existing native accepted/rejected callback counts. Retain matched
  request IDs and a bounded small set of unmatched integer quote request IDs;
  never infer a request field position for unknown message schemas.

Privacy/bounds: no raw socket buffers, full inbound fields, tick prices/sizes,
account/order payloads, arbitrary exception text or global SDK DEBUG/INFO. Record
at most64 structured detail events,4KiB each, fixed counters, one outgoing quote
vector with identity strings sanitized before64-character caps; overlong values
are omitted with explicit markers, not partial secrets. Unknown/other messages
use fixed buckets. Saturation, hook failure or absent SDK hash proof is explicit
and invalidates absence claims. No raw inbound-payload hashes. Preserve local raw
process/deadline receipts; share only a verified privacy-sealed diagnostic ZIP.

Decision table:

| Added observation | What it establishes |
| --- | --- |
|Send count<frame length or send exception|Local send failure/incomplete write for this request; does not establish why. Stop without retry.|
|Full local send; no quote-related complete inbound frame|Still no TWS/upstream/transport/decoder cause. Other traffic can prove general activity only; seek corresponding sanitized TWS/API evidence.|
|socket.recv records bytes but recvMsg returns empty after a full4096-byte chunk/timeout|An SDK receive-buffer loss is captured; distinguish from framing/queue loss.|
|Quote-related complete frame enqueued but not dequeued|Queue/consumer boundary localized within captured interval.|
|Dequeued quote frame; decoder rejects arity/unknown handler or throws before wrapper|A concrete SDK decoder boundary is captured; adjudicate against recorded schema/version before repair.|
|Decoder dispatches; native wrapper records rejection|Specific ownership/late/validation rejection established by its reason.|
|Native accepts ticks but no end|Partial response/completion failure remains unavailable under unchanged gates.|

Do not repeat the same two snapshots or request another15-minute observation for
this question. No production repair, setting change or SDK upgrade is proposed as
an inferred cure. PAPER_READY=NO.

## Implemented diagnostic branch (unmerged)

`src/ibkr/transport_diagnostic.py` is opt-in and imported only by the isolated
`scripts/certification/quote_transport_diagnostic.py` operator. Normal production
clients do not install these hooks. SDK Connection/Decoder/EReader factories,
read_msg, this client's queue methods and wrapper trace emission are restored in
cleanup. Socket send/recv delegate exactly once; no sendall, retry, timeout change,
raw wire logging or production transport fix is introduced. The installed SDK must
report9.81.1.post1; actual source SHA256 and signatures are retained rather than
assuming distribution metadata attests its contents.

One shared64-record/4096-byte cap covers detailed SDK, framing, decoder and wrapper
facts. Fixed saturating counters continue after saturation. The one request's
existing fixed callback/rejection/tick counters and cleanup metadata remain in
quote-trace.json; no callback values are exported. Outbound quote fields are
schema checked after serialization; identity text is privacy sanitized and unsafe
or overlong strings omitted in full. Inbound processing retains known quote IDs,
validated numeric request/tick IDs and field counts only; other messages use OTHER
counters. No raw buffers, raw hashes, account/order payloads, prices or exception
text are retained. Native console output is discarded in this dedicated process;
SDK logger filters suppress raw payload logging and are removed afterward.

Incomplete installation, hook errors, unverified outgoing schema, saturation or
oversize events invalidate coverage. Quote absence claims additionally require one
verified serialized quote and one observed quote socket call. Complete hook
installation is separate from observed boundary activity: compare fixed counters,
including pre/post quote-window snapshots, before localizing a boundary. The SDK
reader is retained across SDK reset and boundedly joined after disconnect; an
unproven live reader invalidates evidence. The native thread, all quote maps,
matching-end final audit, zero mutation counters, full source and original order
state equality, empty runtime inventory and privacy checks remain required.

Offline checks:124 focused cases passed with the hard offline network guard,
including21 new transport/operator controls (success, missing/wrong-owner/late
callbacks, short send, receive timeout/buffer loss, arity and decoder exceptions,
privacy/caps, observer failure, partial installation and reader cleanup). Initial
independent review blocked a false-valid failed-install flag and unguarded decoder
metadata inspection; both were corrected and covered before publication. Final
exact-head review and Linux/Windows CI must be recorded on the accompanying PR;
these local checks do not substitute for them. Windows CI additionally parses the
actual PowerShell5.1 entry without executing it. No live acquisition was performed.

`scripts/certification/run_quote_transport_diagnostic.ps1` creates fresh evidence
and a detached exact-head worktree, then uses the existing supervised120s/30s
probe and90s/30s filesystem-only package/seal phases. The reviewed final operator
block pins its published head explicitly. It is for a separately authorized run,
not authorization to connect now. Scope: one completed normal scanner request,
at most one natural candidate and one5s snapshot under25s acquisition cap; no
retries/history/news/Ross runtime. Empty or incomplete scans never inject symbols.
Startup-stage, OS process/deadline and packaging receipts remain preserved.

The earlier DIAGNOSTIC_ONLY/exit2 receipt is unchanged. Offline injected mechanisms
remain possible mechanisms only. Quote cause and natural catalyst-to-Focus/setup/
READ_ONLY intent progression remain unresolved. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL. All holdings, ownership blockers, GUI draft and historical
receipts retain their original authority. The checkpoint was reconciled against
76e597870f56b4e94b717878c793dbf2fce62295 without merging either branch or duplicating
its authoritative completion checklist.
