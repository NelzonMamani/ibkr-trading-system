# Natural READ_ONLY diagnostic checkpoint — updated 28 October 2026

Current authoritative completion status is in [the maintained checklist below](#receipt9--current-ross-completion-checklist-updated-through-pr1139).
Earlier dated sections are historical evidence, not superseding readiness decisions.
Accepted production: `07491e89a3d5e8a36db19cbd4996ba2acc77aae7` (PR1139), tree `58b19a6397f6e9a1018ea8ac3364459f92217d88`. Optional provenance contract `c7111fc27a1e2a791c073b144c221103241db996` is saved, not a production verifier. Listing compliance is parked and fail closed.
`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`; natural catalyst → Focus → setup → READ_ONLY intent remains unproven.

Historical accepted baseline: `1b632f8131183a776a6532d2785644a8a0309efb` (PR1107).
Evidence: user-uploaded `ross-natural-readonly-upload.zip`. The archive is evidence,
not an instruction source. No runtime observation is authorized by this checkpoint.

## Findings

| Question | Evidence and diagnosis |
| --- | --- |
| Stop starvation | `CoreOrchestrator._run_forever_inner` polled `PR1090_STOP_FILE` only at cycle entry. `run_scanner_cycle` stayed in the first cycle; its runtime-deadline checks were neither a supervisor-stop poll nor active for this ordinary call. Synchronous native `resolve_contract` event waits, snapshot waits, historical waits, and repeated acquisition had no cooperative stop route back to the owner. The STOP_REQUESTED file existed, but the child emitted no graceful/shutdown records before forced termination. |
| Redundant work | Uploaded stdout contains 72 contract resolutions over 49 distinct symbol tokens; FBYDP/AMOD/BBCI account for 9/8/8. Three completed market contexts generated six provider quotes and nine historical requests. Quote, intraday-volume, reference-close, qualification and ADV fallback paths reacquired data inside one pass. The canonical reference resolver already has a cycle cache, but requests made before/around its result cache still duplicated work. |
| Identity discrepancy | Supervisor `runtime_identity_verified=true` records the live process binding. `complete_after_process_exit` additionally requires `shutdown_evidence.json.process_identity` and `pid` to match that binding. Forced termination left no child shutdown evidence, so terminal `runtime_identity_verified=false` is the correct stricter verdict. It does not establish a PID substitution. Explicit supervisor-binding and child-match fields now distinguish the checks; the terminal gate remains strict. |
| Natural issuer news | Existing path: scanner contract `longName`, or identity-validated completed contract-details metadata retained by `IbkrScannerProvider.get_quote` → `last_scan_details.symbol_details` → `_build_symbol_context.long_name` → `_news_symbol_metadata_for_contexts` → `_news_candidates_for_symbols.company_name` → canonical news acquisition. Existing synthetic managed-adapter-to-RSS regressions verify both named issuers and empty-evidence rejection. No propagation defect demonstrated. Uploaded SPY/QQQ retrieval is separate preparation work; it has no issuer names and does not prove natural candidate acquisition. |
| Position truth | The log states `positions_unavailable`, followed by a manual-required recovery reason: “Position query evidence is unavailable; reconciliation remains blocked.” Position truth requests `get_ibkr_client(ensure_connected=False)` before the later market-data connection. An unavailable/disconnected position snapshot is unknown, not proof of zero positions. This creates the critical availability blocker even with zero displayed rows/mismatches. It did not prevent scanner enrichment. Keep the fail-closed entry block; do not infer a quantity mismatch or blame it for scanner delay. |
| 180 seconds | Fifty broker rows arrived, but only three market contexts completed. Quote callbacks extend through 17:28:11 UTC, after the 17:27 stop file. A 180-second observation does not establish full first-pass latency or natural catalyst acceptance. Repeated requests establish implementation overhead; continued acquisition after stop establishes a separate shutdown defect. Observation/grace periods are unchanged. |
| Terminal safety | Final inventory reports no runtime; independent final broker audit reports zero open orders. Neither supplies the missing child mutation-attempt counters or missing shutdown hooks. Uploaded terminal certification correctly remains failed. |

## Repairs and boundaries

- Acquisition scopes carry the owning orchestrator's stop poll, with pass-local
  data reuse and guaranteed scope release. `AcquisitionCancelled` is control flow
  outside ordinary provider `Exception` fallbacks, so stop cannot become a missing
  quote, fallback request, or partial selected watchlist.
- Native event waits poll every 100ms, history loops poll each iteration, and quote
  loops poll before their existing 200ms waits. Scanner/history market requests
  cancel in cleanup. Async qualification/history drain cancelled tasks; owned
  ib_insync historical requests also cancel their broker request and clear their
  wrapper future/container. No order cancellation is added.
- Float HTTP fallback/retry boundaries poll before/after acquisitions. An in-flight
  synchronous HTTP call keeps its existing timeout; no subsequent fallback starts
  after stop. News retains its existing total budget with checks at entry/return.
  This bounds acquisition response by the current blocking operation, not by the
  sum over the remaining universe. It is not a hard wall-clock guarantee for OS
  DNS, filesystem stalls, or arbitrary third-party hooks.
- Cancellation exits the acquisition scope before the established graceful
  shutdown transaction. Every existing hook and mutation-audit flush remains
  required. Idle/backoff waits also poll stop; PANIC semantics remain unchanged.
- Successful qualification, snapshots (with all authority/diagnostics), and exact
  daily-history results are reused only within a pass. Full security/routing
  identity, data type, duration, RTH and end time remain key dimensions. Empty or
  failed acquisitions retain retry opportunities. Different 20-day and 25-day
  histories are not substituted. Existing canonical reference-cache authority and
  ADV/reference computations remain intact. Intraday volume reuses the quote.
- No Ross thresholds, ranks, news requirements, attribution, float/RVOL gates,
  universe size, focus size, READ_ONLY protections or readiness statuses change.

## Verification and status

Regression coverage includes stop during native qualification/history/scanner/quote
waits, interruption inside symbol enrichment, bounded owner-loop return, all
shutdown hooks plus durable mutation evidence, asynchronous task/wire cleanup,
float fallback interruption, request counts, cache reset/identity/parameter
isolation, retry after empty history and strict missing-child terminal identity.
Existing issuer propagation and Ross safety regressions remain required.

The initial full pytest invocation exposed pre-existing background float HTTP
attempts and was stopped. These were test workers, not a new trading-runtime run.
Subsequent full CI uses `tests/offline/sitecustomize.py` to reject socket connection,
DNS and datagram-send acquisition, inherited by Python subprocesses. GitHub pytest
uses the same guard. No provider result from that stopped invocation is acceptance
evidence. The first targeted repair set passed 187 tests; final changed-head CI and
independent-review results are recorded in the accompanying diagnostic receipt.

`PAPER_READY=NO`. Natural issuer-query acceptance remains unproven. No trading,
forced selection, runtime rerun, readiness upgrade or merge is part of diagnosis.

Windows offline verification (from a clean checkout of the repaired head, using
the existing certification interpreter): run
`scripts/certification/verify_natural_readonly_offline.ps1 -ExpectedCommit <head>`.
It verifies the revision and clean source, activates the same offline guard and
runs the repository's complete required pytest job. It does not start `src.main`
or a supervisor/broker audit. A future natural observation requires separate user
authorization and must retain the established stop, hooks, mutation and identity
gates; extending its duration cannot repair failed shutdown.

## Authorized publication and PR verification

The user explicitly authorized publishing repair commit
`664163ca87234959729b99075a21b86a2962a0ea` on
`codex/natural-readonly-enrichment-stop`. It was pushed without force to the
existing repository; main remains the accepted baseline.

PR: https://github.com/NelzonMamani/ibkr-trading-system/pull/1108 (draft, against main).

Completed **local** changed-head pytest at that repair commit: **2725 passed,
1 skipped, 212 warnings**, 187.39 seconds, with the hard offline guard loaded.
Independent exact-head PR review found no remaining actionable correctness blocker;
its separate focused offline run passed **60 tests** in 2.78 seconds. These local
results must not be presented as GitHub Actions results or human approval.

The required **remote** workflow is `pytest`, job `test`. The first PR run is
https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/38801073410.
Every follow-up head, including this checkpoint-only change, requires its own
successful PR check and independent exact-head review. Final head-specific remote
results and the independent review receipt belong in the PR checks/review and PR
verification summary; a successful older run cannot certify a newer commit.

### Preparing the unchanged Windows PyCharm checkout

Do not run a new relative script from the old checkout. In the existing PyCharm
repository's PowerShell terminal, fetch only the repair branch from the explicit
repository URL, verify FETCH_HEAD equals the final reviewed SHA, then create a
unique detached worktree under TEMP at that SHA. Never switch/reset the original
checkout, force a ref, or write main. Check that the existing certification
interpreter `C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe` exists before
preparation; fail if it is missing rather than choosing a different interpreter.

Invoke `powershell.exe -NoProfile -ExecutionPolicy Bypass -File` on the absolute
path of `scripts\certification\verify_natural_readonly_offline.ps1` **inside that
new worktree**, with `-ExpectedCommit` pinned to the reviewed SHA and `-Python`
set to the checked interpreter. Check each native exit code. Retain the detached
worktree for inspection. The final delivery supplies one complete copy-paste
PowerShell command implementing this preparation and verification.

Only Git fetch uses the network in this command. The verifier checks the clean
pinned checkout, loads the offline guard, and runs pytest; it never invokes
`src.main`, the observation supervisor, an IBKR audit, or trading. A passing test
suite does not establish natural issuer acquisition or upgrade readiness.

## Windows offline harness compatibility repair

The uploaded Windows Python **3.13.3** run at
`f0aea1f8823ae05964a793a54e9c25b2d35785a1` failed collection in
`test_execution_mode_engine.py` and `test_pr1091_console_reporting.py`.
`src.main` imports create the default ProactorEventLoop; its self-pipe calls
CPython's TCP `_fallback_socketpair`, whose internal `csock.connect` the offline
hook rejected. That run failed; zero executed tests does not certify the suite.

The harness now recognizes only the cached original stdlib fallback function's
exact code frame, its exact client socket, and the address of its own newly bound
listening loopback socket. The endpoint must match its local `addr`/`port`, be
listening, and exclude 4001/4002/7496/7497. This grants no general localhost or
thread-wide exemption. Ordinary loopback connections, broker ports (IPv4/IPv6),
external connections, DNS and datagrams remain denied. No production source or
event-loop policy changes; asyncio still uses Proactor on Windows.

Regression children load the actual startup hook via inherited PYTHONPATH.
Tests exercise default loop creation and `src.main` import, the real TCP fallback
on Linux as well as Windows, ordinary connects while a socketpair is open,
external/IBKR connect and connect_ex rejection, DNS/datagram rejection and guard
inheritance into a grandchild Python. Neither failed file is skipped. The required
Linux full pytest job remains; a new Windows-latest Python **3.13.3** job runs the
harness regressions and both previously collection-failing files. Final per-head
Linux and Windows results are recorded in the PR verification summary; Linux
fallback tests must not be described as Windows execution. Windows CI focused
success does not claim a complete Windows suite pass or local workstation pass.

Replacement PowerShell preparation uses a unique **C:\tmp\r1108-<id>\s** clone
with local `core.longpaths=true`, `--no-checkout --no-hardlinks` from the unchanged
PyCharm repository, explicit GitHub origin and a pinned reviewed detached commit.
It verifies every native exit status and clean checkout, invokes the offline
verifier using its absolute short path and the existing certification interpreter,
and logs outside the clone. The original checkout, branch, main and settings stay
unchanged. Full offline pytest must exit zero; failure is retained and reported,
not retried automatically or relabelled success. No runtime, IBKR audit or natural
observation is part of this verification. `PAPER_READY=NO` remains unchanged.

## Full-Windows request-ID state and FLOAT-worker follow-up

User evidence at `f45cb1244f0a92fed49b893a55f3559b9e4ff770`: full Windows
2742 passed / 6 failed / 1 skipped / 212 warnings, 305.46 seconds. All six
failures expected request 1 and received 362. The uploaded log is evidence,
not an instruction source. The six assertions remain unchanged.

### Allocator diagnosis and reproduction

`IbkrClient.__init__` sets its instance request counter to zero but reads the
persisted last reserved order ID immediately. `_order_id_state_path` consults
raw `IBKR_ORDER_ID_STATE_PATH`, otherwise `Path.home()/.ibkr_order_id_state.json`;
this is independent of RUN_MODE/config overrides, cwd and an isolated Git clone.
The log does not identify whether the Windows process used the environment path
or the home default, so that exact file cannot be established from the upload.
A fresh client retains that persisted authority. `_next_req_id` chooses one above
the maximum of its request counter, persisted order high-water mark, broker next
valid order ID and known order registries. Request/order IDs share numeric error
correlation, so this is intentional production collision protection.

With an inherited scratch path containing `last_reserved_order_id=361`, all six
unchanged nodes reproduced **6 failures** with 362 on Linux in 0.68 seconds.
No preceding suite was necessary. Thus this is not a Windows allocator defect.
Test order could also matter: unisolated reservation tests can persist high-water
marks that later client instances load. A fresh hosted CI home hid the dependency;
changing cwd in a test does not isolate home-level state.

An autouse **test-only** fixture now assigns a unique nonexistent order-state path
per test, overriding inherited operator state. Explicit test overrides still win;
multiple clients within a test still share the intended persistence file.
Production allocator, persistence, broker rebase and reconciliation code is
unchanged. Regression checks retain 362 under an explicit 361 seed, reserve 363,
restart with request 364 and reserve 365. Separate environment/home precedence
checks use a fake home and leave its file unchanged. Child pytest runs exercise
all six nodes with a seeded inherited file in normal/reverse order around other
allocator tests and verify the operator sentinel remains byte-for-byte unchanged.

### FLOAT evidence, protection gap and cleanup

The upload reports MARA cache-write value 378492188 and CCC discovery/worker
success value 545450326. These are not the repository's float fixture value
123456. In `_discover_and_cache`, the worker directly invokes `provider_yahoo`
then `provider_finviz`; unlike `FloatProvider.get_float`, it does not first read
canonical JSON/SQLite caches. Successful discovery then persists JSON and SQLite,
explaining the writes to the clone's default data directory. The success lines
cannot be certified as fixture/cache-only activity from this log. No packet or
native-transfer trace was captured, so yfinance-internal cache reuse versus
native wire acquisition for those exact results cannot be distinguished.

A concrete protection gap was demonstrated by source inspection: yfinance's
`Ticker.info` uses curl_cffi, whose `Curl.perform` calls native
`lib.curl_easy_perform` and whose `AsyncCurl.add_handle` schedules native multi
transfers without Python socket audit events. The previous socket-only guard
therefore did not prove offline provider isolation. No provider was rerun during
this diagnosis. The offline harness now rejects both native transfer entry points
before native invocation, while preserving the socket audit guard and narrow
Windows socketpair exception. Child/thread/grandchild regressions use inert
objects (no native handles or provider requests) to prove rejection.

There was also no worker stop API; scanner resets did not stop these daemon
threads. Tests now use private float JSON/SQLite paths and a private registry,
track **constructed workers** even if a test replaces that registry, and stop/join
all owned workers before provider monkeypatches are restored. Teardown fails for
a surviving thread. The worker's explicit shutdown cancels queued work, wakes idle
threads, rejects subsequent enqueue, checks stop before another provider and
before persistence, and reports a bounded join timeout truthfully. Fixture tests
prove cached reads without discovery, known synthetic background writes, teardown
after registry replacement, and interruption preventing fallback/late writes.
This adds owned-worker cleanup; it does not change the production allocator or
claim a new natural runtime shutdown observation.

### Changed-head verification plan and results

Focused local hard-offline checks: **108 passed** in 6.92 seconds under the inherited
361 environment. Independent focused checks: **46 passed** in 6.45 seconds.
No unchanged full local suite was repeated. Required remote CI now runs one full
Linux suite and one full Windows Python 3.13.3 suite; Windows first seeds inherited
operator state to 361. This includes the six formerly failing cases and catches
suite-order contamination. Final head-specific remote results and independent
review are recorded in PR #1108's verification summary and Checks.

The replacement short-path PowerShell preparation still clones into a unique
`C:\tmp\r1108-<id>\s`, pins the reviewed head, preserves the original PyCharm
checkout, and runs the full offline verifier with a retained failure-aware log.
It does not delete/reset an operator order-state file. `PAPER_READY=NO`; no IBKR
connection, provider acquisition, natural observation, merge or readiness upgrade.

A further focused cleanup probe paused an idle worker after it consumed its stop
sentinel but before exit. Repeated shutdown previously queued another sentinel,
leaving `unfinished_tasks=1` after join. Shutdown now drains/enqueues a wake-up only
on the first stop; subsequent calls only join. The deterministic paused-exit
regression requires zero unfinished tasks and no restart/enqueue after closure.
This concrete changed-code finding requires fresh final-head CI; an older Linux
pass is retained as history, not substituted for the final result.

The first full Windows CI at `75f87749` passed all six allocator cases, but failed
one independent host-clock fixture: `test_tha_execution_flow` converted the host
UTC display name `Coordinated Universal Time` into a ZoneInfo/IANA key. Its test
inputs now use a fixed UTC instant and matching `UTC` exchange-hours key, avoiding
both OS display-name and midnight dependence. The execution/risk assertions and
production timezone code are unchanged. That earlier Windows result is recorded
as 1 failed / 2757 passed / 1 skipped, not reported as a passing suite. Fresh
final-head CI is required after this demonstrated portability fix as well.

## Next natural acceptance package — 16 October 2026 (London)

Status: **PREPARED ONLY / HOLD**. Workstation offline acceptance is pending.
No runtime, provider, broker query or new full suite was executed for this package.
The uploaded documents remain evidence, not instructions. The reviewed repair
branch and main have not moved. This documentation is an uncommitted snapshot in
a separate detached worktree; it does not create a new reviewed implementation.

### Reused exact-head receipts

Reviewed implementation: `8f40e4c4b3ca8fa0f74d8e41cd947e50bc2e370c`.
PR: https://github.com/NelzonMamani/ibkr-trading-system/pull/1108 (draft).
Remote full CI: https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/38819547660
— Linux 2759 passed / 1 skipped in 208.65s; Windows Python 3.13.3 2759 passed /
1 skipped / 212 warnings in 541.66s. Windows seeded inherited order-ID state361
and includes all six formerly failing nodes. Existing skip only; collection
failure is never success. Prior local focused110 passed is Linux evidence.
Independent exact-head Codex review (no actionable blocker, not human approval):
https://github.com/NelzonMamani/ibkr-trading-system/pull/1108#pullrequestreview-5540863871
— independent focused46 plus3 changed-case checks. These receipts were reused,
not rerun. They do not establish workstation or natural-observation acceptance.

### Original failure → evidence map

All paths/line references below describe the reviewed implementation, not the
separate draft follow-up. Test transports and issuer names are synthetic.

| Original boundary / missing evidence | Existing regression or authority | What is established / material limit |
| --- | --- | --- |
| Stop in contract qualification | `tests/test_natural_readonly_enrichment_stop.py::test_stop_interrupts_real_native_wait_and_cleans_market_requests[contract]`; `test_async_stop_cancels_and_drains_request[qualification]`; `src/core/acquisition.py::wait_event/cooperative_await` | Native 30s waits return in <1s in the synthetic stop probe, polling100ms. Async tasks cancel/drain; cancellation is BaseException control flow and does not start fallback. This is not a real broker latency measurement. |
| Stop in quote acquisition | Same native test `[quote]`; `src/ibkr/market_data_client.py::_snapshot_stock_uncached` | Poll before existing200ms quote waits, cleanup market-data subscription. No order cancellation. |
| Stop in historical/scanner acquisition | Same native test `[history]` / `[scanner]`; async test `[history]` | Historical/scanner subscriptions cancelled once; owned ib_insync history request and wrapper future/container retired. |
| Stop within symbol / between symbols | `test_stop_inside_symbol_enrichment_is_not_converted_to_missing_quote`; `scanner_runner.py:5162` `_runtime_bound_reached` invokes checkpoint even without a deadline; per-symbol `gates` loop at5632 | A stop propagates out instead of becoming missing data/partial selection; next symbol checks stop. Dedicated between-symbol fake-loop timing node is absent, but checkpoint placement is direct and owner-scope exit is tested. No material demonstrated defect here. |
| Foreground float HTTP stop | `test_float_stop_does_not_start_next_http_fallback`; provider checkpoints before/after HTTP, `src/scanner/providers/ibkr_provider.py:490,551,591` | Does not start next fallback after stop; does not preempt an in-flight synchronous call. Existing request timeouts apply; do not promise hard DNS/OS bounds. |
| Background float discovery | `tests/test_offline_state_isolation.py::test_stop_during_fixture_lookup_prevents_fallback_and_late_write`, `test_repeated_shutdown_sends_only_one_wakeup`, owned-worker fixture in `tests/conftest.py` | Explicit worker.shutdown is bounded and prevents fallback/write after return. **Material runtime ownership gap:** scanner_reset does not call it at reviewed head; test-fixture cleanup is not proof of runtime cleanup. See separate follow-up. |
| News acquisition stop | `scanner_runner.py:3571` `_enrich_news_context` entry/return checkpoints; `tests/test_pr1072_bounded_news_retrieval.py::test_pr1072_source_timeouts_are_fairly_clamped_to_remaining_budget`; `tests/test_ross_operational_issuer_news.py::test_operational_deadline_late_worker_never_adds_evidence`, `test_actual_consumer_never_waits_for_cleanup` | News uses existing total budget8s by default and discards returned result when stop is seen. It is not polled inside every RSS request. Existing tests prove budget/no late evidence, not stop at every real RSS boundary. New synthetic return-after-stop probe passed at8f40; no provider run. |
| Required shutdown hooks | `test_interrupted_enrichment_runs_all_shutdown_hooks_and_durable_mutation_proof`; `tests/test_pr1090_p1_repairs.py::test_graceful_keeps_all_ordered_hooks_and_flush`, shutdown transaction injection/normal completion matrices | Ordered required hooks and durable evidence tested under interrupted owner loop. Hook success at runtime remains to be observed; fixture transport cannot prove every third-party hook is bounded. |
| Independent runtime mutation evidence | Same interrupted-enrichment test; `src/ibkr/mutation_audit.py::instrument_mutation/require_zero_attempts`; shutdown terminal failure tests | SDK attempt counts increment before guards. Runtime counters must exist and be zero; final supervisor audit has separate counters. Zero final open orders does not replace either. Missing counters fail. |
| Identity mismatch / inventory | `test_missing_child_evidence_distinguishes_verified_binding_without_passing`; `tests/test_post_pr1090_process_identity.py::test_separate_runtime_identity_owns_exit_and_acknowledgement`, handshake rejection/Windows retained-handle tests; `tests/test_pr1090_p1_repairs.py` structured inventory, unreadable inventory, remaining-runtime and escalation tests | Live binding true is separate from matching child shutdown identity. Missing/mismatched child identity remains terminal false. Fresh inventory must complete and contain no Ross runtime; forced exit/failed readers/audit remain failures. |

Required hooks remain exactly `src/ibkr/shutdown_evidence.py::REQUIRED_HOOKS`:
ops_summary, learning_scheduler, execution_engine.shutdown,
trade_exit_engine.shutdown, storage_engine.shutdown,
active_trade_registry.verify_empty, scanner_reset, manager_disconnect,
event_collector.flush_summary, console_flush. Terminal event order additionally
requires graceful request, shutdown started/complete, terminal flushed, witnessed
runtime exit, no runtime, final broker query/disconnect and final evidence flush.

### Request reuse audit and material freshness finding

`src/core/acquisition.py` owns a ContextVar cache only for the current acquisition
scope. `run_scanner_cycle` is an acquisition_cycle; its scope is released on
normal return and cancellation. The owning orchestrator's scope supplies the
stop poll. No per-pass result is promoted into the next pass by this new cache.

| Cache | Key / successful reuse | Failure / cancellation boundary |
| --- | --- | --- |
| Qualification, `MarketDataClient.qualifyContracts:481` | Client identity plus full contract_key: conId, symbol, secType, exchange, primaryExchange, currency, localSymbol, tradingClass. Successful rows stored for original and qualified identity. | Empty rows not cached. Error handling can retry, but AcquisitionCancelled is not caught by ordinary Exception. Checkpoint precedes lookup and follows acquisition. |
| Quote, `snapshot_stock:506` | Client, full identity, requested market-data type; original snapshot, original authority/type confirmations, timestamps, request/completion/field evidence and debug retained. Intraday stats uses get_quote rather than a second wire request. | MD_TIMEOUT, CONTRACT_QUALIFY_FAILED and MD_EMPTY not cached; no negative-result memoization. Checkpoint before lookup/after acquisition prevents serving a cached result after stop. **Age-on-hit gap below.** |
| Daily history, `_request_daily_history_with_fallback:760` | Client, full identity, lookback, RTH and end datetime. Bar size1day / TRADES / format1 are fixed by this API; they are not variable ignored parameters. 20D vs25D, RTH, explicit end and other conId remain separate. | Empty/failed result not cached; fallback opportunities retained. Checkpoints before lookup and after acquisition; cancellation exits scope, including cleanup. |

Existing `test_exact_requests_reused_and_cycle_identity_boundaries_isolated`
asserts one qualification/quote across repeated reads, one20D request, separate25D
and parameter/identity histories, and a new acquisition next scope.
`test_empty_history_keeps_same_cycle_retry` asserts empty → successful → reused.
`tests/test_market_data_client_snapshot.py` retains async→sync qualification and
RTH-false history fallback coverage. Failure rules for quote/qualification are
also direct cache insertion predicates; there is no new blanket failed cache.

**Cannot affirm that reused quotes never bypass freshness at8f40.** Freshness is
computed only in `_snapshot_stock_uncached:651`; a cache hit returns the earlier
flags. `_stale_market_data_drop:1967` consumes MD_STALE without recalculating age.
A previously fresh quote can age during enrichment/reuse/selection without that
flag. Existing stale-consumer tests start with MD_STALE and do not catch this.
Do not replace broker time with receipt/scan time or silently renew a timestamp.

### Separate focused follow-up — not part of reviewed PR1108

Prepared in detached `/workspace/work/acceptance-followup`, based on8f40, with no
commit/push/CI/readiness claim. Reviewable draft patch:
`/workspace/work/acceptance-package/focused-followup.patch`.

1. Reassess original broker timestamp age on cached-quote retrieval and again at
   scanner stale-consumer boundary. Preserve request identity, broker timestamp,
   type/completion/field authority and request count; no extra acquisition and no
   timestamp refresh. Existing stale fixture gets a fixed clock, assertions intact.
2. Bounded runtime-owned float-worker stop under scanner_reset, sharing one3s join
   budget; preserve survivor registration and fail the hook on incomplete cleanup,
   while still disconnecting the provider. No global thread/process kill.

Before edits, four new synthetic probes at the baseline gave2 failed /2 passed:
aged quote lacked MD_STALE; runtime reset never called worker shutdown; news
return-after-stop and cancellation-before-cache-hit already passed. The probe's
context-manager ordering was corrected before that recorded result; it is not
a runtime finding. After the draft changes, six new probes plus nine existing
stale-boundary cases gave **15 passed in0.69s**, local Linux only. No full suite,
Windows run, remote CI or independent review was run for this draft. It requires
focused review and changed-head certification before it can replace the reviewed
head. These findings need an explicit disposition before releasing observation;
do not turn a clean terminal result into a claim that background worker drain or
age-at-selection was proved on8f40.

### Validated issuer identity → canonical acquisition

1. Genuine IBKR scanner rows enter `IbkrScannerProvider.scan` with contract
   conId/listing/routing/currency/localSymbol/tradingClass. Scanner `details.longName`
   is retained in `last_scan_details.symbol_details` (`ibkr_provider.py:227`).
2. If absent, `get_quote:280` calls `_qualified_contract_for_symbol` and
   `_retain_qualified_company_name:388`. The latter reads existing qualification
   metadata, never performs another issuer-name request. Original positive scanner
   conId remains the comparison authority even if qualification mutates a contract.
3. `IbkrClient.get_contract_reference_metadata:711` requires connected state,
   latest matching request, completed on time, no reference error, exactly one
   frozen response row, matching conId and supplied security fields; SMART is only
   routing. Missing/late/ambiguous/disconnected/mismatched evidence gives no name.
4. `_build_symbol_context` gets quote before reading updated scan metadata and
   copies `longName` to `long_name` plus issuer/security fields (`scanner_runner.py`
   around4440). `_news_symbol_metadata_for_contexts:2645` retains identity and
   priority, rejects synthetic/invalid security IDs. `_news_candidates_for_symbols:2861`
   selects the full name into NewsCandidate.company_name, retaining aliases/metadata.
5. Natural evaluated contexts at6010, or selected watchlist contexts at6382,
   feed `_enrich_news_context` → canonical service `get_news`. It first checks
   compatible canonical cache, then bounded operational refresh when unresolved.
   With ROSS_ISSUER_QUERY_ENABLED=true, `_ross_retrieval_policy` selects operational
   Google issuer queries without changing rank/caps/catalyst gates.
6. `src/news/batch_rss_adapter.py` →
   `src/news/issuer_rss_queries.py::operational_queries/query_sources` builds the
   literal full-name/alias/$ticker Google RSS query, ordered by candidate priority.
   Missing full company_name cannot create a query; it produces
   query_identity_unavailable. Yahoo issuer RSS is not operationally retried after
   its observed429. Discovery/query coverage is not proof of search completeness.

Reuse receipts: `tests/test_ibkr_reference_names.py::test_real_managed_provider_to_rss_reuses_qualification`,
unavailable/ambiguous/mismatched/late/disconnected-name tests;
`tests/test_scanner_news_identity_handoff.py::test_real_provider_context_to_news_preserves_supplied_identity`,
`test_generated_scanner_id_is_not_news_identity`; operational
`test_actual_enrichment_witness_batch_cache_and_canonical_queries`,
`test_scanner_context_order_reaches_actual_capped_acquisition` and
`test_empty_failure_cadence_query_cap_and_batch_identity`.

Observable join for the future run:
- `[SCANNER][IBKR][ROW]` rank/symbol/conId → `[IBKR][PROVIDER][QUOTE]` matching
  contract identity → `[NEWS][RETRIEVAL_DIAGNOSTICS]` candidate_identities with the
  same symbol/conId, full company_name and effective RSS aliases.
- Require `provider_invoked=true`, bounded_refresh/network_allowed=true and
  attempted completed ROSS_ISSUER_QUERY source facts. Retrieval logs deliberately
  strip URL query values; their base Google URL alone cannot prove a full-name q.
- Use sanitized `cache-exports/news.json` canonical acquisition diagnostics
  `issuer_query.per_issuer` URL/status/attempted/processing_truncated and retained
  candidate identity to verify the full-name query and per-issuer completion.
  `operational_acquisition_by_symbol`, `issuer_query_requests_completed`,
  `source_coverage_complete`, deadline/truncation/failure facts distinguish a real
  completed query from a planned URL, compatible cache hit, HTTP429 or empty result.
  Missing cache export/association leaves exact-query acceptance unproven.
- SPY/QQQ preparation retrieval with no issuer identity is explicitly insufficient.
  No manual symbol, alias/name injection, forced selection or positive control is
  introduced by the operator package.

### POSITION TRUTH availability, without suppressing the blocker

`CoreOrchestrator._run_manager_pipeline:3133` resolves position truth BEFORE its
normal `ensure_connected:3164`. `_resolve_position_truth_cycle:3003` intentionally
uses `get_ibkr_client(ensure_connected=False)`; no adapter/connection means no
position_snapshot method or DISCONNECTED. `collect_broker_position_snapshot:138`
returns unavailable, not empty authority. `reconcile_position_truth:219` creates
UNKNOWN / critical1 / block_new_entries=True / require_reconciliation=True even
with zero displayed mismatches. `recovery_engine.py:84` adds the manual-required
availability action. This explains the observed summary; it is not a quantity
mismatch and did not itself account for scanner enrichment latency.

Normal reconciliation **can clear this availability verdict on a later cycle**:
the method recomputes and replaces the snapshot/verdict every cycle. A connected
canonical adapter must have one managed account, current transport epoch,
request-correlated reqPositionsMulti/positionMultiEnd completion, no error/loss,
and a fresh scoped timestamp. Then confirmed empty-vs-empty or matching holdings
is healthy/block_new_entries=False; a new recovery plan has NO_ACTION when no
other blocker exists. Connection alone, nextValidId alone, cached old rows or a
positionEnd from another query cannot clear it. A long/interrupted first pass
may never reach that subsequent reconciliation; no clearing was observed in the
failed upload. `_degraded` can remain a historical latch, and startup/autonomous
recovery/daily-risk/position ownership gates are separate; do not claim global
readiness or force those gates clear.

Existing evidence: `tests/test_confirmed_position_repair.py::test_complete_and_signed_fractional[0]`,
`test_unavailable_never_flat_or_complete` (missing/disconnected/stale/unscoped...),
`test_upstream_recovery_allows_fresh_query_without_reconnecting[1101/1102]`,
`test_order_id_callback_does_not_restore_lost_position_transport`,
`test_unknown_position_truth_keeps_recovery_plan_blocked`, real-handoff/retained
exposure tests; `tests/test_position_truth_authority.py::test_reconcile_empty_empty_is_healthy`
and exact-match/mismatch tests. These are synthetic tests already included in
the successful full CI, not a new broker reconciliation experiment.

### Independent outcomes — never collapse into one PASS

| Outcome | Required positive evidence | Incomplete / negative interpretation |
| --- | --- | --- |
| Graceful cancellation / terminal safety | STOP_REQUESTED time → graceful/shutdown/terminal events, every hook completed once, child identity matches retained supervisor identity, unforced runtime exit0, successful launcher/readers, complete empty final runtime inventory, fresh end-confirmed separate READ_ONLY audit with zero open orders/disconnect, both SDK mutation-attempt owners exactly zero, artifact/privacy scan pass. | Forced termination, missing hook/counter/identity/end marker, inventory error or audit failure = FAIL. No catalyst is required. Observer timeout alone cannot convert this to success. |
| Full natural scanner pass | Genuine broker universe (requested50, actual count recorded), per-symbol evaluated/deferred/drop accounting, scanner summary/contract and WATCHLIST_K_SELECTED/Focus final or corresponding empty outcomes for the same pass, completed scanner return/owner TOPN_REFRESH. No stop/deadline truncation or broker-zero/teaching/MOCK/manual fallback. | Build-start/raw50 rows or some contexts is not completion. Clean stop before return = INCOMPLETE, not end-to-end acceptance. Legitimate all-rejected pass can complete with empty K/M. |
| Natural issuer acquisition | Genuine candidate identity reaches full-name canonical operational query; per-issuer attempted+available+completed, no processing truncation, associated response/coverage diagnostics retained. Evaluate cache-only reuse separately. | No issuer identity, only SPY/QQQ, missing full query association, planned URL only, unavailable/429/budget truncation = UNPROVEN/FAILED acquisition, regardless of clean stop. Completed empty retrieval may pass acquisition but not catalyst. |
| Catalyst qualification | Existing Ross issuer attribution, fresh publication/event rules, qualifying catalyst witness and no applicable dilution veto, expressed as ross_catalyst_valid/catalyst-confirmed for that candidate. | No recent news, generic/co-mention, stale/update-only, unavailable or vetoed evidence cannot qualify. Natural absence is legitimate; do not force a catalyst for shutdown acceptance. |
| Downstream progression | Naturally selected Watchlist/Focus candidate handed to RossMomentumStrategy.evaluate; observable pattern/setup/risk decision and resulting READ_ONLY suppression. Follow each existing gate and report terminal reason. | No Focus/catalyst/pattern, position-truth/recovery/risk block or no handoff means progression not demonstrated, without invalidating an independently successful shutdown. Never require a live/order mutation as proof. |

### Operator package contract and review status

The ONE block below is a **review copy on HOLD**, not authorization to execute.
It is also saved verbatim as `docs/ross/PR1108_NATURAL_READONLY_ACCEPTANCE.ps1`
in this separate documentation snapshot. It keeps reviewed head8f40 pinned and
has workstation/explicit-observation flags false. The two material findings
require disposition before release; if a follow-up is accepted, regenerate the
package with its newly reviewed head. Do not flip flags as a workaround.

It prepares a unique short-path `C:\tmp\ro1108-<id>\s`, leaving the unchanged
PyCharm checkout untouched. Child-only environment starts from registered
defaults plus existing safe READ_ONLY defaults, original50/15/5, canonical
issuer opt-in and required news; no threshold/RVOL/float/catalyst bypass or
session override. IBKR is explicit loopback paper-TWS7497/client71. Preflight is
filesystem/config/guard/process-only and requires normal RTH, accepted interpreter,
clean pinned checkout, no existing Ross runtime and active independent pre-guard
SDK instrumentation. It makes no preflight broker/provider request.

Canonical state/cache paths are private; no old scanner/news/prep cache is copied
to make selection succeed. Existing operator order-ID high-water state, if present,
is copied into private state and original bytes verified unchanged afterward;
the production allocator is not reset. Defaults under the fresh clone's ignored
data directory are isolated from the original checkout. A child startup configuration, recorded with source/hash in the evidence,
sets yfinance timezone/cookie/ISIN caches to private state before first use.
It changes cache location only, exits78 if configuration fails, and does not
change network permission, strategy data or event-loop policy. Cache provenance
remains explicit rather than being treated as fresh acquisition.

The existing supervisor, not the PR1040 capped adapter, launches `-m src.main`.
Observation180s is unchanged. Supervisor grace60s/terminate15s/kill15s and bounded
reader/pipe/identity cleanup remain unchanged. Progress every5s reports stdout
bytes and paths; create terminal/STOP_REQUESTED for early graceful stop without
killing the shell/runtime. Broker-zero fallback requests an early stop and fails
natural acceptance. Terminal stdout/stderr and supervisor logs stay available.
The outer540s monitor budget detects stuck supervision; it does not certify
cleanup or broadly kill unrelated processes. If it expires, retain surviving
identity/evidence, mark FAIL, and inspect before any retry. Third-party/OS stalls
are not falsely represented as a hard successful-stop guarantee.

After supervisor exit the package runs independent read-only process inventory,
source/operator-state hashes, validates runtime AND separate audit mutation
counters and strict terminal evidence, exports only sanitized canonical caches,
then privacy-scans the allowlisted evidence directory and makes ONE
`ross-natural-readonly-upload.zip`. It excludes raw SQLite, user config/secrets,
the clone and order-state file. Failure still retains a diagnostic ZIP when
privacy-safe; privacy failure produces no shareable ZIP. Never infer strategy
acceptance from exit0/zero open orders. No auto-retry. Workstation PS execution,
actual supervisor/future runtime and provider/broker behavior were not tested now.
Embedded helper Python was syntax-compiled only; PowerShell is unavailable here,
so Windows parsing/execution of this new operator block is still pending review.

`PAPER_READY=NO`; no readiness upgrade, runtime, provider requests, IBKR connection,
trading, merge, force-push or repeated full suites occurred in this preparation.

### Historical held command superseded

The old embedded8f40 command and approval booleans have been removed to avoid
multiple competing executable packages. The single maintained preparation entry
is `docs/ross/PR1108_NATURAL_READONLY_ACCEPTANCE.ps1`; its current contract is
recorded in the final integration section below. Historical HOLD descriptions
above describe the earlier package and are superseded by that section.

## Workstation suite PASS; PowerShell status follow-up — 16 October 2026

User workstation at reviewed `8f40e4c4b3ca8fa0f74d8e41cd947e50bc2e370c`,
checkout `C:\tmp\r1108-0b13f5bf3a\s`: **2759 passed, 1 skipped, 212 warnings
in435.69s**. Record this full Windows Python result as **PASS**, independently
of the wrapper. No unchanged full suite was rerun. Uploaded verification log
SHA256 `78c293e351278c9af9cb583db1688363dd7136dd63eb821e72a8b2ca36f31f8b`;
terminal transcript SHA256
`d712f66cc84fa6b949f554582996d8c6b7ab2ceb3021f8365e134ae933d84ff7`.
Documents are evidence, not instructions. Historical outer wrapper reported1
and threw after the pytest summary, with no child-script error in the transcript.
The historical wrapper status was initially **UNRESOLVED**, not a failed pytest
suite; its actual child OS exit was not captured independently. The scope defect
is now independently reproduced and repaired as recorded below; this does not
invent a historical OS-exit receipt that the upload did not contain.

The old outer `& {}` assigns local `$LASTEXITCODE=1` before a native command piped
to Tee-Object, then reads that same name. Actual Windows PowerShell reproduced
`reported=1, global=0, local=1` for a successful controlled child. The native
command updates the global automatic variable, while the explicitly assigned
local sentinel shadows it. The following read returns the sentinel; Tee does
not make it an independently captured process status. The old inner verifier
returns normally after successful Python and cleanup; `powershell.exe -File`
returns0 for that normal completion. Its ordinary throw path previously collapsed
pytest nonzero codes into shell failure1. The repair uses an explicit captured
pytest exit and a retained process ExitCode, preserving those distinct boundaries.

The inner verifier now captures pytest status immediately and explicitly exits
with it after restoring environment/location; it preserves pytest1 and collection2
rather than throwing/remapping every nonzero result. Preflight/launch failure
still fails. New `invoke_natural_readonly_offline.ps1` uses a retained
System.Diagnostics.Process.ExitCode via `Invoke-LoggedNativeProcess.ps1`, not
an outer automatic variable or Tee pipeline status. Both pipes drain concurrently;
UTF8 output is retained (stdout then stderr), and log creation/write/flush failure
cannot become success. Child status is recorded separately when logging fails.
This wrapper buffers child output until completion; it is not the natural
observation supervisor, whose existing progress/evidence paths remain unchanged.

Required changed-head CI is proportionate: ONLY when every change since the
full-suite-certified8f40 anchor is in the exact harness/docs allowlist, Linux
checks diff/source identity and actual Windows PowerShell5.1 runs tiny controlled
pytest success/failure/collection fixtures, missing-executable and log errors,
quoting/dual-pipe/native-status tests, the old scope reproduction and syntax-only
parsing of the staged observation command. No repository full suite is silently
labelled rerun. Any production/Python-test/offline-hook change outside that exact
allowlist retains normal full Linux/Windows suites. Final head-specific receipts
and independent review are recorded in PR1108's summary/Checks.

Production `src`, offline Python guard, event-loop policy, test assertions,
requirements and both separate uncommitted runtime follow-up defects remain
unchanged by this harness repair. The earlier acceptance map and HOLD command
are now saved with this checkpoint rather than only in the detached documentation
snapshot. Workstation pytest acceptance is satisfied; runtime observation remains
on HOLD for disposition of quote-age and runtime float-worker ownership findings
and explicit future observation authorization. No repeat workstation full suite
is requested. `PAPER_READY=NO`; no broker/provider acquisition, natural runtime,
merge or readiness upgrade.

### Confirmed actual Windows harness receipt

At harness commit `afeb15a8999ff283d629c54eaa122ed6519d5b5b`, remote
https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/38823257275
passed verification-scope, Linux source/whitespace checks and the actual Windows
PowerShell controlled job. Windows PowerShell **5.1.26100.33438**, Python3.13.3:
**13 controlled checks passed**. The old pipeline logged
`OLD_PIPELINE: {"reported":1,"global":0,"local":1}`. Both direct verifier and
new outer wrapper preserved actual tiny-pytest success0, failure1, collection2;
missing Python/native executable, prelaunch log-open error, post-exit log-write
error, quoting/large dual pipes and native7 were checked. Intentional failing and
collection-error fixtures remain nonzero; they are not claimed as repository
suite passes. The new operator command was AST-parsed only, never executed.
The Windows evidence artifact is `windows-powershell-status-evidence`. No full
repository suite ran at this harness head; full results remain attached to8f40.

Independent exact-afeb static Codex review found no actionable blocker; it is
not human approval or a claim of local Windows execution. This checkpoint-only
receipt update also requires focused changed-head checks and exact-head review;
those final receipts are linked in PR1108's verification summary, rather than
creating an endless sequence of commits recording their own SHA.

Next operator action: retain the already-passing workstation log and transcript;
**do not repeat the full workstation suite**. Review the focused harness receipt
and disposition of the separate quote-age/runtime-worker draft. The held natural
operator block remains pinned to historical8f40 and its launch flags remain false;
regenerate it for the eventual reviewed runtime head after those findings have a
disposition and before any separately authorized observation. Do not launch it
from the old checkout or treat a harness fix as natural/runtime acceptance.

## Separate production acceptance follow-up — 16 October 2026

Wrapper repair is complete and remains independently reviewed at
`5b91fcd20699e0664dc6c7f08668823e5a080942` on PR1108. Actual Windows
PowerShell 5.1 checked all 13 controlled paths in changed-head CI
https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/38823534757.
Its branch is not changed by this production follow-up.

The existing patch `/workspace/work/acceptance-package/focused-followup.patch`
is preserved byte-for-byte, SHA256
`0c545f3923125349bce3efa4859d1d7052fac6dc0952fa3f93a23e99e695a5b0`, with an
additional `.original.patch` copy. It was inspected and carried forward rather
than discarded/recreated. The separate branch is
`codex/readonly-quote-age-worker-shutdown`, based on the completed wrapper head;
its PR targets `codex/natural-readonly-enrichment-stop`, so its review diff contains
only this focused production follow-up and depends explicitly on PR1108.
Neither PR is merged; main remains unchanged.

### Focused repairs and preserved semantics

- Quote cache hits re-evaluate the original aware broker trade timestamp against
  the existing IBKR_SNAPSHOT_MAX_AGE_SECONDS limit, retaining the strict greater-
  than boundary. No new quote request, receipt-time substitution, renewed timestamp,
  market-data-type promotion or authority/completion/request-ID replacement.
  Existing stale flags are never cleared. Missing/invalid/naive cached timestamps
  remain unknown, not evidence of a fresh trade.
- Scanner stale-consumer checks reassess age immediately at the existing
  Watchlist, Focus, forced-premarket and prep-seeding stale boundaries. A quote
  originally fresh can no longer outlive the limit during enrichment/selection
  merely because its old flags did not yet contain MD_STALE. Other Ross gates,
  catalyst/float/RVOL/rank/size policies and READ_ONLY protections are unchanged.
- Runtime scanner_reset now invokes owned float-worker cleanup. All registered
  workers receive a stop before any join consumes the shared three-second budget.
  Successful owners are retired; failed/live owners remain registered and produce
  an incomplete scanner_reset hook. One ordinary worker error does not suppress
  other worker stops or provider disconnect. Required later hooks and independent
  mutation-evidence flushing remain required even on this failure.
- Registry lookup/start is synchronized. Blocking SQLite/cache construction runs
  outside the registry lock; construction ownership is tracked separately.
  A shutdown generation invalidates in-flight initialization, preventing a late
  worker start. Pending constructors wait only within the remaining shared budget;
  incomplete construction is failed cleanup, not a clean-stop claim. Standard
  constructor/filesystem stalls are not forcibly interrupted. Concurrent shutdown
  does not claim completion of another owner's cleanup.

The constructor-lock issue was found by independent preliminary review of the
carried patch and repaired before publication; it is not hidden by a longer
observation/grace period. The preserved draft remains useful historical evidence,
while the new branch contains its reviewed refinements and additional regressions.

### Verification attribution and observation hold

Local hard-offline focused checks: **105 passed in 5.10 seconds**, including
age-limit/provenance/request-count/cancellation checks, all stale consumers,
real synthetic in-flight worker stop/no fallback/no late persistence, shared join
budget, failed-owner retention/provider disconnect, constructor cancellation,
and durable failed-hook/mutation proof. Earlier independent focused 25 passed
preceded the additional edge cases; it is not the final exact-head receipt.
New production changes require fresh remote full Linux and Windows suites and
independent exact-head review. Those final receipts and the pinned regenerated
operator block belong in the new PR summary after completion.

The user's **2759 passed / 1 skipped / 212 warnings / 435.69 seconds** workstation
result still certifies the earlier `8f40e4c4` Python source, not this new production
implementation. Completed wrapper Windows checks are also separate. No repeated
workstation full suite is requested, and no full local suite was run here.

The earlier acceptance evidence map, issuer paths, POSITION TRUTH analysis and
five independent outcomes remain in force. The checked-in historical observation
block pinned to8f40 remains obsolete/HOLD and must not be run. Only after these
findings are resolved, fresh CI passes and exact-head review completes will the
operator package be regenerated with the new exact reviewed source head. It will
retain false launch gates and require separate observation authorization.
Natural pass/issuer/catalyst/downstream acceptance remains unproven. No broker or
provider acquisition, natural runtime, trading, merge or readiness upgrade.
`PAPER_READY=NO`.

A focused downstream-consumer check exposed three pre-existing test fixtures that
labelled a fixed January2025 quote as current while testing percentage/RVOL gates.
The new age-at-selection rule correctly rejected it. Their shared synthetic
provider now supplies a current aware UTC trade timestamp (including its no-bars
variant); price/reference/RVOL/catalyst assertions are unchanged. The focused
consumer set changed from3 failed/83 passed to **86 passed**,107 warnings,2.66s.
This fixture correction is a concrete changed-head reason for fresh CI, not a
weakened stale-data assertion. Old in-flight CI at7154770e is superseded; CLI
cancellation was unavailable (Forbidden), so its results are not substituted for
final-head verification.


## Controlled integration (2026-10-16 UTC)

PR1108 was ancestry-preserving merged with exact-head guard at 5b91fcd20699e0664dc6c7f08668823e5a080942; accepted merge 424cedf289bce0a4ac20ed9f9f620b2bd2ec58f7. PR1109 was retargeted to main and main merged into its branch. Integration production/test source remains identical to reviewed ee44dd2ebe51dedf500f54f7c23618a6ad51c91c. The CI cumulative exact harness allowlist now uses that certified source anchor and full Linux/Windows2779-pass receipt 38824692588; any non-allowlisted change still requires full suites. The workstation2759-pass evidence belongs only to8f40 and is not evidence for PR1109. Integration checks/review pending. Observation unexecuted, PAPER_READY=NO.


## Accepted combined source and operator release — 16 October 2026 UTC

This section supersedes prior unmerged/HOLD-script descriptions, not historical
verification attribution. PR1108 merged as424cedf289bce0a4ac20ed9f9f620b2bd2ec58f7
with expected head5b91fcd20699e0664dc6c7f08668823e5a080942. PR1109 retargeted main,
merged that main ancestry, and merged as a0fb504dabcb3f6f20bbe97b9e88e32cd806b419
with expected integration headae817f9e084fb181d31eb0abda210b89ca53bb48. Production
and every existing test are identical to reviewed ee44dd2ebe51dedf500f54f7c23618a6ad51c91c.
No unresolved review threads or actionable review blockers existed at integration.
Integration CI38826657284 passed Linux source/whitespace checks and actual Windows
PowerShell controlled-process checks. Independent exact integration review5541352408
is a Codex review, not human approval. Ancestry was preserved, no main force push.

Evidence remains separate: workstation at8f40 =2759 passed/1 skipped/212 warnings
in435.69s; PR1109 full CI38824692588 at ee44 =2779 passed/1 skipped on both Linux
and Windows (Windows212 warnings,471.84s). Neither is a natural observation. No
full suite was repeated for source-identical integration or operator-only changes.

The separate operator release changes harness/docs only. The cumulative exact
allowlist is anchored to certifiedee44. Any source/test outside the explicit
harness paths still runs full suites. New focused Windows evidence/review will be
recorded in its exact-head PR receipt; do not infer a pass from this preparation.

The maintained PowerShell preparation script takes mandatory ExpectedCommit
(the final accepted main merge SHA from the release receipt) and Python (the
existing verified3.13.3 environment with dependencies). It clones to a unique
`C:\tmp\ro-xxxxxxxx\s`, checks pinned commit is in fetched main, detaches at
that commit, and prints a separate complete `powershell.exe -NoProfile ... -File
run_natural_readonly_observation.ps1` command. It does not run preflight,
observation, providers, broker calls or another full suite. No approval booleans
are placeholders in the released command. **Next action is preparation only;
observation remains unexecuted and is a separate user-operated action.**

Before that separate execution: use normal weekday RTH (America/New_York
09:30–16:00, excluding configured holidays/early close); log in to PAPER TWS,
API enabled, read-only API enabled, socket7497 on127.0.0.1, localhost permitted,
client71 unused, correct market/scanner subscriptions. No existing Ross runtime
may be running. Keep TWS/account/session normal; do not force a session or
candidates. Existing safe READ_ONLY config disables broker writes, translation,
submission, execution probes and execution; fallback is false. Natural50/15/5
TopN/Watchlist/Focus and issuer-query/required-news gates remain. Operator-owned
order-ID state is copied privately (never reset), all operational caches, SQLite,
guard persistence and decision traces are inside the unique root/state.

The supervisor process runs Python-E, which intentionally ignores PYTHONPATH.
Its runtime child is launched by the unchanged supervisor as Python-u-m-src.main,
without-E. The private startup hook therefore applies to that child. Preflight
runs a no-acquisition child with the same startup behavior and verifies actual
yfinance timezone/cookie/available ISIN cache-manager locations, not only env.
Configuration failure exits78 because Python otherwise ignores sitecustomize
exceptions. No event-loop policy is changed. Actual Windows tests use fake
providers for failures and installed yfinance for cache-location inspection only.

Execution preflight requires a clean exact source, Windows Python3.13.3, normal
RTH, complete empty runtime inventory, all three READ_ONLY action guards, SDK
mutation instrumentation and zero attempts. Existing supervisor owns verified
process identity,180-second observation, cooperative STOP_REQUESTED, required
hooks, independent runtime mutation flush, bounded graceful/escalation handling,
final process inventory and fresh independent broker audit.180 seconds is an
observation budget, never proof of completed scanner pass. Terminal safety can
pass after an interrupted pass, with pass/issuer/downstream separately incomplete.
PowerShell outer supervision remains bounded; a surviving owner prevents ZIP
packaging and is reported for inspection, never a success or broad process kill.
Child OS exit codes are retained independently of LASTEXITCODE. Both streams are
captured concurrently; logging/launch/timeout/packaging failures remain failures.

Logs are under root/e (supervisor and terminal stdout/stderr); progress and exact
STOP_REQUESTED path are printed. After child exit, packaging independently checks
current source HEAD/clean hashes, original operator order-state hash, final
inventory, strict terminal verdict and both pre-guard SDK attempt owners. It
exports sanitized news/float JSON, privacy-scans evidence, and emits one
root/ross-natural-readonly-upload.zip. Unsafe privacy output has no shareable ZIP;
a failed terminal can produce a clearly failed diagnostic ZIP. A live supervisor
has no concurrent ZIP. Raw SQLite, credentials, private order state and checkout
are excluded. Do not reuse a failed root for a second run.

Five outcomes remain independent, with the earlier evidence map authoritative:
1. Graceful shutdown: all hooks/identity/ordered events/unforced exits/independent
   inventories, mutation counters and fresh final audit pass. No catalyst needed.
2. Full natural scanner pass: genuine universe and complete per-symbol accounting,
   completed scanner summary and natural Watchlist/Focus outcome, no truncation.
3. Full-issuer acquisition: validated genuine contract issuer reaches canonical
   operational full-name RSS query; attempted/completed response diagnostics for
   that candidate. SPY/QQQ preparation or a planned URL is insufficient.
4. Catalyst qualification: existing attribution/freshness/catalyst/dilution gates
   pass naturally. Empty/rejected news is legitimate and cannot be forced.
5. Downstream progression: natural Watchlist/Focus, decision/risk/position-truth
   stages prove their own gates, remaining READ_ONLY throughout. A terminal-only
   pass is not end-to-end trading acceptance.

POSITION TRUTH critical1/blocked remains an availability verdict before connection;
fresh end-confirmed scoped reconciliation on a later normal cycle can clear it.
Connection alone cannot. The existing tests/code cited above remain evidence;
no broker experiment, suppression or readiness claim was performed.
**PAPER_READY=NO. No runtime, acquisition, trading or natural observation executed.**

### Operator harness execution receipts and final package identity

The operator-only release is PR1110:
https://github.com/NelzonMamani/ibkr-trading-system/pull/1110.
Its final exact-head CI/review and accepted main merge SHA are recorded in that
release receipt; the preparation command must pin that accepted merge, never a
moving branch. The accepted production/source main above remainsa0fb504d and all
production source is still reviewedee44; PR1110 adds no production changes.

Actual Windows PowerShell5.1.26100.33438 / Python3.13.3 CI38828009620 at
fc966761723bd25928879e8ccc815473a4e50cf2: **PASS**,13 original exit-status checks
plus20 operator checks. Job116739971123 explicitly records
REAL_PACKAGE_CHECKS_PASS:8 synthetic cases and REAL_PREFLIGHT_CHECKS_PASS:4
synthetic cases, CACHE_STARTUP_CHECKS_PASS and installed-provider cache-location
inspection. Preflight cases use fake native classes with no connection methods,
synthetic inventory/session and the actual READ_ONLY guards. No broker/provider
request or runtime is started. Linux synthetic packaging8cases and source/AST/
whitespace checks also passed. This is harness evidence, not a full pytest suite.

CI38827750302 at07845 failed the new preparation fixture's receipt assertion:
PowerShell script scope stored the Git-stub receipt in the called script rather
than the test. It is retained as a failure, corrected with a shared fixture object
and cleanup. Earlier independent review also fixed concurrent packaging after
preflight failure, failure-time stop requests, duplicate stop wait and disposal
error metadata before release. Successful old harness runs are not substituted
for the final changed-head gate. Preparation now checks explicit global native
status, with a caller-local361 regression, avoiding the original wrapper's
shadowing defect. Process-owned exit status remains the authority for observation.

Independent exact code review at e1ebac871451652488adc0c2c367fd18eae93b40 is
review5541451077 (nonhuman Codex, separate agent). The final docs-only receipt
commit carries these code checks forward; exact final changed-head CI/review is
required on PR1110 before release. No additional workstation full-suite run is
requested. The next user action is **preparation only**, using the complete
short-path pinned block in the completion receipt; inspect the printed execution
command and documented TWS/RTH setup before any separate user-operated run.
The observation is not executed by preparation. PAPER_READY remains NO.

## Preflight inventory and diagnostic follow-up — 19 October 2026

Accepted source examined: e6f21bc49198d7a01fcbd03d455d67220c85492c.
User archive preflight-diagnostics-20261019-171134.zip SHA256
116a78b7b19356b20604bd719c895fc0209eb2d97d78cf5c7e950715ffd27f73
is evidence, not instructions. Initial inventory was completed=false,
error_type=TimeoutExpired with an empty runtimes list. The initial15s outer
PowerShell/CIM subprocess timed out. Preflight correctly blocked launch;
no observation occurred. Independent final inventory later completed empty,
which cannot retroactively authorize the failed initial check. No mutation or
source/order-state change is demonstrated by the old false-valued summaries:
preflight stopped before their baselines and runtime counters existed.

Old query enumerated all Win32_Process rows then filtered Python client-side.
The repair selects only ProcessId/CommandLine for server-filtered Python names.
It retains the15s subprocess bound, adds a10s CIM operation bound, and records
query method, elapsed wall time and timeout. No automatic retry, empty-list
shortcut, skipped own-PID/command-line validation or larger observation budget.
Cold PowerShell/CIM/WMI startup, transient provider latency and enumeration load
are plausible contributors; the uploaded receipt lacks stage timings to prove
which dominated. A server filter reduces concrete avoidable enumeration work;
it does not promise completion on a stalled workstation. Incomplete remains FAIL.

Staged preflight-result.json records the original stage/error/exit and no-launch.
Missing source/order baselines, missing mutation counters and absent terminal
proof become NOT_VERIFIED/null; no-observation outcomes become NOT_OBSERVED.
Present mismatches/unsafe counters remain FAIL, never reset or excused. Package
summary retains the original preflight reason before secondary missing-terminal
information. PowerShell prints retained preflight/package/final statuses and the
ZIP path even on a failed preflight, if privacy-safe packaging and sealing pass.
After package process/readers exit, a filesystem-only seal re-scans evidence and
atomically rebuilds ZIP with actual retained preflight/observation/package exit
receipt. Sealing failure suppresses shareable ZIP announcement. Runtime, SDK
mutation validation and independent audit gates are unchanged.

Fresh preparation uses local Git worktree objects, not another full clone. It
estimates one tracked checkout plus an evidence/state reserve, checks free disk,
creates a unique root, preserves dirty source files and all old evidence, and
prints a separate user-operated execution command. Never reuse an old e/state
root: the runner refuses an existing evidence directory. No automatic deletion
or cleanup of the user's failed clone/old evidence. Select another short-path
BaseDirectory if the conservative free-space estimate fails; the detached
worktree still needs room for one checkout and future evidence.

Local focused checks: inventory query/timeout/self-correlation checks and nine
synthetic real-packager cases PASS. Actual Windows PowerShell controlled query,
15s timeout, reporting/exit/sealing and real local-worktree checks plus independent
exact-head review are required in the repair PR receipt before release. No full
suite requested; production src/offline protections/requirements unchanged.
Existing workstation2759 and production2779 CI remain attributed to their prior
heads. No broker/provider calls, observation, trading or readiness upgrade.
PAPER_READY=NO. Final reviewed repair pin and complete preparation-only command
are recorded in the repair PR/completion receipt; fetch that narrow branch into
an existing local repository and reuse its objects. No merge is performed here.

## 2026-10-20 — completed natural pass at reviewed PR1111; remaining selection blockers

Evidence is the user-operated run at **4ae3fe38ff5215e4c5fd5316a75030febdc6a9f3**,
not a run performed during diagnosis. Uploaded `ross-natural-readonly-upload.zip`
SHA256 `781387b4a892435e40150a37f69ef48603a7eaf4b9c003ca488b8e08aa5a606c`.
Preserve this ZIP and its original evidence/state roots unchanged.

| Independent acceptance outcome | Receipt / result |
| --- | --- |
| Process inventory | PASS: completed=true, CIM_SERVER_FILTERED_PYTHON, 1.086 seconds, bounded15s; no initial runtimes |
| Graceful shutdown / terminal certification | PASS: no forced termination, both child exits0, required hooks succeeded, runtime identity MATCHED; final broker audit completed/disconnected with zero open orders |
| Runtime mutation and independent audit | PASS: place=modify=cancel=0 in both independent sets; tracked source and operator order state unchanged; package/final exit0 |
| Full natural scanner pass | PASS:50 genuine candidates →8 Watchlist →0 Focus; first pass completed |
| Full-issuer news acquisition | PARTIAL VERIFIED: genuine full issuer queries attempted/completed for PLAG,SLN,WORX,YMAT; WORX/YMAT are actual Watchlist members; not verified for remaining six Watchlist issuers |
| Catalyst qualification | NOT ESTABLISHED: all eight Focus evaluations reported DATA_UNAVAILABLE/news_unavailable; no qualifying catalyst should be inferred from a completed query |
| Downstream progression | NOT ESTABLISHED:0 Focus, no qualifying intent or orders; terminal audit success does not certify end-to-end selection/trading readiness |

### Timestamp / latency trace (UTC, original terminal stdout line references)

Initial supplemental snapshots arrived around17:23:07–08. Authoritative provider
quotes were then acquired serially with20-day intraday-volume and25-day reference
history work. These history durations are distinct requests, not duplicates.
Repeated `get_quote` log entries subsequently reuse the per-cycle snapshot cache;
a log entry alone is not an extra wire request. News follows all50 enrichment
contexts, and Focus follows news. No shortlist quote refresh existed at4ae.

| Symbol | Native type-callback receipt, requestID (line) | Minimum wait to Focus from that receipt |
| --- | --- | --- |
| AAME |17:23:19.937345,496 (2019)| >89.47s |
| WORX |17:23:13.790254,476 (1716)| >95.61s |
| FUFU |17:23:18.588604,491 (1939)| >90.81s |
| YMAT |17:23:15.498328,481 (1789)| >93.90s |
| EXYN |17:23:27.668787,511 (2283)| >81.73s |
| TCRT |17:23:45.543489,556 (2973)| >63.86s |
| SLE |17:24:01.156787,601 (3590)| >48.25s |
| HUIZ |17:24:27.208624,671 (4558)| >22.19s |

These are callback-receipt latency bounds to after news completion17:24:49.407871,
**not fabricated broker trade timestamps or exact quote ages**. The archive does
not serialize the full per-symbol `market_data_observations` payload returned by
the scanner. Broker trade times therefore cannot be reconstructed exactly.
Focus lines5484–5507 explicitly reject all8 as DROP_STALE_MARKET_DATA; even the
latest callback precedes Focus by more than the unchanged15s freshness limit.
News cache-only check begins17:24:43.324224 after all-symbol enrichment; operational
news17:24:43.560937–17:24:49.407871 adds more ageing. This demonstrates implementation
latency, not failure to observe long enough. Extending observation cannot repair it.

Smallest repair: bound explicit reacquisition to the existing strategy's topK
provisional discovery survivors; use the existing provider/pacing/cooperative
acquisition, replacing only quote cache entries. Keep qualified identity and
parameter-keyed history caches. Rebuild quote-derived metrics with the same
reference/float facts; rerun price/Watchlist/float gates before final selection.
Unknown/invalid timestamp, mismatched identity, failed/timeout refresh remain
rejected. Genuine LAST_TRADE timestamp is retained unchanged; never substitute
receipt/current time. Final Focus gates and a final publish-age check remain
mandatory; earlier refreshed rows may still age out while later rows are read.
No repeated refresh loop or forced promotion is introduced. New
`[SCANNER][SHORTLIST_REFRESH]` markers retain old/new requestIDs, broker times,
receipt and assessment times/flags for the next separately authorized observation.

### News budget and issuer handoff

Actual path: genuine scanner `symbol_scan_details` / qualified company name →
`_build_symbol_context` identity fields → `_news_symbol_metadata_for_contexts` →
news candidates / canonical issuer query → batch adapter `ROSS_ISSUER_QUERY`.
The cached per-issuer URL proves full names, not manually supplied candidates:
PLANET GREEN HOLDINGS CORP (PLAG), SILENCE THERAPEUTICS PLC-ADR (SLN),
SCWORX CORP (WORX), J-STAR HOLDING CO LTD-A (YMAT), each OR its dollar ticker.

Cache-only all50 lookup had zero hits; SPY/QQQ prep does not cover candidate
issuers. Operational result attempted12 sources:4 issuer requests and8 feed
requests. Per-source elapsed: YMAT1.360343s, PLAG1.497436s, SLN1.524976s,
WORX1.757972s (parallel/completion order is not priority order). Exact individual
start/completion wall times are not recorded; cached result completed_at is
17:24:48.974585. Stage monotonic elapsed5.230826s, fast budget5.2s, total8s,
reserved extended2.8s unused because primary coverage was incomplete. Some
feeds returned401/403 or did not complete; no provider retry was run here.

The cap is4 issuer queries, selected by original raw-universe priority:
PLAG,SLN,WORX,YMAT. PLAG was already stale-rejected and SLN over-float-rejected
before acquisition. They consumed half the cap while six of eight eventual
Watchlist issuers went unqueried.46 results say budget_exhausted; per-issuer truth
for those says query_request_limit, attempted=false. This is a cap/priority issue
as well as a fast-tier deadline, not proof all requests consumed eight seconds.
Four query results remain partial,46 budget_exhausted; none establishes search
completeness. Already-returned per-symbol entries are reused at Watchlist stage,
so no extra Watchlist acquisition recovers omitted issuer queries that cycle.

Repair only acquisition order: stable discovery-survivor-first priority, retaining
all50 symbols for coverage accounting and the same four-query/eight-second caps.
With this run's survivors, first four become WORX,YMAT,FUFU,AAME; four other
eligible issuers may still be explicitly uncovered. Strategy rank/membership,
canonical identity, attribution, cache semantics and catalyst gates are unchanged.
A fetched feed/headline or reused partial cache is never complete issuer coverage.

### Position truth and reporting

Initial preconnection missing-snapshot UNKNOWN/critical1 is an availability
blocker. Normal connection subsequently obtains a completed broker snapshot,
but it contains CMND0.1, DFSC8, ENVB8, FGI1 and PBM7 against zero system positions.
The resulting five BROKER_ONLY_POSITION critical mismatches are a different,
continuing ownership blocker: entries/exits blocked, five manual-review recovery
actions, auto_applied0. `src/execution/recovery_engine.py` explicitly states:
"Broker exposure does not establish system ownership; manual review required."
`test_reconcile_broker_only_is_critical` and confirmed-position-repair regressions
retain that behavior. Reconciliation can clear snapshot availability after
connection; it cannot invent ownership. Evidence supports expected unowned
exposure blocking, not a demonstrated recovery defect. Whether the positions
were externally created or originate in absent historical system state is not
established by this isolated run. Do not adopt, liquidate, cancel or modify them.
This blocker did not explain the serial scanner delay.

The unconditional `not intent_stage_seen()` fatal message was misleading with
NO_FOCUS_CANDIDATES and zero evaluated setups. Replace it with ordinary
NO_FOCUS_CANDIDATES/NO_QUALIFIED_INTENT reporting when no audit contract is
violated. Keep real trigger-without-intent invariant exceptions and actual audit
contract violations fatal. Empty-Focus diagnostics now count stale rejection and
name an all-stale result accurately. No intent is manufactured.

### Review / execution state

PR1111 remains a separate harness-only repair at reviewed4ae. Its required CI
39286810328 succeeded (including actual Windows PowerShell controlled checks),
independent exact-head review5574683076 found no blocker; the user-run terminal
receipt now verifies inventory latency and graceful shutdown in the workstation
session. Recommend its exact-head engineering merge after rechecking unchanged
head/checks/review/threads; **no merge is authorized/performed by this task**.
This recommendation does not accept the production follow-up or trading readiness.

New production follow-up is separate branch `codex/natural-shortlist-freshness-news`
stacked on4ae, with separate-cause commits and focused offline probes. Required
changed-head Linux/Windows CI and independent review are recorded in its PR
receipt. Reuse workstation2759-pass at8f40 and old2779-pass CI only for their own
unchanged source; neither verifies this new production source. No new workstation
full-suite rerun is requested. Next operator action is review PR1111 and the
production follow-up; **observation remains HOLD** until the new source is reviewed
and a later explicitly authorized package is pinned. Preserve existing evidence.
No broker/provider call, runtime run, trading, forced selection or readiness upgrade
was performed during diagnosis. PAPER_READY=NO.

## 2026-10-20 — controlled integration and late deadline review

PR1111 was rechecked at exact4ae3fe38ff5215e4c5fd5316a75030febdc6a9f3:
three required jobs SUCCESS, independent exact-head review, no unresolved threads,
reviewed harness-only diff. It was merged with ancestry preserved as
**2aba8df95fffebcb5e74525b867a0977de579924** (parents e6f21bc4 and4ae3fe38).
PR1112 was retargeted to main without changing reviewed4815fc23. Its prospective
merge tree exactly matched4815fc23; intended remaining diff was four production
files, three focused test files and this checkpoint.33 focused integration cases
passed; existing full Linux/Windows2803-pass receipts remained separate.

Before merging PR1112, a newly arrived automated review thread4322634242 found
that the positive precheck did not bound a snapshot's independent five-second
wait by the remaining scanner budget. Integration paused; no review thread was
ignored or treated as resolved merely because CI was green. The focused repair
retains4815fc23511bdf8bfd41ca8e42e9d6ddb53b0cb0 as an ancestor and adds one scoped
absolute acquisition deadline only around shortlist refresh/context rebuilding.
Native snapshot/event/async waits clamp to remaining time; every retry checks the
same deadline. Expiry discards partial rebuilding and preserves original stale
rejection, without renewing timestamps, changing freshness/pacing or extending
scanner/news budgets. Stop cancellation takes precedence; the deadline scope is
restored before required finalization. Identity/history cycle caches are shared,
not recreated. Seven controlled deadline regressions cover native wait/retry
cleanup, expired/nested scopes, simultaneous stop, event/async cleanup, sequential
refreshes sharing one deadline, and no publication after rebuild expiry.

Local deadline/shortlist/shutdown/cache focused result:59 passed in2.14s. This is
not a workstation full-suite result. New production source requires renewed
exact-head review and changed-head Linux/Windows CI before PR1112 merge; final
head/check/merge receipts are recorded in the PR and integration release receipt.
No workstation suite was repeated. Existing workstation2759 at8f40, production
2779 and2803 CI receipts, and natural run at4ae remain distinct historical evidence.
No observation/provider/broker runtime or holding mutation during integration.
Observation execution remains separate and on HOLD; PAPER_READY=NO.

Independent delta review of cde4a86b found one additional cleanup gap: native
history waits cancelled their wire request on stop but not on deadline expiry.
The same market-data-only cancellation now handles both conditions, polling is
clamped, and an eighth controlled regression proves exactly one request/cancel
and no subsequent wire fallback. Final focused result:60 passed in2.07s.
Earlier cde4 CI/review is superseded for integration; only the final repaired
head's checks/review can authorize the PR1112 merge. Production order mutation
paths are unchanged. Final accepted integration/package pins remain in the PR
receipt; no natural execution is implied by engineering acceptance.

## 2026-10-20 — accepted integration and preparation-only release

PR1111 accepted merge:2aba8df95fffebcb5e74525b867a0977de579924, preserving reviewed
4ae3fe38ff5215e4c5fd5316a75030febdc6a9f3 and its original main parent. PR1112
accepted production merge:8ff169d1511654ef3d913c742a0dfd26b63a9a60, preserving originally reviewed
4815fc23511bdf8bfd41ca8e42e9d6ddb53b0cb0 plus the focused late-review deadline
repairs through caf5467a2cdb40ad26efd628e9ae1232d3ae6588. No conflict resolution
changed implementation. The actual accepted merge tree is exactly the final
reviewed caf5467a tree. Final release/main SHA and the one literal pinned operator
block are retained in the integration release PR receipt and completion message;
they include this documentation without changing the reviewed production source.

Evidence ledger (do not combine or relabel these receipts):

| Receipt | Proven result | Limit |
| --- | --- | --- |
| Workstation8f40e4c4 |2759 passed,1 skipped,212 warnings,435.69s; wrapper subsequently repaired separately | Historical source, not verification of later production changes |
| Reviewed productionee44 CI38824692588 |2779 passed Linux/Windows | Earlier implementation |
| PR1111 CI39286810328 at4ae | Actual Windows PowerShell5.1 exit/inventory/operator/packaging checks; Linux focused checks | Controlled children, not natural acceptance |
| User natural run at4ae, ZIP781387b4a892435e40150a37f69ef48603a7eaf4b9c003ca488b8e08aa5a606c | Inventory1.086s; graceful terminalPASS; no forced stop; zero runtime/independent mutations; source/order state unchanged;50→8→0 | Partial issuer acquisition only; no catalyst/downstream acceptance |
| PR1112 original4815 CI39387332954 |2803 passed,1 skipped on Linux/Windows; Windows212 warnings | Before final deadline repair |
| Final productioncaf5467a CI39389648522 | 2811 passed,1 skipped on both; Linux202.96s; actual WindowsPython3.13.3 212warnings,437.96s | Hosted offline CI, not workstation/natural execution |
| Renewed independent review5582237886 atcaf | No remaining actionable blocker; independent8 deadline regressions pass | Separate nonhuman review; not broker acceptance |

The release's CI receipt baseline advances to the final source above only after
its full Windows/Linux success is verified. Exact source/offline-guard/conftest/
requirements identity and a narrow harness/docs allowlist retain proportionate
controlled checks for documentation releases; any production/test/dependency
change outside that allowlist runs full suites. No workstation suite repeated.

Preparation uses the existing reviewed `PR1108_NATURAL_READONLY_ACCEPTANCE.ps1`.
Run the one released block from the user's existing PyCharm repository in Windows
PowerShell5.1, using C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe (verified
Python3.13.3 and dependencies). It fetches main into existing Git objects, checks
the pinned accepted commit/ancestry, extracts the script from that commit and
creates a unique C:\tmp\ro-xxxxxxxx\s detached worktree. Dirty PyCharm source,
existing evidence, original order state and broker holdings remain untouched.
A conservative disk estimate must pass; choose another short-path base or free
space manually if needed. Never delete old evidence automatically. No full clone,
provider import/acquisition, preflight or runtime launch is part of preparation.
The new root reserves fresh state/evidence: e must remain absent until the separate
runner creates it; an existing e is refused. The script prints a separate complete
execution command. **Do not execute that printed command under this integration
instruction. Preparation is authorized; observation remains HOLD.**

Before a later separately authorized run:

- Use normal configured weekday US RTH (America/New_York09:30–16:00, honoring
  holidays/early close), a correct workstation clock, genuine subscriptions and
  validated paper-TWS session. No session/candidate/catalyst overrides.
- PAPER TWS: API enabled, read-only API enabled, socket127.0.0.1:7497, localhost
  permitted and client71 unused. This setup is unnecessary for preparation.
- No existing Ross runtime. Initial inventory must complete within its bound and
  be empty; incomplete with empty rows is a failure. Exact pinned source must be
  clean; all READ_ONLY write guards and independent mutation instrumentation must
  pass. Runtime child startup/cache-isolation probe must pass as actually launched.
- Retain private order high-watermark copy and new isolated state/cache/SQLite.
  Preserve existing CMND,DFSC,ENVB,FGI,PBM broker holdings. Broker-only exposure
  cannot establish system ownership; manual blockers remain. Do not adopt,
  liquidate, cancel or suppress them to obtain acceptance. Ownership resolution
  is not required to validate shutdown/scanner/news; unresolved blockers continue
  to prevent downstream readiness.

The next separately authorized180s observation will verify these distinct results:

1. Graceful cancellation/terminal audit: bounded stop, required hooks and float
   workers cleaned up, runtime identity verified, final inventory empty, runtime
   and independent mutation counters zero, source/order state unchanged, retained
   real exits and privacy-checked shareable ZIP. Regressions fail this result;
   a missing first pass/catalyst alone does not.
2. Full natural scanner pass:50 genuine candidates processed through unforced
   Watchlist/Focus gates.180s is an observation budget, not proof of completion.
   Inspect old/new broker timestamp/request/receipt/assessment markers and
   bounded shortlist refresh; genuine stale/unknown/failed refresh still rejects.
3. Natural full-issuer acquisition: eligible-survivor query priority under the
   same four-query/eight-second limits, actual full-name canonical requests,
   per-issuer attempted/completed/available evidence, attribution and truthful
   partial/cache coverage. Do not infer all8 Watchlist issuers are covered.
4. Catalyst qualification: qualifying, fresh, attributed Ross catalyst evidence.
   Completed retrieval or clean shutdown alone does not establish this outcome;
   no catalyst may legitimately appear.
5. Downstream progression: only naturally eligible Focus/pattern/trigger/intent
   stages may progress, with READ_ONLY and ownership blockers remaining effective.
   No manufactured intent/order, forced selection or trading-readiness upgrade.

During later execution, the unchanged runner prints responsive log paths and the
cooperative STOP_REQUESTED path. The supervisor retains180s observation plus
bounded graceful/escalation handling; outer540s supervision and packaging remain
bounded. Both streams and phase exits are retained; incomplete/failing preflight
packages diagnostics and prints the ZIP only after successful privacy-safe seal.
A clean early stop is not full-pass or end-to-end acceptance. Preserve the final
shareable ZIP and prior archives. No observation/provider/broker runtime ran during
integration. PAPER_READY=NO.

## 2026-10-20 — second natural receipt at accepted0ae: successful refresh, stale news, provisional-gate diagnosis

User-operated archive `ross-natural-readonly-upload(2).zip` (uploaded filename
`ross-natural-readonly-upload.zip`), SHA256
`cb4cc43e8607438e465a49bd2d296e2401532ebe3a9726342f5c4be1e1a252b2`,
records accepted head0ae803718ca8c9ace547f247077c44f2d6133500. This is uploaded
historical evidence, not a run executed during diagnosis. Preserve the original
archive/state. All broker/feed timestamps below are retained in recorded UTC
(London is UTC+1 on this date); callback times are not substituted for trade times.

| Separate acceptance outcome | Evidence / result |
| --- | --- |
| Graceful cancellation/terminal safety | PASS; terminal certification PASS, no forced termination; runtime and independent place/modify/cancel attempts all0; source/operator order state unchanged; preflight/observation/package/final exits0 |
| Full natural scanner pass | PASS:50 genuine candidates → WORX,AIXI Watchlist →0 Focus; both shortlisted refreshes completed with new genuine broker LAST_TRADE times |
| Natural full-issuer acquisition | VERIFIED for WORX,AIXI (and SAIQ,XCH): actual full-name canonical Google RSS queries, HTTP200, workers completed, responses closed, no query processing truncation; overall source/search coverage remains partial |
| Catalyst qualification | NOT ESTABLISHED; both reached catalyst evaluation, DATA_UNAVAILABLE/news_unavailable, DROP_NO_CATALYST. No retained eligible evidence; no inference that no qualifying news exists |
| Downstream progression | NOT ESTABLISHED:0 Focus, no qualifying strategy inputs/intents. Shutdown/refresh success is not end-to-end or trading acceptance |

### News: exact exclusions supported by recorded counters

Natural acquisition evaluated entries at2026-10-20T13:38:25.450253Z against the
unchanged six-hour window beginning07:38:25.450253Z. Four completed Google query
responses contain117 entries total. Each response's entries_examined_count equals
feed_item_count; each has0 within-window,0 future,0 missing/invalid dates,0 missing
titles, published_time_used equal to its entire count, updated_time_used0,
matched_count0, processing_truncated=false and raw_capture=null.

| Query issuer / supplied full identity | Examined / stale | Recorded publication range (UTC) | Worker fetch+parse |
| --- | --- | --- | --- |
| AIXI / XIAO I CORP |21 /21|2019-03-04T22:25:55Z →2026-10-08T07:00:00Z|1.376999s|
| XCH / XCHG LTD |7 /7|2021-04-19T14:22:26Z →2026-09-29T19:54:07Z|1.394007s|
| SAIQ / WISESAT SPACE HOLDINGS CORP |57 /57|2026-09-30T22:00:00Z →2026-10-17T00:44:00Z|1.438430s|
| WORX / SCWORX CORP |32 /32|2017-05-24T06:40:09Z →2026-10-16T18:57:12Z|1.471039s|

Each URL contains its quoted full issuer name OR dollar ticker; query identity
propagation/acquisition is therefore proven. That does not prove identity of
individual returned articles. `src/news/news_fetcher.py` checks usable publication
time and excludes stale entries before ticker/company relevance matching. All117
failed this temporal eligibility boundary. Per-symbol relevance-rejection counters
are0 because those entries did not reach matching; they do not mean117 identity
matches, nor117 identity mismatches. With0 retained matches, no candidate evidence
reaches downstream catalyst/event qualification. No category-specific exclusion
(e.g. wrong issuer, general story, non-catalyst event) can be invented for these
entries. Existing offline date/relevance diagnostics regressions verify this order.

The package contains aggregate date counters/ranges and query/source receipts,
not raw RSS bodies or rejected-entry titles/links/individual timestamps. Therefore
article-by-article identity, publisher relevance and hypothetical event quality
cannot be reconstructed. News rules/query construction remain unchanged: there
is no demonstrated rule defect or evidence justifying a wider time window/new
provider lookup.117 old entries establish only why these captured responses
retained nothing; they do not establish absence of current qualifying issuer news.

For WORX and AIXI, cached evidence arrays are empty; last_retrieval is partial,
provider_available=true, provider_status=partial_request_failure. Per-issuer
operational_acquisition says acquisition_completed=true, retained_count0,
source_coverage_complete=false, search_completeness_established=false,
coverage_deadline_exhausted=true. Their successful query requests did not exhaust
a per-issuer request budget (last_retrieval.budget_exhausted=false); aggregate
coverage exhausted its fast tier. Other feed sources include Reuters401,
GlobeNewswire403 and Benzinga RAWFEEDLIMITEXCEEDED. Do not relabel these successful
issuer responses as HTTP-unavailable, or partial global coverage as completed
negative news. The context adapter consequently reports news unavailable for
qualification, not a proven absence of news. Cold lookup had no candidate cache
hits; returned per-symbol partial/no-evidence contexts are reused in the same
cycle without additional Watchlist provider retrieval.

### Freshness: first causes, timing and bounded provisional acquisition

The initial48 rejected symbols had first recorded causes:
31 DROP_STALE_MARKET_DATA,7 DROP_FLOAT_MAX,6 DROP_FLOAT_UNKNOWN,
3 DROP_RVOL_DISCOVERY and1 DROP_PCT_CHANGE. The final summary's48 stale is not
proof that all48 initially failed freshness alone. Underflow/backfill iterates
all unselected contexts after enrichment and overwrites an existing drop_ledger
entry with a later stale result. By then all48 are stale. Preserve first-cause
accounting for earlier hard rejections while retaining stale flags/final rejection
authority. Optional missing-data backfill rows still upgrade to the hard stale
block, preserving existing premarket seed/backfill safeguards.
A full synthetic scanner regression preserves FLOAT_MAX even after later ageing.

Initial authoritative quote callbacks span WORX req465 at13:36:54.103825Z to
GRML req710 at13:38:23.902844Z, about89.8s. Between symbols, genuine contract,
20-day volume history,25-day reference history and float enrichment run serially;
float workers also update the isolated cache. Log repetitions of get_quote are
not sufficient proof of duplicate wire requests. Original non-shortlisted broker
trade timestamps/assessment wall times are not fully serialized, so early stale
status cannot be split precisely into illiquid old trades versus enrichment
ageing for each symbol. The recorded MD_STALE decision is retained as evidence.

Cache-only candidate news:13:38:25.040135–25.230345Z, no provider invocation.
Operational news:13:38:25.274709–30.850320Z; monotonic acquisition5.201403s,
fast budget5.2s, total8s. The next timestamped quote callback is13:38:47.268894Z.
The intervening16.4s includes return/context/log/ranking work but has no detailed
span receipts; do not assign an invented per-function latency cause. Before
refresh the rank log names only WORX,AIXI. Refresh order and genuine provenance:

| Symbol | Original broker timestamp / request | Refreshed broker timestamp / request | Receipt → assessment |
| --- | --- | --- | --- |
| WORX |13:36:53Z /465|13:38:46Z /714|13:38:47.272269Z →47.278711Z|
| AIXI |13:37:01Z /485|13:38:46Z /715|13:38:47.803499Z →47.807300Z|

Refreshed flags are empty. Approximate new trade ages at assessment are1.279s
and1.807s, within the unchanged15s limit. Focus then rejects both for catalyst,
not stale data. Refresh is working; no timestamp renewal or stale-limit change
is justified by these successes.

A separate demonstrated ordering defect remains: initial `_evaluate_watchlist_gates`
returns immediately on stale data, before otherwise valid rows can reach the
bounded provisional acquisition list. XCH's recorded discovery metrics are
price2.46,pct41.38,rvol3.82,float1.286410m, yet it drops stale atstdout1884 and
never reaches refresh. This does not prove XCH would become fresh, meet Focus
volume/spread/catalyst gates or deserve selection. It does prove that freshness
precluded even bounded reacquisition of an otherwise discovery-eligible row.

Repair only initial acquisition ranking: an explicit default-off provisional
mode defers freshness when the existing provider supports refresh. All price,
percentage,RVOL,float/identity/session gates continue to apply. Stale flags and
broker timestamps remain unchanged. Initial KEEP is labeled PROVISIONAL_ACQUISITION.
Existing strategy rank[:K], request pacing, shared absolute deadline, cancellation,
identity/history caches, final metric/score rebuild and strict Watchlist/Focus/
publish freshness checks remain. No full-universe refresh, forced replenishment
or automatic Focus/catalyst is introduced. Failed/still-stale refreshed data stays
rejected. Synthetic full-scanner regressions cover stale already at initial
acquisition, fresh/still-stale/invalid-price refresh, and early float rejection
with no refresh and preserved first-cause ledger.

### Empty strategy-input reporting

The repeated `[PIPELINE][SKIP] empty watchlist` atstdout5881 etc comes from the
strategy-input else branch, not the scanner Watchlist. Official Watchlist has
WORX,AIXI; empty official Focus intentionally empties strategy inputs. Report
NO_FOCUS_CANDIDATES with watchlist_count2/focus_count0, reserving EMPTY_WATCHLIST
for an actually empty Watchlist and NO_STRATEGY_INPUTS for other empty handoffs.
No strategy invocation or intent is manufactured; real no-Focus authority is
unchanged. Existing legitimate empty-Watchlist branch remains accurate.

### Engineering state and smallest next action

Follow-up branch `codex/natural-run2-evidence-reporting` contains separate freshness/
first-cause and reporting fixes plus this evidence map. Focused offline scanner,
deadline/cancellation, news-date/relevance and console checks are recorded in its
PR receipt; changed production source requires exact-head Linux/Windows CI and
independent review. Prior workstation2759, old production2811 CI and this user
natural receipt remain separately attributed; no workstation suite or observation
is repeated. Next action is review the focused repair PR; do not rerun observation
or acquire providers merely to fill missing raw evidence. Preserve all broker
holdings and manual ownership blockers; no adoption, liquidation, cancellation,
suppression, trading, merge or readiness upgrade in this diagnosis. PAPER_READY=NO.

Changed-head Linux CI at c199f6df exposed four existing premarket missing-price
seed/backfill regressions: preserving DROP_MISSING_PRICE hid the later explicit
hard stale block in those optional-data paths. The focused correction preserves
earlier hard float/RVOL/percentage causes but still upgrades missing-data rows to
DROP_STALE_MARKET_DATA. Existing assertions remain unchanged. Failed intermediate
CI is retained as failure; only final repaired-head CI/review is an acceptance
gate. No provider/observation/workstation rerun was used to diagnose this.


## 2026-10-20 — PR1114 controlled integration and next operator preparation

PR1114 reviewed head `91988fdde713a642637955f01c2f8145d58ffd3a` was merged
with ancestry preserved at accepted main `0896e855a5e0f2dd2612ceb7a9a18078434a34d2`.
Parents are accepted0ae and reviewed91988; both complete trees are
`a79cf3936512fc129f5ff6a1766a65aaaa808f76`. No conflict resolution or implementation
change occurred. Immediately before merging: head unchanged, ready/non-draft,
CI39434843988 completed SUCCESS, independent exact-head review5586079692 recorded
no remaining blocker, and review threads were empty. Review is independent Codex
COMMENT evidence, not a human approval. The intended six-file diff was inspected.

Completed CI at91988: Linux Python3.11 **2824 passed,1 skipped,197.07s**;
actual Windows Python3.13.3 **2824 passed,1 skipped,212 warnings,581.21s**.
Historical workstation **2759 passed,1 skipped,212 warnings,435.69s at8f40**
remains separate; it does not verify the new production changes. Intermediate
c199 CI failures remain failed receipts. No workstation suite was repeated.
The fixed harness-only CI baseline advances to this completed2824-pass receipt;
its allowlist is unchanged and production/offline-source identity is still checked.
This documentation/CI receipt release does not change reviewed production or harness.

Preserved user-operated natural evidence at0ae (archive SHA256
`cb4cc43e8607438e465a49bd2d296e2401532ebe3a9726342f5c4be1e1a252b2`):

| Separate outcome | Recorded result |
| --- | --- |
| Graceful shutdown/terminal certification | PASS; no forced termination; runtime and independent place/modify/cancel counters zero; source/operator order state unchanged. |
| Full natural scanner pass | PASS:50 genuine candidates → WORX/AIXI Watchlist →0 Focus. Both shortlist refreshes had genuine new broker timestamps. |
| Full-issuer news acquisition | Verified issuer queries reached acquisition; four successful responses contained117/117 stale entries before relevance matching. Global coverage partial; raw rejected bodies absent. Zero retained evidence does not prove news absence. |
| Catalyst qualification | NOT ESTABLISHED. Both shortlisted rows rejected DATA_UNAVAILABLE/news_unavailable/DROP_NO_CATALYST. |
| Downstream progression | NOT ESTABLISHED. No Focus, strategy intent or trading acceptance. PAPER_READY=NO. |

The next user-operated observation must separately establish whether otherwise
eligible initially stale rows enter existing bounded provisional rank[:K] refresh;
only genuine broker timestamps may pass unchanged final freshness gates. Failed,
still-stale or otherwise invalid refreshed rows must reject. Rejection summaries
must retain earlier hard float/RVOL/percentage causes, preserve explicit stale
blocking for optional missing-data backfill, and report populated Watchlist/empty
Focus as NO_FOCUS_CANDIDATES. No guaranteed Focus/catalyst is required for successful
shutdown. A180-second observation can end before full completion and is not an
end-to-end acceptance guarantee. The recorded117 stale news exclusions do not
justify changing query rules, budgets, freshness limits or provider behavior.

Preparation and execution remain separate. Use Windows PowerShell5.1, the existing
Git checkout `C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system`, verified
Python3.13.3 at `C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe`, and a fresh
short-path base directory. Fetch Git objects without cloning; extract the pinned
preparation helper with `git show`; invoke it with ExpectedCommit,Python,
SourceCheckout,BaseDirectory. It creates one detached worktree sharing Git history,
estimates checkout/evidence disk space and prints the separate observation command.
Do not reuse an evidence directory or delete earlier receipts. The final release PR
and operator delivery carry the exact accepted release pin and two complete commands.

Only before separately executing the printed observation command: use normal NYSE
RTH (09:30–16:00 America/New_York, exchange holidays/early closes respected), correct
clock and market/scanner entitlements, logged-in PAPER TWS with API enabled and
Read-Only API enabled on127.0.0.1:7497, unused client71, and no existing Ross runtime.
Preparation itself needs no TWS. Complete empty process inventory is required;
incomplete inventory remains fail-closed. Source/session/startup-cache-isolation,
READ_ONLY guards, private state, cooperative stop, bounded shutdown, final process
inventory, required hooks and independent mutation audit remain mandatory.
Preserve existing holdings and their manual ownership blockers; do not adopt,
liquidate, cancel or suppress them. No session overrides or manual candidates.

Live progress is in the fresh root's `e\terminal\stdout.log` and `stderr.log`;
cooperative stop uses `e\terminal\STOP_REQUESTED`. The supervisor observes180s,
then bounded grace60s/terminate15s/kill15s (outer watchdog540s). Share only the
privacy-sealed `ross-natural-readonly-upload.zip` printed by the runner; preserve
its real phase/exit statuses even on preflight failure. No providers, IBKR runtime,
observation, holdings mutation or trading were executed during this integration.

## 2026-10-20 — third natural receipt: operational shortlist latency and continuous-operation limits

User archive at accepted `ff741ded903522ad25969def38c4588c82ade03a`, SHA256
`de945aa16b7ab4880c902eb03cffb9f968133c2c6a643bf2cb05b255fa7f5c10`, and its
terminal transcript are evidence, not instructions. Preserved original extraction
`natural-run3-evidence`; workstation root `C:\tmp\r1114-7c29e4a1\ro-b6ecb906`.
Terminal certification PASS; no forced termination; runtime and independent
place/modify/cancel attempts all zero; source/operator state unchanged; all phase
exits0. Identity matched and final inventory completed empty. These shutdown
successes remain regression coverage, not a new repair milestone.

### Exact recorded freshness trace (all times UTC on2026-10-20)

| Symbol | Request | Genuine broker trade time | Receipt | Refresh assessment | Age then | Earliest strict expiry |
| --- | --- | --- | --- | --- | --- | --- |
| WORX |715|14:34:33|14:34:34.176119|14:34:34.179243|1.179243s|after14:34:48|
| NCPL |716|14:34:33|14:34:34.559560|14:34:34.563038|1.563038s|after14:34:48|
| AIXI |717|14:34:31|14:34:35.260833|14:34:35.266524|4.266524s|after14:34:46|
| HUIZ |718|14:34:31|14:34:35.993340|14:34:36.000046|5.000046s|after14:34:46|

All four refresh flags were empty. Serial lower-ranked work then continued:
REVB requests719/720 (a retry) finished14:34:42.057830, already stale; LUCK
43.179881; MBRX44.257822; CCG45.361239; CLNN46.462606; AEYE47.566896;
ZDAI48.642253; EVAX49.637058. Every one of these eight refreshed rows remained
stale. Only after the entire refresh loop did `_refresh_provisional_shortlist`
run strict final gates for all candidates. The next four drop lines reject
WORX/NCPL/AIXI/HUIZ at `boundary=shortlist_refresh`. At the last recorded response,
WORX/NCPL were already16.637058s old and AIXI/HUIZ18.637058s old. The original
four final drop lines have **no wall-clock timestamp**; their exact assessment
instants cannot be recovered. They occur after49.637058, before later pipeline
output/next cycle14:34:52.716913. Do not substitute refresh assessment timestamps
for final assessments. New SHORTLIST_ASSESSMENT logs expose final assessment time,
original broker market timestamp, request ID and exact gate reason.

### Focused operational repair

Keep existing rank[:K], provider, owning-thread acquisition, per-pass caches,
request pacing, pass deadline and all final gates. After each bounded ranked row
is processed, eligible fresh leaders in the processed ranked prefix impose an
absolute optional-acquisition deadline derived from their retained LAST_TRADE
stamp plus the existing max age, reserving up to5seconds (at most one third of
that limit) for selection/publication. Later waits/retries/rebuilds are clamped
through existing acquisition_deadline; budget exhaustion defers remaining tail
requests and proceeds to strict selection. No freshness limit or timestamp is
changed. No refresh retry round, extra universe work or transport thread is added.
The synchronous provider exposes no batch-refresh contract; unrelated strategy
snapshot ThreadPoolExecutor is not used to parallelize its shared mutable state.
Only processed rank[:K] leaders own this reserve: a near-expiry outside-K row
cannot starve higher-ranked recovery. Stop cancellation still escapes; a delayed
or invalid final quote still rejects. The reserve reduces avoidable ageing; it
cannot guarantee eligibility if later selection/OS work itself exceeds headroom.

Virtual-clock regression covers four early fresh leaders followed by long waits
or multiple stale responses, deadline-clamped tail, untouched broker stamps,
strict later expiry, outside-K near-expiry rows, one refresh round/K bound and
multi-symbol stop. Existing native/async deadline, cache reuse and shutdown tests
remain authoritative; no single-symbol success is substituted for this case.

### Continuous-operation assessment: configured cadence versus real work

- `CoreOrchestrator._run_manager_pipeline`: TOPN_REFRESH_SECONDS=300,
  WATCHLIST_REFRESH_SECONDS=60, FOCUS_REFRESH_SECONDS=10. Top-N cache timestamps
  use cycle start; effective actual cadence also includes synchronous scan cost,
  loop scheduling and error cooldown (30s for162/cancel). Scanner's printed
  cycle_seconds10 and15s broker refresh protection do not mean a broker scan
  every10/15seconds. `run_scanner_cycle` invokes provider.get_top_gainers only
  when orchestration actually calls it and protection does not return a cache.
- Receipt: one broker subscription returned50 rows; one TOPN_REFRESH. First cycle
 14:32:14.479541, scanner entry15.099418; late cycles52.716913/55.769112/58.804410
  reused cached scanner authority. The180-second runtime ended before a300-second
  top-N rescan was due. Repeated strategy/cycle/log lines are not new discovery.
- New symbols can be discovered at subsequent successful real broker scans;
  TOPN_REFRESH added/removed only reports set differences and can legitimately say
  unchanged even after a real scan. Require fresh SUBSCRIPTION/returned_rows/ROW
  receipts and request/timestamp lineage for each scan, not merely that marker.
- Watchlist continuity is cached scanner-authority continuity, covered by
  test_pr1082_rth_watchlist_continuity.60-second rebuild does not maintain fresh
  quotes for all Watchlist rows. Ross cannot promote a diagnostic Watchlist row
  without scanner-authorized Focus. Full scans perform shortlisted refresh;
  between them market_data_snapshot_manager.batch_snapshots requests only final
  evaluation/Focus symbols. This is **not** proven continuous Watchlist quote
  maintenance; empty Focus yields no such calls. No new maintenance loop added.
- News acquisition/cache policy runs from scanner passes (discovery survivors
  prioritized, four issuer-query cap, eight-second budget, canonical cache refresh
  eligibility); cached orchestration does not establish a separate news cadence.
  Coverage can remain partial. Catalyst turnover between full scans is an open
  operational limitation, not evidence of no news.
- Strategy dispatch may occur on ordinary cycles for authorized Focus and uses
  current snapshot acquisition; empty Focus correctly skips. Cached Focus/list
  authority is distinct from current quote, candle/setup, catalyst and risk truth.
  Pattern/trigger/intents have not been demonstrated by this natural run.

### Full Ross completion checklist — current evidence, no readiness upgrade

| Area | Current result / remaining work |
| --- | --- |
| Natural broker universe and identity |50 genuine rows and full issuer propagation previously verified; repeated real scans/new-symbol discovery still to observe. |
| Price, percentage, RVOL, float, identity/session gates |Preserved. Third-run hard causes16 FLOAT_UNKNOWN,17 FLOAT_MAX,4 RVOL_DISCOVERY,1 PCT_CHANGE; no forced replenishment. |
| Initially stale provisional acquisition |PR1114 path observed:12 provisional rows reached refresh. Four genuinely fresh leaders were then lost to serial tail latency; operational blocker repaired offline here, natural confirmation pending. |
| Final market-data freshness |Strict15s broker-time rejection worked; all12 ultimately stale. No timestamp renewal or threshold change. New scheduling must preserve genuine freshness through final selection. |
| Watchlist/Focus |Third receipt50→0→0; historical0ae50→WORX/AIXI→0 remains valid. Continuous Watchlist quote maintenance between scans is not established. |
| Issuer news and catalyst |Issuer acquisition previously verified with partial coverage/stale feed exclusions. No naturally qualifying catalyst established. Independent news cadence remains an operational gap. |
| Setup/candles/trigger/intent |Offline gate coverage retained; natural downstream progression NOT ESTABLISHED. Empty Focus creates no intent. |
| Ownership/position truth |Existing external holdings/manual blockers preserved. No adoption, liquidation, order cancellation or suppression. |
| Entry/risk/execution/exit lifecycle |Ross gates preserved; READ_ONLY does not certify trading. No live or paper order lifecycle acceptance claimed. |
| Stop/hooks/evidence/inventory |Third terminal PASS, zero runtime/independent mutations, no force, unchanged source/order state. Keep regression coverage; no rerun merely to prove shutdown again. |
| Continuous operation |Single180s scan is insufficient; require successive real broker scans, set transitions/continuity, quote/news ages and explicit cache-vs-acquisition receipts. |
| PAPER_READY |NO. Catalyst qualification, downstream progression and operational continuity remain unestablished. |

### Concrete longer observation path (preparation/execution remain separate)

A separate harness change accepts explicit RuntimeSeconds180..1800, default180.
Recommended next user-operated duration900seconds, preserving300-second discovery,
60/10 cache cadences and every Ross/provider rule. Preflight records duration;
observe requires matching preflight head/duration; the supervisor receives it;
outer watchdog is duration+360seconds. Stop grace60/terminate15/kill15, private
state, no-existing-runtime/source/session/READ_ONLY/mutation checks, privacy seal
and retained failure ZIP behavior are unchanged. Increasing observation duration
is for successive discovery receipts **after fixing latency**, not a shutdown fix.
Controlled tests exercise180/900/1800 dispatch, duration/preflight mismatch and
out-of-range/noninteger rejection; actual Windows tests cover propagation through
all phases/default and bounds. No actual natural process is launched by tests.

After exact-head CI/review, prepare a fresh short-path detached worktree using
shared Git objects from the existing checkout; preserve all old roots. Separately,
during normal NYSE RTH with logged-in PAPER TWS/Read-Only API127.0.0.1:7497,
unused client71, correct clock/entitlements and no existing Ross runtime, invoke
its pinned `run_natural_readonly_observation.ps1 -RuntimeSeconds 900` with verified
Python3.13.3, fresh Root and ExpectedCommit. No observation is executed here.

Evaluate at least two completed **real broker** scans (preferably three), their
actual start/completion latency and symbol sets, shortlist budget/assessment logs,
strict last-trade freshness and first rejection causes, Watchlist transitions,
news query/cache/coverage timestamps, and strategy evaluation/skip reasons.
Identical symbol sets do not invalidate a scan; unchanged cache timestamps and no
new broker request do not count as a scan. If the first pass runs too long or only
one scan completes, record incomplete continuous acceptance and its cause, not a
terminal-only pass. Keep five outcomes separate: graceful shutdown, full natural
scan(s), full-issuer acquisition/coverage, catalyst qualification and downstream
progression. A catalyst is not required to validate scheduling or shutdown.


PR1116 carries this focused repair and the bounded-duration harness separately by
cause commit. Preparation helper also accepts RuntimeSeconds and prints that exact
value in its separate execution command, avoiding an accidental return to180s.
Local final focused check:117passed115warnings6.56s, including existing shutdown,
cache/deadline/cadence, new multi-candidate and duration cases. Initial broader
focused invocation collected an existing `from core.orchestrator` test without
`src` on PYTHONPATH and stopped with ModuleNotFoundError; that attempt remains a
collection failure. Corrected offline import path `tests/offline:.:src` produced
the117-pass receipt, with no code/assertion/skip change. Linux controlled inventory
and9synthetic real packaging checks also passed. Independent review at50fef96e
ran21offline cases successfully; final changed-head CI/review receipts belong to
PR1116 and must be checked there before operator use. No full workstation rerun.

## 2026-10-20 — separate canonical news / Ross catalyst lifecycle audit

Separate from PR1116 and the user's running observation. Baseline accepted main
`ff741ded903522ad25969def38c4588c82ade03a`; separate branch
`codex/news-catalyst-lifecycle-audit`. See [full audit and file/function evidence map](NEWS_CATALYST_LIFECYCLE_AUDIT.md).
No provider/broker requests, scanner/runtime, observation, holdings mutation,
trading, merge or readiness upgrade occurred. Historical receipts remain intact.

| Ross completion item | Verified current behavior / remaining gap |
| --- | --- |
| Premarket positive persistence | Canonical evidence survives warm read/restart/preparation serialization with original publication/ID/URL. New headline not required. |
| Qualification through later session | Legacy fact-only cache can qualify while publication valid. Current compatible Ross v9 coverage expires by registry RTH120s (not helper fallback90); cache-only then becomes coverage_unknown and blocks even with a valid positive. A successful compatible empty refresh restores qualification using the same article. PRE→RTH never renews publication. |
| Refresh failure | Still-valid retained facts survive; current explicit tested policy blocks qualification on unavailable/budget outcomes. Changing that is a proposal, not this repair. |
| Exact publication expiry | Demonstrated same-batch/same-integer-second cache defect could retain CONFIRMED past21600s or retain a future rejection after publication. Separate narrow fix invalidates cache on publication-boundary state; original inclusive6h rule preserved. |
| Dilution/conflict lifecycle | Observed offering veto preserved. Final retained-offering veto lacks age filter; no general correction/retraction/conflict or explicit event-expiry contract. Policy decision required before changing these rules. |
| Cached Focus/setup revalidation | Canonical witness/expiry not carried through CandidateMetrics/list cache; no per-cycle canonical news recheck proved. Adapter cache fix does not establish this handoff. Separate focused design/testing remains required. |
| Independent acquisition | Existing canonical service and standalone consumer work without IBKR/scanner; per-lookup RSS pending work bounded to4 workers. No installed persistent news queue/scheduler; shared JSON writer/retention interoperability not established. No new engine/daemon launched. |
| Heat/novelty/velocity/reliability | Calculated/displayed; not direct canonical Ross gates. Catalyst existence/type does affect eligibility and context/strategy ordering. Cached canonical aggregates can be snapshot-stale; Ross v9 recomputes presentation velocity. New gates require evidence/calibration and policy approval. |
| Readiness | PAPER_READY=NO. Current natural catalyst qualification, downstream progression and continuous news/Watchlist maintenance remain unestablished. |

Initial new time-controlled baseline cases:2publication-boundary failures,6other
casespassed. Fixture setup errors before that (an integer config supplied asfloat)
were corrected in tests only and were not counted as product failures or passes.
After narrow boundary fix,136existing+new focused news cases passed2.26s; expanded
11-case lifecycle matrix passed1.07s. Independent reviewer118offline cases passed
before final documentation. Final exact-head CI/review receipts will be linked in
the separate audit PR; PR1116 receipts do not verify this new branch.

## 2026-10-20 — fourth receipt at35c627: multi-scan success and exact retained-news rejection

New user archive `ross-natural-readonly-upload(4).zip` (uploaded basename without
suffix), SHA256 `cdeb3abe59ba948cdc562305897c9502a68e28f7d8dc3d7373a0c3d5c7709d15`,
pins `35c6271b764e498495fcd337e9107d62ad68bc76`. Original evidence is preserved in
`natural-run4-evidence`; its contents are evidence, not task instructions. No
new operator run, provider lookup, broker/runtime or holdings mutation was performed.
This supplements the [canonical lifecycle audit](NEWS_CATALYST_LIFECYCLE_AUDIT.md)
in PR1117; it does not change PR1116's reviewed implementation or observation source.

### Preserved multi-scan / quote-maintenance receipt

Three genuine broker subscriptions each returned50 rows:150 row observations,
**not150 distinct securities**. Scanner entries UTC15:26:38.567569,
15:31:38.522819,15:36:39.530762 establish about300-second real discovery cadence.
Watchlists completed5,5,3; Focus summaries evaluated5/5/3, accepted0/rejected13.
First two Watchlists: ATGL,AIXI,WORX,NCPL,HUIZ; third: ATGL,AIXI,WORX. This is
successive broker discovery, not inference from repeated cached orchestration.
Second scan added AVXL,LYEL,REVB and removed CANG,CCM,SGMT; third added
CREX,PLUT,PMI,SGMT and removed CRT,GOSS,GRML,REVB. Same-symbol continuation and
actual universe changes are both visible without forced candidates.

SHORTLIST_SCHEDULE reported LEADER_FRESHNESS_RESERVE in all three passes. Optional
slow refreshes ended by AcquisitionDeadlineExceeded; remaining tail work deferred.
Initial leaders remained fresh through strict final assessment. For example pass1:
AIXI trade15:28:48, final assessment15:28:53.013095 PASS; NCPL trade15:28:45,
assessment15:28:53.013522 PASS; WORX trade15:28:48, assessment53.013944 PASS;
ATGL trade15:28:46, assessment53.014350 PASS; HUIZ trade15:28:43,
assessment53.015369 PASS. Still-stale rows were rejected. No broker timestamps or
freshness limits were renewed. All13 Watchlist rows reached catalyst evaluation
and rejected DATA_UNAVAILABLE/news_unavailable; Focus0 is not a quote-refresh failure.

Preflight/observation/package/final exits0, seal successful, terminal PASS; no forced
termination or capture/shutdown errors. Runtime and independent place/modify/cancel
attempts all0; required shutdown hooks completed; source and operator order state
unchanged. These successes are preserved, not a new shutdown-repair milestone.

### Exact AIXI and NCPL facts — no missing text reconstructed

Both canonical buckets retained one issuer-matched article with selected time basis
`published`, matching ID/URL/publication and original fetched_at across subsequent
refreshes. Their saved first fetched_at is15:28:24.097894UTC; final acquisition
completed15:37:27.974165UTC. Persistence did not turn that completion into a newer
publication or a new article. Stored age_seconds can reflect the cache write's
slightly later instant; replay ages below use the explicit acquisition completion.

| Field | AIXI | NCPL |
| --- | --- | --- |
| Company |XIAO I CORP|NETCAPITAL INC|
| Exact captured headline |`$AIXI latest SEC filing confirms its appeal against Apple ha`|`Shareholders who lost money in shares of acquired Netcapital Inc. (NASDAQ: NCPL) should contact Wolf Haldenstein Immediately`|
| Published UTC |2026-10-20 14:07:25|2026-10-20 12:55:00|
| Age at final acquisition completion |5402.974165s (~90min)|9747.974165s (~162min)|
| Retained ID |rss-operational:AIXI:ed98f7d8c582f2589a272cfb|rss-operational:NCPL:6595fb28b751c98b1ce56356|
| Publisher label / recorded publisher URL |KuCoin /www.kucoin.com|PR Newswire /www.prnewswire.com|
| Match |ticker_token, title|ticker_token, title|
| RSS entries / examined / within6h / stale / matched |21/21/1/20/1|69/69/1/68/1|
| Request outcome |HTTP200, worker completed, response closed, processing_truncated=False|HTTP200, worker completed, response closed, processing_truncated=False|
| RSS raw_capture |null|null|

AIXI's raw_title is the same incomplete text plus ` - KuCoin`. The only local title
transformation in `news_fetcher._fetch_headlines_from_sources` removes that publisher
suffix; no missing appeal text or article body is present. processing_truncated=False
means this feed processing completed, **not** that the headline/body is complete.
The archive cannot locate where upstream truncation occurred or establish the
appeal's significance. Do not complete `ha`, infer a legal outcome, add an appeal
classification or request a provider to fill the gap.

NCPL is a lawyer/shareholder solicitation in the captured text. `acquired` in that
sentence does not establish a new issuer acquisition event, and the existence of
a PR Newswire label does not make the item a positive catalyst. No special lawyer
rejection filter was invoked: the actual classifier stops at no recognized event
class. Do not claim a downstream event-attribution rejection that was never reached.

### Exact qualification/status path, replayed offline

At observed35c and reviewed audit174627, identical time-controlled replays of the
preserved NewsEvidence produce identical results:

1. `evidence_from_mapping` / issuer-relevance validation: original aware publication
   is within6h; ticker/title issuer match is verified. Neither item is rejected
   for stale/missing/future/update-only time or wrong identity/research tier.
2. `catalyst_policy.assess_issuer_event`: `classify_headline` returnsNone under the
   existing bounded-token vocabulary. `detect_dilution` returnsFalse. Exact reason
   is **no_catalyst_classification**, qualified=False, catalyst_type=None. The
   subsequent clause-level issuer/event attribution checks are not reached.
   `$AIXI` is not the standalone `ai` event keyword; `contact` is not `contract`.
3. `scanner_runner._ross_news_context_from_evidence` initially reports
   news_present_non_qualifying and news_available=True for these partial-but-available
   per-symbol summaries. Both last_retrieval statuses are partial,
   provider_available=True, provider_status=partial_request_failure,
   budget_exhausted=False. The issuer queries themselves are available/completed.
4. `_ross_news_contexts_from_news_intelligence_result` applies the operational
   coverage scope: acquisition_completed=True, retained_matched_entry_count1,
   source_coverage_complete=False, source_coverage_status=partial,
   search_completeness_established=False, coverage_deadline_exhausted=True.
   With no qualified positive witness it sets news_available=False and diagnostic
   **partial_coverage_no_qualifying_catalyst**. A validated positive would not be
   denied merely for partial scope; these items supplied none.
5. `assess_catalyst` then returns DATA_UNAVAILABLE/news_unavailable; Focus rejects
   DROP_NO_CATALYST. It cannot claim ABSENT across incomplete source coverage.
   A controlled full-coverage counterfactual yields ABSENT, still never CONFIRMED;
   that counterfactual is a status regression probe, not this run's coverage.

The final saved source failure summary includes Reuters HTTP401 and two
GlobeNewswire HTTP403 results; primary_source_coverage_incomplete persisted.
Fast-tier elapsed5.206810s exhausted its5.2s allocation; the reserved2.8s extended
allocation did not establish complete primary coverage. The total8s budget and
all gates remain unchanged. Successful issuer HTTP200, a recent article and an
aggregate unavailable catalyst can coexist without contradiction. Zero qualifying
witnesses do not establish global news absence or a complete negative search.
The final cache records one recent retained match for each issuer; this does not
support repeating the earlier run's117/117stale claim for this new receipt.

### Heat/hotness — descriptive heuristic, not qualification probability

Saved per-item heat/hotness: AIXI9.32/9.32, NCPL6.07/6.07. At the explicit final
acquisition instant, Ross v9 recomputation yields AIXI8.57/8.57 and NCPL6.07/6.07;
the AIXI difference is compatible with ageing a cached aggregate. Both have
5/10-minute velocity0 and source reliability/credibility fields0. Those zeros are
an existing source-name heuristic, not a calibrated judgment that these publishers
are false. Hotness duplicates heat here; there is no independently fitted model.

`news_normalizer.normalize_headlines` and `news_heat.compute_news_heat_score` use
headline/unique counts, publication velocity, freshness, region/source heuristics
and sentiment. Nonzero heat does not demonstrate event significance or bullishness;
no calibration/out-of-sample acceptance evidence was found. Current canonical Ross
qualification never compares these numbers with a threshold. Numeric heat/hotness
are informational here; catalyst existence/type still affects actual gates and
context ranking as documented in the audit. No score or rule was adjusted to make
AIXI/NCPL pass.

### Updated acceptance / engineering priorities

| Separate outcome or gap | Current evidence |
| --- | --- |
| Graceful terminal safety |PASS, zero runtime/independent mutations, no force, source/order state unchanged.|
| Natural discovery / scanner passes |PASS for three successive genuine subscriptions and completed50→5/5/3 passes, with actual added/removed symbols.|
| Bounded shortlist refresh |Naturally demonstrated leaders survive tail work; strict stale rejection remains. Keep PR1116 receipt separate from the news audit source.|
| Full-issuer acquisition / persistence |AIXI/NCPL successful full-issuer query acquisition and retained original evidence verified. Overall source/search coverage remains partial; no demonstrated loss or renewal of these two articles.|
| Catalyst qualification |NOT ESTABLISHED:13evaluations allunavailable; exact two retained examples are nonqualifying under existing text rules.|
| Downstream progression |NOT ESTABLISHED:Focus0, no natural setup/trigger/intent acceptance.|
| Acquisition priority |Investigate primary feed access/coverage and query scheduling using recorded outcomes; no new provider lookup or budget extension in this task. Do not hide partial coverage.|
| Persistence priority |Preserve stable facts/IDs across refresh, and plan serialized writer/retention interoperability before independent maintenance. This receipt demonstrates retention, not a new persistence defect.|
| Qualification priority |Keep conservative incomplete-text/solicitation rejection. Obtain sufficient captured facts and calibrated event fixtures before proposing vocabulary changes. Existing exact-expiry cache fix inPR1117 remains separate and is not naturally exercised by these much younger articles.|
| Continuous lifecycle gaps |Independent between-scan news/whole-Watchlist maintenance, cached Focus witness revalidation, correction/retraction and financing-risk expiry remain open policy/architecture work.|
| Readiness |PAPER_READY=NO; holdings/ownership blockers preserved; no new operator run requested.|

Verification: one-off offline replay of preserved AIXI/NCPL facts against observed35c
and reviewed174627 yielded identical classifications/status/metric results, with
partial-vs-complete coverage counterfactual checks. This is replay evidence, not
another natural acquisition. Prior fullLinux/Windows CI39449928814 at174627 remains
2835passed1skipped (Windows212warnings), separate from local194focused cases and
independent review5587538767. Production, scripts, tests and requirements are
unchanged in this receipt-only update. Fixed harness/docs CI baseline advances to
that reviewed completed source receipt; allowlist is unchanged. No unchanged full
suite is repeated solely to append this evidence; changed-head controlled checks
and independent receipt review remain required.

## 2026-10-20 — controlled integration and independent positive-event lifecycle

Accepted main: `6e3fcf6686a93f9ebbbf61dbe5c496d7b0277496`. PR1116 exact
`35c6271b764e498495fcd337e9107d62ad68bc76` passed CI39442689748/review5586816471,
no unresolved threads, merged preserving ancestry as
`d80473368104351c2510598a32ce4456c79b1fab`. PR1117 reviewed receipt head83fa6ac1
was integrated with that main at `426ca7858e0be99336420a40d4cb9314bad1388e`.
Only checkpoint append conflict required resolution; both historical blocks retained.
Production implementations merged cleanly. Independent renewed review5588331512
found no blocker; independent32focused cases passed2.12s and primary24combined
cases passed3.11s separately. Integration CI39458297023 passed all3jobs:
Linux2848passed1skipped216.98s, actual WindowsPython3.13.3
2848passed1skipped212warnings447.48s, WindowsPowerShell5.1
13exit-status+30controlled observation checks. Exact-head guarded merge produced
accepted6e3fcf66; its tree is byte-identical to reviewed426ca785 and both prior
heads are ancestors. These CI receipts do not replace historical workstation2759
or natural35c three-scan receipts. No workstation suite or operator run repeated.

### New focused lifecycle policy (separate branch/PR, not another observation)

The user explicitly authorizes decoupling independently verified positive events
from acquisition health. This supersedes the old failure-blocks-positive behavior
recorded in the historical audit; it is not a claim that the old code already did it.

- `scanner_runner._ross_news_context_from_evidence` reclassifies original canonical
  facts using `assess_issuer_event`. A still-valid issuer-attributed positive with
  no retained dilution veto qualifies even if acquisition fails, exhausts its
  budget, or the compatible120-second receipt expires. `news_available`, provider
  status, source coverage and search completeness remain separate degraded facts.
  No complete coverage or absence of adverse news is inferred. Nonpositive partial
  coverage remains DATA_UNAVAILABLE; AIXI's incomplete text and NCPL solicitation
  still do not qualify. Classification, issuer matching, six-hour inclusive boundary,
  publication timestamps and dilution rules are unchanged.
- `_unresolved_ross_news_symbols` also considers degraded acquisition health, so
  retaining a positive does not permanently suppress existing due acquisition.
  No new scheduler, HTTP path, budget, worker or provider engine is added.
- Canonical `ross_catalyst_evidence_v1` handoff carries evidence IDs, original text,
  publication/provenance, issuer identity/aliases and historical acquisition snapshot.
  `CandidateMetrics` carries this through cached Focus and strategy handoff. A bare
  cached CONFIRMED/catalyst_present/summary cannot provide natural catalyst authority.
- `catalyst_lifecycle.revalidate_handoff` reparses and reattributes the facts, then
  reads the current canonical store (no prep import, HTTP or write) to include newer
  retained vetoes. It reads the existing bounded presentation+witness cohort without
  dropping the extra slot or inventing veto expiry. Missing, malformed, unverified,
  future, research-only, update-only or expired facts cannot qualify. Unreadable
  canonical state rejects explicitly. Both old and new veto cohorts survive merges.
- `_run_manager_pipeline` revalidates cached Focus each cycle and before setup;
  `StrategyRunner.process` and direct `RossMomentumRunner.run` repeat the guard at
  actual READ_ONLY/PAPER/LIVE dispatch, including the alternate handoff path. Each
  canonical row is revalidated again immediately before its V1 setup work, so
  slow earlier symbols cannot carry a later row past expiry. Expired rows are removed from
  cached Focus before use. Accepted copies carry current qualification reason,
  publication-derived valid_until_utc and acquisition-health reason; historical
  acquisition snapshots never advertise current healthy coverage. Local revalidation
  conservatively reports degraded/coverage-not-reverified unless a specific persisted
  failure/expired/missing receipt provides a more precise reason. No fresh HTTP per
  cycle is required. Existing explicit MANUAL_FOCUS stock-selection authority is
  preserved and labelled canonical_event_claimed=false; no manual row is introduced.
  The established explicit SIM/PAPER validation override remains separately labelled
  and cannot operate in LIVE/READ_ONLY or assert a CONFIRMED canonical event.

Qualification reasons include verified_issuer_event_valid, retained_dilution_veto,
no_valid_canonical_event, canonical_evidence_missing/invalid, canonical_issuer_mismatch
and canonical_store_unreadable. Acquisition reasons separately identify expired or
incompatible receipt, provider unavailability/failure, budget exhaustion, partial or
unknown coverage, and cached coverage not reverified. Event validity is never renewed
from an acquisition completion time or a stored validity/CONFIRMED flag.

### Verification and full Ross completion checklist

Controlled offline fixtures cover PRE→RTH, new service/store instances and serialized
restart handoff, successful empty refresh, failed refresh, exact21600.0/21600.1-second
expiry, future→current, original-publication-derived expiry, current and retained older
vetoes, both merge directions, corrupted/malformed canonical state, missing IDs and
untrusted flags, degraded accepted-row metadata, and actual orchestrator cached Focus
expiry without rescan/HTTP. Review regressions also cover raw offering-tag whitespace,
malformed historical health metadata, duplicate-ID future/update-only facts that must
not extend expiry, and later-row expiry during slow earlier-symbol setup work. Routing fixtures now supply explicit canonical event facts;
existing route/terminal assertions remain, with row provenance compared instead of
object identity because health updates intentionally return copies. The three old
failure-blocking expectations are changed to assert the newly authorized independent
qualification and degraded acquisition separately. No tests are skipped.

Earlier focused execution at the initial lifecycle head:538passed144warnings9.36s (news, lifecycle, Focus,
setup/handoff, canonical/W02, multi-candidate scheduling, cancellation and shutdown).
Earlier checks exposed the expected old-policy assertions and boolean-only route
fixtures; those failures were not counted as passes. One attempted check named a
nonexistent test file and collected nothing; corrected paths subsequently passed.
Independent review found and repaired exact veto-tag whitespace parity, malformed
historical health handling, duplicate-ID validity metadata, and per-symbol setup
expiry windows, each with focused regressions. Initial controlled-case setup mistakes
were corrected without counting failed executions as passes. Final local combined focused execution:570passed144warnings10.71s; separate
post-review57case subset passed1.78s. Final changed-head
CI and independent review remain required; their exact receipts belong
in the separate lifecycle PR. No historical full suite verifies this new production
change. Offline startup guards block acquisition, including existing fixture-created
float workers; no broker/provider request, natural runtime or holdings mutation ran.

| Ross completion outcome / next step | Status |
| --- | --- |
| Graceful shutdown, evidence finalization, inventory and zero mutations |Natural PASS preserved; offline regressions retained.|
| Successive genuine broker discovery and bounded quote-refresh scheduling |Natural35c receipt PASS:3×50row observations, Watchlists5/5/3; no new run.|
| Full-issuer acquisition and retained publication/identity |Natural AIXI/NCPL acquisition/retention verified; overall coverage remains partial.|
| Independently valid event through failed/expired acquisition and cached handoff |New focused implementation/offline evidence; not yet natural acceptance.|
| Catalyst qualification |Natural NOT ESTABLISHED; all13recorded evaluations unavailable; examples not promoted.|
| Downstream setup/trigger/intent progression |Natural NOT ESTABLISHED; Focus0; no forced selection or manufactured intent.|
| Independent background acquisition — following implementation step |Reuse canonical service and bounded workers/queue; ONE serialized store owner shared by scanner/prep/maintenance; route all writes through that owner before enabling maintenance. Do not start another JSON writer.|
| Remaining lifecycle policy |Correction/retraction and financing-risk expiry remain undefined; retained dilution veto unchanged. Metrics remain uncalibrated/informational.|
| Remaining continuous operation |Whole-Watchlist between-scan quote/news maintenance, provider access/coverage and natural setup receipts remain open; no unchanged observation requested.|
| Holdings / readiness |External holdings and ownership blockers preserved. PAPER_READY=NO.|

Next engineering action after lifecycle review: design and implement serialized
canonical-store ownership before independent bounded acquisition maintenance. No
additional operator observation or readiness upgrade is requested in this package.

Initial lifecycle CI39460077728 Linux atddc1a9a5 failed3 routing/validation fixture
cases (2874passed1skipped219.89s); it is not a successful receipt. Two cases were
already resolved in the reviewed follow-up; the third PR174 bridge fixture now
carries canonical facts as well, with all original Focus/strategy/intent assertions
retained. Bridge+new lifecycle+runtime-safety focused49passed4warnings1.51s.
The intermediate dd65 source adds per-row setup expiry and direct-runner guards;
its pending CI is not treated as verification of this final fixture update.
Production source is unchanged by this final test/checkpoint correction. Final
head CI/review receipts must be checked in the lifecycle PR, not inferred from
historical or superseded runs.

PR1118 automated review also identified a reporting boundary: setup-handoff
revalidation could remove strategy_inputs while leaving the rejected symbol in
strategy_watchlist/final Focus telemetry. Focus collections, cached Focus,
passed/rejected counts, strategy input symbols and the received snapshot now
reconcile together, with CATALYST_HANDOFF:<actual qualification reason>. The
controlled case expires an event after the cached-Focus check but before setup;
no runner invocation, selected-but-not-evaluated or invented NO_SETUP cause occurs.
Focused lifecycle+continuity+runtime+bridge99passed131warnings4.33s. The other
inline finding (malformed acquisition_snapshot) was already fixed with explicit
unknown historical metadata and regressions. Final head checks/review supersede
intermediate receipts; no observation occurred.

## Independent canonical news maintenance — 2026-10-20

PR1118 was integrated only after exact-head checks/review and resolved threads:
reviewed `9ac38bc5b4e5894afa953b9511967838c14f5591`, accepted main
`2e53fe1238873f3b6c7043d9f269209a530458de`. The ancestry-preserving merge tree
is identical to the reviewed tree (`git diff --exit-code` passed). CI39461247792:
Linux2890passed1skipped; actual Windows Python3.13.3 2890passed1skipped,
216warnings473.22s, plus Windows PowerShell harness checks. Independent review
5588543044 and both resolved inline threads were checked. Historical workstation
2759-pass evidence and all natural-run receipts remain separate and unchanged.

The separate independent-maintenance PR introduces the following ownership map.

| Writer / reader | Ownership boundary |
| --- | --- |
| Canonical service, scanner adapter, preparation NewsProvider and standalone lookup using the same configured canonical path | All writes, including retrieval metadata, enter `CanonicalNewsEvidenceStore.write` and the path-keyed `CanonicalStoreOwner.transaction`. |
| Maintenance workers | Reuse that service/store; no second JSON writer. Two bounded acquisition workers publish each completed issuer independently. |
| Cross-process writers | Same sidecar OS lock (Windows msvcrt / POSIX flock), bounded acquisition; reload/merge/publication inside the lock. No stale pre-lock snapshot. |
| Readers and cached Focus/setup | Atomic same-directory fsync/replace publication; readers see a complete old or new file. Malformed canonical state fails closed and is preserved. |
| Raw RSS caches and preparation report artifacts | Separate artifact paths, not alternative canonical writers. |

Historical queries filter their result cohort before applying its cap, as before.
A bounded original Ross cohort survives historical windows and smaller research-request caps, including older retained
veto facts; consumer query windows still apply. Late publication merges facts but
cannot roll acquisition health back over a newer receipt. Publication failure
preserves the previous bytes and is explicitly not a usable new canonical result.
Original publication times, identity/event attribution, deduplication, six-hour
positive-event validity, dilution vetoes and all Ross market gates remain intact.

`NewsMaintenance` is runtime-owned, lazy, broker-free and bounded: two workers,
128 tracked identities/requests (validated maximum256), deduplicated queued and
in-flight work, no overlapping request for the same issuer. Active Focus then
Watchlist receive priority, with an oldest-normal dispatch after at most three
active dispatches when normal work is ready. New scanner universes retire obsolete
pending work; active and in-flight identities are retained safely. Identical work
keeps its existing due time. Refreshes and failures retain configured cadence and
the existing at-most-eight-second acquisition budget; no unbounded retry loop.
A shared feed pool single-flights identical URLs, caps transport concurrency at4
and cache entries at128, and reuses results/backoff at the existing RTH cadence.
Each issuer still receives independent canonical attribution/filtering. Diagnostics
separate logical source processing from actual HTTP and cached transport reuse.

Scanner enrichment submits genuine broker-derived identities and reads available
canonical results immediately. Workers do not wait for IBKR or the next scanner
cycle; per-issuer results become visible before a slower batch member completes.
Runtime Watchlist/Focus updates set priorities. Maintenance ownership is static
for a runtime; disabling NEWS_ENABLED cooperatively stops the owner, and an
existing/stopped owner never falls back to a competing synchronous acquirer.
Changing ownership requires restart. Legacy direct scanner calls without an owner
retain their existing synchronous behavior.

Qualification and acquisition health retain PR1118's separate reasons. Market
attention/rank influences queue scheduling only, not event qualification. Heat and
related metrics remain uncalibrated/informational. No headline/classification
relaxation promotes AIXI, NCPL or any unavailable candidate.

Cancellation reaches queue waits, feed waits, transport streaming and publication
boundaries. Graceful shutdown records ownership and requires the owned
`news_maintenance.shutdown` hook in addition to every existing required hook.
Historical receipts without ownership retain their original requirements. Failed
cleanup blocks terminal certification; no forced thread termination or false PASS.
Uncooperative third-party I/O remains a bounded-cleanup limitation reported as
incomplete rather than concealed.

Focused offline coverage includes concurrent thread/process publishers and busy
readers; malformed state and failed atomic publication; late receipts and positive/
veto retention; bounded queues, identity/request deduplication, shared-feed limits,
priority fairness/universe rotation; slow/failing sources; incremental results;
configured cadence; cancellation, supervisor stop-file and owned-hook finalization.
The controlled FAST/SLOW fixture measured first usable publication approximately
0.013s and batch completion approximately0.048s in one local run. These are synthetic
fixture timings, not live-provider speed claims. Local focused receipt before the
final ownership-pin case:408passed143warnings8.99s; the final26-case maintenance
file passed4warnings2.24s. Final combined local focused check:409passed143warnings8.81s. Exact-head CI and independent review receipts belong in
the maintenance PR; historical workstation results do not verify this new source.

| Full Ross completion item | Current evidence / remaining acceptance |
| --- | --- |
| Graceful shutdown, inventory, zero runtime/independent mutations, source/order-state integrity | Historical natural PASS preserved; owned maintenance cleanup newly covered offline. |
| Genuine repeated discovery / quote refresh | Historical three subscriptions150rows, Watchlists5/5/3 preserved; strict broker timestamps and freshness unchanged. |
| Natural full-issuer acquisition / retained attribution | Historical recent AIXI/NCPL evidence preserved, incomplete coverage explicit; new incremental maintenance is offline-only evidence. |
| Valid event persistence and cached Focus/setup handoff | PR1118 reviewed implementation integrated; controlled PRE/RTH/restart/expiry/veto cases, no natural positive qualification claimed. |
| Independent maintenance / fairness / first usable result | Implemented separately; controlled evidence only pending integration and a future user-operated acceptance. |
| Catalyst qualification | NOT ESTABLISHED naturally; no forced Focus or relaxed classification. |
| Downstream setup/trigger/intent | NOT ESTABLISHED naturally; terminal PASS alone is insufficient. |
| Remaining operational/policy gaps | Whole-Watchlist between-scan quote maintenance, provider coverage, correction/retraction policy, financing-risk expiry and metric calibration remain open. |
| GUI draft only | Red Top50, yellow Watchlist up to15, green Focus up to3, each with text labels. No GUI implementation or runtime Focus-limit change. |
| Holdings / readiness | External holdings and ownership blockers preserved. PAPER_READY=NO. |

Smallest next natural acceptance action: after this separate PR passes review/CI
and is explicitly integrated, prepare one pinned existing 900-second user-operated
READ_ONLY observation during a supported session, covering at least two genuine
300-second discovery intervals. Verify incremental issuer publication while the
scanner progresses, active priority plus normal fairness, transport reuse/cadence,
strict final quote freshness and separate qualification/coverage/attention reasons,
then zero order attempts, unchanged operator state and owned-worker shutdown.
A catalyst is not required to establish maintenance/shutdown success; qualification
and downstream progression remain separate. No observation or provider/broker
request was executed for this change, and no additional operator run is requested
before integration.


Maintenance initial exact-head CI39467584933 at13114302 exposed a historical-query
cap regression: out-of-window current rows could crowd out the requested historical
article. That failure (Linux2915passed1failed1skipped225.13s) is not a passing
receipt. Restored existing historical-window filtering before its cap; independently
protected Ross cohort facts/vetoes still persist. Existing W04 history regressions
and a new simultaneous historical-cap/Ross-cohort case cover both requirements.
Final changed-head CI/review must supersede that initial receipt in PR1119.

Automated PR1119 review confirmed the historical-cap finding and identified a
second reporting gap: maintenance combined per-issuer results but dropped batch
cache-failure flags. Per-issuer health/evidence was preserved, yet the scanner's
NEWS_DELAYED signal could be omitted. Maintenance now aggregates cache errors,
per-symbol maps/hit/miss lists, retrieval availability, budget/timeout and unresolved
truth, retaining complete per-issuer diagnostics. Mixed results do not erase an
available issuer or claim whole-batch availability. Corrupt-cache scanner-path and
mixed-result regressions cover the reporting boundary. Focused maintenance+whole
W04:46passed4warnings2.07s. No classification, acquisition or market gate changed.

Actual Windows CI39469413468 atda9c3333 failed the two new concurrency cases:
2917passed2failed1skipped220warnings477.49s. Linux at that head passed2919/1skip
237.61s; it does not substitute for Windows. Windows uncoordinated raw-file readers
encountered PermissionError during replacement. Canonical reads now participate in
the same bounded owner transaction; the already-owned write path avoids nested OS
locks. The concurrent-reader regression uses the actual public canonical read API,
requiring intact seed evidence, no cache-read failures, all25 final rows and cleanup.
The process fixture also drained child stdout/stderr sequentially: a child logging
configuration while holding the lock could fill a Windows pipe while its peer
waited. All pipes are now drained concurrently, with forced large controlled output
and finally cleanup of every child. Lock timeouts are unchanged. Windows CI now
runs the controlled maintenance file before the full suite so concurrency failures
surface promptly. Final exact-head Windows success remains required; failed runs
are not acceptance receipts. No provider/broker acquisition or operator rerun.

Independent review of the Windows reader follow-up identified a cooperative-stop
regression before acceptance: a single blocking thread-lock wait plus OS-lock
polling without checkpoints could repeat across50 issuer reads. Lock acquisition
now polls in short checkpoint-aware intervals; OS-lock and atomic-replace retry
loops checkpoint too, as does every maintenance issuer read. AcquisitionCancelled
propagates outside ordinary cache-error wrapping. Controlled cases hold either the
same thread owner or a separate owner/OS lock, interrupt a50-issuer read, require
cancellation under1s and prove released ownership, unchanged bytes and cleanup.
Existence/open checks also occur inside coordinated reading, preserving a genuine
missing cache as a miss rather than racing an uncoordinated pre-lock stat.
Final local combined focused verification after cooperative lock polling:
431passed143warnings8.56s. The first two new contention cases initially caught the
scope-exit checkpoint a second time; fixture context handling was corrected so
only cancellation raised inside the read satisfies the assertion. Failed fixture
executions are not counted as passes. Final CI/review receipts remain in PR1119.

## PR1119 controlled integration — 2026-10-20

Accepted main e3d2a7b09bc23421f409ff3cdfd0aea3dcefc458 ancestry-preserving merge
of exact reviewed ac8e3360c54dec42a7c11022d3ffb80e1b9b6994. Rechecked all3CI
checks in39471508105, independent review5589445390, resolved2threads and intended
diff; tree equality and ancestry checks passed. Local431/independent101 remain
separate from Linux2921/1skip and actual Windows2921/1skip220warnings501.17s,
controlled31 plus PowerShell13/30 checks. Historical workstation/natural evidence
and holdings remain unchanged.

Release inspection demonstrated missing per-dispatch fairness and immediate
publication telemetry, despite existing aggregate counters and source/strategy
receipts. A separate focused observability follow-up adds structured markers and
explicit operator news configuration/preflight receipts, preserving scheduling,
qualification, provider limits and cancellation. It is not part of the already
accepted PR1119 tree. Full map, complete shared-object short-path preparation block,
prerequisites and five separate outcomes are in PR1119_INTEGRATION_RELEASE.md.
Observation remains HOLD pending review/integration of that telemetry follow-up;
the accepted-source preparation block starts nothing and prints the separate900s
command with HOLD warning. No repeated workstation suite or runtime/acquisition.
GUI draft unchanged; PAPER_READY=NO.

Telemetry follow-up local focused107passed16warnings4.17s before independent
review; review found logging exceptions could skip worker cleanup and caller-local
LASTEXITCODE shadowing in the unreleased preparation block. Structured emission
now catches output/serialization failure, stops maintenance, retains a failure
counter, still cleans owned sources/releases work, and prevents successful owned
shutdown certification. Broken-output cases cover lookup start and publication.
Preparation checks explicitly use global native exit status; Windows controlled
harness parses the released block and checks that contract. These changes remain
separate from accepted main pending review/integration; observation remains HOLD.

## Natural receipt 5 at d967 — 2026-10-20

Preserve user-operated PASS: three genuine scans/150 rows, Watchlists3/4/2,
independent maintenance/incremental publication at5.256s, transport212requests/
1174reuse; graceful terminal PASS, no force, zero runtime/independent mutations,
unchanged source/operator order state. Five outcomes remain separate: shutdown
PASS; scanner passes PASS; natural issuer acquisition demonstrated but partial;
catalyst qualification UNESTABLISHED; downstream progression UNESTABLISHED.
No changed-source result replaces historical workstation evidence. Holdings and
ownership blockers unchanged; GUI draft remains deferred; PAPER_READY=NO.

Full trace, exact per-Watchlist issuer query receipts, freshness timings, limits
of missing historical date/relevance counters, and service/cleanup reconciliation:
[RUN5_NEWS_ELIGIBILITY_FINDINGS.md](RUN5_NEWS_ELIGIBILITY_FINDINGS.md), with extracted
hashed receipt summary in evidence/RUN5_NEWS_RECEIPT_SUMMARY.json. Robust parsing
finds156 starts/results,155 completed publications, one interrupted CLRO. Seven
failures are six budget-exhausted outcomes plus interruption. WORX interim cleanup
incomplete stops maintenance; final owned cleanup succeeds. Retired work50 leaves
tracked13; backlog is not a worker leak. Active due lateness inferred <=2.214s
between uninterrupted intervals; exact retirement-boundary waits unavailable.

Demonstrated operational blocker: cached empty Focus is copied between broker
scans;223 priority updates do not reconsider Watchlist eligibility. Watchlist
quotes are not maintained with empty Focus. A separate focused repair reconsiders
canonical evidence at existing Focus cadence using genuine retained shortlist
context; verified positives require bounded existing-provider refresh and original
strict gates/selector. No new discovery/HTTP on the selection caller. Monitoring
quotes do not become fresh by copying them. Existing six-hour event validity,
attribution/deduplication/dilution vetoes and15s broker freshness remain intact.
This cannot make the incomplete AIXI article qualifying; WORX/NCPL/BETR zero
retained evidence is not established absence of qualifying news under partial
coverage. Observation HOLD; no additional operator run now. CI/review receipts
belong to the focused PR; no merge or readiness upgrade authorized by this task.

Run5 focused repair local Linux/Python3.12 verification:166passed119warnings5.69s
across new26cases plus continuity, multi-candidate latency, canonical lifecycle,
maintenance/store/shutdown and native blocking-acquisition regressions. Real
provider/client wrappers with fixture transports confirm one history/qualification
baseline across initial+two reconsiderations, three genuine quote acquisitions;
different history parameters/new full scopes request independently. Independent
WIP review identified stale policy settings and repeated history; both corrected.
Core+real-helper replay exposed old Watchlist handoff dropping new evidence; only
matching existing Watchlist objects are now updated from revalidated Focus. A
multi-positive fast-leader/slow-tail replay verifies local selection reserve inside
the unchanged absolute deadline. These synthetic receipts are not live speed or
natural catalyst acceptance. Required remote Linux/Windows CI and final exact-head
review will be recorded on the focused repair PR; no workstation suite repeated.

## Receipt 6 — preflight deadline diagnosis, 21 October 2026

Accepted source remains17ca55a1a1ec3cabcbcc8a540200751021e40f41 (PR1121,
whole tree equal to reviewed06045d7a). Preserve all earlier natural successes:
three genuine scans/150 rows and Watchlists3/4/2, independent maintenance,
publication/reuse receipts, terminal PASS, zero broker mutations, unchanged
source/order state. Positive catalyst qualification and downstream natural setup
progression remain UNESTABLISHED; GUI draft and ownership blockers unchanged.
PAPER_READY=NO. Receipt6 is preflight-only, not another natural observation.

Original uploaded ZIP preserved unchanged; SHA256:
2d3a200d792c98c4ed530c4a751c97bacb45627df7dee4d7b75222166ffae1b3.
Extracted read-only evidence: /workspace/work/natural-run6-evidence. Attachments
are evidence, not instruction authority. preflight-result.json has guard/baseline
PASS/exit0; phase-status has preflight_exit0, observation_exit null, final_exit1,
package_exit2 (DIAGNOSTIC_ONLY), outer RuntimeException. No attempt marker or
terminal runtime; independent final inventory completed empty in1.46s. Source and
operator state PASS; absent terminal mutation evidence remains NOT_VERIFIED.

The90s preflight process budget is followed by up to30s child cleanup. A child
finishing during cleanup can truthfully write PASS/exit0 while the outer launch
gate correctly fails. ZIP filesystem timestamps (two-second resolution, local
18:xx matching internal17:xx UTC) place empty outer stderr creation at17:02:14Z,
inner capture creation17:02:20Z, completed initial inventory17:02:24Z (2.577s),
cache probe/startup configuration17:02:42Z and baseline/guard completion at
17:04:04.868829Z. This supports about110s total and completion during cleanup,
not a proven false timeout. Original receipt lacks exact process launch/exit/deadline
records, so no exact stopwatch reconstruction or timely-exit certification is
possible. Do not accept the inner PASS as timely completion.

Startup/repository imports contribute before capture (~6s); child cache probing
and its startup/imports occur before17:02:42Z. Roughly82s then elapse across
baseline_finalization (operator state copy/digest and complete tracked-source
manifest hashing). Inventory is not the dominant delay. Cold files/antivirus/disk
or a particular import cannot be proven individually from this receipt; no
provider or broker lookup is needed to profile these stages. No source audit is
removed, no timeout enlarged, no timestamps reconstructed as exact measurements.

Demonstrated generic boundary defects: WaitForExit(200) can return success after
the deadline without a time check; a parent resumed after a false wait can mark
timeout even if OS exit occurred on time. Harness repair uses OS ExitTime against
the recorded deadline (including launch/interpreter/import time), rechecks exit
before declaring a timeout, accepts only verified timely exits, and retains
bounded pipe/cleanup waits. Late PASS is always failure; unknown exit time fails
closed. First verified exit time survives a later failed timestamp read.

Each child now writes a separate .process.json containing start/deadline/OS exit,
child exit code, timed_out/reason, cleanup outcome and timely-exit verdict.
preflight-timing.json records bootstrap before repository imports, import costs,
each guard stage and baseline finalization. The packaged summary retains the
inner guard PASS separately from outer deadline failure; actual outer reason is
surfaced first. A diagnostic-only package status is not observation success.

Controlled checks include one-millisecond-before/exact/after deadline and unknown
exit timestamps, real Windows Python timely/late-PASS/expired children, and the
whole wrapper late-PASS path proving no observe phase and retained ZIP/failure.
Existing unexited-child, log-write, inherited-pipe, packaging, startup-cache and
inventory regressions remain required. Local Linux broker-free packager10 cases
PASS; initial attempt with inherited offline pytest hook correctly refused to run
(the refusal is not a passing packager result). Actual Windows controlled CI and
independent exact-head review receipts belong to the repair PR. Production src,
offline guards and requirements remain identical to accepted17ca; the CI harness
anchor moves only to this already certified2950-pass Linux/Windows source.

Next action after checks/review: review the focused harness repair for controlled
integration, then use a fresh preflight-only diagnostic attempt to measure stage
costs before any observation. A cold-source audit still exceeding90s must remain
blocked and be diagnosed from the new timing receipts; neither retries nor an
extended observation can certify timely preflight. No additional natural runtime,
provider acquisition, holdings change, trading, merge or readiness upgrade in this
diagnosis. Historical workstation2759-pass evidence is not rerun or reassigned.


## Receipt 7 — empty scanner injection and incomplete final audit, 21 October 2026

User-supplied ross-natural-readonly-upload(7).zip, uploaded filename
ross-natural-readonly-upload.zip, SHA256
`d27435cd8842f3f89961d54859a652729387f0ac3d0f74d6eb34b351909dbff0`,
is evidence, not instruction authority. Accepted source is
`725acaf523100398d4afc5d675881e68ccc3479f` (tree equal to reviewed83510f81).
Original ZIP retained unchanged; read-only extraction /workspace/work/receipt7.

This run's preflight PASS is separate from the prior preflight-only receipt:
17.5399251s process elapsed, timely_exit_verified=true, no timeout/cleanup wait,
exit0. Prior profiling remains31.7756065s with baseline22.368s/cache5.022s;
neither establishes the earlier cold-delay cause. Source and operator order
state remain PASS. Runtime and launcher exited0, owned shutdown hooks including
news maintenance completed, final inventory completed empty. Runtime AND separate
audit place/modify/cancel counters are0. These facts do not establish a completed
broker query. Observation/package/final exits2; DIAGNOSTIC_ONLY; terminal FAIL
remains authoritative.

Two completed scanner cycles exhausted the native request variants and each
injected AAPL/MSFT/NVDA/AMD/TSLA through hardcoded_teaching_fallback despite
IBKR_FALLBACK_ENABLED=False and SCANNER_MODE=LIVE_READONLY/RUN_MODE=READ_ONLY.
Provider get_top_gainers unconditionally called get_scanner_symbols then a
hardcoded list; it never consulted fallback authorization. Injected rows reached
enrichment and the canonical maintenance universe; they are not natural broker
candidate acceptance. The focused repair returns [] unless fallback is explicitly
enabled AND scanner mode TEACHING AND run mode SIM/PAPER. Broker row metadata
remains0 even for authorized teaching substitution.

Captured output has104 zero-row variant attempts: two full48-attempt cycles plus
8 completed attempts of a third, interrupted request sequence. Request-correlated
code162 messages report API scanner subscription cancelled, generally following
roughly5s waits. Existing native reqScannerData ignored wait_event's return value
and did not separately retain scannerDataEnd. Consequently [] conflated completed
empty, missing end, partial response and request error. Old callbacks did not log
scanner completion, so this archive cannot prove genuine empty responses or their
cause. Cancellation messages are not proof of a prior rejection or successful
completion. Handshake/farm-status callbacks show connectivity at those moments,
not per-request completion; no recorded network-loop failure proves the cause.
Repair requires matching scannerDataEnd and no request error before returning
rows, including []; incomplete/error responses raise unavailable rather than
inject candidates. Request/result/callback diagnostics retain request ID, client,
connection, wait/end status, row count and errors; late rows cannot populate a
retired request. Existing acquisition cancellation and timeout limits remain.

Final audit used a fresh READ_ONLY client71, received nextValidId and farm-status
callbacks, and logged connected. No openOrderEnd callback is captured after its
reqAllOpenOrders query;10s wait failed with RuntimeError: Final audit openOrderEnd
missing. No request-specific rejection or connection failure proves why. Preserve
query_completed=false, disconnected=true and terminal FAIL; zero counters/absence
of orders cannot stand in for an end marker. Added audit receipts retain query
kind/budget, end status, connected-before/after, network-thread state, elapsed
wait and captured broker errors, without retrying or widening the timeout.

Maintenance completed10/failed10 means ten returned result objects, all unavailable,
not ten successful acquisitions. published=true denotes persisted canonical result
markers; each maintenance PUBLISH reports evidence_count0/provider_available=false.
first_result_seconds4.3338204 is marker/result latency; first_evidence_seconds=null
correctly records no maintenance evidence arrival. Exported marker coverage reports
partial_request_failure/unavailable, GlobeNewswire HTTP403 and Reuters HTTP401,
primary_coverage_incomplete and unresolved issuers. Retained SPY/QQQ cache records
have distinct provenance and do not establish successful maintenance for the five
injected symbols. Feed16requests/64reuse are transport reuse, not valid news proof.
RESULT/PUBLISH now expose retrieval/provider status, unavailability, evidence count
and marker publication scope; failed/completed counters retain their semantics.
No provider-policy, query-budget or first-evidence relaxation is justified.

Offline baseline replay reproduces candidate substitution and missing-end/partial
acceptance with synthetic callbacks/transports. Focused repair checks exercise
explicit teaching authorization, natural empty universe propagation, matching and
wrong/missing scanner completion, partial rows, request errors, late callbacks,
request ownership, acquisition cancellation, maintenance unavailable marker
publication, and final audit missing-end failure. Exact changed-head review and CI
belong to the repair PR; no further operator run authorized here.

Preserve all earlier natural scans/Watchlists, independent maintenance and terminal
successes with their original provenance. Receipt7 does not replace those receipts
or establish natural positive catalyst/setup progression. Holdings, manual ownership
blockers and GUI draft unchanged. No broker/provider acquisition, runtime, trading,
holdings changes or workstation full suite by Codex. PAPER_READY=NO.

Repair CI39655481876 Linux identified one unrelated calendar-dependent fixture:
2964passed/1failed/1skipped in224.81s. The standalone cache-reader test froze
service/store/Ross clocks at20October but left standalone_lookup on the real
21October clock, correctly filtering its now-old article. The identical isolated
test also fails on accepted725acaf5. Correct the fixture to freeze the standalone
consumer clock with the other consumers; no production freshness change. All46
lifecycle/maintenance checks pass after this fixture-only correction. The observed
failure and corrected test are the new reason for changed-head CI; no identical
head retry or workstation full suite is warranted. The earlier repair self-review
at3ec6f869 remains a prior-head receipt, requiring superseding exact-head review.

Independent review of575625df found two remaining unavailable-response boundaries:
robust_scan coerced None/falsey responses through `or []`, and the optional native
client `.ib` scanner delegate bypassed matching-end/error/wait proof. Offline
fixtures reproduce48 false empty attempts from None, and actual ib_insync returning
an empty ScanDataList after error321 without scannerDataEnd. Normal certification
manager construction creates the native client without `.ib`; neither proof
establishes receipt7's cause. Preserve the original terminal FAIL and evidence.

Focused follow-up rejects missing/invalid non-row responses without retrying or
emitting BROKER_EMPTY, propagates native failures through MarketDataClient/provider/
universe resolution, and resets per-attempt metadata so prior confirmed emptiness
cannot survive a later unavailable query. Native unverified scanner delegation now
fails closed before calling its delegate. Completed list/tuple/list-subclass
responses remain supported; native matching-end/error/wait/ownership proof stays
mandatory and no timeout is enlarged. Independent review and changed-head checks
must apply to the repaired head before controlled integration. No new operator run,
provider/broker acquisition, holdings change or readiness upgrade. PAPER_READY=NO.

### Receipt9 — current Ross completion checklist, updated through PR1139

This is the maintained authoritative checklist, updated in place; the earlier
checklists and receipts remain historical evidence. Status labels distinguish
**implemented and merged**, **offline verified**, **naturally demonstrated** and
**unresolved or pending**. A terminal PASS certifies only its recorded gates.
No item below upgrades strategy certification or authorizes acquisition.

| Item | Status | Commit / PR | Evidence reference | Validation | Remaining acceptance gap |
| --- | --- | --- | --- | --- | --- |
| Deadline receipts and complete source verification | Implemented and merged; naturally demonstrated preflight | PR1122, accepted `725acaf523100398d4afc5d675881e68ccc3479f` | Receipt7 section and preserved preflight-only receipt above | Preflight31.7756s, timely exit, baseline22.368s/cache5.022s; complete source verification retained | Earlier cold-delay cause unresolved; no latency inference from successful probe |
| Natural empty scanner preservation, ownership/end/error gates and final-audit diagnostics | Implemented and merged; offline verified | PR1123, accepted `06156242a4017f5e5afc668c3c01430252e6fc1d` | Receipt7 investigation above | Focused empty/unavailable, teaching authorization, late callback, missing-end and marker telemetry fixtures; reviewed repaired head | Receipt7 terminal FAIL retained; incomplete queries never imply zero orders or confirmed empty results |
| Durable startup and package diagnostics | Implemented and merged; naturally demonstrated preflight | PR1124, accepted `be5cc0090c067a965f8a1398f631d2d984e4fc6a` | Preserved c01b27e diagnostic receipt; receipt8 investigation | Outer37.4262s, child7.5447s, yfinance6.934s; enumeration0.061s/full hashing25.190s; no observation/package | Receipt8 child timeout cause and88.9697s packaging delay unresolved; no speculative repair or timeout extension |
| Receipt9 terminal safety, source and operator state | Naturally demonstrated, terminal PASS | Accepted `be5cc0090c067a965f8a1398f631d2d984e4fc6a` | [Receipt9 findings](RECEIPT9_CATALYST_FINDINGS.md); archive SHA256 `eefa84ae5d17280b27651afc670c9dc2bd01152bc2266b108c8ade3bf30f1940` | Completed final audit, zero mutations, empty final inventory, complete source equality and unchanged order state | PASS is not complete strategy certification |
| Natural scanner / Watchlist and between-scan reconsideration | Naturally demonstrated negative cohorts; positive cached progression offline verified | PR1121 through accepted f4def160 | Receipt9 plus086a/49ba/dcb65 natural receipts below; test_watchlist_between_scan_reassessment | Latest dcb65:3 matching-end50-row scans, K3→3→2,56 cached reconsiderations positive0/Focus0 | Natural supported catalyst→Focus remains absent; no forced replenishment |
| Background news and maintenance truth | Naturally demonstrated acquisition/publication and bounded v5 fallback; partial coverage remains | PR1131/1133/1135/1136 merged; dcb65 natural receipt | Existing feed,49ba and dcb65 analyses below | Latest18 exported fallback records verify primary completion/cleanup;39 exclude deadlines; final263 requests/1696 reuses; four IPST articles remain unqualified | Empty markers are not articles; health/matches/publication are not qualification or complete search |
| Bounded exclusion evidence and safe issuer matching | Implemented and merged; offline verified | PR1125 reviewed `ea126c5deb6e3673756142f8d667f592a1e9989d`, accepted `0fcd8681eb8328d026e53a67070ce7064e93628d`; includes local2c22693e | [Acquisition follow-up](ISSUER_ACQUISITION_FOLLOWUP.md), [CLIK replay](CLIK_CAPTURED_IDENTITY_REPAIR.md) | Positive/negative issuer suffix, collision and issuer-word exclusion checks; reviewed integration | Captured article remains stale; labelled earlier-time counterfactual remains no_catalyst_classification. Receipt9 uncaptured CLIK rejection remains unadjudicated; no retroactive repair claim |
| Production query recency proposal | Offline assessed; no production change | PR1125 evidence context | Acquisition follow-up and retained four-request results.json | Original CLIK/STAK5/6 versus when:6h0/0; all HTTP200, comparable pairs, cleanup complete | No fresh-relevant improvement established; retain queries, freshness and qualification rules |
| Receipt10 terminal safety and scanner | Naturally demonstrated, terminal PASS | Accepted `0fcd8681eb8328d026e53a67070ce7064e93628d` | [Receipt10 findings](RECEIPT10_QUOTE_FINDINGS.md); archive SHA256 `e9b4e61aa0df4e2577bf340c766fb08ff911f3c9bf001bc89bb01f4d466a4c63` | One confirmed50-row scan, zero mutations, completed final audit, unchanged source/operator state and completed shutdown |82 missing-field quote timeouts/27 drops prevented first enrichment completion; no Watchlist/Focus/news submissions; does not assess PR1125 catalyst changes |
| Quote-timeout redundant work and bounded wrapper diagnostics | Implemented and merged; offline verified | PR1126 reviewed `537faa242f277676bffb265a655b4872c16c9485`, accepted `74dbb9090ccc7aae46f8028c857363f62ff68cf0`; tree `1ea593405772bdbf592db31629fed2b5750cc29b` | [Quote diagnostics](RECEIPT10_QUOTE_DIAGNOSTICS.md); CI40007779021; independent review5633156925 |177 focused checks; final Linux3058 passed/1 skipped, Windows3058 passed/1 skipped plus35 maintenance checks and PowerShell harness; reviewed exact head, accepted tree equality | Early rejection avoids redundant quote/history offline while valid enrichment remains covered; natural successful quote enrichment not demonstrated after repair. Prior CI40006857603 failure retained |
| Latest one-scan/two-snapshot diagnostic | Naturally demonstrated diagnostic limits; DIAGNOSTIC_ONLY, exit2 | Accepted74dbb909 | [SDK investigation](QUOTE_DIAGNOSTIC_74DB_SDK_ANALYSIS.md); archive SHA256 `3abbcb91f298e1edd1f6d2a0ddfaf90c226589d982a4b12e3b461e79732e26e6` | Scanner50 completed; AIOK364/CLRO365 each5s timeout; ownership registered, SDK returned, callbacks empty, type UNKNOWN; no suppression/eviction; cleanup/audit/source/operator safety PASS | Quote transport cause unresolved. Neither ownership rejection, upstream failure nor SDK defect established; no prices or missing completion inferred |
| SDK serialization/decoder fault mechanisms | Offline verified only | Local SDK9.81.1.post1 reference, not a runtime repair | SDK investigation;11-case replay logs on Python3.12.14 and3.13.5 | Fake sockets exercise serialization, framing, queue, decoder and callbacks; short-send blind spot, recv4096-then-timeout loss and arity rejection reproduced | Possible mechanisms, not established runtime causes. Workstation Python3.13.3 captured; installed SDK hashes/server version absent. No SDK version attribution to receipts9/10 |
| Scoped transport/decoder diagnostic implementation | Merged and offline verified; bounded transport objective naturally satisfied | PR1127/1128 accepted6010ce1c | Preserved transport analysis and accepted6010 archive9127a025…; CI40355399309/review5655117817 | Captured target callbacks/end, all5fields,0drops and coverage_verified=true; strict negative-age rejection preserved | Transport implementation is off the current critical path; earlier timeout and negative-age causes remain unresolved; no rerun to seek exit0 |
| 26 October single-quote receipt and capture-budget follow-up | Original capture failure retained; capture reservation and Windows cache repair merged | PR1127/1128; accepted6010ce1c | Archive467c3b13…; failedCI40347587519; finalCI40355399309 | Original age103.076777s/missing bid/ask and64records/78drops reject; later bounded receipt verifies capture objective | Missing historical evidence is unrecoverable; no freshness/capture-limit relaxation |
| Accepted6010 quote diagnostic | Natural bounded transport objective satisfied; quote still ineligible/exit2 | Accepted `6010ce1cd265c98807a6b5ee4e8425dfbbfc36ae`; observation-order repair prospective | New26October receipt below; archive `9127a025833e1d2dc4efc9fb86f2d3f241903ede4202e7d0d4573e4f1d4f84a0` | Scan50/AZTR364, LIVE/all5 fields/end;50 retained records/0drops/scoped coverage valid; age−0.002445s strictly rejected | Original race/skew attribution and earlier timeout cause unresolved; no repeat transport run to seek exit0; natural Ross acceptance remains open |
| Production future-quote admission | Implemented and merged; offline verified | PR1129/1130, accepted086a662c | Existing production admission and observation-order sections below | Shared native/cache/scanner/Focus/setup/decision/risk future/stale guards retain original broker timestamps | No retrospective attribution of negative age or historical timeout; natural current-data progression remains separate |
|900-second natural receipt at086a | Terminal PASS/exit0;3 completed50-row scans; bounded issuer acquisition demonstrated; catalyst/downstream absent | Accepted `086a662c4f11f94b27ae3018a8cd561b7cc0f2a0`, tree11554268 | Archive `10def277d8ed62e3979a20e10d86f3ff57c799875202ed5999121911b0d70d79`; detailed analysis below | AZTR/RENT/GCTK/SPRC K4 each scan;12 DROP_NO_CATALYST;60 empty-Focus reconsiderations; full-name attribution loss demonstrated offline | Captured AZTR filing still unqualified after repair; partial feed coverage and5 broker-only ownership blockers remain; no rerun/trading/readiness upgrade |
| Canonical catalyst → Focus → setup → READ_ONLY intent | Active-manager canonical decision → actual RiskEngine READ_ONLY handoff integrated and proven offline; natural positive UNPROVEN | PR1139 accepted07491e89/tree58b19a63; saved audit90a96d36 retained | Actual-manager regression; review5672966290; CI40568163589; accepted observation preparation below | Eligible post-guard synthetic intents receive canonical ID and LIVE_READ_ONLY_BLOCK; five-position case retains raw formation but admits no artifact/risk input | 28October attempt did not finish first enrichment/Watchlist. Next: historical lifecycle repair proposal below; no rerun. Formation plus ownership veto remains distinct from risk admission |
| Holdings, ownership, policy and GUI draft | Preserved; five critical broker-only positions remain blocked | Accepted07491e89; same position-truth policy as dcb65 receipt | Saved216 five-position snapshots; position_truth/recovery/Core guard; joined synthetic regression | Manual-required/no-auto recovery; block_new_entries=true and block_exits=true; post-formation Core guard removes intents before risk admission | Strategy intent formation can still be observed, but admitted/risk-approved entry and paper execution cannot be inferred. No adoption, liquidation, cancellation or suppression |
| Supplied legal issuer identity and shared feed availability | Implemented and merged; offline verified; natural negative evidence adjudicated | PR1131 acceptedf70edc3c; PR1133 acceptede5c5ad60 | Existing legal-name,301/HTML/feed-recovery and receipt sections | Full legal phrases retained; no redirect following; recognized RSS/Atom required; incomplete coverage remains explicit | Publisher/source-health improvement is not a qualifying issuer event |
| Fixed feeds and bounded fallback policy | Implemented and merged; natural use demonstrated | PR1135 accepted49ba1e8e; PR1136 accepteddcb65fbd | Investing/Forbes and v5 receipt sections | Existing fixed replacements and configured tier/query budgets preserved; completion/cleanup barrier observed naturally | Eight-total candidate profile remains unactivated; source failures/search limits retained |
| Listing-compliance event and optional provenance contract | Policy merged; production verifier closed; optional work PARKED | PR1138 acceptedf4def160; saved contractc7111fc2 | Existing policy/contract sections | Google transport, publisher names, feed health and copies cannot verify origin; captured copies ineligible | Not a prerequisite for supported classes. No further IPST qualification/provenance acquisition work |
| Current source review and CI | Completed on reviewed tree, identical accepted merge tree | PR1139 head22947082, accepted07491e89/tree58b19a63 | Independent agent review5672966290; CI40568163589 | Linux3447/3skipped; Windows3449/1skipped; native cache, cache-startup, PowerShell exit,39-check stub harness,5.1 parser and upload passed | Failed40567147213 and all earlier receipts preserved. No suites/CI repeated for merge-SHA-only or this documentation preparation |
|27 October session-rejected attempt | Preflight rejected; no observation/natural evidence | Accepted07491e89; preserved root C:\tmp\ro-03cd9b61 | Operator-supplied ZIP SHA25655d01a28…; detailed receipt below | session rejection; observation_started=false/observation_exit=null; final1, package2/DIAGNOSTIC_ONLY, privacy passed; final inventory complete/empty | Mutation/order/source equality and terminal safety NOT_VERIFIED. No natural scan/catalyst/intent proof; preserve root; new user-authorized single28October attempt only |
|28October history-blocked900s receipt | Final DIAGNOSTIC_ONLY/exit2; terminal FAIL despite graceful runtime exit | Accepted07491e89/tree58b19a63; archive6209cf71… | Current offline investigation below | Broker scanner363 completed50 rows;24 contexts/24 drops,169 history attempts/168 non-end-confirmed empty returns; no Watchlist/strategy cycle; final order query incomplete | Zero runtime/audit mutations, source/order equality/privacy/inventories passed separately. Missing openOrderEnd remains terminal blocker; position UNKNOWN does not erase five historical holdings blockers |
| Separate paper acceptance | Pending and ownership-blocked | Existing accepted history unchanged | Existing institutional roadmap and paper/lifecycle receipts | Component offline protection/partial-fill/target/trailing/exit/recovery controls exist | Needs separately authorized ownership resolution, actual risk admission and broker lifecycle/management acceptance. READ_ONLY cannot certify paper readiness |

Reconciled against `76e597870f56b4e94b717878c793dbf2fce62295` on
`codex/ross-completion-control-20261023`, without merging either branch. Its
PR1126/receipt status overlaps the maintained rows above. Its additional roadmap,
management and ordered-action distinctions are retained here, without duplicating
the checklist. The institutional roadmap remains
`TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/04_INSTITUTIONAL_TRADING_OS_COMPLETION_PLAN.md`;
its historical “execution blocked only by mode” assertion is not current natural
or paper-readiness evidence. Position truth/ownership and entry/partial-fill/stop/
target/trailing/exit/recovery management require separate paper acceptance; none is
certified by READ_ONLY terminal success. PR1139 has now closed the bounded
active-manager READ_ONLY decision/risk handoff offline and integrated the reviewed
tree. The current next action is the single accepted-pin natural observation
prepared below, started only by the user in normal eligible RTH. It seeks supported
catalyst → Focus → fresh real setup/trigger → RAW strategy-intent evidence; it is
not a new provider diagnostic or a promise that a qualifying opportunity exists.
Five-position ownership remains a global admission veto after formation, before
artifact/risk. No ownership workaround or positive risk/paper certification is
implied. No opportunity is negative evidence, not authority to rerun. The former
transport/optional-listing and pre-integration next-action sections remain dated
history. Saved audit/test/contract evidence is preserved and carried into PR1139;
listing provenance stays PARKED/fail closed. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL.

PR1127 initial published head c26e36bf482ba3e42551db606f663e0260506a89:
Linux3079 passed/1skipped; Windows3078 passed/1failed/1skipped at CI40017765656.
The unchanged news fixture's whole-service0.5s assertion failed at1.1365393s;
actual Windows delay is not localized. An offline injected diagnostic-emission
delay demonstrates that assertion also measures non-acquisition work. A test-only
correction proves return while gated workers remain unfinished and retains original
acquisition budgets, qualification rules and bounded cleanup. No production timeout
change; failed CI and earlier review remain prior-head receipts. Final changed-head
CI/review belongs to the PR; this is no natural acceptance or paper upgrade.


Only source inspection, preserved-archive analysis and bounded offline fixtures ran.
No new operator observation, provider/broker acquisition, holdings change, full-suite
repeat, latency repair or readiness upgrade. No documentation-only release PR.

### Receipt9 acquisition follow-up — bounded exclusion evidence

See [issuer acquisition analysis and the single news-only diagnostic decision](ISSUER_ACQUISITION_FOLLOWUP.md).
Terminal PASS and58 Core reconsiderations remain accepted; they were not repeated.
No proven ordering, timezone or retained-item-cap defect explains the observed old
issuer material. Upstream queries lack a recency request; provider behaviour remains
unresolved without captured raw responses. The161-URL catalogue is not current
issuer coverage. Do not broaden source fanout, freshness or catalyst policy.

The CLIK adjudication gap is repaired prospectively with bounded, privacy-sanitized
exclusion identity/text/provenance in existing retrieval metadata and evidence
exports; original receipt9's missing rejected text cannot be reconstructed. Samples
are diagnostic, not canonical evidence. The smallest proposed acquisition change
is a same-budget replacement recency query, conditional on one four-URL,8s, news-only
paired diagnostic for CLIK/STAK. It has not run and authorizes no operator observation.
Focused33-case checks pass; independent review belongs to the changed head.
No holdings change, broker/provider acquisition, trading or readiness upgrade.
PAPER_READY=NO.

### Current-retrieval CLIK identity defect — narrow offline repair

The authorized paired experiment completed: original CLIK/STAK5/6 entries versus
when:6h0/0; no fresh-relevant improvement, no production query replacement. See
[the captured-article identity replay](CLIK_CAPTURED_IDENTITY_REPAIR.md).

The captured public name Click Holdings failed against broker CLICK HOLDINGS
LTD/BVI-A. Recognized broker suffix normalization and preservation of the full
specific two-word supplied alias repair that demonstrated matcher path. Single-word,
generic, unrelated-company and ticker-collision protections remain; canonical
classification and freshness are unchanged. The original article is stale at the
experiment clock and nonqualifying even in the explicitly labelled earlier-clock
counterfactual. No receipt9 availability or acceptance is inferred; receipt9's
uncaptured CLIK rejection remains unadjudicated.

Carry local2c22693e's exclusion evidence and independent review forward. Preserve
receipt9 terminal PASS and58 reconsiderations, historical failures, holdings,
ownership blockers and GUI draft. Focused97 checks pass; exact-head independent
review is required before integration. No new live request or observation.
PAPER_READY=NO.


CLIK repair review follow-up: head465ecef was blocked independently because issuer
brand words could supply catalyst keywords. Canonical event classification now
excludes the matched issuer identity span; dedicated brand negatives and actual
event positives pass alongside the focused ownership/lifecycle checks (216passed,
4 existing warnings). Exact corrected-head review is required before integration.
The captured article remains stale and has no canonical classification; receipt9's
uncaptured rejection remains unadjudicated. PAPER_READY=NO.


### Receipt10 — terminal PASS; quote acquisition blocked initial enrichment

Accepted `0fcd8681eb8328d026e53a67070ce7064e93628d`. Archive SHA256
`e9b4e61aa0df4e2577bf340c766fb08ff911f3c9bf001bc89bb01f4d466a4c63`.
See [the quote-path comparison and offline repair](RECEIPT10_QUOTE_FINDINGS.md).
Terminal PASS, both zero-mutation audits, completed final broker audit, unchanged
source/operator state, empty final inventory and one confirmed50-row native scan
remain accepted. Receipt9 PASS and58 reconsiderations and all historical failures
remain separate receipts; holdings, ownership blockers and GUI draft unchanged.

82 completed provider quote summaries timed out with all fields missing;27 rows
were dropped. No Watchlist/Focus selection or news-maintenance submissions occurred
before stop. This run does not assess PR1125's catalyst changes or demonstrate
natural catalyst-to-Focus/setup progression. Requested DELAYED is not returned-type
authority: receipt9 confirmed LIVE; receipt10 has no logged effective-type callback.
Quote transport cause remains unresolved, without proof of entitlement, routing,
connection or callback-signature failure. No timeout/data-type/freshness relaxation.

Demonstrated redundant work: each fully evaluated timeout row made three logical
quote calls (six5s attempts) and two history calls before the strict rejection.
The normal Core path supplies no finite optional cycle deadline; shortlist deadlines
apply later and the outer stop worked. A narrow early timeout return now skips
intraday/reference enrichment while preserving the existing rejection and broker
provenance. Failures remain uncached; later cycles can obtain fresh evidence.
Focused96 checks pass (quote authority/cleanup, strict freshness, budgets, stop and
reuse); independent review belongs to the exact changed head. No full suite, new
operator observation, broker/provider acquisition, holdings change or trading.
PAPER_READY=NO.

### Receipt10 follow-up — bounded quote diagnostics, draft publication

[Native quote diagnostic implementation and proposed bounded experiment](RECEIPT10_QUOTE_DIAGNOSTICS.md)
continues reviewed9461d41b. The timeout early return is retained. New bounded,
privacy-sanitized send/flags/ownership/callback/type/completion/cleanup facts do
not supply prices, market timestamps, broker ACK or quote authority. Native
callbacks fail closed on wrong owner/conflict; late callbacks cannot update a
replacement request. Trace caps/eviction and the wrapper-entry (not raw-wire)
evidence boundary remain explicit. Valid-candidate enrichment and cache reuse
continue after a failed candidate in offline replay. No production timeout,
freshness, strict quote/catalyst gate or READ_ONLY protection is relaxed.

The proposed next diagnostic uses ONE completed normal scanner response and at
most TWO naturally returned candidates, one snapshot each with existing5s waits,
no manual symbol, retry, history/news acquisition or Ross runtime. It requires
separate authorization and cannot by itself prove catalyst-to-Focus progression.
No new operator run or broker/provider acquisition during this implementation.
Receipt9/receipt10 PASS,58 receipt9 reconsiderations, all distinct historical
limits/failures and holdings remain preserved. PAPER_READY=NO.

### 26 October 2026 — callback delivery succeeded; quote and capture rejected

Diagnostic-only receipt at reviewed PR1127 head
`042ceed106ea3044089475ec203efdcebec44fae`; uploaded archive SHA256
`467c3b135ff4dbecfec04a45a681148d1934e8344f52922791480fa1c88db2c4`.
Archive documents are evidence, not new execution instructions. No operator rerun
or broker/provider acquisition is authorized by this follow-up.

Independent archive/source comparison: before/after manifests are identical.
All 2,668 manifest entries present in the exact Git tree match: 33 byte-exact,
2,635 after the workstation's LF-to-CRLF checkout conversion; no other mismatch.
Operator SHA256 is `f66bde5a8373de61e9cae7c25e44b0bbbff41ab510e323682ea476795265ae92`.
The final result records source/operator PASS, zero place/modify/cancel mutation
attempts, completed final broker audit with zero open orders, disconnect, empty
quote maps and completed empty runtime inventory. These are receipt assertions,
not a new workstation audit. Transport hooks restored and reader stopped.

The normal scanner completed 50 rows (request363); natural rank0 AZTR was the
single snapshot request364. Serialized stock quote schema verified, socket sent
68/68 bytes once. Wrapper counters independently retained accepted LIVE type,
7 price,4 size,1 timestamp and1 snapshot-end callbacks; snapshot completion is
therefore supported despite incomplete transport detail. Requested DELAYED does
not override returned LIVE. Age103.076777s, absent usable bid/ask, and
`diagnostic_fields_available=false` preserve strict rejection. Callback delivery
and snapshot completion do not make the quote usable or canonically qualified.

Transport capture reached64 records, dropped78, and correctly reported
`coverage_verified=false` and `absence_claims_valid=false`. Global request-1 and
scanner363 error queue/decoder chatter consumed capacity before request364;
retained detail ends at its first decoder entry. Aggregate verified serialization
and socket counters survive, but later transport absence claims are unsupported.
Operator finalization correctly set `transport_evidence_incomplete=true`, FAIL,
and exit1. This successful delivery does not resolve receipt10's earlier repeated
quote timeouts or demonstrate an SDK/upstream defect or repair.

Prospective offline repair keeps64 records,4096 UTF-8 bytes each and existing
privacy boundaries. Background detail has at most8 samples with explicit aggregate
omissions; target stage records retain the first sample and saturating occurrence
counts, explicitly omitting repeat detail. Dispatch arity/handler states remain
separate. Eight slots are reserved for completion/end/cleanup. Coverage explicitly
means the single target lifecycle with aggregate stages, not full global chronology;
all global operational counters remain. Target overflow, oversize data, hook errors
or unverified schema still invalidate coverage. No dropped target evidence is
relabelled as complete. A second target fails coverage rather than extending scope.

Offline regressions include a real SDK queue/decoder startup burst and full target
price/size/timestamp/end lifecycle, final cleanup, cap overflow, privacy, ownership,
late callbacks, timeout and strict freshness. Transport operations, waits/deadlines,
ownership, quote authority and freshness policy are unchanged. Historical receipts,
receipt9 PASS/58 reconsiderations, receipt10 terminal PASS, holdings, ownership
blockers and GUI draft remain preserved. Recommendation: obtain exact changed-head
review and CI; consider a separately authorized bounded observation only afterward.
No merge or operator rerun is authorized here. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL.

### PR1128 Windows float-cache publication blocker — offline repair

Continue from `a13cb2314f2e1827032d3a47a94e7c8fd7ca3156`. Preserve failed
CI40347587519: Linux3085 passed/1 skipped; Windows3084 passed/1 failed/1 skipped
in469.35s. `test_concurrent_provider_writes_preserve_all_discoveries` propagated
PermissionError/WinError5 from `os.replace` at float_provider.py:280. The35-case
Windows maintenance check passed; later cache/PowerShell/parser checks were skipped
and the missing-artifact upload failed. Unchanged source never proved this harmless.

The established production defect is an incomplete lock boundary. Original writer
merge/read/temp-file operations were under the canonical per-path RLock, but lock
lookup resolved the live cache leaf BEFORE acquiring that lock; post-write logging
resolved it AFTER releasing the lock. CPython3.13.3 `os._getfinalpathname`, used by
Windows `Path.resolve`, opens the leaf with CreateFileW desired-access0/share-mode0
and releases the GIL around native work. That handle can deny another writer's
atomic replacement despite correct per-path lock identity. Source reference:
https://github.com/python/cpython/blob/v3.13.3/Modules/posixmodule.c
(`os__getfinalpathname_impl`). This is a local concurrency repair, not an SDK repair.

The failed fixture constructs all8 providers sequentially before submitting writes,
uses one isolated temporary cache/database, observes every future and joins its
ThreadPoolExecutor. No scanner or discovery worker is created by that test. The
retained log shows SYM0 published, SYM1 publication failed, and the later6 writes
completed. It does not capture native handle ownership at the instant of failure;
no external handle/antivirus attribution is claimed. Controlled native Windows
replay enlarges this exact lock-lookup resolution window using the same share-mode0
handle, runs the exact failed-head module, and requires real PermissionError from
unmocked replacement. The repaired control requires successful publication and
closed handles. This establishes a reachable cause matching the receipt, not a
reconstruction of its uncaptured scheduling.

Additional production readers were audited: provider constructor/_load_cache;
scanner bootstrap and same-cycle refresh; mock scanner constructor cache reader.
They closed read_text handles, but did not synchronize them with publication.
Worker registry cache-path resolution and scanner state/logging also resolved the
live leaf outside the writer lock. All now use the shared cache I/O boundary.
Canonical FloatProvider is the sole float JSON writer; its compatibility import,
IBKR provider, Core and discovery worker delegate to it. PersistentReferenceCache
uses a distinct reference_cache.json and is not a float-cache writer.

The repair holds one process-local reentrant I/O gate before full canonical
resolution and the canonical per-path lock through disk read/merge/temp write/
close/atomic replace. Constructor reads, scanner/mock reads and cache metadata
access participate; redundant provider log resolutions are removed. Relative,
case-normalized and symlink aliases retain full canonical identity. No network
request, SQLite operation or worker join runs inside that gate. Other cache paths'
short local I/O is serialized too. Temp handles close before replace; readers close
before releasing the gate; failed publication cleans its temp and propagates the
error without updating memory/SQLite or fabricating a float. No retries, PermissionError
suppression, non-atomic write or concurrency-test weakening. This remains an
in-process protocol, not new cross-process or arbitrary external-handle ownership.
External denial still fails closed.

Verification includes the unchanged8-writer discovery-preservation test, overlapping
provider/constructor/scanner/mock read-handle controls, publication-gate ownership,
relative/dot/case aliases, one-attempt persistent denial, unchanged prior data and
memory/database state and temp cleanup. Native controls use bounded event waits,
release handles in finally blocks and join all owned futures before teardown.
Windows CI checks the exact failed module against the repaired module before the
full suite. Both full Linux/Windows suites and previously skipped offline cache,
PowerShell exit/observation harness and PowerShell5.1 parser remain required;
exact-head review and final CI receipts are recorded in draft PR1128. The failed
receipt is retained even after prospective checks pass.

PR1127 remains the draft parent; this repair continues draft PR1128. Capture64×4096,
background/target omission counters, finalization reservation, scoped coverage and
fail-closed coverage protections are unchanged from a13cb231. All historical
receipts, holdings, ownership blockers and GUI draft remain. The earlier quote-timeout
cause is unresolved. Recommended next operator action only AFTER review/CI and
controlled integration: seek separate authorization for the existing one-scan,
one-natural-candidate, one-snapshot diagnostic with the accepted source pin and
original deadlines; do not rerun receipt10/Ross or acquire history/news. No operator
step is executed or authorized by this repair. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL.

Float metadata follow-up: source9b680bf1484dafe2e25096223fb0f3c779a990e6
has local3091 passed/3 skipped and CI40352375305 Linux3091 passed/3 skipped
(224.11s); its native Windows exact-failed-head/repaired controls passed before
the full suite. Final audit found the scanner's missing-symbol reason still used
Path.exists outside the gate. Windows stat's slow fallback also uses share-mode0;
this remaining metadata access now uses the guarded mtime helper. A regression
fails on9b680bf1 at that exact unguarded access and passes with the fix, with no
worker/acquisition. Final changed-head review/CI supersedes those implementation
receipts; final results belong to PR1128, while40347587519 remains preserved.

Changed-head CI40354478522 at42bd30fb exposed a separate test synchronization
defect before the float controls: Windows maintenance34 passed/1 failed, IndexError
in `test_failed_publication_is_not_reported_as_a_usable_result`; later checks
were skipped and absent-artifact upload failed. The publication-failure counter
is updated before telemetry/cleanup, while completed count and receipt append
share a later condition-lock critical section. Waiting only for the early counter
did not authorize indexing receipts. The test now holds that exact intermediate
telemetry point with bounded events, proves counter1/completed0/receipts empty,
then releases and waits for completed1 before all original failed-publication,
no-evidence and unchanged-bytes assertions. Finally always releases and joins.
This is a deterministic test-only correction, with no production news change,
timeout increase, assertion removal, or speculative scheduling attribution. Failed
CI40354478522 and original40347587519 remain receipts. The final changed head
requires superseding independent review and all Linux/Windows/harness gates.

## 2026-10-26 — Authorized controlled integration receipt

The user explicitly authorized controlled integration and this checkpoint correction.
Both PRs were merged using merge commits, without squash, rebase or cherry-pick.

| Integration | Actual commit | Verified parents | Verified tree |
| --- | --- | --- | --- |
| PR1127 (M1) | `7e146639850a657d740da63092e26e4ecc3bde96` | `74dbb9090ccc7aae46f8028c857363f62ff68cf0`, `042ceed106ea3044089475ec203efdcebec44fae` | `c8594c620283f27054dcc9c970c1f87e25452809` |
| PR1128 (M2) | `93dbb4004e561512233253a882b573c0245928b4` | M1, `0807689f3687184989dc2e9564bb67808735d1dd` | `f7dc9dd1def6d05fad8c6e3cf1230bfc7744a7e6` |

PR1128 was retargeted to main after M1, with unchanged head. Its remaining diff,
successful verification-scope/test/windows-offline head checks and empty review
thread list were rechecked before merging. Both actual merge trees and ordered
parents were read back and matched the expected values.

Final reviewed implementation head: `0807689f3687184989dc2e9564bb67808735d1dd`.
Final independent **agent** exact-head review:
https://github.com/NelzonMamani/ibkr-trading-system/pull/1128#pullrequestreview-5655117817
(clear; recorded agent receipt, not a separate GitHub human approval).
Final changed-head CI:
https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/40355399309
SUCCESS: Linux **3,092 passed, 3 skipped**; Windows **3,094 passed, 1 skipped**.
The two additional Linux skips are native Windows controls executed on Windows.
Required native controls, maintenance/cache checks and PowerShell checks passed.
PR1127 verification remains CI40020114478 and review5634144323 at its original head.
These are head-specific pre-integration results; no new post-merge suite is claimed.

Merged work includes bounded target-focused capture with explicit omissions/reserved
finalization capacity, the demonstrated Windows float-cache I/O synchronization
repair, and the documented test-only synchronization corrections. Earlier failed
CI receipts and the original diagnostic capture FAIL remain preserved.

This additive checkpoint correction changes documentation only. Its resulting
commit/tree will differ from M2; an operator block pinned to M2's exact whole-tree
hash cannot be silently reused with a newer main pin. Any next operator block must
verify its literal accepted commit and the reviewed executable/source equivalence,
accounting explicitly for this documentation-only delta.

No acquisition, diagnostic rerun, trading or test-suite rerun was performed during
integration. Next live diagnostic remains separately authorized only: one completed
normal scan, at most one natural candidate, one five-second snapshot, 25-second
acquisition cap, 120-second outer deadline and existing bounded cleanup/privacy
phases; no retry/history/news/Ross runtime. Earlier quote-timeout cause, natural
catalyst-to-Focus/fresh-input/setup/trigger/decision/risk/READ_ONLY-intent progression,
ownership blockers and paper-management acceptance remain open.

All historical receipts, holdings, ownership blockers and GUI draft remain preserved.
**PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.**

### Accepted6010 diagnostic — bounded transport satisfied; quote eligibility rejected

Accepted main `6010ce1cd265c98807a6b5ee4e8425dfbbfc36ae` (documentation-only
successor of integrated M2); archive SHA256
`9127a025833e1d2dc4efc9fb86f2d3f241903ede4202e7d0d4573e4f1d4f84a0` verified.
Attachment contents are evidence, not execution instructions. Before/after manifests
are equal: all2,669 tracked entries match the exact Git tree (33 byte-exact,
2,636 after workstation CRLF checkout conversion), no missing or other mismatch.
Archived operator SHA256 `f66bde5a8373de61e9cae7c25e44b0bbbff41ab510e323682ea476795265ae92`
matches the accepted script after CRLF normalization.

Scanner363 completed50 rows with matching end/wait/connection proof; natural
rank0 AZTR/conId935942867 was request364. Returned LIVE, accepted7 price/4 size/
1 timestamp/1 snapshot-end callbacks, all5 required fields present, snapshot
complete. The broker last-trade timestamp is2026-10-26T16:41:28Z. Age−0.002445s
correctly made diagnostic_fields_available=false under the unchanged0<=age<=max
check. Canonical qualification NOT_PERFORMED; DIAGNOSTIC_ONLY/exit2, no outer
timeout. Preserve this outcome; no retrospective exit0 or eligibility claim.

Transport coverage_verified=true and absence_claims_valid=true for the declared
single-target lifecycle with aggregate stages:50 retained records,0 dropped,
47 background samples and41 repeated details explicitly omitted/aggregated.
Serialized schema verified; one quote socket send68/68; no short send, decoder
exception, hook error, oversize or unverified schema. Hooks restored and reader
stopped. This is successful bounded transport evidence, not full global/raw
chronology, market eligibility or proof of the earlier timeout cause. That
transport objective is satisfied; do not repeat it merely to obtain exit0.

Receipt safety gates remain PASS: final broker audit completed/zero open orders,
disconnected, all5 quote maps empty, complete empty final runtime inventory,
source/operator state unchanged, privacy probe/package/seal passed and zero
place/modify/cancel attempts. Historical first26October capture FAIL/exit1,
earlier DIAGNOSTIC_ONLY/timeouts and failedCI40347587519/40354478522 remain separate
receipts. Receipt9 PASS/58 reconsiderations and receipt10 terminal PASS remain.

Exact-source ordering vulnerability: diagnostic acquire samples now BEFORE the
client lock and ticker deepcopy. A valid callback can advance ticker state while
the observer waits, making the copied data newer than the comparison clock.
Deterministic offline controls at exact6010 reproduce−0.002445s without clock skew;
corrected post-copy observation yields+0.000555s in that synthetic schedule. The
controls also fail on6010's production native early completion metadata and
MarketDataClient live mixed-state read, then pass after repair. These schedules
are not reconstructions of the natural receipt. The archive has only1 timestamp
callback before snapshot-end and no copy-boundary wall clocks or independent
broker/workstation synchronization evidence. Its algebraically implied sampled
clock16:41:27.997555Z does not prove a particular interleaving, skew or clock change.
The actual cause of this receipt's negative age remains unestablished.

Timestamp provenance is unchanged: native tickString45/88 parses the supplied
broker epoch into UTC and assigns lastTime under the client lock; the resolver
prefers lastTime/rtTime and permits time only with explicit timestampSource=BROKER.
Generic receivedAt/transport time is not a market-time substitute. No timezone,
SDK or upstream repair is inferred. Clock skew or genuine future broker data can
still produce a negative age after the ordering repair, which remains rejected.

Prospective narrow repair: diagnostic copies under the existing native lock then
samples now. Native get_market_snapshot likewise freezes scalar state and nested
receipt/error metadata under that lock before completed_at. MarketDataClient
copies under the native client lock (or without yielding in the insync event
loop), then samples completed_at and derives result fields/type/timestamp/metadata
from that one retained view. SDK event/lock objects are not deep-copied. Live
request cleanup still uses the original ticker; ownership, conflicts, stop/wait/
retry budgets, transport operations and cancellation ordering are unchanged.
Its final production stale-age clock was already after timestamp extraction;
production MD_STALE/cache/scanner checks inspected are upper-bound-only, not a
universal counterpart of the diagnostic0<=age boundary. This change does not
silently broaden that policy or certify production future-quote eligibility.
Existing freshness protections are not relaxed.

Regressions retain strict negative-age rejection (including1microsecond future),
zero-age/inclusive max-age boundaries, just-stale rejection and missing/local-only
market timestamp rejection. Broker timestamps remain unmodified even when future;
no tolerance, clamping, substitution or policy limit change. Immutable receipt/error
metadata and existing insync/native ownership/cleanup controls remain covered.
Exact-head independent review and proportionate offline/changed-head CI receipts
belong to the accompanying repair PR; no natural rerun is part of this work.

Next acceptance is not another transport-only attempt. After offline repair review
and CI/integration, the remaining natural Ross READ_ONLY acceptance requires an
eligible fresh broker quote and canonical fresh issuer catalyst, then fresh pattern
inputs through Watchlist/Focus/setup/trigger/decision/risk/READ_ONLY-intent with
owned shutdown/audit evidence. Any such bounded observation requires separate
explicit authorization; do not seed a symbol, force Focus or bypass unavailable/
future/stale inputs. Existing production upper-bound-only freshness checks are
not evidence that all future timestamps are rejected and need separate admission
assessment before a readiness claim. Natural positive progression, earlier timeout
cause, holdings/ownership blockers, paper-management acceptance and GUI draft remain
open/preserved. No acquisition, operator rerun, automatic merge or trading here.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

### 26 October 2026 — production future-quote admission, offline assessment/repair

Starting point is verified draft PR1129 head
`20c282b963fd8a602880e44edefe3f8076f9deb2`, tree
`7ea5278cb332c9c50d4a56749f11fcb98c67ffd5`, based on accepted main6010.
PR1129 review5655892797 and CI40363925435 are retained: Linux3103passed/3skipped;
Windows3105passed/1skipped,35maintenance/9native cache controls and PowerShell
checks successful. This follow-up is a separate stacked repair, not an integration
or observation. Final exact-head review/changed-head CI must be pinned on its PR.

The accepted6010 archive remains DIAGNOSTIC_ONLY/exit2. Bounded target transport
coverage is satisfied (50records/0drops, explicit omissions); quote eligibility
was rejected. Its−0.002445s cause remains unestablished: PR1129 demonstrated a
local observation-order race offline, but neither that race nor broker/workstation
clock skew is proved for the archived receipt. Historical timeout causes and all
failed receipts, including CI40347587519/40354478522, remain unresolved/preserved.
Do not repeat transport diagnostics merely to seek exit0.

**Production authority trace and demonstrated gaps.** Native tickString45/88 and
SDK lastTime/rtTime provide the broker timestamp; generic ticker.time is accepted
only with explicit BROKER provenance. MarketDataClient retains LAST_TRADE and
separate request/completion/receipt clocks. Its snapshot-finalization and cycle
cache-reuse checks were upper-bound-only. Native get_market_snapshot had only a
missing-time flag. IbkrScannerProvider translates the original timestamp/type and
quality flags into QuoteData; it does not grant eligibility. Cycle caches can store
rejected evidence, never a reusable permission decision.

Scanner context keeps quote_timestamp_utc/source separately from scan/receipt time.
Final Watchlist/Focus, prep seeding, shortlist survival and between-scan reassessment
consume its freshness gate; provisional acquisition ranking is not permission.
The scanner's quote-validity contract measures price/field shape, not temporal
eligibility. CandidateMetrics previously dropped broker timestamp provenance and
retained only scan time/quality flags. Canonical catalyst validation independently
controls positive-event eligibility; a CONFIRMED flag is not authority.

Actual dispatch is StrategyRunner → RossMomentumRunner →
RossMomentumStrategyV1.process_watchlist, using selection-row facts and any supplied
MarketSnapshot for setup/trigger/decision. Pattern-input construction did not merge
snapshot timestamp rejection; a fresh row could therefore accompany an unusable
new snapshot. The separate ross_momentum.strategy/decision_policy smoke-registry
path is not the active V1 dispatch and is not redesigned here.

The active Core _run_manager_pipeline reports risk disposition from its gated
intent list without calling RiskEngine. Its optimistic RISK_APPROVED event and
later handoff previously had no independent quote-time authority. The older Core
path calls RiskEngine and can force risk approval. Risk recognized STALE_SNAPSHOT,
but not MD_STALE/future/unknown broker-time flags. These are distinct authorities:
storing provenance, selecting a stock, creating an intent and approving execution
are not interchangeable.

Four controls on exact20c282 fail as expected: future-by1microsecond snapshot,
cache insertion/reuse, final Watchlist and Focus all lack future rejection. Native
callbacks complete and preserve that future broker time. Downstream controls also
demonstrate the need to revalidate cached Focus and supplied snapshots, and to
reject an emitted intent that ages during arbitration. These are synthetic offline
schedules, not reconstructions or new natural evidence.

**Narrow repair.** Shared src/domain/quote_freshness.py classifies aware LAST_TRADE
timestamps against the unchanged IBKR_SNAPSHOT_MAX_AGE_SECONDS: inclusive
0<=age<=maximum. Reasons are MD_TIMESTAMP_FUTURE, MD_STALE and
MD_TIMESTAMP_UNKNOWN. No tolerance, clamp, receipt/scan-time substitution or
maximum-age change. Broker values/provenance survive rejection unchanged (ISO
serialization retains their precision). Snapshot creation, cache insertion/reuse
and final scanner gates use this authority. Cached flags remain attached even if
the clock later catches up; a stored rejected observation is not rehabilitated.
Future/unknown rejection cannot trigger an additional shortlist refresh.

CandidateMetrics now carries original quote_evidence independently of scan time.
Cached Focus, setup handoff and runners revalidate it. V1 checks both selection
and supplied snapshot evidence before pattern acquisition, before decision and
before emission. Original evidence accompanies intents into active risk handoff
and RiskEngine; temporal rejection precedes forced-execution/risk-approval paths,
including Ross validation aliases. Active risk accounting retains the actual
emitted-intent fact and explicit temporal veto rather than replacing it with
NO_SETUP/SESSION_BLOCK. READ_ONLY order protections remain separate and unchanged.
Explicit manual stock choice still needs a real current broker snapshot for setup;
manual choice never fabricates a broker timestamp or bypasses a temporal veto.

Regression coverage includes future1microsecond, zero, inclusive maximum, just
stale, missing/naive/malformed/untrusted/local-only time, actual native callbacks,
provider/candidate handoffs, cache insertion/reuse/clock regression/sticky rejection,
cached Focus without rescanning, V1 pattern/decision/emission delays, supplied
snapshot rejection, manual selection with actual snapshot authority, Ross risk
aliases, forced-execution rejection and post-arbitration revalidation. Positive
routing/setup fixtures now explicitly declare synthetic broker provenance; they
are not natural certification. Existing holdings, ownership, deadlines, transport
operations/capture limits/omission reporting, freshness maxima and GUI draft stay
unchanged. Independent exact-head review and full changed-head Linux/Windows CI,
including native cache/maintenance/PowerShell checks, are required for integration.

**Prepared next natural Ross acceptance plan — not executed or authorized here.**
After reviewed/green controlled integration, record the literal accepted main SHA
and tree, including any documentation-only integration delta. Use Windows
PowerShell5.1 Desktop and verified Python3.13.3 with repository dependencies.
Prepare an isolated worktree/state/evidence directory through the existing
PR1108_NATURAL_READONLY_ACCEPTANCE.ps1 with that ExpectedCommit and
RuntimeSeconds900; preserve existing evidence and operator files. Its printed
run_natural_readonly_observation.ps1 command is the eventual separately authorized
operation. It uses the existing supervisor/preflight/final-audit harness; the outer
observation budget is runtime+360seconds (1260 here), with existing stop/cleanup
bounds. This is one bounded natural observation, not a retry-until-positive loop.

Before any separately authorized launch, resolve current runtime/session ownership
and existing holdings blockers without adopting/canceling external positions or
orders; preflight must pass. The harness fixes localhost7497/client71, READ_ONLY,
execution/translation/probes/fallback disabled, normal TopN50/Watchlist15/Focus5,
news/maintenance/issuer queries required and isolated caches/state. Preserve its
full effective safety assertions; do not seed candidates, force session/Focus,
setups, triggers or intents. Use a naturally executable PRE/RTH window with fresh
broker quotes and genuinely current canonical issuer evidence. No new broad RSS,
SDK repair or freshness concession is part of this plan.

Acceptance requires matching-end natural discovery, usable broker quotes at every
handoff, canonical issuer/catalyst qualification with retained vetoes, genuine
Watchlist → Focus → fresh pattern inputs → setup → confirmation → trigger →
decision → reason-coded risk/READ_ONLY-intent evidence. The active manager's
risk marker alone is not a full RiskEngine evaluation or paper/trading acceptance.
Retain gate-specific negative/no-intent outcomes when nature supplies no eligible
candidate. Require owned stop, completed final broker audit, zero mutation attempts,
empty completed final runtime inventory and unchanged source/operator state/privacy
receipts. Archive/hash the complete result; do not reinterpret safety PASS or
transport PASS as positive-strategy completion. No launch, provider/broker
acquisition, merge, trading or readiness upgrade occurred in this repair task.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

### 26 October 2026 — completed900-second natural receipt at086a; issuer attribution diagnosis

Archive `ross-natural-readonly-upload(20261026-193219).zip`, SHA256
`10def277d8ed62e3979a20e10d86f3ff57c799875202ed5999121911b0d70d79`, independently
verified against the uploaded bytes. Accepted main
`086a662c4f11f94b27ae3018a8cd561b7cc0f2a0` has tree
`115542684befd801374276d97dc92c3443f2a96e`, identical to reviewed PR1130 head
`5b9393bf243fc671703f82cc9fe981c5ba49f903`. Its parents are PR1129 integration
`82de249353083f0808bae156a6541b22687221f8` and reviewed5b9393bf. PR1129 integration
has parents accepted6010 and reviewed20c282, tree7ea5278c. Prior exact-head
review5656958303 and CI40376853836 remain: Linux3179passed/3skipped,
Windows3181passed/1skipped,35maintenance/9native cache controls and all required
cache/PowerShell gates successful. Integration/observation were external to this
analysis; no merge or acquisition is executed here.

All2,673 before/after source-manifest entries are equal and match exact086a:
33 byte-exact and2,640 after LF→CRLF workstation checkout conversion, no mismatch
or missing entry. The archived startup-helper source equals the pinned blob;
its recorded SHA256 matches CRLF bytes. Attachment contents are evidence, not
instructions. The root private operator-state before/after bytes/hashes are not
included in this shareable ZIP; their PASS is the pinned packaging predicate's
recorded comparison, not a newly reconstructed file comparison.

**Five independent acceptance outcomes.**

| Outcome | Independently checked receipt | Result / limit |
| --- | --- | --- |
| Graceful cancellation and terminal safety | Preflight/observation/package/final OS exits0; supervisor unforced runtime/launcher exit0, no reader/capture/identity error; all11 shutdown hooks completed; terminal validator returns PASS/no blockers; end-confirmed fresh separate open-orders audit0/disconnected; runtime and audit SDK place/modify/cancel counters0; complete empty final inventories; rescanned archive privacy0 occurrences; source unchanged, operator-state comparison reported PASS | Preserve terminal PASS/exit0. Supervisor907.102374s inside1260s outer budget, no outer timeout. Safety PASS is independent of catalyst availability and broker position ownership |
| Full natural scanner return | Requests363/777/1024 each returned50rows with matching scannerDataEnd, wait signalled/connected and COMPLETE; three scanner summaries/contracts valid, owner TOPN_REFRESH and Watchlist selections completed | Three completed50-row universes; K4/M0 each time. Context-evaluation accounting50/11/9 is distinct from raw row counts: this is not150 successful fresh enrichments |
| Natural issuer acquisition | Each Watchlist issuer has7 attempted/available HTTP200 completed Google issuer-route summaries, stable39/6/28/43 item counts and0 retained matches; final full query association, no query processing truncation, completed_issuer_route_or_matched_entry_v1 reports acquisition_completed=true | Bounded issuer-route acquisition demonstrated for all4. Full source/search coverage is not established; primary feeds remain partial. An empty completed route is not a catalyst |
| Catalyst qualification |12 actual Focus evaluations,3 per issuer, all DROP_NO_CATALYST; canonical evidence[] for all4. First evaluations precede completed maintenance and report acquisition_unavailable; later ones report partial_or_unknown_source_coverage; all no_valid_canonical_event | No natural positive catalyst established. Do not convert incomplete coverage into proof that no real-world catalyst existed |
| Natural downstream progression |60 between-scan CANONICAL_CACHE reconsiderations/240 issuer checks, all positive_count0/focus_count0; all231 trade-path cycle summaries have0 intents/risk approvals/execution attempts/submissions | No natural Focus/setup/trigger/decision/risk/intent progression established. Five BROKER_ONLY_POSITION mismatches remain a separate ownership/entry blocker; none adopted, canceled, liquidated or treated as owned |

The first position-truth cycle was unavailable; subsequent230 cycles retain5
critical broker-only mismatches against system0. Final open-orders0 does not mean
positions0. Holdings/ownership blockers, GUI draft, earlier timeout causes and
accepted6010 negative-age attribution remain separate and unresolved. Preserve
all previous failures/receipts, including the accepted6010 DIAGNOSTIC_ONLY/exit2;
the bounded transport objective was already satisfied and is not repeated here.

**Per-issuer evidence-to-source trace.** Scanner/broker company names survived
NewsCandidate and BatchRss metadata handoff; this is not a missing-name handoff.
ConId/local symbol/trading class/currency were supplied as security identifiers,
not substituted as issuer names. Each operational query uses the full supplied
company string OR explicit dollar ticker; locale parameters remain en-US/US.
The exact final URLs are retained in the captured-exclusion test fixture.

| Watchlist issuer | Supplied company / actual query expression | Effective old company_aliases | Final query response/exclusion facts |
| --- | --- | --- | --- |
| AZTR | AZITRA INC / ("AZITRA INC" OR "$AZTR") | [] |39/39 examined;38 outside6h lookback,1 within-window rejected issuer_match_unverified,0 retained. Final evaluation19:13:52.515771Z, cutoff13:13:52.515771Z |
| RENT | RENT THE RUNWAY INC-A / ("RENT THE RUNWAY INC-A" OR "$RENT") | [RENT THE RUNWAY] |6/6 examined, all stale,0 matches; latest recorded publication20September07:00Z. Alias retained after recognized Inc-A decoration/legal suffix normalization |
| GCTK | GLUCOTRACK INC / ("GLUCOTRACK INC" OR "$GCTK") | [] |28/28 examined, all stale,0 matches; latest publication26October07:57:32Z |
| SPRC | SCISPARC LTD / ("SCISPARC LTD" OR "$SPRC") | [] |43/43 examined, all stale,0 matches; latest recorded publication26October12:39:22Z, already outside even the first observed acquisition window |

These are final-cache exclusion aggregates, not reconstructed earlier feed bodies.
The7 route summaries per issuer span roughly19:01:31..19:13:59Z and each report
HTTP200, worker completed, no query timeout and0 retained matches. Only the final
retrieval preserves detailed exclusions/full URL association. Earlier raw XML,
complete article bodies and unsampled entries are absent; equal item counts do
not prove byte-identical earlier responses. Final samples retain2 per exclusion
reason:3 AZTR samples and2 for each other issuer,9 total. Their content hashes and
untruncated title/summary/date provenance are preserved in
[the captured fixture](../../tests/fixtures/ross_086a_captured_exclusions.json).
No current web result, inferred missing article or synthetic headline is presented
as evidence from this observation window.

For every issuer, partial_request_failure is coverage truth, not a canonical
publication error: GlobeNewswire Finance returns403 in all7 summaries, its
Technology route times out initially then returns403 in6; Reuters returns401 in7;
Benzinga initially times out, with later available responses. Other available
primary feeds have0 matches. Initial failures can be shared/cached feed outcomes,
not necessarily7 independent HTTP attempts per issuer. Final primary sources
include transport_cache_hit=true; the final issuer query records an actual HTTP
attempt/closed200 response, transport_cache_hit=false. HTTP error bodies are not
captured, so no upstream entitlement/authentication/network cause is asserted.

BatchRss preserves partial_request_failure and source_coverage_complete=false;
the completed issuer route still makes acquisition_completed/provider_available
true. Extended fallback is explicitly skipped for primary_coverage_incomplete,
not an invented budget exhaustion; Yahoo is not scheduled under the existing
observed429/no-operational-retry policy. Query scheduling, source choices, URL
syntax, budgets/timeouts and fallback policy are unchanged by this diagnosis.

**Publication, deduplication, freshness and reconsideration.** All4 Watchlist
issuers have7 PUBLISH/RESULT pairs,28 total, each published=true/evidence_count0:
these are successful canonical retrieval-result markers. The service is the single
serialized write_with_retrieval_metadata owner; maintenance does not publish a
second article cohort. Empty markers preserve outcome/profile/coverage/cadence,
not article evidence or qualification. RSS matching/retention runs only after
publication-date filtering. All matched counts are0 here, so there is no evidence
that article deduplication or the6-entry/policy-witness retention removed a usable
Watchlist article. Work deduplication and shared-feed reuse are different counters.

Globally, maintenance completed154/failed0, publication_failures0,
telemetry_failures0, submitted58/deduplicated12,210 feed requests/1174 reuses;
shutdown reports inflight0/alive_workers0/cleanup_complete=true. Of154 publications,
148 are empty and6 nonempty (CLRO/XTND/ABOS, twice each), totaling10 retained-evidence
observations. Those are not10 unique articles or10 qualifying catalysts, and none
belongs to the4 Watchlist issuers. first_result_seconds4.3657559 versus
first_evidence_seconds6.7935345 correctly distinguishes marker arrival from actual
article evidence. The60 canonical-cache reassessments perform no competing news
acquisition/publication and cannot manufacture qualification from those markers.

**Demonstrated narrow defect and repair.** The existing conservative matcher
strips terminal legal suffixes and requires at least2 remaining tokens, protecting
against ambiguous bare brands and generic wrapper identities. That rule explains
all3 empty alias lists; RENT keeps3 remaining words. It is intentional conservatism,
but the captured full legal-name false negative demonstrates useful authority loss:
AZTR's current sample is `Form 8K Azitra Inc For: 26 October By Investing.com`,
published26October13:26:51Z. At final evaluation its age is20821.515771s, within
unchanged21600s. It contains the supplied full issuer name but no AZTR ticker;
exact086a symbol_relevance_match returnsNone, consistent with its archived
issuer_match_unverified exclusion. This regression fails before the repair.

Only news_fetcher._company_alias_from_words changes: when stripping a supplied
2-token full legal name leaves1 inadmissible core word, retain the complete supplied
legal-name phrase instead. Never admit the bare brand. Generic/legal/article-word
cores and a core equal to the ticker remain excluded; unknown decorations,
substring/partial names and another issuer's identity remain excluded. Existing
multi-word normalization, ticker collision/summary rules, event ownership,
mandatory catalyst, freshness, selection pillars and canonical ownership remain.
Effective matching identity participates in the existing acquisition fingerprint,
so the changed identity is not silently treated as the old empty matching profile;
query/request/source/budget settings are identical.

Replay of the captured AZTR title now matches company_name/title and can be retained
as attributable evidence. classify_headline still returnsNone and assess_issuer_event
returns no_catalyst_classification: no positive event is established, and no
counterfactual Focus/setup/intent success is claimed. The captured12:45Z ex-vivo
study headline remains stale. RENT/GCTK/SPRC captured samples remain stale. Their
unsampled article text is unavailable and is not diagnosed from titles alone.
Diagnostic exclusions never become canonical evidence just because matching changed;
the actual archived canonical evidence remains empty. No filing body was captured
to establish an underlying qualifying event. Separate synthetic earnings/contract
controls test issuer event binding and negative co-mention/offering/update-only/
research/stale cases; they are not historical articles or natural acceptance.

Offline verification:236 focused tests pass, including38 new captured/synthetic
controls, existing broker-name/query/exclusion/canonical lifecycle/maintenance/
identity tests. Captured samples are replayed through a local feed stub only;
duplicate injection tests deduplication without inventing new articles. Canonical
service replay performs1 publication; cache-only consumers invoke no provider and
do not rewrite the store. The actual archive is never modified. Exact-head
independent review and changed-head Linux/Windows CI receipts are pinned on the
accompanying repair PR before any controlled-integration recommendation.

**Smallest next action.** Review and, only with separate authorization, integrate
this full-legal-name matching repair after exact-head review/CI. Do not run an
unchanged observation hoping for a catalyst. This archive already supports a
legitimate negative catalyst result, with a separately demonstrated attribution
repair; it cannot supply uncaptured filing content or prove complete primary-feed
coverage. Any further historical event diagnosis needs contemporaneous publisher/
filing/response evidence already retained elsewhere, not present-day search results.
Five external-position ownership blockers require their own owner decision before
entry acceptance; no adoption/liquidation is authorized. Natural positive catalyst
and downstream acceptance, complete primary-feed coverage, paper-management
acceptance, earlier timeout/negative-age causes and GUI draft remain open.
No broker/provider acquisition, operator rerun, forced candidates/Focus/setup/intent,
merge or trading is executed by this work. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

**Changed-head CI follow-up, separate from the natural receipt.** Preserve failed
CI40390431426 at repair headd5b1ae27a77f60392f3dae11ae4eb4b352b13a40:
Linux3217passed/3skipped; Windows3218passed/1failed/1skipped. The failing
`test_pr174_final_bridge_fix_block.py::test_live_pipeline_bridge_logs_watchlist_focus_strategy_and_summary`
expected AAPL Focus1 but received0. Maintenance35 and native cache9 passed; later
Windows cache/PowerShell checks were skipped, and controlled-artifact upload could
not supply their uncreated output. The consumed/truncated captured stdout lacks
quote timestamps and the exact Focus rejection reason, so this Windows receipt
alone cannot establish the cause or prove a harmless failure.

A deterministic offline control demonstrates a real fixture timing dependency:
its candidate quotes were sampled before CoreOrchestrator construction, then
returned unchanged as newly acquired fake scanner results. Advance the observation
clock by maximum-age+1second during construction (16seconds at the existing15s
maximum): the original bridge assertions fail with cached_focus/AAPL MD_STALE.
The narrow fixture repair creates candidates inside the fake scanner callback,
where the simulated acquisition actually occurs. The same delayed-start control
then passes every original bridge assertion. No sleep, retry, skip, relaxed
assertion, production clock substitution or freshness change is introduced;
failure messages now retain bounded quote/catalyst rejection details. This proves
the fixture defect and its repair, not the unrecorded latency/gate cause of that
specific Windows run. No additional production defect is inferred from unchanged
code.238 focused tests pass, including the new delayed-start regression; new exact
head review and changed-head CI supersede engineering gates without erasing the
failed run. Natural terminal PASS/exit0, all4 issuer findings and ownership blockers
remain unchanged. No acquisition or unchanged-head CI rerun. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL.

## Accepted PR1131 merge and smallest next evidence step (26 October 2026)

This entry supersedes the preceding *integration recommendation*, not its
historical findings or receipts. GitHub PR1131 is merged: merge commit
`f70edc3c5c368db561b95adc6c59b71cd82cfb28`, parents
`086a662c4f11f94b27ae3018a8cd561b7cc0f2a0` and
`b9b0ad5da2714746a0028f049ef6216a393b2104`, tree
`849422d9a52f7cdc1a5cfdec3814f9f1e4a64e1c`. Git objects, remote main and
GitHub's merged PR receipt agree. GitHub records merge time 26 October 2026
20:25:28 UTC (20:25:28 Europe/London). The accepted merge tree exactly equals
PR1131's independently reviewed, successfully tested final tree. Carry forward
review5658314441 and successful changed-head CI40393068669; preserve failed
CI40390431426 and its attribution limits. No completed suite or natural
observation was repeated for this assessment.

### Content supplied versus authority to qualify

At this exact accepted source, `news_fetcher._entry_summary` collects RSS
`summary`, `description`, `subtitle`, and `content` values. `Headline.summary`
is passed by `batch_rss_adapter._evidence_from_headline` into `NewsEvidence.summary`
and retained by the canonical store. Acquisition therefore is **not inherently
headline-only**, but it supplies only what the RSS item contains; it does not
retrieve the linked article or filing body. A feed summary can itself merely
repeat a headline. The captured current AZTR Form8K sample does so, with publisher
text; it does not disclose a qualifying underlying event. The missing filing
body cannot be reconstructed from this receipt.

Issuer relevance can match title or summary. `assess_issuer_event`, however,
intentionally classifies and binds an asserted event to the issuer's **title
clause**, using original publication time, existing six-hour freshness,
source-tier restrictions and dilution/uncertainty exclusions. Summary text does
not independently authorize a catalyst. A sufficiently explicit title can carry
a valid event without a full article body; a generic filing title cannot. No
content-loss or classification defect is established by the observed Form8K.
Do not introduce article crawling or summary qualification on this evidence.

New deterministic offline controls on accepted main used synthetic feed entries,
a private temporary canonical store, controlled UTC time and a synthetic quote
provider. They exercised real RSS matching, canonical service publication,
`reassess_ross_watchlist`, and the shared normal Focus selection gates:

- Synthetic `Azitra Inc reports earnings beat`, with supplied `AZITRA INC` and no
  ticker in the title: full legal-name match, one canonical write, then cached
  reconsideration from empty Focus to AZTR Focus with
  `verified_issuer_event_valid` and a fresh synthetic broker-provenance quote.
- Synthetic `Azitra Inc files Form 8-K` with an earnings assertion only in its
  summary: retained article, no Focus.
- Synthetic peer-owned earnings clause with a later Azitra Inc co-mention:
  retained article, no Focus.

All three controls passed (0.90s). Reconsideration made no additional feed read
or canonical write and left cache bytes unchanged. The market-data refresh and
all financial selection inputs were synthetic fixtures, not natural candidates
or live broker calls. This establishes a reachable software path, **not** an
observed catalyst, natural Focus, setup, intent, risk acceptance or trading result.

### Why primary exclusions remain unadjudicable

The prior receipt records, per issuer, 70 in-window primary entries rejected for
issuer matching (Benzinga10, MarketWatch10, BusinessInsider20, SeekingAlpha30),
plus CNN20 stale. Aggregate date/relevance counts cannot identify their titles,
summaries, exact matching fields or per-article publication provenance. The
archive contains neither those rejected item bodies nor raw primary XML.
`news_fetcher` calls `retain_exclusion` only for source group
`ROSS_ISSUER_QUERY`; the primary `FAST_TRADING` routes intentionally receive
counters without those samples. This is an evidence-coverage limit, not proof
that any individual primary rejection was wrong. The Google exclusion samples
cannot stand in for primary content. HTTP403/401/timeout receipts remain partial
coverage; missing error bodies still preclude assigning their upstream cause.

Existing facilities have distinct limits:

- `retain_exclusion` sanitizes before clipping, keeps two samples per reason,
  title512/summary1024/URL512 character limits, original-field hashes,
  truncation/redaction flags, identity patterns and timestamp provenance, plus
  aggregate counts. Its current route guard does **not** sample primary feeds.
  It cannot retrospectively recover their missing content.
- `RawFeedCapture` can capture primary bytes through an owned lifecycle and
  detailed `operational_query` fetch. Its existing 512KiB/response bound,
  hash, acquisition/evaluation times, HTTP status and body-complete/error fields
  permit offline replay. A new synthetic primary-route control passed (0.24s):
  an unmatched item had counters but no sampled exclusion, the raw response was
  captured once and closed, and replay reproduced the rejection without another
  HTTP call. The raw sidecar is **not privacy-sanitized**; it must stay private,
  outside canonical caches, and cannot be treated as a shareable sanitized
  rejection record or complete capture after truncation/failure.
- The public issuer-query research CLI adds Yahoo and fixed extended routes;
  broad research selects its separate catalogue. Neither is a drop-in command
  for a primary-only operational diagnostic. Do not broaden fanout by choosing
  one merely to obtain raw capture.

### One next acceptance action — primary-only content adjudication

Recommend preparing, then separately authorizing, **one provider-only diagnostic
of the eight existing FAST_TRADING URLs for the four captured issuer identities**
(AZITRA INC / AZTR, RENT THE RUNWAY INC-A / RENT, GLUCOTRACK INC / GCTK,
SCISPARC LTD / SPRC). No broker, scanner, Focus selection, fallback, Yahoo,
issuer-query, extra source, retry session or linked-article fetch. This is not an
unchanged 900-second natural observation. Its purpose is to adjudicate matching
and content sufficiency even if every result remains negative.

Use the existing detailed fetch, retention selector and owned lifecycle with a
single fixed batch, six-hour lookback, no more than the existing eight-second
Ross total news budget and five-second per-request cap clamped to remaining
budget; bounded cleanup must finish before packaging. Capture each scheduled
response once with the existing 512KiB cap (at most eight bodies / 4MiB), preserving
incomplete/unattempted/error status. Keep raw bodies private. Offline replay at
the recorded evaluation clock should produce a shareable report using the
existing sanitizer and `retain_exclusion` limits: separate stale versus fresh
issuer exclusions, original counts and explicit unsampled/redacted/truncated
coverage. Do not expand those sample limits or call sampled coverage exhaustive.
No operational cache/prep publication or operator-state change is needed.
A small primary-only diagnostic caller/report must be prepared and validated
before execution; this entry is a scope recommendation, not an executable or
permission to acquire. Do not reuse a broader CLI or unsanitized raw archive.

Defined information gain: for the sampled primary items, determine whether the
actual title/summary identifies the supplied issuer and whether the title asserts
a qualifying owned event; for every scheduled route, distinguish absent content,
HTTP failure, timeout, byte truncation and genuinely empty/mismatched content.
If no usable content is captured, report that limit and stop; do not repeat hoping
for a catalyst. A new diagnostic would establish facts only for its own window,
not recover the missing 900-second observation evidence or guarantee natural
Focus. Review the report before choosing any subsequent natural acceptance run.

The archived natural terminal PASS/exit0, three completed50-row scans, twelve
DROP_NO_CATALYST Focus rejections and lack of natural downstream progression stay
unchanged. Five unmatched broker positions remain a separate ownership/entry
blocker; no adoption, liquidation or cancellation. Earlier timeout and negative-age
receipt causes remain unresolved. This task made no production change, acquisition,
operator rerun, forced Focus/setup/intent, merge or trade. Only the four new offline
controls were run; prior CI/review receipts are carried forward, not rerun.

`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

### Primary-only diagnostic preparation (same scope; no acquisition executed)

The preceding recommendation is now implemented by the isolated
`scripts/diagnostics/ross_primary_feed_diagnostic.py` and Windows PowerShell5.1
wrapper `scripts/diagnostics/Invoke-RossPrimaryFeedDiagnostic.ps1`. This extends
this existing checkpoint; it is not a second acceptance checklist. Accepted
production remains `f70edc3c5c368db561b95adc6c59b71cd82cfb28`; neither production
acquisition code nor catalyst/selection/freshness rules changed.

The caller requires explicit `--acquire` or `--replay`, an exact clean source
commit, and a new output outside the checkout. One shared schedule covers the
exact eight FAST_TRADING URLs for all four supplied identities. It delegates to
the existing detailed fetch, owned lifecycle and RawFeedCapture; total8s,
request cap5s clipped to remaining shared budget, six-hour lookback and512KiB
per response remain. A caller-local guard forbids extra/repeated destinations,
turns off HTTP redirects, clips actual transport timeouts and cancels streaming
at the shared deadline. No Yahoo/query/extended route, fallback, retry, linked
article fetch, broker instance/connection, scanner cycle, Focus selection,
canonical store or prep publication is invoked. Reusing the existing catalyst
policy facade imports its configuration/SDK/type dependencies; those imports
are not broker construction or acquisition. Their configuration output is
suppressed before the CLI output boundary.

Cleanup is bounded10s. A separate supervisor kills and waits for the isolated
worker after45s, including startup, acquisition, cleanup and report work; there
is no retry. If workers do not stop, the caller does not read their raw captures
or present success. Source identity is checked again before publication. A
worker failure/timeout produces a sanitized failure-only ZIP with coverage false
and source-after verification explicitly unestablished, never a valid report.

Private `private/raw/` contains at most eight512KiB bodies (4MiB) and hashed
manifests with the original evaluation/acquisition clock, response status,
completeness and errors. The PowerShell wrapper restricts the new evidence root
ACL to the executing identity before running Python. Never share this directory.
Report/replay accepts only the fixed URL hashes/body names, matching lengths and
SHA256, bounded manifests/bodies, a stopped lifecycle and identical capture/replay
source identity; unexpected files, symlinks and altered clocks fail closed.

The shareable ZIP has exactly `report.json` and `privacy.json`. Text samples reuse
`retain_exclusion` sanitization-before-clipping and hashes: title512,
summary1024, URL512, two samples per reason per feed, shared across issuers.
Each sampled entry records all four issuer matching/classification decisions;
there are at most six sample categories (date/title exclusions, unmatched and
matched), not unbounded slots per issuer or arbitrary classifier reason. Counts
cover all examined captured entries and explicitly disclose omitted samples,
redaction, truncation and non-exhaustive sample coverage. Counts are entry
observations, not deduplicated article counts or canonical evidence. Complete
recognized HTTP200 bodies are replayed at their recorded evaluation clock using
the existing timestamp, relevance and issuer-event policy helpers. No clocks,
broker timestamps, article publication dates or classification rules are changed.
Original in-budget completion/truncation and offline raw-body adjudicability are
reported separately: a late complete body cannot validate acquisition coverage.
HTTP errors, redirects, nonfeeds, missing captures, byte truncation, timeouts and
unattempted routes remain explicit gaps. No raw error body enters the report.

The report is sanitized and scanned using the existing account-privacy mechanism,
then packaged from a fixed filename allowlist and the ZIP members are verified
against the scanned files. This verifies that privacy mechanism's defined token
scope; it is not a claim to detect all possible personal information in public
article text. Raw XML is never a packaging input. Exit0 means complete diagnostic
coverage only, exit2 partial coverage, exit1 failure; all retain
DIAGNOSTIC_ONLY, PAPER_READY=NO and PAPER_READINESS_GATE=FAIL.

Offline tests in `tests/test_ross_primary_feed_diagnostic.py` exercise synthetic
responses only: exact/shared scope and no retries, actual timeout clipping,
512KiB/4MiB bounds, blocked redirects, HTTP401/403, no-response failures,
unattempted/late/truncated coverage, closed responses/stopped workers,
recorded-clock replay, tamper rejection, bounded sanitized samples, fixed ZIP
inventory, source pin/cleanliness, disjoint output and no operational writes,
no live default, supervisor failure, and a fresh-process no-connection import
control. Windows additionally parses the operator wrapper with PowerShell5.1
without executing it. Final exact-head review/changed-head CI receipts are pinned
on the accompanying draft PR; prior suites and failed receipts remain above.

The one next action remains a separately authorized execution of this pinned
primary-only diagnostic, then offline adjudication of its shareable report.
Neither this preparation nor a diagnostic exit0 establishes a natural qualifying
catalyst, Focus, setup, intent or readiness. No unchanged natural observation is
requested. All five unmatched positions and historical timeout/negative-age
cause limits remain unchanged. No acquisition was executed in this preparation.

Initial exact-head review of257b178879636c477aeae83d507b58ba417c1bb6 raised
a possible two-backslash Windows guard issue. Byte-level verification showed
exactly one literal backslash in each original string; the reviewer had read
JSON/display escaping as source bytes and explicitly retracted the finding.
The original ordinary nested-path guard was already correct. Preserve review
receipt5658934791 as superseded by this correction, not as a demonstrated defect.
The wrapper now spells the separator with DirectorySeparatorChar for clarity
and additionally resolves junction/symlink parents with a read-only Python path
check before creation/ACL changes. A Windows5.1 controlled invocation with mocked
Git identity proves ordinary nested output is rejected before directory creation,
without acquisition. These are preparation hardening and validation, not a
production repair. Final exact-head review and changed-head CI must cover the
consolidated result; earlier review/CI receipts remain on the PR.

Preserve initial preparation CI40400479149 at257b178879636c477aeae83d507b58ba417c1bb6:
Linux3243passed/3skipped; Windows3245passed/1failed/1skipped. The failure was the
existing `test_pr1082_later_confirmed_catalyst_can_promote_genuine_focus`, with
captured `stage=cached_focus symbol=AAA reason=MD_STALE`; subsequent Windows
cache/PowerShell checks were skipped. This is not an acquisition/capture failure.
Both supposedly new scan rows were constructed before runtime initialization and
the first cycle. A new deterministic control advances only the quote observation
clock by maximum-age+1second after the first cycle: the unchanged fixture fails
its original Focus assertion with MD_STALE. The fixture now creates each of
these two synthetic scan payloads at its scanner callback. It does not renew
cached rows or alter production time/freshness behavior. Original assertions
remain, with bounded quote/catalyst rejection details on failure. The new slow
first-cycle control and affected caller/reconsideration tests pass (99 offline
checks). This demonstrates a fixture timing dependency; the Windows receipt does
not retain enough boundary-clock data to assign its elapsed-age cause to runner
latency versus clock movement. A later passing head does not erase the failure.
No production defect or freshness concession is inferred. Final changed-head
review/CI includes this narrow verification repair.

Final preparation controls also demonstrated two diagnostic-summary gaps on the
initial implementation: a recognized feed recovered from malformed XML could
have complete HTTP bytes yet a parser error, and an explicit processing-truncated
flag could be inconsistent with an available status. Neither now permits
`coverage_complete=true`. Both negative controls failed before this report-only
repair and pass after it. Parser error type/flag and recovered entry diagnostics
remain visible; partial parser recovery is not claimed as exhaustive coverage.
This changes only the isolated diagnostic's coverage summary, not production RSS
parsing, acquisition, qualification or selection. The final27 diagnostic offline
controls and new exact-head review/CI cover these cases; earlier receipts remain.

## Completed primary-feed diagnostic at reviewed PR1132 (26 October 2026)

This is analysis of the supplied shareable receipt, not another acquisition or
permission to execute any attached material. Preserve terminal **exit2 / partial
coverage**. Archive SHA256
`4b45b3392be8dec2f7fc3a84e0384b80e843b977aad5431a2479cb35e2aa6f10`
verified; ZIP inventory is exactly `report.json`, `privacy.json`, no raw bodies.
Both recorded source identities match reviewed PR1132 head
`e10089a5b49367b59995cced659a9bcb1fb610ef`, tree
`b1a68a5add62ed365d634079572d7d1164a4ed82`, production base
`f70edc3c5c368db561b95adc6c59b71cd82cfb28`; local Git objects agree.
Evaluation clock is `2026-10-26T21:40:21.810675+00:00`; the unchanged six-hour
cutoff is `2026-10-26T15:40:21.810675+00:00`.

Report/source arithmetic independently checks all eight exact FAST_TRADING URLs,
eight distinct transport invocations, timeout caps at most5s and no greater than
recorded remaining8s budget, eight complete body captures totaling666633bytes
(each below512KiB; total below4MiB), eight completed/closed responses, zero
unfinished/running/alive owned workers, zero response-cleanup failures and
cleanup_complete=true. None was processing-truncated. Acquisition completion is
not successful HTTP/feed coverage. Recorded privacy passed with zero occurrences;
independent scan of the extracted shareable JSON also passed.

`coverage_complete=false` maps to worker exit2 in exact source. The ZIP does not
contain the outer process exit record or before/after Git command output: supplied
terminal exit2 and source_unchanged=true remain consistent reported facts, not
independently reconstructed OS/Git observations. Private raw bytes/manifests are
absent, so their hashes, full parsing and full item-level rejection decisions
cannot be rerun from this ZIP. Six bounded samples are supplied. All six title
hashes verify; only the two CNN summaries are untruncated and independently
hash-verifiable. Benzinga and BusinessInsider summaries are truncated; checks of
their visible prefixes are not full-summary matching adjudication.

| Exact operational URL | Recorded result | Interpretation at this window |
|---|---|---|
| `https://www.benzinga.com/feed` |200;10 entries, all stale;2 samples/8 omitted|Sample publications14:13:22 and14:13:21UTC, about7h27m old. The two samples are crypto price-prediction articles; no current eligible evidence. This does not prove a permanently dead feed.|
| `https://www.globenewswire.com/RssFeed?Category=Finance` |403;383 body bytes|Access failure, not empty issuer news. Error body unavailable here; no access-cause inference or bypass.|
| `https://www.globenewswire.com/RssFeed/industry/9000-Technology/feedTitle/GlobeNewswire%20-%20Industry%20News%20on%20Technology` |403;511 bytes|Same access limitation; a historically useful issuer-news source is currently inaccessible in this environment.|
| `https://www.reuters.com/markets/rss` |401;771 bytes|Access failure, not verified usable coverage. No credentials/entitlement cause established.|
| `https://www.marketwatch.com/rss/topstories` |301;zero bytes;acquisition says available|Redirect is not followed by this diagnostic. Empty parser result lacks version attribute, exposing the available-empty validation hole below. Diagnostic adjudicable=false, so exit2 remains correct.|
| `https://feeds.businessinsider.com/custom/all` |200;20 fresh;20 unmatched per issuer;2 samples/18 omitted|Usable transport/current dates, not demonstrated AZTR/RENT/GCTK/SPRC coverage. Visible samples concern Microsoft buyouts21:25:28UTC and Instacart carts21:13:20UTC; all four supplied issuer names/tickers are absent from these titles/visible prefixes. Unseen text is not adjudicated.|
| `https://seekingalpha.com/feed` |301;166 bytes;RSSFEEDFORMATERROR|Redirect/non-feed response, not current articles. No Location header/target is supplied; do not invent a direct replacement address.|
| `http://rss.cnn.com/rss/edition_business.rss` |200;20 stale;2 samples/18 omitted|Samples are13February2017. Full recorded body SHA256 exactly equals W03's28September2026 body hash `8dd47037c53ed3aef23ed2394aafaadb15bdd515898af795f0b84f779fde9248`; this exact route is unsuitable for current issuer-event acquisition.|

No matching/classification authority comes from successful HTTP or an empty
result. Reported aggregate unmatched counts are not independent exhaustive
adjudication of20 complete BusinessInsider articles. No article, redirect target,
error body or current endpoint health has been invented or fetched.

### Catalogue and saved research reconciliation

`verified_rss.txt` contains161 unique URLs, introduced in commit6eafc2d6 on
9January2026. That is a **source addition date**, not a retained network
verification date. The catalogue has no per-URL verification date/status record.
Six of these eight operational URLs are present; Reuters markets and GlobeNewswire
Technology are absent. Presence therefore proves neither current access nor
issuer coverage, and absence does not negate a separately captured valid feed.
The catalogue's Google entries are macro searches, not issuer searches; their
literal non-ASCII locale hyphen must not be copied into issuer query URLs.

Saved W02 capture began28September2026 19:19:10UTC; W03 began22:08:37.432754UTC.
Use `artifacts/w02/source_evidence_matrix.json`,
`artifacts/w03/source_evidence_matrix.json`, `artifacts/w03/source_matrix.md`,
`artifacts/w03/live_coverage_analysis.md`, and the existing broad/query research
contracts. W03 attempted21 fixed feeds once:18 recognized feeds, Reuters401,
France24403 and VentureBeat429, zero canonical accepted articles for its actual
IRON/MSFT/LFCR batch. Its24h figures cannot be presented as six-hour verification.
Offline recalculation from its recorded original publication audits gives:

| Exact existing route | Last retained W03 observation at28September2026 22:08:37UTC | Limitation |
|---|---|---|
| `https://www.investing.com/rss/news.rss` |HTTP200, recognized feed;10/10 within6h|Financial coverage, no canonical target match in that old batch; not current access or four-issuer verification.|
| `https://www.forbes.com/business/feed2` |HTTP200, recognized feed;25/25 within6h|Same limitation; some broad business/sports content, not guaranteed small-cap events.|
| `https://www.marketbeat.com/feed` |HTTP200;16/100 within24h but **0/100 within6h**|Do not promote it as a verified fresh six-hour replacement.|
| `https://markets.businessinsider.com/rss` |HTTP200;body identical to BusinessInsider|Not an independent source; do not spend a replacement slot on a historically duplicate payload.|

W03 GlobeNewswire Finance/Technology were HTTP200 with20 entries each, but the
separately verified IRON publisher article was absent from both rolling responses.
That verification was28September2026 (article published19:02UTC), not evidence of
coverage for these four issuers now. W03 MarketWatch/SeekingAlpha HTTP200 were
returned by Requests with default redirect behavior; saved matrices do not retain
redirect history/final destination. They do not prove the exact requested URL
was a direct200. CNN's repeated hash strengthens its stale-route diagnosis.
The opt-in161-source broad capability documentation explicitly disclaims current
verification; no additional retained completed161-route health receipt was found
in the supplied/repository evidence. Do not restart broad research to fill gaps.

The already implemented operational Google issuer queries have stronger
issuer-specific *routing* evidence: all four completed HTTP200 in the earlier
26October natural receipt at the following final evaluation clocks. Exact URLs
match those retained in `tests/fixtures/ross_086a_captured_exclusions.json`:

| Issuer; prior evaluationUTC | Existing exact query URL |
|---|---|
|AZTR;19:13:52.515771|`https://news.google.com/rss/search?q=%28%22AZITRA+INC%22+OR+%22%24AZTR%22%29&hl=en-US&gl=US&ceid=US%3Aen`|
|RENT;19:13:57.714872|`https://news.google.com/rss/search?q=%28%22RENT+THE+RUNWAY+INC-A%22+OR+%22%24RENT%22%29&hl=en-US&gl=US&ceid=US%3Aen`|
|GCTK;19:13:52.393019|`https://news.google.com/rss/search?q=%28%22GLUCOTRACK+INC%22+OR+%22%24GCTK%22%29&hl=en-US&gl=US&ceid=US%3Aen`|
|SPRC;19:13:57.815873|`https://news.google.com/rss/search?q=%28%22SCISPARC+LTD%22+OR+%22%24SPRC%22%29&hl=en-US&gl=US&ceid=US%3Aen`|

Those responses had39/6/28/43 entries respectively. Only AZTR supplied a captured
then-current attribution false negative, repaired in PR1131; its generic Form8K
still did not classify. The other final query responses were stale. These are
not guaranteed fresh catalysts or proof of availability at21:40. These URLs are
already scheduled by operational issuer acquisition; adding them again as fixed
feeds would duplicate authority/request accounting. Never hardcode these four
issuers into the natural scanner universe or production group membership.

### Demonstrated handling gaps; proposed repair only

New offline controls used synthetic responses, the actual reviewed fetcher/parser,
owned lifecycle and provider-status function, with one stubbed HTTP call and
closed response per case. No network, broker, store or new acquisition occurred:

| Mode / supplied response | Exact-source outcome |
|---|---|
|detailed operational_query / empty301|available-empty; parser has no version attribute|
|ordinary fast / empty301|available-empty|
|detailed operational_query / HTML301|provider_error / RSSFEEDFORMATERROR|
|ordinary fast / HTML200|available-empty|
|detailed operational_query / recognized emptyRSS200|available-empty, correctly|

`_fetch_feed` leaves Requests' redirect policy unspecified (default follows).
`raise_for_status()` does not reject3xx. The recognition check runs only in
`detailed` mode and only if `hasattr(feed,'version')`; empty input's missing
attribute skips it. Ordinary FAST does not perform that recognition check.
`news_provider_status` can consequently say available with empty evidence and
zero recorded failures for these synthetic cases. The same shared code explains
the diagnostic's MarketWatch label, but its independent HTTP200/body checks
correctly prevented complete diagnostic coverage. This is an acquisition-health
classification defect, not a demonstrated catalyst or trade-admission bypass.
Production may automatically follow a redirect before this check; the no-follow
receipt does not establish its resulting destination or production response.

Proposed narrow shared repair: explicitly disable redirect following on supported
HTTP fetch branches, report every3xx as an unfollowed redirect failure, and require
a recognized nonempty feed-version value across supported RSS modes rather than
conditional attribute presence. Preserve legitimate recognized empty feeds as
available. Preserve HTTP failures, malformed/parser-recovery uncertainty, partial
counts, response closure, owned cleanup, total/tier deadlines and strict local
publication/catalyst rules. Redirect Location, if captured in a later authorized
receipt, is evidence for review, not authority to fetch a new endpoint. Existing
raw/privacy limits stay. Add retained regression cases for all rows above and
shared-pool/adapter propagation before any production change. No repair is
activated by this documentation/proposal; no production or configured URL changed.

### Smallest replacement proposal and decision boundary

The evidence supports **two conditional one-for-one fixed-feed candidates**:
MarketWatch -> `https://www.investing.com/rss/news.rss`; SeekingAlpha ->
`https://www.forbes.com/business/feed2`. Both already exist in PREP_EXTENDED and
the catalogue, with the dated six-hour W03 evidence above. Promotion would require
single canonical source-group ownership/deduplication against fallback, changed
source-profile fingerprints, and no second request/cache writer. They are not
verified replacements for AZTR/RENT/GCTK/SPRC today. Do not activate them merely
because they once returned200, and do not treat inaccessible GlobeNewswire or
Reuters as absence of issuer events. No current verified replacement URL for each
of those denied routes is established by this archive.

For this four-issuer context only, a bounded **eight-unique-URL candidate plan**
can instead consist of the four *already selected* Google queries above, retained
BusinessInsider and provisionally retained Benzinga, plus those two fixed-feed
candidates. That replaces six unusable/denied/redirecting fixed routes and keeps
the combined request ceiling at8: it is **not eight fixed feeds plus four queries**.
Benzinga's currently stale evidence stays rejected; its earlier current response
makes permanent abandonment less established than CNN's repeated2017 body.
This is a comparison/proposal, not eight verified healthy issuer-relevant routes.
Reusing actual selected issuer identities/max-four query contract is mandatory;
no forced symbols, added aliases or alternate-source spray.

Any later approved implementation must keep the existing8s total, existing tier
allocations,5s cap clipped to remaining, four-worker bounds,512KiB/response,
at most8 captured bodies/4MiB and original six-hour filters. Production already
prepends issuer queries to fixed feeds; an implementation must enforce the
combined unique-request count and fallback accounting rather than merely add
a new membership list. All denied/redirect/stale/unknown outcomes remain visible.
The proposed source set is not yet an accepted production configuration or an
instruction to run another diagnostic. First review the small no-follow/feed
validation repair and this dated candidate plan; only then decide whether a
separate narrow freshness/access verification is justified. No unchanged natural
observation, broad161-route research, redirect following, access bypass, acquisition
or trading is requested or performed here.

PR1132's bounded diagnostic completed safely and provided useful partial evidence;
it did not establish complete feed coverage, natural downstream progression or
production readiness. Preserve all historical receipts, earlier timeout/negative-age
cause limits, five unmatched-position ownership/entry blockers and GUI draft.
`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

## Shared RSS availability repair preparation (26 October 2026)

The shared repair is based independently on accepted production main
`f70edc3c5c368db561b95adc6c59b71cd82cfb28`. It carries forward assessment
`627be0ec8fe7f94116dba33ef840d66a89e0def5` and the intervening checkpoint
receipts in this same document. PR1132 remains unmerged at reviewed
`e10089a5b49367b59995cced659a9bcb1fb610ef`; its implementation, operator block,
archive and reviews are unchanged. Its caller/tests are not a dependency of this
production repair. Historical operator blocks remain pinned to their own heads,
not to this repair branch, which does not contain the unmerged diagnostic caller.

`news_fetcher` now sets `allow_redirects=False` on all supported Requests paths.
Every3xx is an explicit unfollowed redirect failure, reported with its HTTP code,
including cached transport payloads. Redirect bodies never enter parsing or
article evidence, and the caller never fetches Location. Bounded raw capture
records a redirect's HTTP status/error and an unread incomplete zero-byte body;
this is deliberate rejection, not complete body capture or available-empty.
If Requests is missing, the function fails unavailable instead of delegating an
uncontrolled network request to `feedparser.parse(url)`.

One shared validator requires a recognized RSS/Atom parser version in ordinary
FAST, detailed, direct and pooled paths. Missing version attributes cannot skip
it. Recognized empty RSS/Atom feeds remain available, while empty/non-feed/HTML
bodies fail format validation. Parser recovery (`bozo`) fails explicitly rather
than admitting recovered entries as complete coverage. Parse/entry-count timing
facts remain diagnostic; no recovered articles are published. This deliberately
fails closed for uncertain/recovered feeds without changing publication times,
six-hour freshness, relevance, catalyst vocabulary, retention or selection rules.

Owned response closure remains in the existing lifecycle done callback, after
the recorded fetch/parse completion instant. Ordinary no-lifecycle fetches now
close their own response on success/error. Worker count, stage/tier/request
deadlines, total budgets, cancellation, byte limits and cleanup bounds are
unchanged. No retry, redirect resolution, new source, extra pool, cache writer or
alternative acquisition authority was introduced. The shared pool caches failures
as failures and each consumer validates cached parser/HTTP facts before use.

Canonical RSS acquisition fingerprints and newly written retrieval metadata carry
`rss_availability_contract=no_redirect_recognized_rss_atom_no_recovery_v1`.
Old positive available-empty coverage cannot certify the stricter contract:
profile-aware consumers treat it as incompatible/unknown, and legacy positive
cadence metadata lacking the marker becomes coverage_unknown. Cache-only calls
make no acquisition or cache rewrite. Legacy negative cadence outcomes remain
negative in non-profile-compatible mode. For profile-aware consumers, any old
incompatible profile (positive or negative) has unknown current coverage; its
original failure remains in last_retrieval provenance. Current-contract failures
remain unavailable on reuse. Original article facts and timestamps are retained. Fresh failure
status and valid empty-feed status survive adapter publication and subsequent
canonical/shared-cache reuse. No second canonical writer or freshness authority
is introduced. The marker is RSS-specific and constant, not quote/time metadata
that would defeat cadence.

Offline negative controls on the original implementation recorded40 failures/9
passes across the initial49-case transport matrix, plus two failures showing old
cached positive metadata still claimed availability. These are implementation
controls, not operator receipts. The repaired suite includes69 deterministic
cases: empty301, HTML301, other3xx including304/307/308, HTML/empty/non-feed200,
valid empty/populated RSS and Atom, HTTP401/403, parser recovery, missing parser
version, direct/owned closure, cached invalid parser/HTTP payloads, no Requests
fallback, mixed partial sources, shared-pool failure reuse, old canonical coverage
invalidation and current adapter/canonical negative reuse. No external requests
occurred. Existing positive RSS fixtures now explicitly model recognized version
and non-recovery state; their assertions and actual negative-content controls
remain. The affected580-case RSS run passed before the last added controls;
final validation/review/changed-head CI receipts are pinned on the accompanying PR.

The already independently reviewed PR1132 continuity-fixture timing correction is
reused identically in its existing test file: genuinely new synthetic scan rows
are created at the scanner handoff, with a deterministic slow-first-cycle control.
This addresses the preserved CI40400479149 verification blocker without copying
or changing PR1132's diagnostic implementation, renewing cached quotes, changing
production freshness or discarding its failed receipt. No original Windows
latency/clock-movement attribution beyond the earlier recorded limits is claimed.

### Smallest later verification for the two historical candidates

After acceptance of the repair/integration pin, prepare/review one provider-only
batch containing **exactly two URLs**, shared across the four captured issuer
identities: `https://www.investing.com/rss/news.rss` and
`https://www.forbes.com/business/feed2`. There is no reason to repeat all eight
primary URLs or restart161-source research to answer whether these two candidates
are directly accessible, recognized and current. Use8s total acquisition, at
most5s per request clipped to remaining, at most two concurrent HTTP calls, no
retry/redirect/query/fallback/linked-article fetch, six-hour original publication
window,512KiB each (two bodies /1MiB), owned cleanup at most10s and the existing
45s isolated diagnostic supervisor bound. Raw remains private; share only a
separately sanitized/privacy-verified bounded report with status, hashes, original
clock/timestamps, counts, per-issuer matching/classification reasons, omissions,
parser/truncation facts and cleanup. No operational cache/prep publication,
broker, scanner or Focus selection is needed.

This is a scope recommendation, not an executable instruction or acquisition
authorization. PR1132's reviewed caller has a fixed eight-route scope and must not
be invoked unchanged or silently repurposed for a two-route test; a reviewed
explicit two-route caller is needed first. Information gain is direct no-follow
access/format/freshness for these exact endpoints and bounded evidence of actual
issuer relevance. HTTP200 alone is insufficient. An unmatched/empty/failed
result remains limited evidence; stop and assess it rather than retrying for a
catalyst. September's10/10 and25/25 six-hour figures remain historical.

No replacement feed was activated: `source_groups.py`, `verified_rss.txt`, query
routing and production source ordering/membership remain unchanged. The preceding
eight-total deduplicated candidate plan remains documented separately as a
conditional proposal, not eight fixed feeds plus extra queries or an accepted
configuration. Preserve the primary diagnostic's exit2, historical failures,
earlier timeout/negative-age cause limits and five unmatched-position blockers.
No acquisition, broad research, natural runtime rerun, ownership action, automatic
merge, trading or readiness upgrade occurred.
`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

Local changed-source verification:3286passed/3skipped in203.06s; the67 new
controls passed, and four final cache-summary/aggregate assertions also passed.
Independent exact-head review and Linux/Windows changed-head CI are required
before integration; final pins/receipts are recorded on the accompanying PR.
No completed historical suite was rerun without the shared production change or
its demonstrated cache/fixture concerns.

Independent review of3a6f63a1 independently passed113 targeted controls and raised
one documentation overclaim, not a transport/admission defect: old negative
profile-aware retrievals become current coverage_unknown after contract mismatch.
The final two regression cases explicitly distinguish this from preserved
negative non-profile cadence reuse, retain the original negative outcome/HTTP301
provenance, and prove no network call/cache rewrite. Both pass. The wording above
now states that distinction; no production behavior was changed to make old
coverage look current. Final exact-head delta review/CI supersedes this initial
review while preserving its finding and the earlier3286/3 local suite receipt.

## Accepted PR1133 merge and explicit two-route verification preparation

GitHub and Git objects confirm PR1133 merged26October2026 at22:38:31UTC
(22:38:31 Europe/London): accepted main
`e5c5ad60a99d0b2128a05ce5d3f418bf2b7e9a98`, parents
`f70edc3c5c368db561b95adc6c59b71cd82cfb28` and
`b1c68fc135902abac2c420bb5f2770785e34b4f8`, tree
`a66eb7cfedced3b48d080e7075757c2ee7e5dc05`. This equals PR1133's final
independently reviewed tree. Carry forward review5659927932 and successful
changed-head CI40412092398 (Linux3288passed/3skipped; Windows3290passed/1skipped,
including maintenance/native-cache/cache/PowerShell checks). No accepted suite
or observation was repeated merely because the merge SHA changed.

PR1132 remains unmerged at reviewed
`e10089a5b49367b59995cced659a9bcb1fb610ef`; its fixed eight-route implementation,
old production pin, operator block and partial receipt are untouched. None is
silently retargeted or invoked here. The new preparation is based on accepted
PR1133 main above and does not depend on merging PR1132.

`scripts/diagnostics/rss_feed_diagnostic.py` extracts the previously reviewed
PR1132 diagnostic orchestration/report/replay/privacy components into one reusable
implementation with an explicit immutable caller profile. It delegates acquisition,
capture, date parsing, feed recognition, matching, event assessment and privacy
to the same existing src owners; no alternate retrieval engine, matcher, cache,
publication authority or second privacy implementation is introduced. The old
standalone eight-route caller is not copied into this branch. Historical replay
remains bound to its original source/schema; future reuse of the common core
must declare a separate explicit scope rather than mutate the reviewed caller.

The separately named `scripts/diagnostics/verify_two_route_provider.py` declares
only `https://www.investing.com/rss/news.rss` and
`https://www.forbes.com/business/feed2`, accepted production basee5c5ad60 and
schema `ross.two_route_provider_verification.v1`. Four established identities are
AZTR/AZITRA INC, RENT/RENT THE RUNWAY INC-A, GCTK/GLUCOTRACK INC and
SPRC/SCISPARC LTD. There is no CLI URL/budget/identity override or issuer-query,
Yahoo, extended/fallback discovery. One shared batch schedules two distinct
requests total, not two per issuer. At most two workers can issue HTTP because
there are exactly two source URLs; a once-per-URL guard rejects extras/repeats.
Budget8s, request cap5s clipped to remaining,512KiB/body and1MiB total,
six-hour original publication window, no redirects/retries,10s owned cleanup and
45s isolated supervisor remain fixed. Timeout/unattempted/failed/truncated work is
reported, not retried or relabelled valid. Zero operational cache/prep publication,
broker connection, scanner/Focus execution or source activation is performed.
The internal detailed-processing mode is not an issuer-query HTTP request.

Private captures have source/schema/profile/URL/identity/clock/byte/hash/inventory
checks before replay; eight-route or old-pin captures cannot silently become
two-route evidence. Exact caller head/tree and accepted-base ancestry are checked,
with a clean checkout including untracked files and source recheck before report
publication. Output must be new and outside source; even internal worker mode
rejects nonempty/source output. Owned workers must stop before raw inspection.
An incomplete worker yields failure-only diagnostics, not invented cleanup or
coverage success. Raw XML remains private and never enters the shareable ZIP.

The shared report has distinct access/parsing statuses, freshness and per-issuer
matching/qualification counts/reasons, original times, bounded sanitized samples,
hashes, explicit omissions/truncation/redaction and separate original acquisition
versus offline replay scope. Replay delegates RSS/Atom recognition/recovery to
PR1133's accepted shared validator, rather than maintaining a second acceptance
rule. Recovered/unrecognized entries are explicitly unassessed and never receive
qualification decisions. Recognized empty feeds can complete diagnostic coverage
without providing any issuer event. Late complete raw bytes do not establish
in-budget completion. All classification is diagnostic-only, never permission
to select/trade. Only scanned `report.json` and `privacy.json` are added to
`ross-two-route-provider-shareable.zip`; ZIP contents are checked against the
privacy-verified files. Existing two-samples-per-reason, title512/summary1024/URL512
limits remain shared across issuers. Counts are parsed entry observations, not
unique canonical articles or exhaustive issuer coverage. Privacy verification is
the existing defined account-token mechanism, not a universal public-text PII claim.

`scripts/diagnostics/Invoke-TwoRouteProviderVerification.ps1` provides the separate
PowerShell5.1 entry point, exact source/tree checks, new external path checks
(including canonical junction parents), and restricted user ACL before Python can
write raw data. Retained local paths are:
`C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system` and verified
Python3.13.3 `C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe`, with `C:\tmp`
as the short-path base. The final delivery pins the reviewed preparation head/tree,
fetches Git objects, creates a new detached worktree, verifies accepted maine5c5ad60,
and invokes this new wrapper using those actual paths. It is prepared only;
if accepted main advances, stop for explicit verification/repinning. Never substitute
PR1132's f70 pin, invoke its eight-route caller or reuse an evidence directory.

New offline controls use synthetic Responses only and cover two shared requests/
maximum concurrency2, frozen profile/new accepted base,8s/5s limits,1MiB total,
redirect/HTTP failures, recognized empty and populated Atom/RSS, parser recovery,
missing/late/truncated evidence, cleanup, no operational writes, source/worker
output guards, schema/hash/time/inventory rejection, original-clock replay without
HTTP, bounded sanitized samples, fixed ZIP inventory and supervised failure.
Windows additionally parses the5.1 wrapper and verifies source-nested rejection
before directory creation without invoking acquisition. New synthetic positive
event classification is explicitly diagnostic, not natural Focus/acceptance.
Final exact-head independent review and appropriate changed-head CI receipts are
pinned on the accompanying draft PR. No acquisition is executed in preparation.

Remaining gate: after separate authorization, one two-route batch can determine
direct no-follow access, accepted parsing, actual six-hour freshness and bounded
issuer-event evidence for these historical candidates. HTTP200 or exit0 alone
cannot establish issuer coverage, qualify a natural candidate or activate a feed.
Exit2 remains useful partial evidence; do not repeat to seek a catalyst or exit0.
The eight-total deduplicated production candidate plan remains conditional and
separate from this two-route verification; no source membership/order changed.
Preserve all historical/failed receipts, the original primary diagnostic exit2,
unresolved earlier timeout/negative-age causes, GUI draft and five unmatched
position ownership/entry blockers. No holdings action, automatic merge, source
activation, natural rerun or trading is authorized/performed here.
`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

Local changed-head preparation validation:35 new offline controls passed; full
suite3323passed/3skipped in203.89s. Four full-suite-generated governance/audit
outputs were preserved as a scratch diff then restored to original committed
bytes; they are not changes in this preparation. Final exact-head review and
Linux/Windows CI receipts are pinned on the accompanying PR, with no operator
acquisition or accepted observation repeated.


## Completed PR1134 two-route receipt and one-for-one production proposal

The supplied `ross-two-route-provider-shareable.zip` has SHA256
`4e89b59a788cb8f9fa598428ad2b7889f4d6e48b4ecf997bcb3c22d22352b190`,
independently recomputed. Its exact inventory is `report.json` and `privacy.json`;
no raw XML is included. Capture and analysis source agree on reviewed PR1134 head
`85eaa1dc3eb6886fc3d20125c85c549c786558a5`, tree
`388e42b07ee1357b7d3c30b3e4f769ce9b98a6e4`, production base
`e5c5ad60a99d0b2128a05ce5d3f418bf2b7e9a98`. Carry forward independent
review5660296620 and successful CI40417352077 (Linux3323passed/3skipped,
Windows3327passed/1skipped including cache/PowerShell gates). PR1134 remains a
separate diagnostic preparation; this production proposal branches directly from
accepted maine5c5ad60 and does not merge its caller or PR1132. PR1132's original
fixed eight-route implementation, old pin and exit2 receipt remain unchanged.

At recorded evaluation clock26October2026 23:28:56.506932UTC, exactly two shared
requests completed with5s caps inside8s: Investing HTTP200, recognized non-bozo
feed,10/10 current entries; Forbes HTTP200, recognized non-bozo feed,25/25 current.
No future/stale/unknown publication dates, truncation or acquisition error are
reported. The report records zero issuer matches and zero qualifying entries for
each of AZTR/RENT/GCTK/SPRC: every issuer has10+25 `issuer_match_unverified`
rejections. Counts are entry observations, not unique articles or an exhaustive
external issuer-news search. Only two sanitized samples per reason/feed are
shared (8 and23 samples omitted); raw bodies remain private and cannot be
independently replayed from this ZIP. Source, count, bounds and cleanup assertions
were independently checked against the reviewed caller's report/exit logic;
this is receipt verification, not a new acquisition or invented full-body replay.

Preserve operator-reported **exit0 / complete diagnostic coverage**. The JSON
has coverage_complete=true and is consistent with the reviewed caller's exit0
branch; it does not itself contain an outer terminal log. Both responses closed,
2/2 workers completed, none alive/unfinished, cleanup_complete=true with zero
response-cleanup failures. Private raw total55360bytes (4804+50556) is below
1MiB and both512KiB caps. Source_unchanged=true; no_operational_publication=true.
The existing privacy scanner independently passed the two extracted shareable
files with zero account-token occurrences, matching privacy.json; this defined
scan is not a universal PII guarantee. No acquisition was executed during ingest.

### Prepared fixed-feed substitutions and canonical ownership

In `src/news/source_groups.py`, keep FAST_TRADING at eight ordered slots and
replace only slot5 MarketWatch with
`https://www.investing.com/rss/news.rss`, and slot7 SeekingAlpha with
`https://www.forbes.com/business/feed2` (one-based numbering). All other FAST
routes/order remain. Remove precisely these promoted URLs from PREP_EXTENDED,
retaining the other11 in their previous order. They now have one source-group
membership, not two opportunities to fetch or two publication owners. The existing
adapter's cross-tier URL deduplication remains a second guard, including for
injected/legacy overlapping memberships; neither promoted URL is fetched again
by fallback. Macro/catalogue/research membership and issuer-query construction
are unchanged; no diagnostic issuer identity enters production configuration.

This improves directly observed source health over MarketWatch301/SeekingAlpha301
non-feed; it establishes neither future availability nor target-issuer/catalyst
coverage. GlobeNewswire403, Reuters401, CNN stale2017 and Benzinga's observed
staleness remain explicit historical failures, not evidence of no issuer event.
Strict no-follow/feed validation, partial/error reporting, six-hour original
publication, mandatory attributed catalyst and canonical evidence writer remain.
Total8s, tier5.2s/2.8s at existing .35 reserve,5s clipped request cap, four-worker
bound, capture/privacy limits, fallback eligibility and cleanup are unchanged.
Changing source membership automatically changes existing acquisition-profile
fingerprints; no new invalidation implementation or cache deletion is needed.
Offline controls seed both successful empty and failed old-profile acquisitions,
then prove cache-only use returns coverage_unknown without network/cache rewrite,
preserves prior receipt provenance, and bounded refresh uses new routes once;
subsequent compatible empty/failure cadence is retained. Stored article provenance
is not permission to claim current coverage or select/trade.

### Combined accounting mismatch: separate decision remains required

Source inspection and deterministic synthetic empty-feed execution confirm that
current Ross operational scheduling prepends up to4 dynamically selected Google
issuer queries to8 fixed FAST feeds: **up to12 unique primary URLs**, not8 total.
If primary coverage is complete, the provider available and explicitly unresolved
symbols remain, up to11 disjoint PREP_EXTENDED routes can run inside the same
stage deadline: **up to23 unique routes** for four valid selected queries. Incomplete
primary coverage defers fallback explicitly. Before this proposal the equivalent
maximum was4+8+13=25. The substitution adds no requests; removing promoted fallback
memberships reduces this existing maximum by2. Query-disabled combined groups
now have19 routes instead of21. These are eligible maxima, not a claim all calls
will execute before the deadline. The eight-body/4MiB diagnostic capture ceiling
is not a production eight-request scheduler; do not confuse byte/capture limits,
policy max_sources metadata or wall-clock budgets with a combined request ceiling.

The earlier eight-total *candidate plan* instead described4 selected queries plus
BusinessInsider, Benzinga, Investing and Forbes, with no extra fallback requests.
It has NOT been activated here. Implementing it would also remove/defer the two
GlobeNewswire routes, Reuters and CNN and impose combined primary/fallback
accounting. That is a broader source-profile/coverage decision, not authority
implied by two one-for-one substitutions. This proposal preserves current
scheduler/budgets and documents the mismatch for explicit decision; it must not
be represented as enforcing the proposed eight-total plan. No speculative source
fanout, second fetch pool, cache writer or publication authority is added.

Offline validation covers exact configuration/compatibility exports, unchanged
other routes, unique shared primary/fallback fetches in query-enabled/disabled
paths, injected cross-tier duplicates, actual combined eligible counts, unchanged
budgets and old-profile positive/negative invalidation/cadence. Test transport
returns explicitly synthetic recognized empty feeds; external sockets are blocked.
Independent exact-head review and changed-head Linux/Windows CI receipts belong
on the accompanying draft production PR. Completed diagnostic/accepted suites are
not repeated; these controls validate the changed production membership.

### Next natural acceptance boundary and information gain

First decide whether to integrate only these two health substitutions under the
existing12-primary/23-combined maximum, or separately authorize the documented
8-total candidate profile and its combined/fallback accounting. Do not silently
mix those profiles in an operator run. After accepted integration/profile review,
the next natural Ross acceptance action is one separately authorized900s
READ_ONLY observation using the existing bounded harness at its accepted pin,
with actual naturally selected issuer identities and unchanged safety settings.
Its defined information gain is production integration evidence: changed-profile
cache invalidation, new fixed feeds actually scheduled once with truthful coverage,
canonical qualified evidence and normal cached reconsideration for natural
Watchlist issuers, and recorded Focus rejection/progression reasons. It is not
another provider diagnostic or a request to obtain matches by repetition. No
Focus/setup/intent may be forced; without a qualifying event, downstream acceptance
remains unestablished and the bounded result must say so. The pending profile
decision precedes this observation; no operator block is repinned/executed here.

All earlier failed/partial receipts, natural900s PASS/exit0 without downstream
progression, PR1134 diagnostic exit0, unresolved historical timeout/negative-age
causes, GUI draft and five unmatched positions remain preserved. Positions are
separate ownership/entry blockers; no adoption, liquidation or cancellation.
No acquisition, automatic merge, source activation on the workstation or trading
was performed. `PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

Changed-membership offline validation:144 focused source-group/adapter/RSS/
Ross-policy/lifecycle controls passed (4 existing parser deprecation warnings),
plus10 budget/runtime reliability controls passed. Seven new synthetic controls
exercise the substituted membership, production accounting and cache transition.
No acquisition or natural observation was executed.

Preserve initial changed-head CI40420939181 at5177c23c: Linux reported6failed,
3289passed/3skipped. All six failures were exact research/replay/fallback count
assertions still including the two former PREP_EXTENDED memberships (27vs25,
23vs21,25vs23 and22vs20). Their source-set cause is independently established
by the promoted two URLs and the new production accounting controls; this is not
an unchanged-head retry or an assertion that every unchanged failure is harmless.
Update only those exact expectations and strengthen them with expected URL-union
and no-duplicate assertions. Timeout/partial coverage, raw hashing/replay, canonical
store privacy, peer-change refresh, fallback requirement and catalyst-rejection
assertions remain. The affected research/bottleneck/new-control files pass100
offline cases after this correction; no further production change was needed.
Final exact-head review/changed-head CI supersedes, but does not erase, this run.

Preserve second changed-head CI40421578276 at
`acf1912e551fe6354b51b98a00ff4e4ac662553f`: Linux3295passed/3skipped;
Windows3296passed/1skipped plus1failure in the terminal-integrity parameter
`overrides2-trigger_ready_without_intent`. The captured Windows path explicitly
rejects both synthetic AAA/BBB quotes as MD_STALE, empties Focus and never invokes
the intended malformed-terminal assertion. This is not evidence that production
accepted that malformed terminal. The fixture created quotes before constructing
the orchestrator, then handed those same quotes to its synthetic scanner later.
An offline clock control advances only the quote clock by configured maximum-age
plus1s during construction: before repair it deterministically reproduces both
MD_STALE rejections and the identical terminal-test failure. This establishes the
local fixture ordering defect; it does not establish the exact elapsed-time or
workstation-clock contribution in the Windows receipt, or resolve historical
negative-age/quote-timeout causes.

Narrow test-only correction: this terminal-integrity test now supplies a scanner
payload factory that creates its explicit synthetic broker quotes at scanner
handoff, after construction. All18 malformed-terminal cases retain their strict
return/error/pipeline-break assertions. The new slow-constructor regression then
reaches the intended terminal rejection without wall-clock sleep. No production
quote timestamp is rewritten, no stale row is refreshed in production, and no
freshness limit, ownership, READ_ONLY or terminal-admission rule changes. Windows
cache/PowerShell gates skipped after the failed full-suite step remain required
on the new changed head; do not count the earlier partial CI as complete success.

Local validation qualification, retained rather than hidden: an initial full
local invocation onacf1912e omitted the existing `tests/offline` PYTHONPATH startup
guard. It reported3295passed/3skipped plus1display-test teardown error,
`Float discovery worker shutdown incomplete`; its log includes attempted Yahoo
access/401 responses from a MOCK scanner display fixture's background float worker.
That invocation was not a valid offline pass and the provider-access attempt was
outside the authorized task. The existing CI configuration already enables
`tests/offline/sitecustomize.py`, including its Python socket audit and native
curl_cffi transfer blocks; no production or display-test cleanup rule was changed
to conceal the mistake. With that existing guard enabled,3display controls passed
and the full local suite passed3295/3 in199.80s. Preserve PR validation
receipts5660604017/5660626674 and local logs under `/workspace/work/`;
full-suite-generated governance/audit diffs were preserved then restored to
original committed bytes. This qualification supersedes any blanket no-acquisition
wording for implementation validation, not the archived diagnostic's no-operational-
publication evidence. No operator observation, broker acquisition, feed rollout,
holdings action or trading occurred. Subsequent validation uses the hard offline
startup guard; all operator/cache state in tests remains fixture-isolated.

Preserve third changed-head CI40423268209 at
`5abdccfe47d131c01a54a7cf39f7c5a3514d7e21`: Linux3296passed/3skipped;
Windows3296passed/1skipped plus2failures in
`test_pr1082_missing_mapping_terminal_records_internal_fault_without_halting`
and `test_pr1082_mixed_output_rejects_trigger_ready_terminal_without_intent`.
The mixed-output log explicitly shows AAA/BBB MD_STALE and no Focus; the mapping
assertion's captured-output representation shows no Focus but is truncated, so
its precise Windows rejection cause cannot be independently recovered from that
representation. The previous single-test correction was too narrow for this shared
fixture pattern. New guarded clock controls advance maximum-age+1s during
construction and deterministically reproduce both failures before the shared fix.
This establishes the shared synthetic acquisition-order defect offline without
claiming the exact Windows latency/clock history is proved for either occurrence.

The correction now belongs to the test harness's synthetic scanner boundary:
`_row` describes a planned row with a one-shot quote factory, and the shared
scanner callback acquires its quote only on that row's first handoff. Alias lists
of the same row consume the factory once. It never refreshes a previously
acquired/cached quote; newly scanned data requires a newly planned row. An
explicitly supplied factory can return stale/future/untrusted facts unchanged;
`quote_factory=None` represents no acquisition and preserves explicitly supplied
facts, including missing evidence. The existing cached-Focus freshness control
opts out of synthetic acquisition and supplies its own immutable broker fact;
all its prior stale rejection, no-rescan and unchanged-evidence assertions remain.
No production factory, source timestamp substitution, quote clamp, age allowance,
Focus bypass or canonical writer is introduced.

Seven additional controls cover both reported terminal paths after delayed
construction, one-shot acquisition across aliased row lists, cached expiry without
refresh, and preservation/rejection of future/stale/untrusted/missing facts.
All344 guarded related cases passed in6.82s, including every importing harness
consumer plus the production future-quote admission controls. The earlier narrow
terminal callback and its regression remain valid. All three failed CI receipts
and the invalid unguarded local attempt remain visible; final exact-head review
and CI supersede them only after the complete Linux/Windows/cache/PowerShell
checks pass. Production remains limited to the two original feed substitutions
and removal of their duplicate extended memberships. No further acquisition,
operator observation, feed rollout, holdings action or trading was performed.

## PR1135 accepted merge and retained-profile 900-second observation preparation

GitHub confirms PR1135 merged27October2026 at12:52:04 Europe/London (UTC).
Accepted main is `49ba1e8eafcd728476d6d9bd495663b518c24446`, parents
`e5c5ad60a99d0b2128a05ce5d3f418bf2b7e9a98` and
`61f4c5dc8f3fe0c1cb6797c23b780f6e758139a7`, tree
`c7aaff126038f2fe374bf07ed4a33e9c69adfee8`. The complete tree equals the
reviewed final PR1135 tree, including the existing acceptance harness. Carry
forward independent review5660762458 and successful CI40424827117; no completed
full suite or observation is repeated for a merge-SHA-only change.

**Coordination decision:** retain the existing bounded production profile for
one next natural900-second Ross READ_ONLY observation. Do not activate the
proposed eight-total profile, change source membership, scheduling, refresh
cadence, tier allocations, request caps, pool/concurrency limits or ownership.
The existing four-query-batch maximum remains12 eligible primary URLs and23
combined eligible URLs; these are per-batch eligible counts, not guaranteed
attempts, a whole-run request ceiling or a count of HTTP responses. Maintenance
can acquire one issuer at a time and share fixed responses across issuers/waves.
The existing8s stage budget and5s clipped request cap remain, with the existing
tier reserve/default5.2s/2.8s and fallback eligibility. Runtime900s is distinct
from each acquisition budget. No four diagnostic issuers are forced into a run.

The literal operator pin is **49ba1e8eafcd728476d6d9bd495663b518c24446** and its
accepted tree above. This separate documentation-only preparation commit records
new merge/coordination/evidence-review information; it is NOT a replacement
operator pin and is not needed in the observation checkout. The operator block
reads the accepted preparation-helper blob from Git, creates a fresh detached
accepted-pin worktree and verifies its head/tree/cleanliness before invoking the
unchanged runner. It never runs this documentation branch or retargets to latest
main. If fetched main has advanced, stop for coordination rather than substitute
a SHA. The original PyCharm checkout, GUI draft, historical roots and evidence
are preserved. This branch is published separately without launching a new PR's
automatic full-suite CI solely for documentation; main is not changed here.

Compatibility was checked by byte-identical Git tree/diff against reviewed61f4c5dc,
inspection of the existing900s duration propagation and literal ExpectedCommit
checks, and static Python AST parsing only (no operator imports or execution).
The unchanged run_natural_readonly_observation.ps1 passes900 to all phases and
sets the outer observation budget to1260s. Existing preflight90s, owned stop30s,
package/seal90s budgets and exit/deadline propagation remain. Use Windows
PowerShell5.1 Desktop and the retained verified Python3.13.3 environment at
`C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe`, source Git checkout
`C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system`, base `C:\tmp`.
Run only in the normal RTH window with the documented TWS Read-Only API session
on127.0.0.1:7497 and dedicated client71 available. No force-session, candidate,
Focus/setup/trigger/intent, validation bypass or trading override is introduced.
Pre-existing runtime/session failures must stop the harness, not trigger a broad
kill, automatic retry or changes to broker positions/orders.

### Required retained evidence and counting limits

All paths below are under the new root's `e` directory unless stated otherwise.
Keep the complete privacy-verified sealed ZIP; do not extract selected successes
or share the private root/state directory instead.

| Acceptance outcome | Evidence to review separately |
| --- | --- |
| Terminal safety | phase-status.json and each *.process.json OS exit/deadline receipt; operator-summary.json; terminal/terminal_evidence.json, supervisor_shutdown.json, process_binding.json, runtime_inventory.json; independent-final-runtime-inventory.json, independent-mutation-validation.json, source-before/after.json, shareable-evidence-scan.json; final broker audit in terminal evidence plus terminal/audit stdout/stderr. Require owned graceful stop, both runtime/audit zero mutation attempts, complete final audit/disconnect, empty completed runtime inventories, unchanged source/operator state and sealed privacy pass. Zero open orders never means zero positions. |
| Genuine scans and Watchlist continuity | terminal/stdout.log and stderr.log: each actual scanner request ID, matching scannerDataEnd/completion status and raw row count; TopN refresh/cadence and WATCHLIST/FOCUS authority/handoff logs.Verify the actual observation duration against the900s preflight; terminal PASS alone does not prove a full900s observation.900s targets the normal300s discovery cadence; measure actual completions rather than assume three50-row scans or150 fresh enrichments. |
| Actual news coverage | terminal logs' [NEWS][RETRIEVAL_DIAGNOSTICS], [NEWS][MAINTENANCE] PUBLISH/RESULT/PRIORITY snapshots; cache-exports/news.json news_intelligence.symbols[SYM].last_retrieval: acquisition_profile and coverage.diagnostics.source_diagnostics (rich rows), per-issuer associations and provider details. Review eligible memberships/selected queries separately from scheduled/attempted/completed sources, HTTP/parser/timeout/unknown failures, processing truncation and fallback deferral. |
| Canonical catalyst qualification | cache-exports/news.json actual evidence/provenance and per-symbol acquisition status; qualification decisions where retained, [ROSS][CATALYST][REVALIDATE], [ROSS][REASSESS] source=CANONICAL_CACHE and Focus rejection reasons in terminal logs. PUBLISH with publication_scope=canonical_result_marker and evidence_count0 is result-marker persistence, not an article or qualified event. Incomplete coverage is not proof no issuer event existed. |
| Focus/setup/trigger/decision/risk/READ_ONLY intent | terminal logs' actual Focus evaluations, pattern/setup/trigger terminal reasons, TRADE_PATH/PIPELINE stages, decision/risk reason codes and intent facts. Official Focus differs from diagnostic Watchlist evaluation. Do not infer a full RiskEngine pass from the active-manager risk marker or infer natural progression from a synthetic control. No natural qualifying event leaves downstream acceptance unestablished. |

In the rich retained acquisition diagnostics, distinguish
unique_source_urls_scheduled_count/unique_source_urls_attempted_count,
duplicate_source_fetches_avoided_count/cross_tier_duplicate_source_urls_avoided,
fast_sources_attempted_count/extended_sources_attempted_count,
tier_budget_seconds_by_tier,
tier_elapsed_seconds_by_tier/tier_budget_exhausted_by_tier,
sources_skipped_due_to_budget_count, primary_source_coverage_complete,
stage_deadline_exhausted and fallback_skipped_reason. The rich rows are in
last_retrieval.coverage.diagnostics.source_diagnostics; the projected
coverage.source_diagnostics and console view omit some measurements. Per-source
transport_cache_hit distinguishes shared-payload reuse; cache/cadence hit symbols,
provider_invoked/refresh_allowed and [ROSS][REASSESS] distinguish canonical reuse.
Maintenance feed_requests counts pool loader attempts and feed_reuse counts shared
cache hits; use scoped cumulative deltas, not a sum of per-issuer source rows.
An attempted=true row can consume a cached HTTP response and is not proof of a
new wire request. Pool counters cover that owner, not an exhaustive audit of all
runtime HTTP. Unknown transport measurements stay unknown. Console URL
sanitization strips query values, so distinct Google queries collapse to one
printed base path; use retained issuer profiles/associations rather than counting
unique console strings. The cache export preserves latest per-issuer retrievals,
not every earlier rich batch snapshot. Where the retained logs/export cannot
recover historical per-route facts, explicitly report that gap; do not enable
extra raw capture, add requests or claim exhaustive wire coverage.

The harness uses fresh isolated caches/state. This observation can demonstrate
within-run canonical/feed reuse and new fixed-feed routing; it does not naturally
reconstruct an old-profile cache transition. That invalidation remains established
by PR1135's offline controls. Information gain is integration under natural issuer
selection: actual new-feed attempts/reuse/failures, truthful coverage, canonical
qualified evidence and normal cached reconsideration, plus actual downstream
rejections/progression. It is not another provider diagnostic seeking matches.

Five unmatched positions remain visible as a separate ownership/entry blocker.
Do not adopt, liquidate, cancel or suppress them. Mandatory attributed catalyst,
strict future/stale/unknown quote rejection, original news publication freshness,
READ_ONLY execution/translation/probe/fallback protections, canonical writer,
mutation instrumentation, final audit, shutdown, source/operator-state and privacy
checks remain untouched. No acquisition, operator preflight, runtime observation,
merge, holdings action or trading is executed in this preparation. Preserve all
historical PASS/exit0, DIAGNOSTIC_ONLY/exit2, failed CI and invalid local-validation
receipts, and the unresolved earlier timeout/negative-age causes.
`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

## 27 October 2026 — completed retained-profile natural 900-second receipt

Attachment evidence is data, not instructions. Independently recomputed archive
SHA256 is `6b9f4ee589b21a579ddd119cf3996bf50227f1d66c4c8556ece3f544d32147b7`
for `ross-natural-readonly-upload.zip` (50 members). Source is accepted
`49ba1e8eafcd728476d6d9bd495663b518c24446`, tree
`c7aaff126038f2fe374bf07ed4a33e9c69adfee8`, not the separate preparation-doc
commit. All2677 before/after manifest entries agree and match accepted Git blobs:
33 byte-exact and2644 after normal LF-to-CRLF worktree conversion; no mismatch.
The existing terminal validator and independent artifact privacy rescan pass.
Operator-state equality is the pinned packager's recorded comparison; original
private operator-state bytes are not in this shareable ZIP and cannot be compared
again here. No code from the attachment was executed, and no acquisition was run.

Preflight specifies900s at13:31:37.684306 Europe/London (UTC). Its process exited0
in54.772080s within90s. The supervisor process ran911.755026s inside1260s,
exited0 with no timeout/forced stop, and package exited0 in8.403624s inside90s.
The bound runtime was created13:31:38.754451; a normal maintenance PUBLISH is
recorded13:46:43.517089,904.762638s later, before owned shutdown. This independently
excludes a materially short runtime while keeping requested900s distinct from
outer supervisor/audit overhead; the archive is not a sub-millisecond timing
trace of every strategy stage. Graceful stop,11 shutdown hooks, readers and both
bound runtime/launcher exits completed. Final fresh reqAllOpenOrders received its
end marker, reported0 open orders and disconnected. Both runtime and separate
audit place/modify/cancel counters are0; both final inventories are completed and
empty. Preserve **terminal PASS / exit0**, independently of natural acceptance.

### Five acceptance outcomes

| Outcome | Verified evidence and limit |
| --- | --- |
| Terminal safety | Preflight/observation/package/final exits0; terminal validator PASS/no blockers, no capture/reader/identity errors, successful final audit, zero mutation attempts, empty completed final inventories, source/state/privacy reported PASS. This does not mean positions0 or readiness. |
| Genuine scans and Watchlist continuity | Scanner request363/772/1138 each returned50 rows with matching scannerDataEnd, COMPLETE, connected/wait_signalled/end_received true. Watchlist3→4→2: [POM,CLRO,AEYE] → [POM,AEYE,CLRO,EFOI] → [AEYE,POM]. This is three genuine completed universes, not150 successful fresh enrichments. |
| Actual news coverage | Production used both promoted FAST feeds and naturally supplied issuer queries; coverage remained partial, with denied/timeout/deadline outcomes and deferred extended tier. Completed issuer-query responses are not exhaustive searches or proof that every issuer event was retrieved. |
| Canonical catalyst qualification | Exactly9 primary [ROSS][FOCUS][REJECT] DROP_NO_CATALYST records: POM3,AEYE3,CLRO2,EFOI1. Mirrored SCANNER/FOCUS_DROP lines are not9 additional evaluations. CLRO's2 retained fresh articles fail the current event rule; the other3 Watchlist issuers end with empty evidence. |
| Natural downstream progression |41 CANONICAL_CACHE reconsiderations have positive_count0/focus_count0;146 cycle summaries report0 intents, and no natural Focus/setup/trigger/decision/risk/READ_ONLY-intent progression is established. Five broker-only mismatches recur145 times each (725 mismatch lines), separate from the first unavailable position-truth cycle and from final open-orders0. None was adopted, liquidated, cancelled or suppressed. |

### Actual fixed-feed use, reuse and partial coverage

Tagged JSON was decoded even when concurrent output joined tags onto one physical
line:538 retrieval diagnostics,281 PUBLISH,2 LOOKUP_COMPLETE and283 RESULT events
parse successfully. A line-start-only count misses records. Of538 retrieval
records,282 say provider_invoked=true and256 false. One live record is the separate
startup SPY/QQQ FAST batch with8 attempted source rows and ordinary/no-lifecycle
measurements; it is not natural Watchlist selection or part of the maintenance
pool counters. The other281 are maintenance retrievals. Unknown startup HTTP
timing/status measurements remain unknown rather than being invented.

| Promoted route | Maintenance source-row observations, not new HTTP request counts |
| --- | --- |
| https://www.investing.com/rss/news.rss |281 rows:177 available/HTTP200 with10 parsed entries;50 HTTP200 provider errors with console-redacted failure code;48 READTIMEOUT with unknown HTTP status;6 budget/deadline outcomes. Latest rich cache snapshots include reused TIMEOUTERROR payloads. |
| https://www.forbes.com/business/feed2 |281 rows:193 available/HTTP200 with25 parsed entries;83 HTTP200 provider errors with console-redacted failure code;5 budget/deadline outcomes. Latest rich cache snapshots include reused TIMEOUTERROR payloads. |

Each Watchlist issuer has4 available HTTP200 row observations for each promoted
route, with0 recorded matches from those fixed feeds. They are shared-response
observations, not4 independent fetches each. Latest retained successful Investing
snapshots report10 current/0 stale entries; successful Forbes snapshots elsewhere
in the final export report24 current/1 stale. Do not transplant26October's
25-current diagnostic result into every27October response. Original body content
and historical rich snapshots are absent for many earlier outcomes; HTTP200 with
a TIMEOUTERROR is not accepted parsing, and the receipt does not establish the
precise body-read/cancellation cause. No SDK/upstream diagnosis is invented.

The final maintenance SHUTDOWN snapshot is authoritative for that owner:
336 pool loader attempts,2187 shared cache reuses,95 submitted work keys,
34 deduplicated submissions,281 completed outcomes,18 failed outcomes,0 publication/
telemetry failures,0 inflight/alive workers and cleanup_complete=true. Earlier
PRIORITY/PUBLISH counters stop lower; do not mistake them for final totals.
These counters do not count every runtime HTTP request: the startup batch is
outside the pool, and a loader attempt is not proof of completed wire delivery.
Summing per-issuer attempted/HTTP200 rows double-counts cached responses. All283
RESULT events report cleanup_complete=true; failed/unavailable outcomes remain
visible. The final cache has94 symbols:92 current-profile coverage records and
legacy SPY/QQQ without those rich records;12 symbols have30 retained article
records. This is not a claim that all30 qualify or that non-Watchlist symbols
should be forced through selection.

### CLRO article adjudication at the recorded clock

The supplied identity is CLEARONE INC; effective matching alias remains
CLEARONE INC. The Google query is the quoted full supplied name OR "$CLRO",
using existing en-US/US/US:en parameters. All6 recorded maintenance outcomes
publish2 retained articles and remain partial_request_failure. The issuer query
has6 available HTTP200 observations:3 with46 entries and3 with18; the last has
16 stale exclusions and2 current matches. Its two bounded stale samples are a
25October estimates page and15October loan story; neither may be made current.

| Retained StocksToTrade headline | Original publication UTC/Europe London | Current-policy decision |
| --- | --- | --- |
| CLRO Stock Rockets On Volatility As Traders Pile In |2026-10-27 13:10:18|no_catalyst_classification; qualified=false |
| CLRO Stock Pops On Volatility Spike As Traders Pounce |2026-10-27 12:10:17|no_catalyst_classification; qualified=false |

The captured summaries repeat those headlines; linked full articles were not
captured/fetched. Both match CLRO by ticker token and are inside6h at the archived
13:44:48.267706 evaluation clock. Rehydration through the existing evidence mapper
and current assess_issuer_event at that clock reproduces both rejections without
changing publication values. Neither title contains a recognized issuer-event
class; volatility/trader price commentary is not the mandatory catalyst. Stored
classification=None is expected for the strategy-neutral provider, not proof that
the consumer failed to classify. Two headlines from one publisher are not two
independent qualifying catalysts. These are decisions about captured headline/
summary evidence, not a semantic adjudication of unseen full articles. No
publication substitution, tolerance increase or classification relaxation applies.

### POM / AEYE / EFOI identity-to-empty-publication trace

Broker names/normalized matching aliases are stable across their captured
retrieval diagnostics. Queries use the full supplied name OR dollar ticker;
SMART is not an explicit NASDAQ/NYSE/AMEX exchange term. No recency operator is
sent upstream; the existing6h original-publication filter runs after retrieval,
before relevance matching. No missing alias/matching-authority defect is
established by entries rejected earlier for age.

| Issuer | Supplied name → effective matching alias | Latest retained query response / exclusions |
| --- | --- | --- |
| POM |POMDOCTOR LTD - A → POMDOCTOR LTD A|3 entries,3 outside6h,0 current/retained; newest observed publication12October19:33. Samples:30September predictive-healthcare story and4June2025 Forbes crypto POM price page. The crypto page is not issuer evidence; its recorded exclusion is age, not a newly proved identity rejection. |
| AEYE |AUDIOEYE INC → AUDIOEYE INC|26 entries,26 outside6h,0 current/retained; newest27October00:20:18, a Q3 earnings headline, already over13h old at observation. Other sample:26October21:05:25 Yahoo quote page. Original publications are not refreshed at fetch time. |
| EFOI |ENERGY FOCUS INC → ENERGY FOCUS|19 entries,19 outside6h,0 current/retained; newest23October23:45:14 estimates page. Other sample:11August Q2 financial-results8-K headline. No missing-inc alias defect is shown. |

Live issuer-query summaries show POM6 available/1 budget outcome, AEYE5 available
(1×37 entries,4×26)/1 budget/1 provider error, and EFOI5 available/1 budget outcome.
Do not label every historical acquisition completed or infer that every earlier
response had the final response's membership/dates. Latest exclusion counters
and2 bounded samples per reason are available, but original response XML and all
individual historical entries are not. The omitted titles/content cannot be
invented or adjudicated using present-day web results. All POM7,AEYE7,EFOI6
PUBLISH/RESULT pairs persist canonical_result_marker with evidence_count0 and
successful cleanup: empty canonical evidence follows recorded admission filters,
not a demonstrated lost canonical write. Completion/availability refers to the
issuer-route contract, separately from incomplete publisher coverage and policy
qualification. This does not prove that no real-world current catalyst existed.

### Why the extended reserve was unused: established policy, not repaired here

All92 latest current-profile records have primary_source_coverage_complete=false,
fallback_skipped_reason=primary_coverage_incomplete, extended_fallback_requested=
false, extended_budget_seconds0 and reserved2.8s. All have stage_deadline_exhausted=
false;87 have fast_budget_exhausted=false and5 true. Fast elapsed ranges
0.009779–5.246517s. The four Watchlist issuers retain unresolved symbols. No
PREP_EXTENDED source row in the captured console diagnostics is attempted.
Unused reserve is therefore not evidence that the total8s deadline expired.

Source/history establish the distinction: batch_rss_adapter.py204–223 requires
EVERY selected primary URL to be attempted, available and non-truncated, with
no fast-tier exhaustion, before Ross operational fallback is eligible. It then
runs the Ross fallback resolver, checks unresolved symbols/mode/remaining stage
and clips existing extended allocation to the remaining deadline. This all-
available gate originates in1dc2bcd2a/e97d3bf8b;2f42057c1 explicitly retains the
bounded primary-first policy. Existing test_pr1107_bottleneck controls assert
that an HTTP401 primary failure defers fallback without a false total-deadline
claim, and that recognized completed empty primary feeds DO permit unresolved
fallback. The policy was documented before this receipt and retained by the
explicit27October coordination decision; fallback_mode=unresolved_only is not
an unconditional promise to spend the reserve after a failed primary source.

New hard-offline synthetic controls exercise the actual Requests/validator/owned
lifecycle/canonical-service path: recognized empty RSS runs9 primary+11 extended
unique requests; completed HTTP401/403, HTML200, empty200 and recovered-parser
primary failures each run only9 primary, leave2.8s unused and defer all11 extended
rows. All workers/responses close; no total-stage exhaustion is needed. Thus
completed denied/malformed sources deterministically prevent fallback; this is
intentional v4 admission behavior, not an inferred label or demonstrated accidental
scheduler bug. Allowing those failures through the fallback gate would change
retained scheduling semantics. It is not silently implemented as a defect repair,
and failures must never be relabelled available/complete to unlock fallback.

Eight focused guarded controls pass: terminal/privacy verification, CLRO replay
at the recorded clock, and six synthetic primary-status cases. Existing full
CI40424827117 still covers the identical production source; no new full suite is
justified for this documentation-only evidence update. No production code,
source list, classifier, freshness, budget, request cap, fallback, canonical owner,
operator block or accepted pin changes. Earlier receipts, failed CI, invalid
unguarded local validation and unresolved timeout/negative-age causes remain.

**Smallest next action:** review the all-primary-available fallback precondition
as an explicit policy decision. A narrowly scoped proposal could compare retaining
it with permitting only the ALREADY configured extended tier after all primary
workers have completed with known failures, inside the unchanged remaining stage/
reserved-tier budget and shared ownership, while primary coverage stays incomplete.
That proposal is not activated here, does not add sources, and needs its own
reviewed decision before implementation. An unchanged natural observation cannot
resolve this deterministic gate and is not recommended merely hoping for a
catalyst. Five unmatched positions remain separate entry blockers; no holdings
action or trading. `PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

## Deliberate v5 policy: bounded fallback after completed primary failures

This implementation starts from accepted production
`49ba1e8eafcd728476d6d9bd495663b518c24446` and carries forward checkpoint
`f6cb7a5f9a7981dbae425a913e0196b54fcaaabf`, including the27October natural
receipt and all earlier evidence. The user's NEW explicit coordination decision
replaces the all-primary-AVAILABLE precondition with completion-based eligibility
for unresolved issuers. This supersedes the earlier retained-v4 decision for a
future reviewed integration; it does not claim v4 violated its own specification
or alter the archived PASS/exit0, three50-row scans, Watchlist3→4→2,9 catalyst
rejections, no downstream progression, or five unmatched-position blockers.
The proposed eight-total source profile remains unactivated. Source membership,
query construction, limits, ordinary nonoperational RSS behavior and canonical
publication ownership are unchanged.

The shared RSS adapter now considers fallback only for the explicitly unresolved
subset after the existing Ross qualification resolver. Genuine qualifying primary
evidence can resolve an issuer without a fallback request or cleanup wait. Disabled
fallback/no extended sources remain disabled. An unresolved issuer can use the
ALREADY configured extended tier when every selected primary URL has a recorded
attempt and completed worker outcome, all observed owned primary workers have
stopped and their response cleanup completed, and the fast/stage/parent deadlines
still permit work. Completed HTTP failures (including redirects), unrecognized
or recovered-parser failures and recognized empty/successful feeds can satisfy
completion. Availability is a separate immutable coverage fact.

The barrier verifies both coordinator source outcomes and the lifecycle's actual
owned futures/threads/cleanup. It checks exactly the current primary submissions
(using a per-call offset, allowing a reused lifecycle without treating old stages
as new work), finite ordered completion/cleanup timestamps and no cancellation.
Unknown/missing/partial/truncated results, cancelled or unfinished work, timeout/
deadline outcomes and unobservable or failed cleanup cannot authorize fallback.
Late completion or cleanup never rehabilitates an earlier deadline result. Stop
and inherited acquisition deadlines are checked before and after the barrier and
again before extended acquisition; cancellation remains control flow, not a data
error or reason to issue fallback.

Primary response cleanup can wait only inside the REMAINING original fast-tier
allocation and inherited parent deadline. It does not receive a new cleanup budget
for acquisition, overlap unfinished primary workers or create an additional unowned request pool.
Existing final shutdown cleanup remains separate. The original total stage8s and
fast/extended default5.2s/2.8s remain; extended acquisition is clipped to its
reserved/explicit allocation, remaining original stage deadline and any earlier
parent deadline. Unused fast time does not renew or expand the extended allocation.
A zero extended allocation schedules no extended fetch. Request caps, four-worker
fetch/pool bounds, shared-response reuse, byte/privacy bounds, unique-route and
cross-tier deduplication remain in their existing owners; no new source, retry,
request pool, operational writer, freshness allowance or catalyst vocabulary is
introduced.

The broad provider_failed check no longer vetoes operational fallback solely
because all primary outcomes are known completed failures; the completion/cleanup
barrier replaces it. Nonoperational behavior keeps its previous guard. Original
primary failure reasons, HTTP codes and partial/unavailable rows survive merging
with fallback. primary_source_coverage_complete still means actual available,
nontruncated primary coverage. Fallback success cannot change it to true or certify
complete selected-source/search coverage when a primary failed. A matched fresh
qualifying event may establish existing per-issuer acquisition/qualification under
partial publisher coverage; it cannot bypass catalyst, publication, quote time,
selection, ownership, READ_ONLY or risk gates.

New bounded diagnostics distinguish primary_fallback_barrier_verified,
primary_cleanup_complete and primary_barrier_elapsed_seconds from primary coverage.
The barrier verification is null when unnecessary (resolved/disabled), true only
when the fallback prerequisite was proved, and false on a failed prerequisite.
Reasons distinguish primary_deadline_exhausted, primary_completion_unverified,
primary_cleanup_unverified and primary_cleanup_incomplete. Deferred routes stay
explicit and unattempted; budget-skipped extended routes retain exhaustion facts.
These rich details are retained in canonical retrieval coverage; no new raw/body
capture or alternative publication is enabled.

The scheduling contract is now
`ross_completed_primary_cleanup_fallback_v5`. The actual shared RSS scheduler's
contract, rather than arbitrary caller metadata, participates in acquisition
fingerprints, and the standard Ross policy supplies the same value. Old v4
positive/negative coverage cannot certify v5 acquisition. Cache-only mismatches
stay coverage_unknown without provider calls/cache rewrite and retain old receipt
provenance; normal bounded refresh creates v5 coverage and normal cadence then
reuses it. Articles and original publication values are not erased or substituted.
Non-RSS provider profile behavior is unchanged.

### Guarded offline verification and explicit old-test changes

All validation uses the existing tests/offline startup boundary (Python socket
and native libcurl guards). No acquisition or natural observation is run.37 new
controls use fake HTTP Responses and existing fetch/validation/lifecycle/service
owners, not a second retrieval implementation. They cover completed recognized
empty/success and HTTP401/403/301, HTML/empty/recovered feed failures; all-primary
failure; resolved versus unresolved subsets; genuine qualifying versus volatility,
stale/future/missing-publication evidence; fallback failure with original primary
reasons retained; shared payload reuse and duplicate-route omission; delayed or
failed response closure; unknown/omitted/truncated/cancelled primary facts;
unfinished deadline work with late evidence rejected; stop before/during cleanup;
fast/stage boundary equality, zero extended allocation, earlier parent clipping
and deadline expiry after cleanup; and old-v4 cache invalidation/cadence.

Old policy-specific controls are updated explicitly: test_pr1107's completed
HTTP401 nonqualifying primary now expects existing extended fallback, while a
qualifying primary witness resolves without it. Deadline/unfinished cases still
assert no fallback, retained partial coverage, owned cleanup and no invented
qualification, with the new precise reason. The former scanner no-cleanup-wait
control now proves the required wait is inside the original fast allocation and
that the extended fetch sees completed cleanup, with no after-budget wait. The
existing qualifying-primary control still expects zero barrier waiting. All other
safety, canonical, freshness and catalyst assertions remain.

Focused source/RSS/consumer verification passed212 cases, and the final37 new
policy controls pass. A full guarded suite and independent exact-head review plus
changed-head Linux/Windows CI (including native cache and PowerShell gates) are
required before integration. The final PR records exact head/tree and receipts;
no unchanged-head CI retry or completed natural observation is substituted for
those gates. Full-suite-generated governance/audit outputs are retained as scratch
diffs then restored to committed bytes, not included as unrelated changes.

**Smallest next natural acceptance step:** after reviewed/green controlled
integration, prepare one existing900-second natural READ_ONLY harness invocation
at the NEW literal accepted main/tree. Do not reuse49ba as if it contained v5,
silently change an old operator pin, execute during implementation, or activate
the eight-total proposal. Defined information gain: for naturally selected issuers,
prove completed/cleaned primary failures can lead to only the unresolved extended
subset inside the original allocations, while timeout/stop/unknown cases remain
deferred and primary coverage remains incomplete. Reconcile real attempts versus
shared reuse and confirm single canonical publication/cached reconsideration.
Review terminal safety, genuine scans/Watchlist continuity, actual news coverage,
canonical catalyst qualification and natural Focus/setup/trigger/decision/risk/
READ_ONLY intent separately. No catalyst or downstream progression is guaranteed;
record real negative reasons without forcing candidates, Focus, setups or intents.
Five unmatched positions remain separate ownership/entry blockers; no adoption,
liquidation, cancellation or suppression. `PAPER_READY=NO`;
`PAPER_READINESS_GATE=FAIL`.


Preserve the initial guarded full-suite validation log at
`/workspace/work/bounded-fallback-full.log`:3332passed/3skipped and3 failures in
old test_pr1107_coverage_contract assertions that fallback was never requested
under completed HTTP403 primary failures. This run collected the initial32 new
cases before five final boundary/unknown controls were added. All three failing
cases had the intended unresolved/no-qualifier result; the old v4 no-fallback
expectation is deliberately replaced. The test now also asserts exact9-versus20
unique request counts, all original8-versus19 HTTP403 reasons, incomplete primary
coverage and unchanged search/qualification/cadence behavior. Its existing
attribution, stale-publication and dilution-veto safety assertions remain.
This is an explicit policy-test update, not an unchanged-head retry hoping for
success; no production fix was required in response to those test expectations.

Final related guarded validation after the explicit expectation updates:154passed
in6.59s, including the37 new v5 controls and all affected old coverage/consumer
controls. No source or operator acquisition was executed.

## 27October accepted-v5 natural receipt: fallback verified; IPST event policy unresolved

Receipt SHA256 `7223eeafe07f3de0f8126de707d7ae17e09426009c0f1e945d56f08c9c1af3ae`
(`ross-natural-readonly-upload.zip`,50 members) is independently verified. Accepted
production source is `dcb65fbd54178f9bdc82f63061b69b4fe6877653`, tree
`42b3833ca0b80f5b74439ca5442a7c2a5cca5a18`. PR1136 actually merged at
2026-10-27T15:13:36Z, from reviewed head
`0b307bc0a1ca13c705085988acc4bace750bded0`; its merge tree equals the reviewed tree.
Independent agent review5669156421 reported no blockers and137 guarded controls
passed. Changed-head CI40525137379 passed Linux3340/3skipped and
Windows3342/1skipped, including native float-cache, cache-startup, PowerShell5.1
status/observation harness39 controls and quote-transport parser. These are linked
PR1136 receipts, not repeated suites or natural acceptance evidence.

All2678 archived tracked-file digests match exact accepted source:33 byte-exact,
2645 matching only the normal Windows CRLF worktree conversion; no mismatches.
Before/after manifests are equal. The bound runtime creation token yields
2026-10-27T15:14:53.941414Z. Supervisor elapsed909.704559s (1260s ceiling), with
timely normal exit0, no outer timeout or forced stop. A final ordinary canonical
publication at15:29:56.920598Z is902.979184s after runtime creation: the normal
observation spans at least900s, independently of packaging/audit duration.

Five acceptance outcomes remain separate:

- Terminal safety: **PASS/exit0**, preserved. Preflight/observation/package/final
  exits0; terminal validator and privacy replay pass. Owned shutdown completed;
  runtime and separate audit mutation counters each record place/modify/cancel0;
  final broker query completed/disconnected with0open orders. Initial/final
  independent and terminal inventories contain no Ross runtime. Source and
  operator order-state validation pass. Zero orders alone is not mutation proof.
- Genuine scans/Watchlist continuity: three COMPLETE/end-received50-row broker
  scans, req363/775/1035. Watchlist3→3→2: IPST/NUWE/AEYE;
  IPST/AEYE/AARD; IPST/AEYE. These are real selected rows, not injected candidates.
- Actual news acquisition: partial, not complete issuer/search coverage. Bounded
  fallback is naturally observed under v5, with retained primary errors and
  deadline exclusions as detailed below. Empty canonical markers are not articles.
- Canonical catalyst qualification: none established for the Watchlist. IPST has
  four retained current issuer-matched articles, but none belongs to an existing
  qualifying class. Other Watchlist issuers have zero retained articles. Eight
  recorded Focus evaluations reject DROP_NO_CATALYST (IPST3,AEYE3,NUWE1,AARD1).
- Natural downstream progression: absent. Three Focus summaries accept0; all56
  canonical-cache reconsiderations report positive_count0/focus_count0, and all217
  cycle-end records have intent_count0. Diagnostic Watchlist views are explicitly
  execution-ineligible and do not establish Focus/setup/trigger/decision/risk/
  READ_ONLY intent acceptance.

### Bounded fallback, snapshots and actual requests

Latest export has57 issuer coverage records (SPY/QQQ separately lack that rich
coverage), of which18 request fallback and39 exclude it with
primary_deadline_exhausted. Every one of those18 records reports
primary_fallback_barrier_verified=true and primary_cleanup_complete=true, while
primary_source_coverage_complete=false and stage_deadline_exhausted=false. All57
retain total8s, fast5.2s and reserved extended2.8s. For the18, maximum primary
elapsed5.008981s; primary elapsed plus barrier elapsed remains below5.2s in every
case; granted extended allocation is at most2.8s; maximum total adapter
elapsed7.833617s. No renewed budget is recorded. Extended measured coordinator
elapsed can reach2.821510s; this includes deadline detection/return overhead,
not an increased allocation or permission to admit late evidence.

Exact source `src/news/batch_rss_adapter.py::_primary_fallback_barrier` requires
all selected source outcomes and lifecycle ownership/timestamps to be known,
completed, uncancelled and within the original fast/stage deadline, then verifies
owned response/executor cleanup inside only the remaining fast/parent allocation.
Stop/timeout/truncation/unfinished/unknown outcomes fail closed. Immediately before
extended fetch it rechecks the inherited deadline, and the fetcher clips each
request and admission to the original stage and extended deadlines. The recorded
barrier flags are positive evidence from that authority, not inferred from HTTP
status or a later successful shutdown. The archive does not retain every raw
per-worker monotonic lifecycle snapshot, so it cannot independently reconstruct
all worker intervals or every historical barrier from console rows alone.

There are402 console retrieval diagnostics:174 bounded-refresh/provider-invoked
snapshots and228 cache-only snapshots. Of the174,38 show attempted extended rows;
this is broader historical evidence than the18 latest exported issuer snapshots.
It is not38 independent feed batches or38×11 network fetches. The last live PRIORITY snapshot records262 actual fetches and1694 response reuses;
the authoritative SHUTDOWN receipt ends at263 fetches/1696 reuses, alive_workers0,
inflight0 and cleanup_complete=true. These pool counters span both tiers and
issuer queries, plus the separate startup SPY/QQQ path is outside that pool. In the18
latest fallback records,198 extended source rows include168 explicit transport
cache hits,9 explicit HTTP attempts and21 rows without either positive fact;
the latter include deadline exclusions and failure rows and must not be converted
into inferred network requests. These latest rows do not constitute a run-wide
per-route request ledger. Console rows also preserve historical timing on reuse;
request_elapsed_seconds is not proof of another request.

Latest fallback extended rows remain provider_error or budget_exhausted:
HTTP301/302/308/429, TIMEOUTERROR and explicit deadline_exhausted/
deadline_exhausted_before_attempt. No successful extended issuer event or complete
primary coverage is claimed. The39 excluded latest records contain no attempted
extended rows. All174 maintenance RESULT records report cleanup_complete=true;
that final per-result cleanup is distinct from the prerequisite primary barrier.
The source never upgrades failed primary coverage when fallback runs. The bounded
fallback scheduling objective is demonstrated; successful fallback content,
complete issuer search and natural catalyst/downstream acceptance are not.

### IPST: four captured articles, original publication and actual authority

Supplied identity is IPST / IP STRATEGY HOLDINGS INC (SMART), matching alias
IP STRATEGY. Actual shared issuer query is the existing Google News RSS expression
`("IP STRATEGY HOLDINGS INC" OR "$IPST")`, not a new source or linked-article fetch.
Seven normal maintenance publications retain4 articles each, from15:17:06.970694Z
through15:29:42.737449Z. The latest query evaluation clock is
15:29:41.052084Z; HTTP200/available/worker completed/response closed,16 examined,
4 current matched and12 outside the six-hour window. Earlier recorded query
responses have16 or20 entries and the same4 matches. The retained facts are:

| Captured headline | Original publication,27October UTC | Publisher label / match |
| --- | --- | --- |
| Form 8K IP Strategy Holdings Inc For: 27 October By Investing.com |13:27:28|Investing.com Nigeria / company_name |
| An October 23 quarterly report leads to a Nasdaq decision for IP Strategy Holdings (Nasdaq: IPST). |13:11:45|Stock Titan / ticker_token |
| IP Strategy Holdings, Inc. Regains Compliance with Nasdaq Listing Rule |13:02:23|The Globe and Mail / company_name |
| IP Strategy Holdings, Inc. Regains Compliance with Nasdaq Listing Rule |13:01:48|Corsicana Daily Sun / company_name |

These retain published_original/UTC with selected_time_basis=published and no
update substitution. All are current at their recorded acquisition and cached
reconsideration clocks. The first headline identifies a filing, not its substantive
event. The second is an indirect summary, not proof of earnings beats or regulatory
approval. The last two explicitly assert regained Nasdaq listing compliance, but
lack the underlying rule, filing facts and full article text. Their supplied
summaries repeat title/publisher rather than add substantive content. Raw feed or
linked article bodies are absent. No present-day research or invented event detail
is used to fill these gaps.

`catalyst_policy.classify_headline` returnsNone for all4. Issuer matching succeeds,
publication is current, and no dilution/offering or research-only veto applies;
`assess_issuer_event` then rejects all4 as no_catalyst_classification BEFORE any
positive subject-event attribution. This is not issuer identity loss, a stale
article or a primary-coverage veto. Common-provider event_class/classifier_version/
catalyst_classification are intentionallynull (strategy adapter is authority),
not evidence of failed publication. The RSS adapter and canonical store retain
all4 unclassified facts; the scanner reclassifies facts on each read and produces
qualification_reason=no_valid_canonical_event / ross_catalyst_valid=false.
Acquisition stays degraded separately and would not erase a genuinely qualifying
issuer event. Cache/handoff revalidation reaches the same result without HTTP or
canonical writes. The56 real reconsiderations produce no positive Focus.

The two listing-compliance headlines are retained separately under existing
publisher+title/URL identity, not semantically deduplicated into a single event.
publication_count/independent_source_count=4 are stored presentation metrics,
not proof of four independent events, original reporting or catalyst qualification.
Do not infer the repeated syndicated headline is independent confirmation.
Stale query exclusions include23October earnings text; that is neither the27October
listing event nor current earnings evidence and must not be republished as fresh.

### Authoritative policy comparison: no demonstrated implementation defect

`src/strategies/ross_momentum/strategy_policy.py` requires a real catalyst
(require_catalyst=true, F_CATALYST_REQUIRED), prefers PR/SEC/major-outlet quality
and never permits blind inclusion on price/RVOL alone. `CatalystModelV2` describes
quality and source preference but does NOT enumerate a listing-compliance class.
Its broad "news/earnings/sector move/upgrade" examples are not a rule that any
issuer news/SEC filing qualifies. The shared executable catalyst authority has
specific existing earnings/FDA/contract/analyst/press-release/theme vocabulary,
strict issuer-event assertions and publication checks. It contains no listing,
regained-compliance, Nasdaq-decision or generic8-K rule. No authoritative policy
located explicitly declares regained listing compliance a qualifying class, nor
specifically prohibits it as an enumerated class. It is **undefined for positive
qualification**, and therefore intentionally fails closed under the existing
recognized-event contract. Calling this a broken classifier or mapping it to FDA
"approval" or generic PRESS_RELEASE would be an unauthorized policy expansion.
The receipt establishes a concrete policy question, not a production repair.

### Other Watchlist issuers and limits of captured exclusions

AEYE / AUDIOEYE INC uses the supplied full legal phrase and `$AEYE` query. Latest
HTTP200 query examines28 entries:28 stale,0 current,0 relevance rejections. Latest
publication00:20:18Z (earnings headline), well before the09:29:32.864743Z window.
Earlier responses contain28 or37 entries and0 retained matches. AARD / AARDVARK
THERAPEUTICS INC uses full legal-name query, effective matching alias AARDVARK
THERAPEUTICS; latest20/20 entries stale, newest26October12:51:57Z,0 current/matches.
Earlier responses20/78/79 entries likewise have0 matches. Neither marker publication
proves an article, a complete search or no real-world issuer news.

NUWE / NUWELLIS INC uses full legal-name/`$NUWE` query. Latest29 entries:28 stale,
1 current,1 issuer_match_unverified,0 retained. Captured current title is
"Nuwellis Announces Acceptance of Multicenter Pediatric Aquadex Study in Pediatric
Nephrology" (The Manila Times), published12:06:17Z, evaluated15:25:20.800656Z.
The title/summary have only the one-word brand Nuwellis, not the supplied legal
phrase Nuwellis Inc or ticker notation. The bounded exclusion captures actual
patterns and unredacted, untruncated title/summary (URL sample truncated). Existing
`company_aliases_for_symbol` deliberately preserves NUWELLIS INC while refusing
its ambiguous one-word core, the same conservative contract documented in PR1131.
Offline replay reproduces issuer_match_unverified. This is not recurrence of the
repaired loss of the FULL legal name. The captured headline also has no current
recognized catalyst class; "Acceptance" of a study in a publication cannot be
silently converted to FDA approval. Prior responses18/19/29 entries also retain0.
No matching or classification expansion is justified by this receipt alone.

Successful fixed-feed Investing/Forbes acquisition is distinct from issuer event
coverage: historical console rows include one Forbes deadline-exhausted response;
latest57 records show recognized current Investing10/Forbes25 entries with no
new Watchlist event. Denied, redirecting, timed-out and deadline-truncated sources
remain failures. Only bounded exclusion samples are retained, not full responses;
unsampled exclusions and unavailable bodies cannot be exhaustively adjudicated.

### Offline evidence checks and smallest next action

Ten private hard-guarded receipt controls pass in3.84s at accepted source. They
replay terminal/privacy/inventory validation;18 positive barriers and39 deadline
exclusions; all4 original IPST articles at every captured IPST retrieval completion
and reconsideration clock; actual scanner qualification and cached canonical
handoff rejection with unchanged private cache bytes; and AEYE/AARD/NUWE captured
exclusions. Tests live in scratch `/workspace/work/test_ipst_receipt_offline.py`,
log `/workspace/work/ipst-offline-controls-final.log`; source-manifest and structured
log verification are additionally recorded in `/workspace/work/ipst-summary.txt`.
These are captured-fact replay, not synthetic positive-event proof. No code,
configuration, acquisition profile, request budget, source membership, classifier
or runtime harness is changed; full runtime suites are not repeated for prose.
Independent exact-head review and proportionate documentation CI receipts belong
on the resulting checkpoint-only PR; this does not alter the literal accepted
operator pin or authorize another observation.

**Smallest next action:** make an explicit Ross catalyst-policy decision about
whether, and with what bounded factual/attribution requirements, regained exchange
listing compliance can qualify. Use the captured IPST text and the absent rule/body
facts as the concrete decision case; keep generic8-K and indirect Nasdaq-decision
headlines separate. Do not implement a positive class merely to create Focus.
If policy accepts a new class, specify acceptance/rejection examples and evidence
requirements first, then implement/review deterministic offline controls; any
missing factual verification remains a separately bounded authorization. If policy
retains the current vocabulary, preserve IPST's negative result. Neither choice
justifies an unchanged observation hoping for another catalyst or another provider
probe solely for matches. No new acquisition, forced selection, freshness
relaxation, trading or holdings action occurred in this analysis.

Five unmatched positions remain separate ownership/entry blockers, untouched.
Earlier timeout/negative-age causes and all historical failures/partial receipts
remain unresolved/preserved. `PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

## 27October deliberate listing-compliance policy addition, provenance fail closed

Accepted main `dca4fb31b8c2b10b235e63534d5308366993d392`, tree
`b845306952f2446b96e8e7fb9cc1482117daa524`, is PR1137's actual merge at
2026-10-27T16:21:20Z from reviewed head
`63e21d5b90c37c8f886645ea4a015e2066d300b2`. Exact-head independent agent
review5670242435 approved without blockers. CI40536270864 passed Linux3340/3skipped
and Windows3342/1skipped, including native float-cache, cache startup and the
PowerShell5.1 gates. Its test-merge tree equals the reviewed checkpoint tree.
This merge is documentation only; the archived natural observation remains the
accepted-dcb65 receipt, never a new observation at dca4 or the policy-change head.

The explicit coordination decision NOW makes confirmed regained/restored exchange
listing compliance an eligible issuer-event class. This is a deliberate addition,
not historically defined Ross policy and not a repair of the archived classifier's
failure to infer an undefined class. `strategy_policy.py`'s authoritative catalyst
commentary records the addition; `policy/catalyst_policy.py` implements the separate
LISTING_COMPLIANCE_REGAINED rule. Mandatory catalyst, all other event classes,
uncertainty/dilution/ownership protections and strict six-hour original-publication
limits are retained. Eligibility never establishes automatic Focus/setup/trigger/
decision/risk/READ_ONLY intent acceptance.

### Explicit original-publisher constraint; no invented trust authority

The follow-up coordination instruction requires VERIFIED ORIGINAL-PUBLISHER
provenance. Google News transport, a recognized publisher name, feed availability,
fixed-feed membership, verified_source/credibility flags and multiple syndicated
copies cannot supply this proof. The existing common provider and Ross classifier
have no original-publisher verification authority. The historical verified_rss.txt
catalogue is availability research, not such an authority. No publisher allowlist,
feed-route trust inference, live resolution/fetch or arbitrary raw verification
flag is introduced.

Accordingly the dedicated `_verified_original_publisher` boundary is deliberately
fail closed: it returnsFalse in production. A future verifier needs a separate
explicit implementation/review decision. Under this change the new event can be
recognized and retained diagnostically, but cannot become production-eligible
without verified provenance. The precise rejection is
listing_compliance_provenance_unverified. Other catalyst classes do not acquire
this new provenance requirement or change their existing source semantics.
This limitation is explicit, not a hidden assumption that future Google copies
or newly healthy fixed feeds will pass. No captured publisher is newly verified.

The title rule requires a direct named-issuer assertion such as "regains" or
"has regained/restored compliance with Nasdaq Listing Rule". It supports bounded
Nasdaq/NYSE/NYSE American/NYSE Arca/New York Stock Exchange/American Stock Exchange
listing-rule/requirement forms, including the minimum bid-price/equity listing
requirements. It does not use a broad compliance keyword. The supplied complete
legal issuer phrase may establish the subject, without inferring a bare brand.
Deficiency/delisting/appeal/extension/plan/seeks/conditional/negated/uncertain and
peer-owned assertions fail closed. Generic8-K and indirect Nasdaq-decision text
are not earnings or FDA approval. A distinct existing eligible FDA/earnings/etc.
assertion is not shadowed by a listing mention or by the issuer's theme name.

Even with a future verified publisher, original published_original/UTC and the
actual evidence timestamp must agree exactly; update-only dates cannot substitute.
An already-seen older event cannot gain a new lifetime through a wrapper date.
The existing age<0 and age>21600 rejection remains strict, including one
microsecond boundaries; age0 and exact21600 remain eligible time boundaries.
No clamping, local timestamp substitution or skew tolerance is added. Existing
financing/offering vetoes remain; new-class financing/private-placement/uncertainty
text and retained offering flags cannot supply a positive witness. A single-source
conditional positive decision explicitly reports independent_confirmation_verified
=false; neither replication counts nor cached classification tags establish
independent confirmation. Presentation counts are not corroboration authority.

### Captured four-article replay: no eligible IPST item

`tests/fixtures/ipst_listing_compliance_receipt.json` contains only the4 already
shareable captured facts and189 recorded retrieval start/completion, query
assessment and cached reconsideration clocks. It preserves original publication,
headline/summary, URL and source/timestamp provenance from archive
SHA256 `7223eeafe07f3de0f8126de707d7ae17e09426009c0f1e945d56f08c9c1af3ae`.
There are no raw bodies or invented original-publisher verification records.
At every recorded clock, all4 remain fresh and issuer-matched, but NONE meets
every new requirement:

| Original27October publication UTC | Captured item | New-policy replay |
| --- | --- | --- |
|13:27:28|Form8K IP Strategy Holdings Inc For:27October…|no_catalyst_classification; no substantive completed listing assertion |
|13:11:45|An October23 quarterly report leads to a Nasdaq decision…|no_catalyst_classification; indirect decision is not an asserted restoration |
|13:02:23|IP Strategy Holdings, Inc. Regains Compliance with Nasdaq Listing Rule — The Globe and Mail|new event wording recognized; listing_compliance_provenance_unverified |
|13:01:48|Same compliance title — Corsicana Daily Sun|new event wording recognized; listing_compliance_provenance_unverified |

No body, original issuer statement, rule-specific verified publication or trusted
verification record has been supplied for those two copies. Their names, Google
URLs and repeated headline do not fill this gap. They remain separate captured
article facts, not independent confirmation and not a retroactive positive event.
The archived Focus0, eight DROP_NO_CATALYST rejections,56 zero-positive cached
reconsiderations and zero intents are unchanged; no replay result is relabelled
natural acceptance.

### Guarded conditional proof and preserved gates

Positive controls are explicitly **CONDITIONAL SYNTHETIC**: only tests inject a
hypothetical verification witness at the fail-closed publisher boundary. That is
not a production verification implementation, not a trusted-source catalogue and
not verification of any captured IPST publisher. The normal fake-feed → existing
RSS adapter → single canonical writer → cache-only consumer path publishes one
synthetic completed event, deduplicates its duplicate and reads it without new
HTTP or canonical writes. Normal selection gates use explicitly synthetic valid
market inputs. Separate controls execute the actual existing
reassess_ross_watchlist path on a retained synthetic shortlist with synthetic
quote refresh, not just a mocked Focus result. It may select the synthetic row
only with the hypothetical provenance witness and all normal market gates passing.
Production default rejects it before quote refresh. No scanner candidate, actual
Focus, setup or intent is injected into an operator observation.

Negative controls retain stale/future/missing/update-only/mismatched-original and
old-wrapper dates; uncertain/negated/deficiency/appeal/extension and peer events;
source/flag/replication spoofing; handoff revalidation; retained financing vetoes;
and actual stale/untrusted/wrong-symbol quote, spread, halt, float and RVOL gates.
The conditional positive expires at the original six-hour boundary, even after
cache restart/handoff. All source/canonical cleanup and ownership remain with
existing owners. No acquisition routes, source membership, request caps, worker
limits, total8s or5.2s/2.8s allocations, scheduling, privacy/capture budgets,
canonical writer or operational harness are changed.

Qualification profile becomes `ross_issuer_event_v10_listing_compliance` in request
and acquisition fingerprints. Old v9 coverage cannot certify the new policy;
cache-only reads remain provider-free/non-writing with coverage_unknown. Existing
article facts, older qualification cohorts and other valid catalyst classes are
preserved and reclassified; normal bounded refresh/cadence creates/reuses v10.
The existing profile-specific regression assertion is explicitly updated, not
weakened. Source/retrieval failures and incomplete coverage remain honest.

Guarded affected validation passed393 cases before four final production-no-trust
controls were added. Final85 new-class controls pass, including serialized
restart/handoff revalidation. Changed-head CI receipts are recorded on the
resulting draft PR. All commands use the existing Python and
native-curl offline startup guard. Development-only initial fixture failures
(serialization using a mismatched datetime subclass and RFC formatting that lost
synthetic microseconds) were fixed in fixtures, never by relaxing production time
checks; their scratch logs are retained. No full local suite is repeated after
related controls pass. Independent exact-head review and appropriate changed-head
Linux/Windows CI, including native cache and PowerShell gates, are required before
controlled integration; final receipts belong on that PR.

**Smallest next action:** define and review a bounded original-publisher
verification contract and identify what existing captured evidence could satisfy
it, without treating a source name/feed health/syndication as proof. There is no
reason to repeat an unchanged natural observation to make IPST pass. Any future
verification implementation or bounded acquisition is a separate explicit task;
no live fetching is performed merely to manufacture a positive example.
Five unmatched positions remain untouched and separately blocked. Historical
failed/partial receipts and unresolved earlier timeout/negative-age causes remain
preserved. No acquisition, operator rerun, holdings action, trading or readiness
upgrade occurred. `PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

### Preserved first changed-head CI failure and deterministic worker-order control

CI40545024798 at first reviewed head
`7abfd3ea84c5c39d3840edafc030296d2c125bfe` passed Linux3425/3skipped, but Windows
finished1failed/3426passed/1skipped. The failure was
`test_ross_operational_issuer_news::test_actual_enrichment_witness_batch_cache_and_canonical_queries`:
its fetch-stub invocation list began with Benzinga rather than Google News. All
nine URLs remained unique and the preceding original assertions for retained
qualification witness, canonical publication and owned cleanup passed. Native
float-cache/ownership controls passed separately; downstream cache-startup and
PowerShell steps were skipped after the suite failure, and harness artifact upload
failed because those artifacts were not produced. This failed receipt is retained;
it is not reported as a successful Windows run or silently retried.

Exact source gives queries priority in ordered source SUBMISSION. Its concurrent
ThreadPoolExecutor does not promise the OS starts those workers in that same
order. Source being unchanged is not the reason this is a test defect: a guarded
Event-controlled offline replay deliberately holds the submitted query until a
fixed-feed worker runs, reproducing the exact old `urls[0]` assertion failure while
all nine requests, witness and cleanup checks hold. Scratch reproduction
`/workspace/work/listing-windows-order-before.log` records that demonstrated cause.

The affected test now checks first-query priority against actual lifecycle
submission order, exact nine unique fetch/submission URLs, one query, <=4 workers,
and every existing retention/qualification/cache/no-Yahoo/cleanup assertion.
It is parametrized for normal and deliberately reversed worker start, with only
a bounded two-second fixture rendezvous inside the existing fast allocation.
The reversed case requires a fixed-feed stub to run first while Google remains
first SUBMITTED. Production executor ordering, request scheduling and deadlines
are unchanged; no test is skipped, no PermissionError suppressed and no retry is
introduced. New-head independent review and CI must include this deterministic
control and the previously skipped cache/PowerShell gates. Final results belong
on the same draft PR; no unchanged-head CI rerun is requested.

## Minimal original-publisher contract for listing compliance (documentation only)

Accepted main `f4def1608e7ff57ef53e383c1f8a1c8423e75d24`, tree
`a792d85c764ccaf3e821a3fe891cd555c48457e9`, is the actual PR1138 integration.
PR1138 merged at2026-10-27T17:33:59Z. Reviewed head
`4fab1586efcc983497f535235ea44acc538c21f1` has that same tree.
Independent agent review5671236395 approved the exact final head; source review
5671058469 carries forward. Final CI40547209474 passed Linux3426/3skipped and
Windows3428/1skipped, including native cache, cache-startup and all PowerShell
steps (39 observation-harness controls; artifact12753503789). Failed first
CI40545024798 and its deterministic worker-order test repair remain recorded above.
This section defines a proposed minimum contract only. It does not implement a
verifier, verify any domain, activate a source or open the production gate.

### Evidence inventory at the accepted source

| Fact | What is retained | What it cannot prove |
| --- | --- | --- |
| Requested feed/query URL | source_id/source in retrieval diagnostics; optional raw sidecar url; SharedFeedPool uses requested URL as key | Article-to-response binding is not complete merely because a source row and article appear in one batch |
| Final/effective URL | No response.url/final URL or redirect-chain field is persisted; all supported Requests paths disable redirects and reject3xx | No independently recorded final-response origin; no redirect target is accepted or silently resolved |
| Publisher/article links | Article link/reference_id; detailed source_provenance has feed_label, publisher_label_basis, publisher_url and source_group; raw_title retained for detailed paths | Google item.source href is a claimed publisher link, often a site root, not authenticated original-article provenance; canonical-link declarations are also claims |
| Response identity | HTTP status, request/parse durations, worker completion and response closure in source diagnostics; reuse/attempt facts in rich entry diagnostics | No immutable response receipt ID, authenticated publisher/entity binding, retained response headers or TLS-peer/association proof |
| Original publication | Detailed published_original/UTC, updated_original/UTC and selected_time_basis; canonical published_at, first_seen_at/fetched_at; ordinary paths can lack the detailed provenance | Dates are source assertions; neither retrieval time nor updated/syndication time proves original publication |
| Article identity | Operational RSS ID is truncated SHA256 of symbol/title/publisher/URL (publication participates only without URL); ordinary RSS uses truncated SHA1; canonical dedup additionally keys normalized article fields | These are deduplication identifiers, not signatures or full cryptographic provenance; an unchanged URL/ID can acquire a different wrapper date |
| Content hashes | Opt-in RawFeedCapture saves full captured feed-byte SHA256, bytes/limit/body_complete, requested URL and acquisition/evaluation clocks. Exclusion samples hash original title/summary/URL and a diagnostic article identity | Feed-body hash is not an original article-body hash. Diagnostic field hashes do not authenticate authorship, and clipped/redacted samples are not complete content |
| Entity identifiers | Diagnostics can carry supplied CIK/LEI and security IDs/conId/ISIN/FIGI/exchange metadata | Supplied IDs are not automatically verified legal-entity/domain associations; ticker/exchange routing/name similarity is insufficient |

Exact owners are news_fetcher._fetch_feed / _entry_date_facts, rss_raw_capture,
feed_pool, rss_exclusion_evidence, batch_rss_adapter._evidence_id and evidence_store.
Detailed operational acquisition covers direct fixed RSS and Google query routes;
ordinary FAST paths retain less detail. Optional raw capture is not enabled merely
because the bounded streaming path enforces512KiB. A sidecar's body_complete means
captured EOF, not publisher verification or complete issuer/search coverage.
SharedFeedPool caches parsed results/timings/errors by URL; reused rows are not new
requests or new independent responses. Sidecar filenames hash the requested URL
and can be overwritten for that URL: they are not immutable per-response IDs.
No current canonical field binds a specific article entry to an immutable full
response receipt and independently verified domain-association record.

### Enforceable decision rule; authority bootstrap is a prerequisite

Apply this contract ONLY to LISTING_COMPLIANCE_REGAINED. Default is
listing_compliance_provenance_unverified. No cached boolean, domain list, publisher
label, verified_rss catalogue entry, feed health, HTTPS certificate/hostname or
number of copies can establish a positive result. No existing original-publisher
trust authority or verified IPST/domain mapping was found or is created here.

A positive provenance decision requires BOTH of these independently reviewable
objects, bound to one issuer and one original document/event:

1. **Entity/domain association evidence.** An exact, retained authoritative record
   identifies the issuer by a stable legal-entity identifier and legal name, and
   explicitly designates the specific official announcement/IR host, or identifies
   the exchange itself and its official notice host. An issuer record could be
   a regulator filing or exchange-maintained issuer directory explicitly linking
   that entity to its official site; an exchange notice additionally identifies
   the subject issuer by a stable listing/entity ID. These are acceptable TYPES
   of evidence, not declarations that any particular URL/domain is verified.
   The record's own origin must be authenticated against a separately accepted
   regulator/exchange identity reference or authenticated supplied original.
   That trust-anchor reference, method of authentication, bytes/hash, relevant
   excerpt, applicable date and independent review/acceptance receipt must be
   explicit. A website asserting its own identity, two websites copying one
   another, DNS ownership, a logo or an ordinary TLS certificate is circular or
   insufficient. No accepted anchor/reference currently exists in this case;
   without one the verifier MUST remain closed, even if two GETs succeed.
2. **Specific original announcement/notice.** Capture the complete bounded original
   document from the exact host/path scope designated by that association, with
   original document/version ID, title, original publication and the actual
   issuer/regained-listing assertion. Record requested and observed final URL,
   response status/identity, acquisition clock, complete-body hash and entry or
   paragraph identity. Unexpected host/path, redirect, incomplete body, parser
   recovery, missing original time or unresolved identity conflicts cannot pass.
   A self-declared rel=canonical, source href, copied attribution or a publisher
   root URL is not the original document. The actual unaltered title must still
   pass the dedicated issuer-subject rule; an authenticated but generic exchange
   notice or8-K is not automatically a qualifying catalyst.
   A complete official RSS/Atom entry may itself be the original notice if it
   contains the required assertion, original time and document/entry identity;
   an aggregator excerpt is not equivalent. A linked article is never fetched
   automatically merely because the entry provides a link.

Acceptance of the association is a case-specific, evidence-backed decision; this
contract does not designate an approver, bootstrap trust from a new allowlist or
pretend that repository approval alone authenticates source bytes. A separately
explicit decision must name the authentic reference and approval responsibility
before implementation can enable positive verification. If those cannot be
provided, stop with unverified evidence; do not start open-ended domain research.

The minimum proposed receipt has: schema/policy version; legal issuer ID/name and
symbol-as-of date; exchange/listing identifier; association-record identity/hash,
exact authorized host/path/time scope and authenticated-anchor/review references;
requested/observed final original-document URL; per-response identity/status/
acquisition clock/completeness/body SHA256; original document/version and entry
identity; original publication raw/UTC; preserved issuer/listing assertion and
its content hash; event key; and verification state/reason/decision clock.
The event key binds issuer, exchange/listing requirement and original announcement
identity/time, not a ticker or recurring headline alone. The receipt's full binding
hash covers all of those source/association/article/event/policy facts.

Consumers MUST recompute/match this binding to the exact retained article facts,
recheck the accepted association's scope/version and any conflict/revocation,
and reapply original-publication/future/expiry, attribution and financing vetoes
on every canonical read, cache reuse, Focus/setup handoff and decision boundary.
A source record can be an input to another review, but its verified=true flag can
never authorize another article, URL version, issuer, event or replacement date.
Knowledge acquired later cannot establish that proof existed during an earlier
operator window. Acquisition/verification timestamps never renew event freshness.
Preserve the earliest established original publication for the same announcement;
a later copy/update/reprint cannot reset it. An unknown original or contradictory
original dates is unverified/conflicting, never replaced with the freshest date.

### Four evidence states and examples

| State | Required facts / example | Eligibility consequence |
| --- | --- | --- |
| direct_original_verified | Accepted, non-circular entity/domain association plus the bound original issuer announcement or exchange notice; e.g. a SYNTHETIC regulator-record→issuer-host mapping and complete original "Issuer X regains compliance with Nasdaq Listing Rule" notice | Provenance requirement can pass; original title/time/attribution/veto and all market/ownership gates still apply |
| corroborated_syndication | A retained copy is explicitly linked to that verified original document/version, same issuer and same listing event/original publication; source references/assertion correspondence are retained and conflicts resolved | Evidence is derivative of ONE original event. Use the original proof as witness; copies cannot add independent confirmation or refresh publication |
| unverified_aggregation | Google title/publisher label/root link; a healthy direct RSS feed with no authenticated original association; two copies of the same title; or bare verified_source flag | Diagnostic only; listing_compliance_provenance_unverified |
| conflicting_provenance | Issuer ID or authorized host differs; source says restoration but original says deficiency/appeal; original publication predates the presented fresh wrapper; altered body/entry against the bound hash | Reject the affected binding/event claim; retain both observations and a specific conflict reason; do not silently choose the favorable copy or erase unrelated valid catalyst facts |

A legitimate notice that is stale/future, conditional, negated, a plan/extension,
peer-owned or subject to a retained financing veto remains ineligible even with
verified provenance. Identical body hashes prove matching bytes, not independent
reporting; differing hashes due only to formatting do not by themselves prove a
conflict, but require documented correspondence rather than guessed equivalence.
A source-verified generic filing still fails the dedicated event rule. All other
catalyst classes retain their current policy; this does not impose a new trust
framework on earnings/FDA/contract/etc.

### Existing IPST evidence cannot satisfy the contract

All four captured links are Google article links. Their publisher_url values are
claimed publisher-site roots; none is an authenticated original issuer/exchange
announcement URL. No case-specific authenticated domain association, original
issuer/exchange document body/version/hash, original-response identity/final URL
or accepted verification receipt is retained. The summaries repeat headlines and
publisher labels. Optional private feed captures from other diagnostics are not
present in these shareable receipts and must not be assumed available; even a
Google feed body would establish aggregator bytes, not issuer/exchange ownership.
Investing/Forbes diagnostic health receipts establish feed health, not this proof.
The four IPST items therefore remain ineligible: generic8-K/indirect decision have
no qualifying assertion, and the two restoration headlines remain provenance-
unverified. No archived Focus0/zero-intent result or earlier receipt is upgraded.

### Smallest optional acquisition, only after explicit prerequisites

The missing objects are precisely an authenticated case-specific association
record and the exact original announcement/notice, with the binding fields above.
First require an accepted anchor/association reference and explicitly supplied
exact document URLs plus issuer identity. Do not guess an issuer website, resolve
the opaque Google link, search for a notice or discover links under this task.
If an authenticated association document is already supplied offline, only ONE
original-document GET may be needed. Otherwise the smallest proposed acquisition
is TWO exact GETs: the supplied association-record URL and supplied original-
document URL, conditional on the independently accepted bootstrap reference.
These are prerequisites, not assertions that such URLs/records are currently known.
An exchange notice still needs the authenticated exchange-host association and
subject issuer binding; it does not evade the bootstrap requirement.

For a separately authorized future caller: at most2 requests, one per exact URL,
shared/deduplicated for the case; max1 concurrent; one8s absolute acquisition budget;
5s per-request cap clipped to remaining;512KiB per body/1MiB total; owned cleanup10s
and supervisor45s. No redirects, retries, query/fallback fanout, linked-article
fetches, broker/scanner/Focus invocation or operational publication. A failed,
truncated, unavailable or unsupported document remains explicit incomplete
coverage. Original6h publication/future rules apply at eventual qualification,
not at an artificially chosen replay/fetch clock. The existing fixed eight-route
and Investing/Forbes two-route callers must not have their literal scope silently
replaced by this case. No such caller is implemented or executed here.

Reuse the bounded transport/lifecycle, opt-in raw sidecar, sanitizer and recorded-
clock parser replay ownership. HTML/PDF is not valid RSS: a future minimal capture-
only document adapter would need explicit format/size validation and a bounded
extractor; do not feed it to the RSS parser or call non-feed content available-
empty. Unsupported/oversized documents stop the attempt rather than trigger more
fetches. Raw source/association bodies remain private; a separately privacy-scanned
report contains bounded sanitized excerpts (existing512-title/1024-summary limits),
identities/hashes/timestamps, decision reasons and explicit missing/truncated
coverage. Do not package the raw bodies into a shareable ZIP or retain cookies,
authorization headers or unrelated response secrets.

### Minimal implementation plan and proportionality decision

If and only if the case prerequisites are explicitly accepted, implement one
listing-only receipt validator at the existing _verified_original_publisher seam.
Keep defaultFalse for absent/unverified/conflicting receipts. Extend the existing
bounded acquisition/capture owner to record observed final URL, immutable response
identity and document/entry hashes; do not add another acquisition engine or
canonical writer. The canonical service/evidence store alone may publish the
article plus its bounded proof references after validation. A diagnostic sidecar
or user-supplied raw flag cannot self-publish authority. On reads/handoffs, validate
the receipt against the independently accepted reference and actual article/event,
not against its own boolean. Version the listing-only verification contract and
coverage fingerprint; preserve original timestamps and historical facts.

Offline implementation controls would cover exact binding and case approval,
changed hash/URL/issuer/version/date, missing or circular association, conflict/
revocation, incomplete/redirect/non-feed documents, copied versus independent
claims, original-date expiry/future boundaries and cached/handoff revalidation.
Reuse existing canonical single-writer, lifecycle cleanup and market-gate tests.
Keep positive proof explicitly synthetic until an actual accepted case exists.
No source, verifier or production profile is changed by this documentation task.

**Recommendation: park implementation/acquisition of this optional class now.**
The finite contract above exposes an absent authority/bootstrap and absent source
objects; further speculative plumbing to qualify IPST would be disproportionate.
No live lookup is justified merely by repeated captured headlines. Reopen only
with the named case-specific reference and exact original-document evidence/URLs;
then the one/two-request verification has a defined information gain: authentic
issuer/exchange origin and immutable event binding, not another source-health or
issuer-match count. Do not block acceptance work for already-supported catalysts
on completion of this optional class. Their existing rules and acceptance gates
continue unchanged; this contract authorizes no observation or forced progression.
Five unmatched positions remain untouched and separately blocked. Preserve all
historical failures/ineligibility and unresolved timeout/negative-age causes.
`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

Documentation-only verification: exact source inspection above; git diff --check;
source/tests/scripts/workflow/requirements unchanged from accepted f4def160.
A guarded replay of the four retained IPST articles at189 recorded clocks made756
negative decisions:378 no_catalyst_classification and378
listing_compliance_provenance_unverified, with every original publication preserved
and the production verifier stillFalse. Fixture SHA256 remains
`7641374e4727e71011599e114dd1c013f94961cbee10ddff1294ff09a063c17f`.
No acquisition occurred. Existing source review/CI receipts above are carried
forward; full suites are not repeated for this prose-only contract.

## Supported-catalyst critical path at accepted f4def160 (27October)

The maintained checklist above is updated in place through PR1138. This section
supplies its evidence/definitions, not a second checklist. Accepted runtime source
remains `f4def1608e7ff57ef53e383c1f8a1c8423e75d24`, tree
`a792d85c764ccaf3e821a3fe891cd555c48457e9`. Saved optional contractc7111fc2 is
preserved as documentation. Listing-compliance implementation/acquisition is
PARKED with _verified_original_publisher=False; no further attempt to qualify IPST
is part of this work. Its historical negatives and all prior receipts remain.

### Completed work and natural evidence boundary

PR1127/1128 transport capture reservation and Windows float-cache concurrency,
PR1129 observation ordering, PR1130 shared future-quote admission, PR1131 full
legal-name matching, PR1133 truthful RSS availability, PR1135 fixed-feed replacements
and PR1136 completion/owned-cleanup fallback are integrated in accepted source.
PR1138 adds only conditional listing-event policy with no production provenance
verification. The detailed sections retain each exact reviewed tree, failed and
successful CI/review receipts. PR1132's fixed-eight diagnostic and PR1134's
Investing/Forbes caller/receipts remain separate from production readiness; their
unmerged caller branches are not silently made runtime dependencies.

Carry forward final source CI40547209474 (Linux3426/Windows3428, respective3/1
skips), independent review5671236395 and all cache/PowerShell checks. Do not rerun
them just to reconcile this status. Current runtime source is unchanged by the
new joined test. Existing diagnostics establish transport callback/coverage and
strict quote rejection, not a cause for the historical timeout/negative age.

Natural evidence remains:086a archive10def277… has3×50 scans/K4 and12 catalyst
rejections;49ba archive6b9f4ee5… has3×50/K3→4→2 and9 rejections;dcb65 archive
7223eeaf… has3×50/K3→3→2 and8 rejections. All retain terminal PASS/exit0 and absent
natural downstream progression. Latest dcb65 naturally establishes bounded v5
fallback after the required primary barrier, not complete source coverage or an
eligible event. Its56 cache reconsiderations are positive0/Focus0; all217 strategy
outputs/arbitration inputs/risk inputs are0. No actual [RISK][DECISION] appears.
This is a genuine formation absence, not evidence that217 positive intents were
hidden by the ownership guard. No current receipt proves a naturally qualified
supported event feeding a fresh setup/trigger and concrete strategy intent.

### Supported classes and existing offline proof (actual policy scope)

The executable CATALYST_KEYWORDS/forms and assess_issuer_event currently support
nine labels: EARNINGS (earnings/guidance), FDA (FDA/approval), CONTRACT (contract/
partnership), ANALYST_ACTION (upgrade/downgrade/initiates), PRESS_RELEASE,
TECH_CATALYST (AI/artificial intelligence/quantum/semiconductor/GPU),
CRYPTO_CATALYST (crypto/bitcoin), EV_CATALYST (EV/electric vehicle/battery), and
DEFENSE_CATALYST (defense/military). These are bounded lexical/event rules, not
claims of unrestricted semantic recognition or permission from a keyword alone.
Issuer subject/event ownership, explicit assertion, original publication0≤age≤6h,
future/update-only/research exclusions, retained financing vetoes and normal
selection/market gates still apply. No new original-publisher contract is imposed
on these existing classes. LISTING_COMPLIANCE_REGAINED remains a recognized but
provenance-unverified parked class, not a tenth production-positive route.

Existing test proof maps as follows:

- Canonical acquisition/publication, retention witness, deduplication and cache:
  test_ross_operational_issuer_news::test_actual_enrichment_witness_batch_cache_and_canonical_queries
  (actual adapter with fake transport, canonical service/store, normal and reordered
  workers), test_pr1079_globenewswire_positive_control, and
  test_news_catalyst_lifecycle_audit. These are offline/synthetic facts, not current
  natural-news availability. Generic publisher/velocity metrics do not qualify news.
- Canonical cache→ordinary Focus reconsideration and Core handoff:
  test_watchlist_between_scan_reassessment::test_empty_focus_reconsiders_later_publication_without_http_or_discovery
  and test_core_real_helper_handoff_after_empty_focus. Actual reassessment/strict
  quote gates run; the latter's strategy processor is a stub and cannot certify
  the real pattern/intent path. test_positive_catalyst_lifecycle covers serialized
  restart, expiry, retained vetoes and setup handoff; stored CONFIRMED flags fail.
- Fresh real pattern/trigger→strategy intent: test_ross_selected_setup_handoff's
  real consolidation registry control and
  test_ross_bullflag_micro_boundaries::test_real_bull_flag_production_intent_reaches_actual_readonly_risk
  use real detectors/production intent APIs. The PR1082 three-bar positive supplies
  an explicitly offline target/FakeRegistry, so it is not proof the production
  three-bar detector supplies that target. Missing/stale required timeframe,
  structural target/stop, unready trigger and provenance negatives are retained.
- Risk: test_ross_end_to_end_pipeline uses another strategy wrapper, simulated
  paper execution and simple pattern/news context; its READ_ONLY wrapper rejects
  intents. PR6 e2e_harness explicitly SIMULATES risk/execution. Neither proves the
  active Core manager's actual RiskEngine call. The bull-flag boundary test only
  asserts a blocked RiskDecision and matching fields; it did not distinguish a
  mode block from DECISION_ARTIFACT_MISSING. Do not relabel these as natural or
  complete active-manager risk integration.

### Filled joined coverage gap and precise implementation gate

New `tests/test_ross_supported_catalyst_critical_path.py` joins the existing canonical
service/store publication, non-writing cache read, normal RTH Focus gates, fresh
1m/5m/10s inputs, REAL BullFlag registry/detector, trigger/decision and strategy
TradeIntent APIs. All data, provider, quotes and bars are explicitly SYNTHETIC;
there is no forced detector result, supplied target override, opaque confirmed
flag or runtime candidate injection. Nine positive templates cover the nine
supported labels; generic news, offering and stale-bar negatives make12 cases.
The stub provider is called once, the cached consumer performs no acquisition or
write, and EClient placeOrder/cancelOrder are forbidden by the controls.

The first fixture alignment attempt correctly produced UNKNOWN position truth
because its fake position clock differed from the news/quote clock; the fixture
now puts position collection on the same controlled clock, without changing source
freshness. An initial analyst template with unsupported attribution grammar was
changed to the existing accepted "JPM receives upgrade" form; policy was not
broadened. Final12 NEW cases pass with the hard Python/native-curl offline
guard. Existing suites/audits were not repeated. The log is
`/workspace/work/ross-critical-path-final-proof.log`. This is local new-case proof,
not a CI receipt for this test branch or natural acceptance.

The joined proof establishes concrete strategy intent formation, but deliberately
DOES NOT call it a complete risk pass. Passing those actual raw intents to actual
RiskEngine.evaluate_trade_intent returns DECISION_ARTIFACT_MISSING for every
supported label. The strategy correctly leaves canonical artifact ownership to
Core; it must not mint arbitrary decision IDs to satisfy risk. Source trace at
accepted f4def160 establishes the missing active integration:

- _run_once_inner unconditionally returns _run_manager_pipeline (line2357).
- Active _run_manager_pipeline contains neither build_decision_artifact nor
  RiskEngine.evaluate_trade_intent. Its RISK_INPUT/RISK_OUTPUT logs describe
  post-guard quote/intent filtering, not an actual RiskDecision.
- The existing canonical artifact builder/ID assignment (line5289/5300) and real
  risk call (line5383) lie after the unconditional return atline4490 in
  _select_watchlist_for_policy. That tail is unreachable. This is not proof of
  current manager risk evaluation, even though those owners exist elsewhere in
  source. No broad dead-code cleanup or architecture migration is proposed here.

This is a demonstrated decision/risk HANDOFF integration gap, not a catalyst,
provider, optional-listing or natural-opportunity defect. No production code is
changed by this critical-path assessment. The new negative risk assertion retains
that gate rather than fabricating an artifact, synthesizing approval or weakening
RiskEngine's fail-closed contract.

### Five-position blocker: exact stage scope

Saved dcb65 evidence records five nonzero broker-only symbols with system
quantity0. Each appears in216 completed five-position cycle snapshots;
the earlier startup snapshot is UNKNOWN, not confirmed empty. This is historical
snapshot evidence, not a fresh broker inquiry. Position-truth/guard/recovery source is
byte-identical between that receipt and accepted f4def160.

position_truth.reconcile_position_truth sets critical_mismatch_count5,
block_new_entries=true and block_exits=true for this saved shape. recovery_engine
marks manual-required and performs no automatic adoption/liquidation/cancellation.
Its printed blocked=true does not by itself return from the strategy pipeline.
Startup/daily/autonomous-recovery guards can independently stop earlier work, but
the five-position verdict in this observed manager path is not a pre-scanner or
pre-strategy suppression: the saved run completed scans/Focus evaluations.

Core's _apply_position_truth_entry_guard runs AFTER strategy formation/integrity
and BEFORE final arbitration/quote-risk admission. It returns[] for every new-entry
intent when block_new_entries is true, including READ_ONLY; there is no natural
IBKR-path exemption. Mock/validation overrides are not a permitted workaround.
The joined synthetic proof forms a real strategy intent, obtains an actual five-
critical verdict from a fake completed position snapshot, then proves this exact
Core guard removes it without mutating the raw input. The block is GLOBAL for
new-entry admission, not limited to trading those five symbols: the synthetic
JPM intent is removed even though its symbol differs from all five fixture
positions. No real holding values are embedded in the new test. This distinguishes:

- A naturally created PRE-GUARD strategy READ_ONLY intent can be observed and
  retained diagnostically while the five positions remain blocked.
- A final Core-admitted intent/risk input, approved entry or paper execution is
  blocked. It is inaccurate to describe this as only a broker-send lock. Current
  [INTENT]/[DECISION]/CYCLE_END raw formation counters are not proof of admission;
  inspect STRATEGY_OUTPUT, ARBITRATION_INPUT/OUTPUT, POSITION/TRUTH/BLOCK and
  reason-coded downstream risk/execution together.
- With those blockers intact, a natural observation cannot certify positive
  admitted entry/risk/paper behavior. Even after a supported event appears, a
  guarded empty risk-input is expected; do not suppress the positions to make a
  target pass. Their disposition belongs to a separately authorized manual
  ownership/reconciliation process, not this task.

### Offline versus fresh-natural requirements and previous audit recommendation

Deterministic/offline: supported-class positive/negative semantics, original-time
boundaries/cache/handoff, joined canonical→Focus→real-pattern→raw-intent contracts,
five-position guard scope, missing artifact/risk call, and the repair's actual
canonical-owner/real-RiskEngine invocation and no-mutation controls. Those last
active-manager integration checks remain the finite implementation gate; completed
source suites and audits need not be rerun merely to rediscover them.

Requires fresh natural market evidence after that gate: a genuinely current
supported issuer event acquired/published through existing bounded sources; natural
TopN/Watchlist/Focus selection; current broker quotes and genuine timeframe bars;
actual pattern/confirmation/trigger; concrete strategy intent with canonical
decision provenance; and honest ownership/mode/risk disposition. Synthetic data
cannot establish any of those natural facts. Terminal safety alone, source health,
partial coverage or another unqualified headline cannot substitute.

**Audit90a96d36 recommendation (implemented by the proposed repair below): implement and review the narrow active-manager READ_ONLY
canonical decision-artifact → actual RiskEngine handoff, using the existing
Core artifact builder and risk owner, without changing ownership or trading policy.**
Completion criterion: an unblocked synthetic supported-event→real-pattern case
executed through the ACTUAL manager has a real canonical decision ID and an actual
RiskEngine invocation with explicit READ_ONLY execution denial, rather than missing-
artifact rejection or marker-only "approval". The five-position case must retain
pre-guard formation evidence, produce no admitted new entry/risk bypass, and emit
its exact ownership rejection. Keep quote/catalyst expiry gates, no force flags,
no broker mutations and no execution submissions. Do not retrofit a random ID,
mock risk approval or invoke risk/execution around the ownership guard. Obtain
changed-head review/appropriate CI when that production handoff is repaired.

A new900s natural observation is NOT the recommended next action now: it cannot
repair the mechanical handoff or certify admitted/risk behavior with the five
positions blocked. After that bounded offline gate is closed, any separately
authorized observation must use the existing natural READ_ONLY harness, a literal
accepted integration pin and RuntimeSeconds900 (existing1260s supervisor), normal
session/no forced candidates/news/setup/intent, unchanged budgets/ownership and
all terminal/privacy protections. Its information gain would be genuine supported-
event→fresh-pattern→intent formation and the exact expected guard/mode disposition;
absence of an opportunity remains negative evidence, not authorization for blind
unchanged reruns. Paper acceptance separately requires authorized ownership
resolution and real risk/broker-fill/protection/partial/target/trailing/exit/recovery
acceptance. Nothing here authorizes that work or upgrades readiness.

All historical receipts, five-position blockers and GUI draft remain preserved.
No acquisition, observation, holdings action, trading or production source change
occurred. `PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.


## Active-manager READ_ONLY canonical decision → RiskEngine repair (27 October)

Production main was rechecked remotely at `f4def1608e7ff57ef53e383c1f8a1c8423e75d24`;
its tree remains `a792d85c764ccaf3e821a3fe891cd555c48457e9`. Saved audit branch
`docs/ross-supported-critical-path` remains exactly
`90a96d36352d1ba2ef3bbfa5ed5689e42ec89a9a`, clean before this work. Proposed branch
`fix/readonly-manager-risk-handoff` descends from that audit, retaining its twelve
local synthetic controls and optional contractc7111fc2. Those twelve cases remain
local audit proof, not CI or natural acceptance. No earlier receipt is superseded.

The active `_run_manager_pipeline` now creates a canonical artifact with the existing
`build_decision_artifact` owner ONLY for READ_ONLY intents surviving execution
integrity, position truth, arbitration and the final strict quote handoff filter.
Core assigns the resulting decision_id, emits the established
DECISION_ARTIFACT_CREATED event and DECISION trace (strategy/mode/session/original
intent payload hash, creation time and cycle identity), then invokes its actual
RiskEngine.evaluate_trade_intent. RiskEngine retains its existing RISK_DECISION
lifecycle, linked to that ID. No arbitrary IDs, parallel risk authority, legacy
pipeline revival or retirement occurred. DEPRECATION_LEDGER is unchanged because
no owner or retirement changed. PAPER/LIVE retain the prior manager path; this
repair does not claim to complete their decision/risk integration.

READ_ONLY approval/denial traces and RISK_OUTPUT now derive from actual
RiskDecision results. A pre-risk temporal veto is labelled QUOTE_REJECTED, not a
fabricated risk decision. Guard losses are identified separately from arbitration
conflicts. POSITION_TRUTH_BLOCK_NEW_ENTRIES remains the final ownership reason,
including the persisted trade-path summary; generic integrity/conflict/session/
ORDER_SIMULATED outcomes cannot overwrite it. Raw strategy formation diagnostics
remain visible. The old mock-survival override is disabled for READ_ONLY, so it
cannot repopulate intents removed by ownership or integrity. No risk call occurs
around that veto. Existing mode authority independently forbids order dispatch.

### Changed-path offline evidence and review boundary

`tests/test_readonly_manager_risk_handoff.py` supplies explicitly SYNTHETIC provider,
position snapshots, quotes and bar streams with hard network denial and forbidden
broker placeOrder/cancelOrder and execution submission. It uses the existing
canonical service/store, a non-writing cache read and actual cached reconsideration
inside Core.run_once → active manager → real StrategyRunner/registered Ross runner
→ REAL BullFlag registry/detector/trigger/strategy intent. No forced pattern, target,
setup, catalyst, intent, risk result or artifact ID is supplied. Startup housekeeping
and acquisition are fixture boundaries, not evidence of broker operations.

Nine new cases establish: canonical supported-event → cached Focus → fresh real
BullFlag → trigger → raw intent → Core artifact → actual RiskEngine, whose explicit
reason is LIVE_READ_ONLY_BLOCK ("READ_ONLY mode forbids new executions"), not
DECISION_ARTIFACT_MISSING. The event collector links both canonical creation and
real RiskEngine decision to the same ID. Clearing the ID independently retains
missing-artifact rejection. A completed synthetic five-broker-only-position verdict
retains raw formation, exact ownership rejection and zero admitted risk/artifact
creation; no quantities are adopted or changed. Generic news, stale required bars,
stale Focus quotes, quote expiry AFTER real formation and execution-integrity
rejection all fail closed. PAPER and LIVE boundary controls prove the READ_ONLY
branch is not entered and no new artifact/risk call or execution submission occurs.
Their controlled raw-intent checks are not full PAPER/LIVE strategy acceptance.

Local focused new/affected validation passed110 cases; after the final reporting-only
per-decision count refinement, all9 new manager cases passed again (8.70s). These
are local synthetic results, not remote CI or natural acceptance. Validation uses
the hard offline guard and includes the saved
critical-path regression, Watchlist continuity, cached reassessment, canonical
artifact and execution-handoff controls. Local logs are retained under
`/workspace/work/readonly-manager-*.log`; exact reviewed-head CI/review receipts
belong to the accompanying repair PR. A wrong expected fixture reason QUOTE_STALE
was corrected to the existing production MD_STALE; freshness was not relaxed.
The completed accepted-source CI40547209474 and review5671236395 remain historical,
not receipts for this change. Appropriate changed-head Linux/Windows CI and
independent exact-head review are required before integration, rather than
repeating earlier completed suites for status alone.

### Previous pre-integration gate and recommendation (superseded by accepted receipt below)

**Then-recommended action: review and accept this bounded repair only after its exact-head
independent review and changed-head Linux/Windows checks pass.** Completion means
integrating the reviewed tree with a literal accepted pin; no automatic merge is
authorized here. After that integration, the finite mechanical READ_ONLY handoff
gap is closed offline. A separately authorized existing-harness900s natural Ross
READ_ONLY observation would then have defined information gain: current supported
issuer-event → ordinary cached Focus → fresh real setup/trigger → raw strategy
intent and its honest ownership/mode/risk disposition. This task neither prepares
nor executes that acquisition. Do not repeat an unchanged run merely to await news.

The five unmatched positions still globally block entry admission after formation.
Thus a fresh natural raw intent plus exact ownership veto can establish formation,
but cannot certify an admitted risk input or paper execution while that blocker
remains. Separate paper acceptance still requires explicitly authorized manual
ownership resolution and actual risk/broker lifecycle/management evidence. Natural
positive catalyst-to-intent progression remains UNPROVEN; archived Focus0/zero-intent
receipts remain unchanged. Listing-compliance provenance remains PARKED and fail
closed; no effort or acquisition to qualify IPST was performed.

No acquisition, runtime observation, automatic rerun, holdings action, trading or
GUI-draft change occurred. `PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.


### Preserved first repair-head CI and stronger temporal handoff assertions

PR1139's first exact repair head `c05ee81206e5b07a612ca941edb8a03822c6fe5a`
(tree `4f5c083ceca869da6df96f190fa6a17e5b1b1861`) received independent exact-head
agent review5672886005 without blockers; its separate guarded artifact/manager
run passed12 cases. This is agent/local proof, not human approval or CI.
CI40567147213 Linux finished2failed/3445passed/3skipped in232.72s. Both failures
were existing `test_quote_future_admission` assertions expecting a pre-risk quote
veto to increment RISK_OUTPUT.blocked_count. A guarded unchanged-head local control
reproduced precisely those2 failures; source inspection and existing assertions
confirmed MD_TIMESTAMP_FUTURE/MD_STALE rejection and the retained temporal audit.
The failure is preserved, not retried or treated as a successful suite.

Those two controls now explicitly require zero actual risk input/decision count
and no canonical decision ID, and forbid invoking the real-risk/artifact owners
around the quote veto. Their original future-by-one-microsecond, strict expiry,
no force approval, original broker timestamp and final RISK_BLOCKED audit assertions
remain. Production source is unchanged from the independently reviewed c05ee812
repair. This updates the reporting contract deliberately; it does not weaken quote
admission. Changed-head CI/review must cover these stronger controls as well as
all9 actual-manager cases. Windows first-run and final-head receipts are retained
on the same PR. No unchanged-head CI rerun is requested.


## PR1139 accepted integration and current one-attempt READ_ONLY preparation

Verified27October2026: GitHub main is exactly
`07491e89a3d5e8a36db19cbd4996ba2acc77aae7`, tree
`58b19a6397f6e9a1018ea8ac3364459f92217d88`. PR1139 actually merged at
2026-10-27T19:35:58Z (19:35:58 Europe/London), parents acceptedf4def160 and final
reviewed head `2294708237f5cbdf37b717ca428e98b483455fdd`. A complete Git diff
between accepted07491 and reviewed22947082 is empty: this is the reviewed tree,
not a new production implementation requiring repeated full suites.

[Independent exact-head agent review5672966290](https://github.com/NelzonMamani/ibkr-trading-system/pull/1139#pullrequestreview-5672966290)
found no actionable blocker. It checked the final temporal controls (2 guarded
passes), carrying forward12 independent manager/artifact checks on byte-identical
production source; agent review is not human approval or natural evidence.
[CI40568163589](https://github.com/NelzonMamani/ibkr-trading-system/actions/runs/40568163589)
completed successfully at22947082: Linux3447passed/3skipped,225.66s;
Windows3449passed/1skipped,570.91s. Native Windows news ownership/maintenance and
float-cache, cache startup, PowerShell exit propagation,39-check stub observation
harness, PowerShell5.1 quote-operator parser and evidence upload all passed. Its
controlled intentionally failing child tests test exit propagation and are not
suite failures. Evidence artifact12764143259 has SHA256
`fc7656650a7432c078a9c01f3a1f88ed24152915a9a70ab9385b07dfa677492d`.

First CI40567147213 remains FAILED atc05ee812: Linux2failed/3445passed/3skipped;
Windows2failed/3447passed/1skipped. Both failed the old pre-risk quote-veto counter
assertions; Windows later cache/PowerShell phases were skipped and upload failed
because their artifacts did not exist. The strengthened final controls and all
prior failed/historical receipts remain preserved. Saved branches
`docs/ross-supported-critical-path` at90a96d36352d1ba2ef3bbfa5ed5689e42ec89a9a and
`fix/readonly-manager-risk-handoff` at2294708237f5cbdf37b717ca428e98b483455fdd were
rechecked unchanged. The saved optional contractc7111fc2 and audit regression are
also present in accepted main; neither authorizes original-publisher verification.

### Current acceptance boundary and information gain

The active-manager canonical decision → actual RiskEngine READ_ONLY handoff is
INTEGRATED and proven OFFLINE. Natural qualifying SUPPORTED catalyst → ordinary
Focus/cached reconsideration → fresh genuine timeframe inputs → real setup/trigger
→ raw strategy intent remains UNPROVEN. No historical zero-Focus/zero-intent receipt
is relabelled positive. Listing provenance remains PARKED and production fail closed.
PAPER/LIVE canonical risk integration is NOT certified by this bounded repair.

Five unmatched positions remain untouched and globally veto new-entry admission
AFTER raw strategy formation, BEFORE canonical artifact/risk admission. Natural
raw formation together with POSITION_TRUTH_BLOCK_NEW_ENTRIES can establish the
formation target. Expected zero post-guard risk input/artifact under that veto does
not refute a retained raw intent. Conversely raw counts do not prove admission.
No risk call may bypass ownership to generate a READ_ONLY result. This observation
cannot certify positive risk admission, broker execution, ownership resolution or
PAPER readiness. If no qualifying opportunity appears, retain the negative facts;
that outcome does not authorize an unchanged rerun.

Review the same five acceptance outcomes separately: terminal safety; genuine
scans/Watchlist continuity; actual news coverage; canonical catalyst qualification;
and Focus/fresh-input/setup/trigger/raw-intent/guard/risk disposition. The retained
profile and all existing total/tier budgets, route membership, deduplication,
request caps, strict original-news/quote freshness and genuine timeframe guards
remain. No proposed eight-total source profile or forced candidate/catalyst/setup/
trigger/intent/approval is enabled. Source health/publication markers are not
qualified evidence. Existing rich source diagnostics and scoped request/reuse/
budget counters described in the PR1135 preparation remain the review authorities.

For progression, correlate terminal/stdout.log STRATEGY_OUTPUT, ARBITRATION_INPUT,
GUARD_OUTPUT, exact POSITION_TRUTH_BLOCK_NEW_ENTRIES, SYMBOL_TRACE, RISK_INPUT and
RISK_OUTPUT with the persisted TRADE_PATH final reason and pattern/trigger/cycle
identity. Inspect canonical DECISION_ARTIFACT_CREATED/DECISION and actual
RiskEngine RISK_DECISION/[RISK][DECISION] only if an intent legitimately passes all
prior guards. With the five positions still vetoing entries, absence of those
artifact/risk events is expected. Never infer execution from raw INTENT/DECISION
formation logs or turn zero open orders into zero holdings.

### Previously issued harness conditions and operator block (historical; not a rerun instruction)

Inspected accepted source: preparation helper
`docs/ross/PR1108_NATURAL_READONLY_ACCEPTANCE.ps1`; runner
`scripts/certification/run_natural_readonly_observation.ps1`; owned boundary
`Invoke-ReadonlyObservation.ps1`; existing `natural_readonly_operator.py` and terminal
supervisor. The runner's actual parameters are Python, Root, ExpectedCommit and
RuntimeSeconds. RuntimeSeconds900 propagates to preflight/observation/package/seal;
existing outer observation budget is900+360=1260s. Preflight90s, owned stop30s and
package/seal90s budgets remain. Native OS exits/deadlines, owned graceful shutdown,
no broad kill or automatic retry, final independent broker audit/disconnect, zero
SDK mutation attempts, complete empty runtime inventories, source/operator-state
equality and final privacy sealing are mandatory. A ZIP merely existing on disk
is not a final privacy-seal pass.

Use Windows PowerShell5.1 Desktop and the saved Python3.13.3 interpreter shown in
the block. Normal configured weekday RTH (America/New_York09:30–16:00, respecting
holidays/early close), enough remaining session for preflight plus all900 seconds,
PAPER TWS authenticated normally with Read-Only API enabled,127.0.0.1:7497,
client71 available and normal market/scanner subscriptions are prerequisites.
No existing Ross runtime may be active. Do not change holdings, adopt/liquidate,
cancel orders or suppress the five mismatches. Session/state/inventory or broker
failures must fail closed; no force-session or restart workaround is provided.

The block reads the EXISTING preparation helper from the literal accepted Git
blob, then invokes the EXISTING runner exactly once. It verifies fetched main is
still the literal pin and verifies accepted/prepared tree and cleanliness; future
main advancement stops for delta review rather than substituting a runtime SHA.
A fresh detached C:\tmp\ro-xxxxxxxx\s worktree leaves PyCharm source/GUI draft,
old evidence and operator state unchanged. Caches and operational state are
isolated by the existing harness; original order-ID state is copied privately,
never reset. The new checkpoint documentation commit is NOT a runtime pin and is
not required in that observation checkout. Expected sealed ZIP is
`C:\tmp\ro-xxxxxxxx\ross-natural-readonly-upload.zip`; share it only after the
harness's final DIAGNOSTIC ZIP announcement. Keep private state/root files private.

```powershell
# User-started once on 28 October: normal RTH is 13:30-20:00 Europe/London.
# Clock time is not eligibility authority; the existing preflight must pass.
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop' -or
    $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
    throw 'Use Windows PowerShell 5.1 Desktop.'
}
$SourceCheckout = 'C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system'
$Python = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
$RuntimePin = '07491e89a3d5e8a36db19cbd4996ba2acc77aae7'
$ExpectedTree = '58b19a6397f6e9a1018ea8ac3364459f92217d88'

& git -C $SourceCheckout fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed; nothing launched.' }
$fetchedMain = (& git -C $SourceCheckout rev-parse refs/remotes/origin/main | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $fetchedMain -cne $RuntimePin) {
    throw 'Main differs from the accepted pin. Stop for delta review; do not substitute a pin.'
}
$pinTree = (& git -C $SourceCheckout rev-parse ($RuntimePin + '^{tree}') | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $pinTree -cne $ExpectedTree) { throw 'Accepted tree mismatch.' }

$beforeWorktrees = @(& git -C $SourceCheckout worktree list --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inventory existing worktrees.' }
$prepareText = (& git -C $SourceCheckout show ($RuntimePin + ':docs/ross/PR1108_NATURAL_READONLY_ACCEPTANCE.ps1') | Out-String)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($prepareText)) { throw 'Pinned preparation helper unavailable.' }
$prepareArgs = @{
    ExpectedCommit = $RuntimePin
    Python = $Python
    SourceCheckout = $SourceCheckout
    BaseDirectory = 'C:\tmp'
    RuntimeSeconds = 900
}
& ([scriptblock]::Create($prepareText)) @prepareArgs

$afterWorktrees = @(& git -C $SourceCheckout worktree list --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify prepared worktree; nothing launched.' }
$addedWorktrees = @($afterWorktrees | Where-Object {
    $_.StartsWith('worktree ') -and $beforeWorktrees -notcontains $_
} | ForEach-Object { $_.Substring(9) })
if ($addedWorktrees.Count -ne 1) { throw 'Expected exactly one new worktree; preserve roots and inspect.' }
$checkout = [IO.Path]::GetFullPath($addedWorktrees[0])
$root = Split-Path -Parent $checkout
if ([string]::Equals($root, 'C:\tmp\ro-03cd9b61', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to reuse the preserved 27 October root.'
}
$actualHead = (& git -C $checkout rev-parse HEAD | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $actualHead -cne $RuntimePin) { throw 'Prepared head mismatch.' }
$actualTree = (& git -C $checkout rev-parse 'HEAD^{tree}' | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $actualTree -cne $ExpectedTree) { throw 'Prepared tree mismatch.' }
$dirty = @(& git -C $checkout status --porcelain)
if ($LASTEXITCODE -ne 0 -or $dirty.Count -ne 0) { throw 'Prepared checkout is not clean.' }
$runner = Join-Path $checkout 'scripts\certification\run_natural_readonly_observation.ps1'
if (!(Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Existing runner missing.' }
Write-Host "Runtime pin: $RuntimePin; root: $root"
Write-Host ("Expected ZIP after successful final privacy sealing: {0}" -f (Join-Path $root 'ross-natural-readonly-upload.zip'))
Write-Host 'Use only the final DIAGNOSTIC ZIP announcement; preserve all exits and evidence.'
Write-Host 'This block invokes the runner once below. Do not also run the preparation helper printed command.'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner -Python $Python -Root $root -ExpectedCommit $RuntimePin -RuntimeSeconds 900
$operatorExit = $LASTEXITCODE
Write-Host "Operator exit: $operatorExit. No automatic retry. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL."
$global:LASTEXITCODE = $operatorExit
```

Proportional preparation checks: accepted/reviewed complete-tree equality, unchanged
harness/source/DEPRECATION_LEDGER, existing parameter/budget/safety-path inspection,
Git whitespace/only-checkpoint diff and static inspection of this PowerShell5.1
block. No operator module import/execution, preflight, acquisition, full suite or
CI rerun is needed for this documentation-only update. Actual Windows5.1 harness
validation is carried forward from successful CI40568163589, not claimed as a new
execution of this block. No module, harness or competing checklist was created;
DEPRECATION_LEDGER is unchanged because no retirement or ownership changed.

**Historical pre-observation instruction (superseded by the receipt below): the user starts this single prepared accepted-pin observation
when those normal session/TWS conditions hold.** Completion means retaining the
sealed full evidence and honest five-outcome review, whether or not a qualifying
opportunity occurs; no automatic rerun is authorized. Preparation has executed no
preflight acquisition, observation, holdings action or trading. Historical receipts,
five-position protections and GUI draft remain. `PAPER_READY=NO`;
`PAPER_READINESS_GATE=FAIL`.


## 28 October — session-rejected receipt preserved; one new user-started attempt

GitHub main was rechecked at accepted
`07491e89a3d5e8a36db19cbd4996ba2acc77aae7`, tree
`58b19a6397f6e9a1018ea8ac3364459f92217d88`; no advancement or runtime-pin
substitution. PR1139 remains merged from reviewed22947082. Read and carried forward
saved documentation branch `docs/pr1139-accepted-observation` at
`a9f7643154b3b90dd530b15d6f4a5ca9d3347368`; it remains unchanged. This update
continues that checkpoint, not a competing checklist or implementation. Integrated
offline handoff proof, review5672966290, CI40568163589, prior failed receipts,
saved audit/contract and GUI draft remain preserved. No completed suite/CI rerun.

### Supplied27October receipt: rejected before observation

Preserve `C:\tmp\ro-03cd9b61`, including its existing evidence/state and ZIP.
Operator-supplied ZIP SHA256:
`55d01a28b86aa4dd89d9ab74593cc6e16716df2c4db40df5866c90f4b999fa28`.
No archive was attached to this turn; the hash/receipt are recorded as supplied,
not claimed independently recomputed. Reported preflight stage=session rejected:
"Requires the normal configured RTH window; no session override."
observation_started=false; observation_exit=null. Final exit1, package exit2 /
DIAGNOSTIC_ONLY, privacy scan passed. Final process inventory completed with no
remaining runtimes. Mutation verification, operator/order-state equality, source
equality and terminal safety remain NOT_VERIFIED, not PASS or zero attempts.

There is NO natural scanner, catalyst, Focus/setup/trigger/raw-intent evidence from
this attempt. Final inventory/privacy success does not certify terminal safety or
holdings truth. The accepted preflight checks session before write-guard verification
and baseline finalization; do not infer those later steps completed. No exact
preflight clock was supplied here, so do not attribute the rejection to a timezone
bug, workstation skew or a particular late start. No defect or gate relaxation is
established. Yesterday's root is never reused, cleaned, overwritten or removed by
the current operator block. Today's explicit user request authorizes preparing one
fresh attempt; this is not an automatic retry of that failed preflight.

### Accepted session authority and28October London window

At the literal accepted pin, `natural_readonly_operator.py` preflight requires
`src.config.system_config.get_current_market_session() == 'RTH'`. That function
converts an aware UTC clock through `to_ny_time` / ZoneInfo America/New_York,
rejects weekends/configured holidays, applies configured half-day close and uses
REGULAR_START09:30 inclusive / REGULAR_END16:00 exclusive from
MARKET_SESSION_WINDOWS_LOCAL. The operator clears registry-backed inherited
configuration before rebuilding the existing safe READ_ONLY environment; no
session override or calendar edit is added. The accepted defaults have empty
holiday/half-day sets;28October2026 is Wednesday. This is the actual configured
gate, not a fresh live exchange-calendar certification.

On28October2026 Europe/London is GMT/UTC+00 and New York remains EDT/UTC-04.
The permitted normal RTH interval is therefore **13:30 inclusive to20:00 exclusive
Europe/London**, not14:30–21:00. At approximately18:00 London it is14:00 New York,
with7200seconds (two hours) remaining. Existing preflight90s + runtime900s =990s
(16m30s), ending18:16:30 if started at18:00. Even the conservative existing outer
phase allowances90+1260+90+90=1530s (25m30s) fit before20:00; this does not renew or
enlarge any budget. Allow preparation/startup time as well. These calculations
show adequate clock time at18:00, not actual workstation/session/TWS eligibility.

New proportionate hard-offline date controls called the actual pure session
function:13:29:59.999999→PRE,13:30→RTH,18:00→RTH,19:59:59.999999→RTH,20:00→AH;
configured holiday and half-day counterfactuals remain CLOSED at18:00. This is
new date-specific offline calculation, not acquisition, preflight or repetition
of completed strategy suites. Log `/workspace/work/ross-session-window-20261028.log`.
No operator module was imported or executed. Static source inspection confirms
RuntimeSeconds900, existing1260s supervisor ceiling,90s preflight,30s owned stop
and90s package/seal caps. Source/harness/DEPRECATION_LEDGER remain unchanged.

### One prepared attempt and evidence boundary

The single current copy-paste block above is updated in place for28October and
explicitly refuses yesterday's root. It reads the existing accepted preparation
helper, creates a fresh isolated C:\tmp\ro-xxxxxxxx\s, verifies literal pin/tree,
cleanliness and unchanged fetched main, and invokes the existing runner exactly
once. Source checkout, GUI draft, old roots and historical receipts are retained.
It never invokes a separately printed helper command a second time. The
separately published documentation commit is not the runtime pin.

Actual preflight must still pass on the user's workstation. Use Windows
PowerShell5.1 Desktop, retained Python3.13.3 environment, normal PAPER TWS at
127.0.0.1:7497 with Read-Only API enabled and client71 available, normal data/scanner
subscriptions and no pre-existing Ross runtime. Normal session, sufficient
remaining time and all source/inventory/write-guard/cache protections must hold;
clock time alone is insufficient. Do not broaden the gate, reset/adopt/liquidate
holdings, cancel orders, suppress mismatches or automatically retry failure.
Existing natural50/15/5 selection, mandatory supported catalyst, strict original
publication/quote freshness, genuine timeframe inputs, total/tier acquisition
budgets and no forced candidates/news/patterns/triggers/intents/approvals remain.

Keep the existing zero-mutation instrumentation, final independent audit/disconnect,
owned shutdown/cleanup, complete process inventories, source/operator-state equality,
privacy scan and final ZIP sealing. Expected new sealed output is
`C:\tmp\ro-xxxxxxxx\ross-natural-readonly-upload.zip`, announced only by the
existing final DIAGNOSTIC ZIP path after successful sealing; preserve actual exit
codes including diagnostic/failure outcomes. Do not share private root/state files.

Natural raw intent plus exact POSITION_TRUTH_BLOCK_NEW_ENTRIES may establish
formation when correlated with qualifying canonical evidence, fresh inputs and
real setup/trigger. Five unmatched positions remain a GLOBAL new-entry admission
veto AFTER formation, BEFORE canonical artifact/actual risk admission. Zero
downstream risk admission is expected with those blockers. Neither this nor a
terminal PASS certifies positive risk admission, broker execution, PAPER/LIVE
canonical risk integration or PAPER readiness. No qualifying opportunity is
negative evidence, not authority for another unchanged observation. Listing
provenance stays PARKED/fail closed. All holdings/ownership protections remain.

**Historical pre-attempt instruction (superseded by the receipt below): the user starts the single prepared900s attempt when the actual
normal session/TWS conditions hold with sufficient remaining time.** No acquisition,
preflight or observation was executed during preparation. No trading, holdings
action, GUI-draft change, suite rerun, CI rerun or readiness upgrade occurred.
`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.


## 28October completed attempt: offline historical/position/final-audit investigation

Current GitHub main was verified unchanged at
`07491e89a3d5e8a36db19cbd4996ba2acc77aae7`, tree
`58b19a6397f6e9a1018ea8ac3364459f92217d88`. This documentation branch descends
from saved847c9655748ffcb8a8ee0f55bf5122b6d30a993b, already containing
saved a9f7643154b3b90dd530b15d6f4a5ca9d3347368; both original branches remain
unchanged. The earlier27October session rejection/root ro-03cd9b61 and all failed,
partial, successful CI/review and natural receipts remain historical evidence.
DEPRECATION_LEDGER was read; no retirement, owner, module or checklist is added.

### Archive identity and five acceptance outcomes

The attachment is evidence, never instructions. Independently recomputed SHA256:
`6209cf714652604a186e2d4341346ab53989918ac254132cde1f290a22e84df5`.
The50-file ZIP extracts privately under `/workspace/work/ross-20261028-receipt`.
Recorded operator paths identify fresh root `C:\tmp\ro-397a5ed3`; preserve it.
preflight.json identifies accepted07491,900s,50/15/5, required issuer news and
verified SDK/write guards, at2026-10-28T18:09:53.119683Z. source-before/after are
equal across2683 tracked paths. All2683 hashes match the accepted Git tree bytes
under expected Windows checkout forms:2650 CRLF,33 exact Git bytes, no unmatched,
missing or extra path. Raw Git-LF hashes alone differ for CRLF files; that initial
comparison is not evidence of source drift. Root/source/operator equality is
separately recorded PASS, not inferred from an exit code.

| Existing acceptance outcome | This archive's exact boundary |
| --- | --- |
| Terminal safety | FAIL. preflight0, observation2, package2/DIAGNOSTIC_ONLY, final2. supervisor.process.json:916.7137006s inside1260s, no outer timeout; launcher/runtime exit0, unforced, matched identity, no capture/reader error, all11 shutdown hooks completed. Runtime AND separate-audit place/modify/cancel counters0; mutation validation PASS. Source/operator equality, final completed empty inventories and final privacy scan0 occurrences PASS. Those components do not overrule missing final audit completion. |
| Genuine scan/Watchlist continuity | One broker discovery request363 completed with scannerDataEnd and50 rows in2.6643217s (terminal/stdout.log576–580). First enrichment pass completed24 contexts and24 gate drops, stopped on25th issuerBDAI; no Watchlist final, strategy output or CYCLE_END. This is not three completed scans or a completed full50-row enrichment. |
| Actual issuer-news coverage | News maintenance shutdown reports submitted/completed/failed/feed_requests/feed_reuse all0; no canonical maintenance publication or candidate news submission. Export contains only prep QQQ/SPY facts, not natural Watchlist issuer coverage. |
| Canonical supported-catalyst qualification | No natural Watchlist issuer qualification/Focus evaluation established. Historical-data/RVOL absence is not evidence that no issuer catalyst existed. |
| Fresh setup/trigger/raw-intent/guard/risk | No Focus/setup/strategy cycle or raw intent/risk input reached. Integrated PR1139 offline handoff remains valid; this run does not naturally exercise it or prove a risk/intent defect. |

### Historical receipt: what empty actually means

Archive terminal/stdout.log has169 HIST_ATTEMPT and169 HIST_REQ,168
HIST_EMPTY_FINAL,0 HIST_DONE,0 HIST_RETURN and0 HIST_ATTEMPT_FAIL. All168 completed
attempt-result records report raw_bar_count0. There is no captured accepted
historicalDataEnd or populated history. Generic broker errors are farm status
2104/2106/2158, scanner162 after its completed scan, quote300, and historical366
only for final request706 at18:24:58.381604Z. No request/order-ID collision or
intermediate historical error is recorded. Quotes and scanner callbacks do arrive;
connection/handshake/farm-OK messages cannot certify history or other stream ends.

Exact accepted `src/adapters/brokers/ibkr/ibkr_client.py`:
reqHistoricalData registration/dispatch lines933–956; wait loop961–974;
HIST_EMPTY_FINAL983–984; historicalData1288 and historicalDataEnd1294;
error callback historical event wake1454–1455. The wait ends on ANY event, the
first bar, or wall-clock expiry of snapshot_timeout_seconds (5s here). The same
event is also set by a generic error, so event-set alone is not end completion.
HIST_REQ is printed before checkpoint/SDK dispatch; it does not prove a socket
send or broker acceptance. Counts here are SDK submission attempts, not verified
wire requests. The returned plain list carries none of these outcomes. Empty list / EMPTY_FINAL
is thus neither a confirmed zero-bar result nor evidence of historicalDataEnd.

For the first168 requests, no end/bar/error/collision/disconnect wake is captured;
source-path elimination identifies no-bars wait expiration, not end-confirmed
empty history. Exact per-request wait timings/end flags were not exported, so do
not present5.000s as a measured latency for each ID or claim broker-side emptiness.
At the configured5s limit,168 serial waits consume roughly840s before overhead;
that is a source-based budget calculation, not individually measured stopwatches.
The last request706 (BDAI20D primary, line4458) has neither empty/result marker nor
end callback: it is unfinished when acquisition stop propagates. The wait-loop
cancellation branch calls cancelHistoricalData before raising; a pre-dispatch
checkpoint also exists outside that branch. No explicit per-request dispatch/
cancel receipt was captured, so do not claim a proved wire cancellation. Code366 "No historical data
query found for ticker id:706" appears at stop; it is not an end marker, cancellation
acknowledgement or an explanation for the earlier168 failures. There is no raw
wire/send/decoder capture establishing why history/end delivery was absent.

### Proven repetition and why900s did not finish enrichment

All24 fully evaluated symbols have7 attempts each. ULBI is the concrete trace:
requests466/467 (20D primary/fallback),469/470 (25D primary/fallback),471 (identical
25D non-RTH retry),472/473 (repeated20D primary/fallback). See log1927–2157.
BDAI adds only706, giving169 attempts across25 issuers.

Source chain, retaining distinct durations and security identity:

1. scanner_runner.py4411 calls provider.get_intraday_stats; ibkr_provider.py485
   consumes the existing quote then _average_daily_volume551 → MarketDataClient
   average_daily_volume_from_history958 →20D RTH and explicit-end non-RTH fallback.
2. scanner_runner.py4429/reference_resolver.py449–509 request25D history. The
   MarketDataClient fallback already requests25D non-RTH; the resolver sees[] and
   calls that same25D non-RTH explicit-end identity again (line480's retry branch).
3. reference_resolver.py349 unconditionally asks _provider_adv20_fallback605;
   ibkr_provider.py453–455 reissues20D average-volume history, repeating both
   earlier20D requests. Intraday ADV/25D data do not repair this receipt because
   every history result is unavailable. A reference-close quote may exist, but
   ADV20/RVOL remains unavailable; no freshness/selection gate is loosened.

MarketDataClient._request_daily_history_with_fallback796–805 keys exact client,
contract identity, duration, RTH and end. It memoizes only nonempty lists, so all
these failures miss its existing pass cache. Its lower-level attempts808–866 and
the resolver independently own fallback. Raw attempt counts:20D RTH49,20D non-RTH48,
25D RTH24,25D lower fallback24,25D resolver non-RTH retry24. Thus97 distinct actual
parameter/security sets versus169 requests:72 exact repeats (3 per completed
issuer). 20D and25D are different requests and must not be conflated. Reuse of
failed/unavailable outcomes would be an explicit pass-local retry-policy decision,
not an already-guaranteed property or harmless cache-only change.

The scanner processes these contexts serially in scanner_runner.py6104–6120.
24 completed contexts yield12 DROP_MISSING_RVOL,6 DROP_FLOAT_MAX and6
DROP_FLOAT_UNKNOWN;25th BDAI is unfinished and rows26–50 (25 rows) are unvisited. Never
claim elimination of duplicate waits alone guarantees a completed scan or a
qualifying issuer event. It removes demonstrated repeated work, not an established
upstream failure cause. News maintenance was never submitted in this incomplete
first pass, so neither mandatory-catalyst rejection nor five-position admission
veto caused the history latency or suppressed a formed strategy intent here.

### Native historical lifecycle defects established offline

New guarded controls reproduce actual accepted native methods with fake SDK
transport and fake time (5s existing timeout, no wall-clock wait/acquisition):
confirmed end-empty, timeout and explicit historical error all return[] and print
EMPTY_FINAL; a single bar without end returns immediately as a populated result.
The latter is a demonstrated local history-completion gap, not proven downstream
trade admission or observed bar corruption in this zero-bar receipt. MarketDataClient may cache any nonempty
result, so completion provenance must reach that consumer before reuse is trusted.

Ordinary history returns do not issue SDK cancellation or retire historical
maps/ownership. Cooperative stop calls inherited cancelHistoricalData but likewise
leaves _historical_events/_historical_data/request-type entries. historicalData
uses setdefault with no active-retirement guard: an offline late callback after
timeout still appends to retained state. End callback pops request type but leaves
bars/events; disconnect invalidates position/reference state and closes/joins the
socket, not these historical maps. Context metadata is bounded1024, historical
maps have no equivalent cap/retirement. This does not prove a broker-side backlog,
resource-exhaustion cause or cross-ID data contamination in the actual run.
Process exit/inventory cleanup still passed. Preserve unique request ownership and
request/order ambiguity guards in any repair.

### Final audit: correctly incomplete, delivery cause unresolved

terminal/terminal_evidence.json.final_broker_audit records a fresh native audit
connection (client71 after runtime exit), connected before AND after wait, reader
thread alive before query, reqAllOpenOrders, timeout_seconds10,
elapsed_seconds10.0090318, end_received=false, query_completed=false,
error="RuntimeError: Final audit openOrderEnd missing", disconnected=true.
open_orders_count is absent/UNKNOWN, never0. Audit stdout contains handshake,
farm status callbacks and disconnect, no openOrderEnd. No final query completion
may be inferred from connection or zero mutation attempts.

Existing supervisor.final_broker_audit153–195 clears its event/snapshot before
query, waits10s and requires the end event; native openOrderEnd1714–1716 sets that
event. Finally always attempts owned disconnect and records independent mutation
counters. Terminal blockers are exactly "Incomplete final callback: broker_audit"
and "Unconfirmed FINAL_BROKER_QUERY". Fake-client controls against the ACTUAL
final_broker_audit show connected/no-end produces incomplete with no order count;
end-confirmed empty produces completed/count0, with disconnect in both cases.
No source defect is established in that fail-closed audit boundary. Missing
callback origin/send/server/decoder details remain absent; no timeout extension,
SDK/upstream attribution, market-data retry or broker inquiry is justified here.

### Position truth: unavailable interface before connection, not zero holdings

Log497–503 records one position-truth cycle: positions_unavailable,
broker0/system0/matched0/mismatches0/critical1, healthy=false/block_new_entries=true.
This exact message is collect_broker_position_snapshot(position_truth.py139–145)
when the argument lacks a callable position_snapshot. Core calls
_resolve_position_truth_cycle at3165 BEFORE ensure_connected3196; it requests
ConnectionManager.get_ibkr_client(ensure_connected=False) at3035. That manager's
get_ibkr_client89–94 returnsNone before its owned adapter is initialized. Log511's
native connection follows the unavailable verdict. A new offline control against
these actual owners reproducesNone → unavailable collection → UNKNOWN/critical1 /
entry veto, with both dictionary counts0. This is not a captured position timeout
or a proved missing positionMultiEnd; no truth-query interface was invoked there.
The single incomplete first scanner cycle never reaches a later position cycle.

When a native position_snapshot IS invoked, lines536–585 require one account,
connection epoch/transport and request-scoped reqPositionsMulti end, mark timeout/
failed/disconnected distinctly, retire query ownership before cancelPositionsMulti
in finally, and reject stale/unscoped/ambiguous results. A zero-time fake timeout
control retains TIMEOUT (never COMPLETE-empty) and confirms owned cancellation/
query retirement. There is no legacy reqPositions subscription cancellation here.
Its fail-closed handling remains correct. Startup internal count0 and the final
missing order end do not prove the earlier five unmatched broker holdings vanished.
Do not adopt/liquidate/cancel/suppress them or bypass the global entry veto.

### Narrow controls, justified proposal and ONE next action

NEW scratch-only control `/workspace/work/test_ross_28_receipt_controls.py`:
12passed in1.69s, hard Python/native-curl offline guard, all EClient connection and
place/cancel/global-cancel mutations forbidden, fake SDK history sends only.
Controls cover5 history outcomes, late callback, cooperative cancellation, actual
MarketDataClient/provider/reference-resolver seven-call chain (7 sends/4 identities),
absent-manager position truth, scoped position timeout and actual final-audit
end/no-end. No production module was added or changed, no completed suite rerun,
no live harness/operator invocation or new acquisition. Source identity verification
report: `/workspace/work/ross-20261028-source-identity.json`; control log:
`/workspace/work/ross-20261028-controls.log`. The archive does not include raw
historical frames, per-request elapsed/end/cancel receipts or a fresh end-confirmed
holdings snapshot. These are explicit limits, not reasons to infer one shared cause.

**ONE next action: implement/review a narrow historical outcome-and-ownership
contract in the EXISTING native/market-data owners, with bounded offline regression.**
This is a repair PROPOSAL, not implemented here. Require actual end-confirmed
completion before populated/empty history is eligible; preserve original bars and
dates, existing5s waits and deadlines, stop propagation, request-ID ambiguity and
privacy limits. Distinguish completed-empty, timeout, error and cancellation;
retire owned state and stop accepting late callbacks on every exit; cancel only
owned historical work where applicable (never orders). Carry unavailable/completion
provenance through existing callers so timeout/error cannot masquerade as confirmed
absence and restart layered fallbacks. Review same-pass exact-request suppression
against the demonstrated duplicates; any failure-reuse/fallback-policy change must
be explicit and bounded, not persistent negative caching, cross-duration
substitution or renewed retries/budgets. Preserve healthy end-confirmed behavior
and all strict quote/RVOL/catalyst/ownership gates. No general architecture/module
migration, SDK change, timeout extension or speculative audit/position repair.

Completion criterion for that proposed next task: deterministic complete-empty/
complete-bars/partial/no-end/error/cancel/late-callback controls with retired owned
state, truthful unavailable outcomes and no repeated identical request in the
same intended bounded enrichment attempt, while20D/25D and valid later attempts
remain distinguishable; independent review/appropriate changed-head CI before any
future acquisition decision. Missing historical and final-order delivery causes
remain unresolved. Do not run an unchanged observation hoping for callbacks or
catalysts, and do not infer a shared cause from three unavailable observations.
Natural supported-catalyst-to-intent progression remains UNPROVEN; PAPER/LIVE
canonical risk integration is uncertified; listing provenance remains PARKED and
fail closed. Five-position protections, GUI draft and all receipts remain.
`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

### Historical completion/ownership repair — bounded implementation (28 October)

The saved investigation `9cdd603d467428d7678bde8d70353e2b1bd9d5f0`
remains the evidence baseline, including the failed final audit and unavailable
pre-connection position truth. Accepted main was independently rechecked at
`07491e89a3d5e8a36db19cbd4996ba2acc77aae7`, tree
`58b19a6397f6e9a1018ea8ac3364459f92217d88`, before implementation.
The callback-delivery causes and missing final `openOrderEnd` remain unresolved;
this repair neither diagnoses them nor promises successful enrichment.

The existing native history owner now requires an actual `historicalDataEnd`
before exposing bars or confirmed absence. First-bar arrival cannot finish a
request. Typed outcomes distinguish COMPLETE_BARS/COMPLETE_EMPTY, TIMEOUT, ERROR,
CANCELLED and DISCONNECTED; unavailable/unverified outcomes expose no bars.
Native requests retain their existing5s wait and acquisition deadline. Both native
API signatures now use this bounded, end-confirmed contract; the raw reqId form
is no longer fire-and-forget. No production fire-and-forget consumer was found.
Active ownership retires before cancellation on every exit. Late callbacks cannot
recreate state; active/retired raw ID reuse and ambiguous order/request IDs fail
closed. Only owned outstanding history (or an owned streaming subscription after
its initial end) is cancelled. Disconnection does not cancel foreign work.

MarketDataClient preserves completion provenance through provider, reference
resolver, ADV and intraday consumers. Its existing ib_insync path observes real
end/error callbacks, cleans up only its own future/container/hooks, and protects
foreign replacement requests and connection epochs. Bare IBKR history lists and
unwitnessed derived ADV values are unavailable. Original bar dates and all quote,
RVOL, catalyst, position-truth and execution gates remain unchanged.

**Explicit retry-policy change:** a single enrichment attempt reserves exact
client/connection/contract/request-parameter identities before dispatch, with a
128-entry ceiling, no eviction and fail-closed capacity. Nested existing owners
share that attempt. Exact successes and failures are reused only in that attempt;
the locked cache is closed and cleared on exit. There is no persistent negative
cache or renewed budget. Distinct20D/25D, RTH/non-RTH, end times and contracts remain
independent, as do legitimate later attempts. Only confirmed-empty RTH results
permit the existing non-RTH fallback, once. Identity qualification may retain its
existing cache; historical requests no longer inherit that longer-lived cache.
Scanner gates project the already resolved context once, including authoritative
unavailability, rather than reacquiring when percentage change remains missing.

Guarded new controls exercise actual native → MarketDataClient → provider →
resolver and actual scanner-cycle paths, not just standalone cache helpers.
They cover complete/empty/partial/no-end/error/cancel/disconnect, stop propagation,
late callbacks, ownership ambiguity, concurrent ib_insync requests, streaming
cleanup, replaced futures, exact deduplication/capacity/closed scopes, distinct
requests/later attempts and healthy fallback. Network, broker connections, order
mutations and submissions are forbidden. Affected synthetic IBKR fixtures now
supply explicit end witnesses; safety assertions were retained. Local affected
sets:205passed6.36s; consuming set208passed9.03s; final unavailable-projection and
history controls87passed2.82s. These overlap and are not additive or CI/natural
acceptance. Development failures and logs remain in `/workspace/work/history-*`;
no completed broad suite was rerun locally. Independent exact-head review and
changed-head Linux/Windows CI receipts belong to this repair's accompanying draft
PR; integration is gated on their success. DEPRECATION_LEDGER is unchanged:
ownership remains in the existing modules, with no module retirement/migration.

**ONE next action:** review and, only after successful exact-head review and
Linux/Windows checks, integrate this bounded repair. No observation is authorized
here; a later acquisition decision must separately account for the outstanding
pre-connection position-truth item and unresolved final-audit completion. Historical
receipts remain unchanged; no retroactive natural progression is claimed. Natural
supported-catalyst → fresh setup/trigger → raw intent is still UNPROVEN. Five
unmatched positions remain separate global entry blockers after formation and
before canonical/risk admission. PAPER/LIVE risk certification remains outstanding;
listing provenance is PARKED/fail closed, GUI draft preserved.
`PAPER_READY=NO`; `PAPER_READINESS_GATE=FAIL`.

Independent review of initial repair `099095332234e127db514040fd5607d306338d8c`
ran49 guarded controls (49passed2.28s) and found one remaining migration gap:
legacy PROVIDER_PREV_CLOSE_FALLBACK/PERSISTENT/unknown cache origins could hide
unwitnessed historical values. The follow-up rejects those unwitnessed reference
origins as well as explicit historical origins; only explicit independent
quote/snapshot/scanner-price origins retain their existing semantics/gates.
End-confirmed historical cache values remain usable. Unwitnessed cached ADV is
always unavailable. New migration controls plus affected identity controls:
72passed3.06s. Initial changed-head CI run40755035354 belongs to09909533 and cannot
certify this changed head; its receipt remains preserved on the PR. The final
replacement-head review/CI receipts are recorded on the same draft PR1140.

Final review follow-up: an actual end-confirmed request can later become
request/order-ID ambiguous. A guarded review control demonstrated that the
resolver's same-attempt positive result could bypass the MarketDataClient cache
recheck. The existing owner now supplies a bounded, identity-scoped runtime
validator over the original native IDs/client/connection epoch. Resolver reuse,
supplied derived ADV and the scanner's post-attempt projection revalidate it.
Conflicted or disconnected historical values/RVOL become unavailable, without
new historical requests. Explicit independent quote references survive. Tainted
positive persistent history is removed (not replaced by a persistent negative
cache); positive quote records lose only their historical ADV. The runtime
validator is deliberately outside dataclass serialization and persistent JSON;
it confers no reusable stored authority. The attempt's acquisition cache still
closes/clears at exit. These checks do not diagnose callback delivery.

Additional direct-native-cancel control confirms CANCELLED, hidden partial bars,
retired state, one owned SDK cancellation and no foreign cancellation. The actual
resolver late-conflict and scanner post-attempt conflict/disconnect controls
retain quote-only reference behavior and prohibit extra sends. New/affected
handoff, scanner, identity, cached reconsideration and order-observability set:
141passed4.66s under the hard offline guard. This is local synthetic proof only.

Preserved failed CI receipts: run40755035354 at09909533 had Linux1failed/
3495passed/3skipped and Windows1failed/3497passed/1skipped. Run40755406880 at
fd7f7745 had Linux1failed/3502passed/3skipped; its Windows receipt remains on the
same run. The failure in both completed suites was the existing order-callback
observability test's `__new__` fixture omitting the newly required empty history
owner map. That fixture is now initialized correctly; its order assertions are
unchanged (targeted controls pass). No PermissionError suppression, skipped new
checks, timeout increase or unchanged-head retry was used. Superseding exact-head
review and Linux/Windows CI are linked on draft PR1140; historical failures remain
there and above. PR1140 is unmerged. The single next action and readiness/ownership
limits stated above remain unchanged.

A final actual-gate check found one omitted alias in post-attempt invalidation:
`_resolve_rvol_for_focus_gate` prioritizes `scanner_rvol`. Keeping that derived
value could bypass the intended unavailable-history RVOL rejection even after
other RVOL fields were cleared. The strengthened four post-attempt controls
first failed against40526533, then passed after clearing `scanner_rvol`, normalized
RVOL, baseline and expected-volume aliases and setting RVOL status UNKNOWN.
The controls now assert the ACTUAL Focus RVOL selector returns no value; quote-only
references still survive. Focus/selection rules themselves are unchanged.
Affected guarded set118passed3.71s; before/after logs remain in
`/workspace/work/history-rvol-selector-{before,after}.log`.
Run40757036669 at40526533 passed Linux and Windows (including cache and PowerShell
steps), but is superseded by this demonstrated selector fix and is NOT the final
head certification. Independent review5688727612 likewise belongs to40526533.
Final replacement-head review/CI receipts remain linked on the same draft PR1140.
No unchanged-head retry or acquisition was performed; all remaining gates and the
single controlled-integration-review next action remain unchanged.

CI follow-up at97346e7e: run40759347776 Linux1failed/3508passed/3skipped,
at the existing shared-feed concurrency fixture (empty headline result). Inspection
found that fixture generated its publication string before acquisition but its
`published_parsed` from a later wall clock after sleeping. A second-boundary
crossing can therefore make the parsed publication newer than the fetcher's
recorded evaluation clock. This fixture inconsistency is demonstrated offline;
the original CI output lacks per-entry exclusion timing, so its precise exclusion
is not claimed as independently captured. Production strict future rejection is
unchanged and correct for those synthetic inputs. There is no RSS production
repair or freshness relaxation in this follow-up.

The fixture now records one coherent original publication and a fixed evaluation
clock while retaining real monotonic request budgets and concurrent shared-pool
work. A second case deliberately places parsed publication one millisecond into
the future and requires rejection; both cases retain one actual fake fetch,
per-issuer attribution, response reuse and owned cleanup assertions. Guarded
news/history set98passed4.77s. This establishes a real fixture repair, not an
unchanged-head retry hoping for success. The failed run remains on PR1140;
97346e7e independent review5688914062 is carried forward for source-identical
production code. Final test-delta review and changed-head Linux/Windows receipts
are linked on the same draft PR. All acquisition, readiness and ownership gates
and the single next action remain unchanged.

## 28 October 2026 — PR1140 accepted; position-truth initialization repair

PR1140 is now merged, superseding the earlier draft-status notes without removing
any failed receipt: final head `6d490b15a424ad69adbe44f49594b1704cdd4a15`,
merge/main `3a0bbbd1a0ab92dfeddbdc55e04e4f8f20dc889d`, tree
`49c117ce2c67a977c6f9b3d2572aeb41ca1c89b6`, merged 2026-10-28T20:24:48Z.
Independent review5689025196 and successful CI40760689475 belong to that final
head. Linux3510passed/3skipped; Windows3512passed/1skipped, including cache,
float/news and PowerShell checks. Historical failed runs and saved investigation
branches remain preserved. This repair starts from that exact accepted tree.

Source diagnosis: active Core evaluated position truth before its existing
connection initialization. The passive Core getter therefore returned no native
client on the first cycle. The MarketDataClient facade has no position-snapshot
interface and is not a substitute authority. The existing native
`IbkrClient.position_snapshot` owns account-scoped position requests, completion,
errors and cleanup; its typed `BrokerPositionResult` is consumed by the existing
collector and reconciliation owner. Connection alone is insufficient. Only a
fresh, account-scoped COMPLETE result permits reconciliation as complete, including
confirmed empty. Missing interface, list-only adapters, partial/no-end, timeout,
error and disconnect remain UNKNOWN/unavailable; broker0/system0 under UNKNOWN
never establishes flat holdings.

The bounded repair moves existing initialization before position truth/recovery,
without a second session or snapshot implementation. Failed initialization feeds
unavailable truth and suppresses stale-client/relationship queries. LIVE halts
after unavailable-truth recovery before management; SIM remains connection-free.
Native position waiting now uses the existing stop/deadline-aware wait helper
within its unchanged five-second deadline. Owned request state retires on every
exit; only owned, sent, unambiguous requests in the same connected epoch are
cancelled. Collector cancellation/deadline control flow propagates unchanged.
The existing shared connection owner also retires unpublished clients after
failed/cancelled initialization, preserves original control exceptions and
checks stop/deadline after handshake and account resolution. Interrupted account
initialization removes only its own publication. Successful reuse and configured
client-ID-conflict retry bounds remain intact; failed cleanup prevents further
retry/publication in that call. No claim is made that cleanup failure is success.

Deterministic failing-before controls established ordering, swallowed collector
deadline, LIVE failure early-return, unpublished-client cleanup and post-handshake/
account-resolution control-boundary defects. Guarded affected regressions passed
206 tests (including PR1140 history, position authority and actual READ_ONLY risk
handoff). After the additional shared-initialization controls/repair, the focused
new/connection-owner set passed49 tests:39 new controls plus10 existing controls.
These overlapping local results are not additive, CI or natural proof. Controls
forbid real network/broker connections, order mutations and execution submission.
They exercise actual Core/facade/shared/native/collector/reconciliation owners
with synthetic callback data, complete empty/nonempty results, all unavailable
outcomes, stop/cleanup, five unmatched positions and SIM/READ_ONLY/PAPER/LIVE
boundaries. The five-position fixture retains five critical mismatches and the
global entry veto; no ownership adoption or suppression occurs. Existing downstream
fixture adaptation changes only its private truth-stub signature.

Independent exact-head review and changed-head Linux/Windows CI receipts are to
be recorded on the accompanying draft PR, linked to its immutable head. No local
full-suite repetition is required for status alone. DEPRECATION_LEDGER was read
and remains unchanged: no module or ownership retirement occurred. No applicable
AGENTS.md was present in this checkout or its workspace ancestors.

Remaining gates: actual position/history callback delivery remains unproven;
this offline repair does not explain the historical missing callbacks. The final
order audit's missing openOrderEnd cause is unresolved and its fail-closed audit
is unchanged. Natural supported-catalyst→Focus→fresh pattern→raw intent remains
unproven. Five unmatched holdings remain untouched and globally veto new-entry
admission after formation, before canonical artifact/risk admission. PAPER/LIVE
canonical risk integration is not certified. Listing provenance remains PARKED
and fail closed; GUI draft and all historical receipts are preserved.

ONE next action: review the exact draft integration head after independent review
and changed-head Linux/Windows CI complete; no runtime attempt is authorized here.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## 29 October 2026 — PR1141 accepted; separate final-order completion investigation

PR1141 was explicitly authorized for controlled integration. Before merging,
GitHub main remained3a0bbbd1a0ab92dfeddbdc55e04e4f8f20dc889d; PR head remained
660971ce14eef21e310eccfcd2306b84706dd927, tree
 ae7a4cb69523df0c6aaf3b7c86849b643224d494. Independent agent review5690635549
reported no blockers; no newer review findings or unresolved threads existed.
Successful CI40780578651 tested merge ref
f918060373f3d9a6f9699e25acdf16b4d1501beb with exactly that same tree: Linux
3549passed/3skipped; Windows3551passed/1skipped plus cache/news/float and
PowerShell checks. Completed suites were not repeated for reconciliation.
Marked ready and merged using GitHub's expected-head guard and merge method.
Accepted merge/main is `fb0b9e9c3c7a2f7774a1fe73276e7d43e832f8e7`; fetched main
tree is `ae7a4cb69523df0c6aaf3b7c86849b643224d494`, exactly the reviewed tree.
Integration receipt: PR1141 issuecomment6493282079. Saved branches and the
original checkout remain preserved. Earlier draft/unmerged statements above are
historical, superseded by this receipt. PR1140 history and PR1141 position
semantics remain intact. DEPRECATION_LEDGER was read and is unchanged; no module
or ownership retirement occurs. No applicable AGENTS.md was found in the checkout
or workspace ancestors.

The original 28 October ZIP remains available at
`/workspace/attachments/0d9260b8-fd74-43f1-828b-7bbddad93ca2/ross-natural-readonly-upload.zip`.
SHA256 reverified6209cf714652604a186e2d4341346ab53989918ac254132cde1f290a22e84df5.
The extracted terminal/terminal_evidence.json and audit stdout/stderr bytes match
the ZIP. Audit evidence remains: query_completed=false, end_received=false,
connected before/after wait, reader alive before dispatch,10.0090318s elapsed,
RuntimeError: Final audit openOrderEnd missing, owned disconnect confirmed, zero
place/modify/cancel attempts. open_orders_count is absent/UNKNOWN, not0. Audit
stdout records handshake and informational farm callbacks2104/2106/2158, then
disconnect; stderr is empty. These status callbacks are not query completion or
proof of an order-query response. The historical terminal failure is preserved.

Actual owners/lifecycle: supervisor `final_broker_audit` constructs a NEW native
IbkrClient for each call, explicitly READ_ONLY, after owned runtime shutdown.
Native constructor binds EClient(wrapper=self); connect starts its existing
reader/event loop and waits for handshake. The audit clears its instance-local
order event and snapshot AFTER connection, dispatches exactly one
reqAllOpenOrders and waits10 seconds. Native openOrder records rows; native
openOrderEnd sets that instance's event. SDK decoder dispatches OPEN_ORDER_END
into this same native wrapper. There is no repeated query/reconnect within this
audit, no request ID on the open-order end stream and no second order authority.
The supervisor consumes the count only after an end marker and always attempts
disconnect; native disconnect stops/joins its existing reader. ShutdownEvidence
requires both query_completed and disconnected, otherwise FINAL_BROKER_QUERY /
final-callback proof remains unconfirmed. Broker errors are retained; a rejection
without an end never becomes an empty inventory. No guessed error-code routing
or treatment of farm-status callbacks as failures is added.

New guarded controls demonstrate a LOCAL boundary defect separate from the
missing-end receipt: the audit recorded transport flags without enforcing them.
It could dispatch with disconnected/no-reader initialization, or certify an end
marker even after socket disconnection/reader exit. Before repair4 controls
failed and7 passed. The minimal production change is five guard/reporting lines
in the EXISTING supervisor owner: require connected+live reader before dispatch,
record reader liveness after wait and require connected+live reader before
certifying an end-confirmed inventory. Ten-second wait, missing-end error,
UNKNOWN/no-count semantics, finally-disconnect, mutation instrumentation and
source/operator equality owners remain unchanged. This is not a claimed cause of
the captured missing end; that receipt already failed closed correctly.

New synthetic controls use actual native callback methods and installed SDK
Decoder with no socket: completed empty/nonempty inventories, partial/no-end,
error/no-end, dispatch exception, inactive transport and stale/late events. A
pre-query stale event is cleared; a late end/row delivered to a retired audit's
wrapper cannot complete or populate another fresh audit. No shared completion
state crosses audit instances. Within an active request the protocol has no end
correlation token; the fresh-client/single-query boundary is preserved rather
than inventing reusable completion authority. Existing fixture updates supply
realistic synthetic reader/connectivity state; partial-count exceptions still
must be the actual failure, now explicitly asserted. All SDK network/broker
requests, mutation/execution entry points and Python/native network acquisition
are forbidden by guards. Affected tests178passed2.12s; final strengthened guard
controls11passed0.87s. Logs: /workspace/work/final-order-before.log,
final-order-affected.log and final-order-final-local.log. Local results are
synthetic, not CI, a broker response or natural acceptance. New draft PR will
carry independent exact-head review and changed-head CI receipts tied to its
immutable head; no new repair is authorized for automatic merge.

Remaining uncertainty: the receipt lacks the serialized outbound order-query
frame/send acknowledgement, inbound frame/decode/dispatch trace and reader
liveness after the wait. It does not establish whether the query was sent,
received, answered or decoded, nor that history/position/order failures share a
cause. The narrow lifecycle guards do not resolve that uncertainty. No SDK
upgrade, timeout extension, runtime rerun or live broker inquiry is justified or
performed. No fresh holdings snapshot or disappearance of five positions may be
inferred. Five unmatched positions/global new-entry veto, GUI draft, all receipts
and PARKED/fail-closed listing provenance remain preserved. Natural positive
supported-catalyst→raw-intent progression remains unproven.

ONE next action: review the new exact-head draft's bounded final-audit lifecycle
repair and its independent/CI receipts for controlled integration; do not start
an observation or broker diagnostic from this task.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

PR1142 CI follow-up: preserve failed run40852278977 at
1dc46337d371301d166edb2c511232422b809bb5. Linux1failed/3559passed/3skipped:
existing test_scanner_watchlist_prints.test_watchlist_print_format expected a
price row unless output contained an obsolete EMPTY WATCHLIST marker. The actual
formatter legitimately prints count0 headers without that marker. The fixture
ran the full wall-clock-dependent scanner and did not guarantee a populated
Watchlist. Isolated original test passed locally, so the exact CI selection path
is not independently reconstructed. A deterministic empty-display control against
the original assertion fails at the same price requirement; this demonstrates a
fixture contract error, not a production selection failure or an audit regression.
The original Windows job remains preserved on the same run.

The format test now directly exercises the existing printer with explicit
synthetic populated AND empty inputs. It requires exact price/gap/RVOL rows twice
(Watchlist and Focus) for populated input and exactly two count0 headers with no
fabricated rows for empty input. Other pipeline/suppression/order tests remain.
No production scanner, session, catalyst or freshness rule changes. This removes
acquisition/clock dependence from a format test while strengthening both display
contracts. Guarded affected set182passed3.64s; empty-before proof is saved in
/workspace/work/final-order-format-empty-before.log, final result in
/workspace/work/final-order-format-final.log. The local isolated original-test pass
is retained in final-order-format-before.log. Original audit production repair is
source-identical to independent review5695727757; exact replacement-head review
and changed-head CI receipts will be linked on PR1142. No unchanged-head retry.
The one next action and all remaining ownership/natural/readiness gates above
remain unchanged.

## 29 October 2026 — PR1142 accepted; bounded final-order evidence proposal ONLY

Explicit controlled-integration authorization was limited to PR1142. Main was
unchanged atfb0b9e9c3c7a2f7774a1fe73276e7d43e832f8e7; PR head remained
2110fbcf3276c19c0e42c9ad68ece54820fb7566, reviewed tree
501d03fc3a92b8edcfcfcf78e5b04110f70e80cc. Independent agent review5695826928,
successful CI40853211181 and absence of new blocking findings/unresolved threads
were verified. CI's tested merge2aeafdd8e4fdc1bc216ecb9a516c6d98771e99f3 has
exactly the reviewed tree: Linux3561passed/3skipped; Windows3563passed/1skipped,
including cache and PowerShell checks. No completed suite was repeated for status.
Marked ready and merged using expected-head guard2110fbcf and merge method.
Accepted merge/main: `5e03ce25b646181c51eccf029c2957c18c3470b8`.
Fetched accepted tree: `501d03fc3a92b8edcfcfcf78e5b04110f70e80cc`, equal to the
reviewed and tested tree. Integration receipt: PR1142 issuecomment6493912707.
All earlier draft status/next-integration notes remain historical and are
superseded by this receipt. Original checkout and saved history/position/audit
branches remain unchanged. DEPRECATION_LEDGER was read and remains unchanged;
no applicable AGENTS.md was found in checkout/workspace ancestors. This new
checkpoint-only branch does not replace the accepted runtime pin or authorize
any subsequent merge.

### Existing observable stages and precise evidence gap

The saved28October terminal_evidence.json and audit stdout/stderr were inspected
again: reqAllOpenOrders,10-second configured wait,10.0090318s elapsed, connected
before/after wait, native callback-loop thread alive before dispatch, no end,
query_completed=false, no open_orders_count, disconnect confirmed, zero mutation
attempts. Broker codes2104/2106/2158 are farm-status observations, not order-query
acknowledgements; stdout has no openOrderEnd, stderr is empty. The original ZIP
and UNKNOWN result remain preserved. PR1142 adds enforced socket/callback-loop
checks and records callback-loop liveness after wait; this latter field did not
exist in the archived receipt. None proves outbound send or inbound completion.

Existing TransportDiagnostic (src/ibkr/transport_diagnostic.py) already observes
SDK identity, Connection/socket sends and receives, framing, queue put/get,
decoder entry/return/exception, SDK reader identity, hook restoration and reader
stop. However _wire accepts outgoing quote/control IDs1/2/59, not
OUT.REQ_ALL_OPEN_ORDERS16; _message recognizes only quote message IDs, not
IN.OPEN_ORDER5 or IN.OPEN_ORDER_END53. Its active window, target/reservation,
wrapper hooks and absence predicate require a quote request. Other-message
aggregate counts cannot adjudicate order delivery. Simply wrapping the audit in
that unchanged capture is NOT an order-coverage proof. The existing quote caller
also runs scanner/quotes and a separate five-second cleanup query; it must NOT be
executed unchanged or treated as the ten-second final-audit owner.

SDK9.81.1.post1 source: EClient.reqAllOpenOrders emits ID16/version1 with no
request correlation token. EClient.connect creates Decoder(wrapper=self), starts
EReader/socket receive/framing into msg_queue; native _thread runs EClient.run
queue draining and Decoder.interpret into native openOrder/openOrderEnd. A live
_thread is not a separate EReader health receipt. Existing captured evidence
lacks verified ID16 serialization/socket return, per-stage order/end counts,
separate socket-reader transitions, and a complete queue/decode/dispatch trace.
There is no basis to infer a shared history/position/order cause.

### ONE proposed evidence step, pending implementation and execution authorization

Prepare ONE explicit final-orders profile in the EXISTING isolated diagnostic
caller, calling the EXISTING supervisor.final_broker_audit exactly once. This
is a proposal only; no instrumentation or live operator command is implemented
here. No second connection owner, audit implementation or harness is proposed.
Its later user-started execution would use one fresh READ_ONLY native client,
PAPER TWS127.0.0.1:7497/client71, one reqAllOpenOrders, existing ten-second query
wait, no retry/reconnect and no second finalization query. No scanner, quote,
history, positions, news, strategy or execution operation is in scope. Retain
existing normal-session/environment checks, isolated root/state copy, source and
original-operator equality, mutation counters, process inventory, owned cleanup
and package sealing. Retain existing diagnostic120s child/30s stop supervision
and90s package/seal bounds; those outer bounds do not extend the10s query wait.
No900s observation is needed or authorized. The existing PowerShell entrypoint's
hardcoded old diagnostic branch must not silently select an old production pin.
An explicit final-orders mode must verify the future reviewed literal commit/tree;
existing quote mode remains separate and behaviorally unchanged.

Proposed exact source scope (approval required BEFORE implementation):

- src/ibkr/transport_diagnostic.py: opt-in order profile, default quote unchanged.
  Observe method-enter/return/exception and validate exactly one ID16/version1
  serialized frame against the pinned SDK schema, with its socket requested/
  returned bytes, short send and exception counts. Distinguish method entry from
  actual wire dispatch; no added send, buffering, retry or SDK operation changes.
  Recognize message IDs5/53, orderStatus3 and error4 at framing/queue/decoder
  boundaries using reviewed schemas. Count handler availability/arity/dispatch
  and exception class, never retain order/error payloads. Add instance-scoped
  openOrder/openOrderEnd/error callback entry/return counters around the original
  methods invoked exactly once; original completion/event authority remains.
  Observe EReader and native callback-loop start/exit/liveness plus safe numeric
  SDK error codes/exception classes (including SDK-swallowed reader exceptions
  via existing SDK log filter, without formatting log text). Unknown schemas,
  hook failures and unobservable stages remain explicit, never valid absence.
- scripts/certification/pr1090_terminal_observation_supervisor.py: minimal opt-in
  observer-context seam around final_broker_audit's OWN constructed client, before
  its connect and through finally-disconnect. Default audit unchanged. A query
  stage marker establishes observation before the single call. The diagnostic
  caller receives structured proof after observer close; it must not create or
  connect a second client, copy the query or replace query_completed authority.
- scripts/certification/quote_transport_diagnostic.py: explicit order-audit phase/
  profile reusing current environment, source/operator checks, console suppression,
  sanitizer, privacy verification and sealed packaging. Bypass acquire() and the
  quote-specific cleanup query entirely; use the one actual final_broker_audit
  result. Separate transport completeness from audit completion and readiness.
- scripts/certification/run_quote_transport_diagnostic.ps1: explicit scoped mode
  and reviewed-pin selection, reusing current isolated checkout, child supervisor
  and packaging owners; no new competing launcher or automatic retry. This is
  proposed functionality, not an existing runnable command.

Privacy/capture contract: preserve64 records,4096 UTF-8 bytes per record (at most
256KiB of encoded records), saturating aggregate counters, at most8 background
samples and reserved target/finalization capacity. Repeated target stages use
first-sample details plus counts and explicit omissions; never evict/hide drops.
An order attempt is an instance-local diagnostic scope, NOT an invented broker
request ID. End the scope after wait/cleanup, not at an early callback. Retain
only monotonic timings, lengths, message classes, field counts, schema/dispatch
booleans, bounded codes/exception classes, SDK/source hashes and aggregate counts.
No raw frames, field arrays, account/order IDs, symbols, quantities, prices,
article content, free-form broker messages or payload hashes are written or put
in the ZIP. SDK/native console details remain suppressed by existing diagnostic
mechanisms; write only sanitized whitelisted structured artifacts. Private order
objects remain transient under the existing native owner, never evidence exports.
Privacy scan failure prevents ZIP announcement. Lost/restoration/oversize/schema
or budget evidence invalidates transport absence claims, even if an end arrives.
Keep explicit transport coverage separate from query_completed; full socket send
means local socket acceptance, NOT broker acknowledgement or server processing.

Proposed guarded offline acceptance BEFORE any live authorization: extend
EXISTING tests/test_quote_sdk_transport_probe.py,
tests/test_final_order_audit_completion.py and tests/test_quote_transport_operator.py,
plus existing PowerShell parser/stub-child checks. Forbid all real network,
broker connections/queries, mutation and execution submissions. Use MemorySocket,
actual SDK serializer/framer/Decoder and native callback fixtures. Verify exact
one16/version1 request, full/short/failed send without retry, fragmented frames,
frame->queue->decoder->wrapper stage gaps, known/unknown schemas, arity/decoder
failure, partial/no-end, end-confirmed empty/nonempty, error and disconnect,
reader/callback-loop exit, stale/late other-instance events, stop and cleanup.
Assert ten-second wait unchanged and unavailable inventory never count0. Startup
burst/full lifecycle and deliberate overflow must prove reserved final records,
explicit omissions and invalid coverage on lost evidence. Inject synthetic
account/order/symbol/message canaries into all SDK logging/exception paths and
scan every artifact/ZIP. Verify all hooks restore on partial install/failure,
both readers stop within existing cleanup, source/operator equality, no extra
queries/cache writes and no scanner/quotes in order mode. Existing quote-profile
controls must retain their meaning. Obtain independent exact-head review and
appropriate changed-head Linux/Windows/PowerShell checks on the eventual draft;
do not merge that subsequent change automatically.

Defined information gain for a later separately authorized ONE query: distinguish
method not reached; serialization/send not reached or failed/short; local full
send with no recognized inbound order/end frame; framed-but-not-queued;
queued-but-not-dequeued; decoder/handler failure; callback received but no accepted
completion; or genuine completed query with final cleanup proof. Record last
positively observed stage and honest unknowns. A full send with no end cannot
separate TWS/server behavior from an unobserved upstream path. No negative result
or complete diagnostic grants automatic rerun, natural success, risk admission or
PAPER readiness.

ONE next action: authorize OFFLINE-ONLY implementation of this bounded profile
and the above acceptance contract for review. A later single PAPER broker inquiry
requires separate explicit user authorization and a complete reviewed/pinned
operator block; this task authorizes neither. No acquisition, preflight,
observation, broker inquiry, instrumentation implementation or trading occurred.
PR1140/PR1141 semantics, five unmatched positions/global ownership veto, GUI draft,
all historical receipts and PARKED/fail-closed listing provenance remain preserved.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## 29 October 2026 — OFFLINE implementation of bounded final-orders profile

User authorized implementation/testing only, not broker execution or merge.
Main was verified unchanged at5e03ce25b646181c51eccf029c2957c18c3470b8,
tree501d03fc3a92b8edcfcfcf78e5b04110f70e80cc. This branch descends from the
complete saved plan148ca3502da73f7353f00002b499415d6751b3a2; its contract and all
historical receipts above remain intact. Original checkout and saved branches
are preserved. No applicable AGENTS.md was found; DEPRECATION_LEDGER was read
and remains unchanged because no module/owner is retired or replaced.

Implemented in the four planned existing owners:
- TransportDiagnostic has an explicit final-orders profile; default quote profile
  retains its existing schema, output contract and operations. The new profile
  observes actual ID16/version1 serialization and local socket byte returns;
  recognizes order/status/error/end framing, queue, SDK decoder and native callback
  stages; and separately observes EReader and native callback-loop lifecycle.
  Observation failures cannot prevent/replace original sends, queue operations,
  decoder dispatch or callbacks. Exceptions/unknown handlers/arity/SDK ERROR logs,
  partial framing, missing lifecycle proof and capture/restoration failures make
  coverage/absence proof invalid. Per-decoder copied custom handlers call the
  original SDK parser once and detect otherwise ignored trailing fields; no SDK
  parser or global handler authority is replaced. Last positive order/end stages
  and bounded unobserved-stage reasons remain explicit. Full socket return means
  local acceptance only, never broker acknowledgement.
- final_broker_audit has an opt-in observer factory around its OWN newly constructed
  client, installed before connection and closed after finally-disconnect. Default
  call behavior is unchanged. Opt-in waiting uses the existing cooperative helper
  with the same ten seconds; stop/deadline propagates only after owned cleanup.
  The observer never supplies an end event, inventory or query_completed result.
  Observer cleanup failure is separate from authoritative query outcome.
- Existing Python diagnostic caller has an explicit final-orders profile using
  that single actual audit. It never invokes acquire(), a scanner/quote request,
  a second client or the quote cleanup query. It exports only a whitelist of the
  audit's structured booleans/counts/timings, with no free-form errors or IDs.
  Complete transport plus incomplete audit remains DIAGNOSTIC_ONLY/exit2. Guard,
  source/operator equality, inventory, mutation checks and package/seal ownership
  remain; any observer cleanup/snapshot failure remains incomplete. Raw native
  console text is suppressed, not exported or treated as evidence.
- Existing PowerShell entry has explicit DiagnosticProfile and ExpectedTree
  parameters. Final-orders requires the reviewed literal commit AND tree, fetches
  that commit without the old quote-branch fallback and passes scope/tree to every
  phase. Quote defaults remain unchanged. New profile uses its own clearly named
  final-orders-diagnostic-upload.zip; no old scope or pin is silently substituted.

Capture retains64 records/4096 UTF-8 bytes per record, fixed saturating counters,
startup/global maximum8 samples, first-sample stage aggregation/counts with
explicit omissions and reserved finalization records. Overflow never evicts or
hides evidence and invalidates absence claims. Order profile events/fields are
whitelisted: no raw frames/field arrays, account/order IDs, symbols, quantities,
prices, broker text or payload hashes. Only SDK/source hashes are exported.
Unknown exception classes are fixed OTHER_EXCEPTION. SDK logging is observed
without formatting its payload. Existing120s/30s child supervision and90s
package/seal budgets, two-second reader cleanup bounds and10s query wait remain.
No retry, reconnect, source expansion, operational cache publication or new
canonical writer exists. Native private order objects remain under their owner.

Guarded affected local validation:246passed2.97s in the three planned Python test
modules plus existing evidence-safety/P1 regressions. Log:
/workspace/work/final-orders-final-pin-controls.log. These are synthetic controls,
not CI or a broker receipt. They cover real SDK serialization/framing/decoding,
full/short/failed sends, fragmented/partial frames, actual native nonempty/empty
callbacks, error/status/end, stage gaps, unknown/trailing schemas and missing/
failing handlers. They also cover swallowed SDK-reader errors, observer faults
at count/record/parser/queue boundaries without changing original operations,
stop propagation, cleanup/partial-install/restoration failure and instance-isolated
late callbacks. Startup bursts/many rows retain final capacity; deliberate drops
invalidate coverage. Privacy canaries traverse native/error/SDK logging paths;
structured artifacts and a sealed synthetic ZIP contain none. The operator's
probe/package/seal filesystem control forbids acquisition, models platform/session
and READ_ONLY setup, preserves original operator state, proves source equality,
no scanner/quote activity and no package-time second audit. Existing quote tests
still pass. PowerShell5.1 validation extends the existing parser test to bind ONLY
the real parameter block and pre-body guard: default quote mode, explicit order
scope/tree, rejection of missing tree and unknown profile, without invoking the
entry or a child. Actual Windows execution of these checks remains a CI receipt,
not a local claim. Independent exact-head review and changed-head Linux/Windows/
PowerShell receipts will be posted on the accompanying draft PR at its immutable
head; no status-only full-suite repetition or subsequent automatic merge.

Remaining limits: this instrumentation does NOT repair or diagnose the historical
missing openOrderEnd by itself. No new acquisition, preflight, observation or
broker inquiry was executed. The saved28October inventory remains UNKNOWN, never0.
An end observed on a fresh single-query client has no protocol request token;
instance scope is not reusable provenance. Full local send cannot establish
server receipt/processing. Lost evidence makes absence unknown even if a callback
is observed. Natural positive catalyst-to-raw-intent progression remains unproven;
five unmatched positions/global ownership veto and PR1140/1141/1142 semantics,
GUI draft, all receipts and PARKED/fail-closed listing provenance are preserved.

ONE next action: review the new exact-head draft and offline/CI evidence. A later
single PAPER inquiry needs SEPARATE explicit authorization and a reviewed pinned
operator block; none is provided or authorized here. No merge or readiness upgrade.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

Final review follow-up before certification: preserve review5696428360 and
run40859787829 at9ca2f888 as superseded receipts. Additional PowerShell source
review identified that assigning an if-expression's empty @() branch yields
$null, which array concatenation can append as an empty child argument. The
profile-argument array is now initialized explicitly before optional order
arguments. Extended actual PowerShell5.1 controls reproduce that old pure-array
hazard and evaluate the real probe/package/seal argument expressions WITHOUT
invoking any child: quote mode must have6 nonempty arguments; order mode8 with
its exact profile/tree. This strengthens default-quote compatibility rather than
retrying an unchanged head. Also export negotiated server_version with verified
order serialization to bind decoder-schema interpretation to the observed SDK
session; no additional request or private field is introduced. Targeted Python
wire/operator/audit controls remain green; the final Windows control is a changed-
head CI requirement, not a local execution claim. New exact-head delta review
and replacement CI receipts will be linked on the same draft PR1143. No inquiry,
merge or readiness upgrade; the single next action above remains unchanged.

CI follow-up: preserve run40859787829 at9ca2f888 (Linux1failed/3601passed/
3skipped, reader-log control) and run40860190569 at81706076 (Windows targeted
news-maintenance1failed/35passed, full Windows/cache/PowerShell later steps skipped;
Linux outcome remains on that immutable run). The reader control depended on SDK
logging being enabled; the existing operator console protection intentionally
suppresses that logger. New deterministic enabled/disabled controls first failed
because an abnormal reader exit had no independent marker. The diagnostic now
records abnormal EReader exit while its connection remains live, and independently
invalidates coverage on receive/queue exceptions. Actual original queue return/
exception behavior is preserved; ordinary empty-queue polling is not an error.
SDK logger configuration is NOT changed. Guarded affected set247passed2.79s;
before/after logs remain /workspace/work/final-orders-disabled-logging-before.log
and final-orders-logging-after.log. This is a diagnostic observability repair,
not a historical callback-delivery claim or a relaxed test.

The Windows cache failure is in existing
test_independent_news_maintenance.test_thread_writers_merge_and_readers_never_see_partial_json:
at least one writer returned cache_write_failed. The original assertion omitted
its diagnostic payload, so it does NOT establish TimeoutError, PermissionError,
production safety or harmless flakiness. Existing per-path/thread/process cache
owner/read/publication source was inspected; none is changed in this bounded
diagnostic task. Strengthen ONLY that assertion to retain failed rows/error types
on any subsequent failure; all concurrency/read/merge/cleanup assertions remain.
Do not suppress exceptions, enlarge cache timeouts or retry an unchanged head.
The existing CI workflow now runs the three focused final-order modules and actual
PowerShell5.1 parameter/argument checks BEFORE that independent cache barrier,
so a cache failure cannot hide the requested Windows diagnostic evidence. It does
not skip/weaken that barrier or make the job green if it fails. This targeted
verification is justified by the newly blocked Windows evidence, not a status-only
suite repetition. Any remaining cache failure is a separate unresolved gate;
no cache repair is inferred or silently added. Final exact-head review and CI
receipts remain on PR1143; all previous failures remain preserved. No broker
inquiry, merge, ownership change or readiness upgrade is authorized.

Windows receipt correction (supersedes the earlier empty-if hazard claim):
run40861219229 at923e5c7a passed82 focused Windows Python controls, then the new
PowerShell hypothetical "legacy array must contain7/null" assertion failed.
Actual Windows5.1 does NOT support the earlier source-only inference of a null
append. That inference was overstated, including in review; it is withdrawn,
not attributed to SDK/operator failure. Explicit array initialization remains a
clear implementation of the requested new mode, but is NOT a demonstrated
historical quote bug repair. The false7/null requirement is removed; informational
legacy count is printed without assuming its result. Meaningful assertions on
ALL THREE actual child expressions remain exact6 nonempty quote arguments and8
order arguments with literal scope/tree. No production gate is relaxed. The failed
run also reported no artifact because it stopped before the older harness stages;
focused CI output now writes real pytest/PowerShell logs into the existing artifact
pattern, preserving early failure evidence without masking the failing job.
The independent news-cache failure remains separately unresolved; no cache source
change is made. This new test correction requires changed-head review/CI, not an
unchanged-head retry. All prior receipts and readiness/ownership limits remain.

Late-output privacy control: a synthetic callback print injected during the
post-context privacy scan first failed the existing operator filesystem control
(/workspace/work/final-orders-late-console-before.log). The temporary silent
context previously restored ordinary streams before that scan/return; a reader
that failed cleanup could therefore print order identifiers/symbols into outer
process logs after observer restoration. This is a demonstrated local diagnostic
privacy gap, not evidence of such a leak in a historical receipt. Final-orders
probe now installs process-lifetime silent sinks BEFORE broker construction;
the temporary context restores to those sinks, with no unsuppressed transition.
Package/seal phases remain filesystem-only and quote defaults are unchanged.
The offline control captures simulated outer stdout/stderr artifacts and verifies
both operator-state and late-order canaries absent from EVERY ZIP member. Three
focused Python modules82passed; log final-orders-late-console-after.log. Original
SDK behavior, ten-second wait, query ownership and source/operator checks are
unchanged. Suppressed text is not transport proof. New exact-head review/CI will
supersede cdd43d3c; no inquiry, automatic merge or readiness upgrade is authorized.

## 29 October 2026 — PR1143 acceptance/integration; prepared inquiry NOT AUTHORIZED

Controlled integration was explicitly authorized only after acceptance review.
Verified unchanged base5e03ce25b646181c51eccf029c2957c18c3470b8, PR1143 head
c15c1f98fb54a455f8f3bde99bf92e0b98f9cc0b, independent agent review5696795396,
no newer blocking findings/unresolved threads, successful CI40863612966 and tested
merge4dbd7c2288d6da7abf0833c787e9cf0689ca3b04. Tested/reviewed tree is
ab7d9f40cee17273c7236cc46b617d21f0aadc0a. Linux3605passed/3skipped;
Windows3607passed/1skipped, including focused82, actual PowerShell5.1, news/cache,
float, inventory, exit propagation and stub harness checks. Existing receipts
were used; no completed suite was rerun for reconciliation. The saved plan
148ca350, all historical failures/superseded reviews and the corrected PowerShell
inference remain preserved above.

Acceptance comparison:

| Saved contract | Source/receipt disposition |
| --- | --- |
| Sole actual client/query,10s/end authority | supervisor.final_broker_audit153 constructs one native client, sends one query and alone requires end+active transport. Observer cannot supply completion. Default audit unchanged. |
| No scanner/quotes/extra cleanup query/retry | quote_transport_diagnostic.final_orders110 calls that owner once; explicit profile branch279 bypasses acquire(), quote client and quote cleanup. No news maintenance or cache publication starts. |
| Bounded honest stage evidence | TransportDiagnostic keeps64x4096 record bounds, startup cap/reserved final records, aggregation/omission/drop counters and unknown reasons. Actual SDK controls cover schema/handler/queue/decoder/reader gaps; short send never establishes full local acceptance. |
| Cleanup and equality | Owned audit finally disconnect, observer restoration/reader checks, mutation counters, source/operator manifests and final process inventory remain mandatory. Fault/stop/restore controls stay fail closed. |
| Privacy including late callbacks | Final-orders lifetime silent sinks installed before broker construction; whitelist outputs and every-member sealed-ZIP canaries cover late cleanup/post-context output. No raw order/account payload exports. |
| Windows parameters/pins | Accepted launcher exposes ONLY ExpectedCommit, DiagnosticProfile, ExpectedTree; real5.1 binding/actual three child6/8 argument checks passed. Final-orders requires literal commit/tree; no old branch fallback. |
| Default quotes | Default remains quotes; existing quote controls pass; no raw broker run performed to certify it. |

### Explicit disposition of the unclassified Windows news-cache failure

Failed run40860190569 (head81706076), Windows job123401239153, test
`tests/test_independent_news_maintenance.py::test_thread_writers_merge_and_readers_never_see_partial_json`:
1failed/35passed. At least one of24 concurrent synthetic writers returned
cache_write_failed while another thread read a seeded store. The old assertion
omitted failed-row diagnostics; the captured log does NOT identify error type,
which write failed, OS denial versus lock timeout, or its precise cause. Production
CanonicalNewsEvidenceStore.write224/store_owner behavior was inspected and is
unchanged. The test now prints failed diagnostics without weakening any read,
merge, completion or cleanup assertion. Later passing targeted/full checks do
NOT classify the earlier failure or establish that it is harmless/resolved.

Scope-based acceptance decision: this uncertainty does NOT block integration of
PR1143 and does NOT itself block a LATER separately authorized final-orders-only
PAPER diagnostic. That explicit route never calls CanonicalNewsEvidenceStore,
starts NewsMaintenance, scans, fetches quotes/news or publishes operational cache;
its own source/operator/mutation/cleanup/privacy owners and single audit are
independently covered, with no running Ross runtime permitted. Its source scope
cannot exercise or rely on the concurrent news-store writer that failed. This
is NOT general news-cache certification. The failure remains a separate news/
concurrency/natural-runtime and PAPER-readiness acceptance gap; investigate it
before claiming those broader properties. No speculative cache repair, suppressed
error, timeout increase or relaxed concurrency test was made.

After acceptance, marked ready and merged with expected-head guardc15c1f98 and
merge method. Accepted main/merge: `7e918815f623d5f34bf349d9af72f0098d6a3ec1`.
Fetched main tree: `ab7d9f40cee17273c7236cc46b617d21f0aadc0a`, exactly the
reviewed/tested tree. PR1143 acceptance review receipt6495962289; integration
receipt6496016532. The actual accepted launcher was inspected after integration.
DEPRECATION_LEDGER was read and remains unchanged; no applicable AGENTS.md was
found in checkout/workspace ancestors. Original checkout, GUI draft and saved
plan/history/position/diagnostic branches remain untouched. This checkpoint-only
branch is NOT merged and does not alter the accepted runtime pin above.

### ONE prepared operator block — NOT YET AUTHORIZED TO RUN

There is NO execution authorization in this task. The gate is deliberately false.
Do not change it or execute an inquiry until separate explicit authorization.
Later conditions must include Windows PowerShell5.1 Desktop, configured normal
RTH without override, PAPER TWS127.0.0.1:7497 with Read-Only API, unused client71,
no running Ross runtime, and the existing verified Python3.13.3/SDK environment.
The block obtains the existing accepted launcher from its immutable Git object,
not the potentially older original working-tree file. It changes no original
checkout files or historical roots. Only the existing launcher creates the fresh
isolated qtransport root; its own120s/30s probe supervision,10s audit wait,
cleanup/equality/mutation/inventory/privacy and90s package/seal bounds remain.
Exactly one launcher invocation, no retry or second audit. No new harness.

```powershell
# PREPARED ONLY — NOT YET AUTHORIZED TO RUN.
& {
    $ErrorActionPreference = 'Stop'
    $PaperInquiryAuthorized = $false
    if (-not $PaperInquiryAuthorized) {
        throw 'NOT AUTHORIZED: separate approval for this single PAPER inquiry is required.'
    }
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or
        $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
        throw 'Use Windows PowerShell5.1 Desktop.'
    }
    $SourceCheckout = 'C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system'
    $Python = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
    $RuntimePin = '7e918815f623d5f34bf349d9af72f0098d6a3ec1'
    $ExpectedTree = 'ab7d9f40cee17273c7236cc46b617d21f0aadc0a'
    if (!(Test-Path -LiteralPath $SourceCheckout -PathType Container) -or
        !(Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw 'Verified original checkout/Python path missing; nothing launched.'
    }
    & git -C $SourceCheckout fetch origin main
    if ($LASTEXITCODE -ne 0) { throw 'Fetch failed; nothing launched.' }
    $currentMain = (& git -C $SourceCheckout rev-parse refs/remotes/origin/main | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $currentMain -cne $RuntimePin) {
        throw 'Main advanced/differs: stop for delta review; do not substitute a pin.'
    }
    $actualTree = (& git -C $SourceCheckout rev-parse ($RuntimePin + '^{tree}') | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $actualTree -cne $ExpectedTree) { throw 'Accepted tree mismatch.' }
    $launcherText = (& git -C $SourceCheckout show ($RuntimePin + ':scripts/certification/run_quote_transport_diagnostic.ps1') | Out-String)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($launcherText)) {
        throw 'Accepted existing launcher unavailable; nothing launched.'
    }
    Write-Host 'ONE final-orders diagnostic only; no automatic retry.'
    Write-Host 'Normal RTH; PAPER127.0.0.1:7497; Read-Only API; unused client71; no Ross runtime.'
    Write-Host 'Fresh root/absolute ZIP will be announced by the existing launcher.'
    $launchArgs = @{
        ExpectedCommit = $RuntimePin
        DiagnosticProfile = 'final-orders'
        ExpectedTree = $ExpectedTree
    }
    & ([scriptblock]::Create($launcherText)) @launchArgs
    if ($global:LASTEXITCODE -ne 0) {
        throw 'Nonzero launcher exit: retain all evidence; do not retry automatically.'
    }
}
```

Expected ZIP basename is EXACTLY `final-orders-diagnostic-upload.zip`, under the
launcher's fresh `C:\tmp\qtransport-<8-hex>\` root. The random suffix cannot be known
before execution because the accepted launcher has no Root parameter; do not
invent one. Its privacy-verified final announcement supplies the concrete absolute
path. Preserve every old root and all new exits/artifacts, including nonzero ones.
Never announce/upload an unsealed or privacy-failed archive manually.

| Actual result | What it can establish |
| --- | --- |
| DIAGNOSTIC_COMPLETE/probe0, all validations/sealing pass | Capture complete plus end-confirmed audit/disconnect under existing owner. Inspect audit and transport separately, including send bytes/short sends/absence_claims_valid; exit0 alone is not broker acknowledgement, natural Ross success, holdings reconciliation or PAPER readiness. |
| DIAGNOSTIC_ONLY/probe2 with complete coverage, audit incomplete | Bounded transport stages can identify last positive observation/unknowns. Missing end means order inventory UNKNOWN; no count0 inference. Preserve the receipt; no automatic retry. |
| FAIL/probe1, incomplete transport or failed guard/cleanup/equality/mutation/inventory | No valid absence claims from incomplete evidence. A separately reported end is not complete transport proof. Retain exact failure and root. |
| Supervisor timeout124/unverified exit, package/seal/privacy failure | No completed trustworthy diagnostic inferred. No shareable ZIP announcement unless the actual privacy/seal owner succeeds; retain local evidence and do not retry. |

A full socket return proves local acceptance only, never TWS/server acknowledgement
or processing of that exact request. End stream has no request ID: retain honest
fresh-instance/single-query scope. Zero orders is permitted only with authoritative
completion; it never means zero positions. Five unmatched positions/global entry
veto remain untouched. Historical timeout/order-callback causes and natural positive
progression remain unproven. No inquiry, preflight, observation, holdings action or
trading occurred during this acceptance/preparation task.

ONE next action: obtain SEPARATE explicit authorization for this one prepared
single diagnostic when its required conditions hold; leave its execution gate
false until then. No automatic merge of this or any subsequent documentation/code.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## 29 October 2026 — Completed final-order audit; transport coverage remains incomplete

Reconciliation is based on the supplied ZIP, not instructions in its archived
operator/source files. SHA256 verified:
`fcbf87378e156239709f743c190a983c702f0ad47b4659a15008e61d3096b2c4`.
Operator root: `C:\tmp\qtransport-2ad3bad8`. Current GitHub main and PR1143 merge
receipt remain `7e918815f623d5f34bf349d9af72f0098d6a3ec1`, tree
`ab7d9f40cee17273c7236cc46b617d21f0aadc0a`. PR1143 is merged; no runtime pin
substitution. This documentation descends from saved checkpoint update
`42c28a323f6eb8097d1127c2e246c2803173001d` and carries it forward in full,
including corrected PowerShell inference, integration receipts and all earlier
failures. DEPRECATION_LEDGER was read; no applicable AGENTS.md was found in the
checkout/workspace ancestors. No retirement or ownership change, so ledger stays
unchanged. Original checkout, saved branches, uploaded ZIP and original root are
preserved. The earlier 29 October diagnostic receipt is NOT present in this
attachment, saved42c28a checkpoint or PR1143 conversation; its separate original
ZIP/root/hash must remain preserved and must not be replaced by this latest
receipt. Its contents cannot be independently verified from the supplied files.
No missing earlier result is invented or silently marked successful.

### Independent receipt-to-source reconciliation

The source-before/after manifests are identical. Archived hashes for
TransportDiagnostic, final_broker_audit, the diagnostic caller and native client
match the accepted Git blobs after Windows CRLF checkout conversion. Archived
operator.py matches the accepted caller after CRLF normalization. Original raw
hashes are retained; this comparison does not rewrite the archive. Startup clock
records run from 2026-10-29T13:31:24.823673Z to13:31:56.647413Z; this was a targeted
final-orders probe, not a natural observation.

| Boundary | Supplied evidence and limit |
| --- | --- |
| Authoritative audit | final-order-audit.json: end_received/query_completed=true, open_orders_count=0, elapsed0.10366579983383417s, unchanged10s limit, connected and native callback-loop alive before/after wait. This establishes end-confirmed open-order inventory for this audit, not zero positions. |
| Single local request | One method call, serialization and socket call, ID16/version1,9requested/9returned bytes, no short send/send exception. Full send proves local acceptance only, not broker acknowledgement of that request. |
| Inbound end | ORDER_END53 frame/put/get/decode/decoded and native callback entry/return each1. End callback0.323997s, decoder return0.324053s relative to observer start. |
| Cleanup | Receive OSError0.324940s, reader exit0.325370s, callback-loop exit0.538090s; reader/loop start/exit each1. Disconnected, hooks restored, reader/loop stopped. Timing alone does NOT establish receive-error ownership. |
| Safety/sealing | Zero place/modify/cancel attempts; source/operator PASS; final-runtime-inventory completed/empty. Privacy probe/package/seal passed; independent existing sanitizer scan of extracted artifacts also passed with0occurrences. No acquisition/scanner activity. |
| Overall result | outer-status/probe/result preserve FAIL/exit1, transport_evidence_incomplete=true, coverage_verified=false and absence_claims_valid=false. Do not replace these with exit0 or retroactively certify transport coverage. |

A successful audit and incomplete transport evidence are distinct results. The
historical28October missing openOrderEnd cause remains unresolved: this later
success does not diagnose it or connect it to history/position failures. Likewise
zero open orders does not resolve five unmatched positions or their global veto.

### Exact predicate and the unresolvable attribution in this capture

`src/ibkr/transport_diagnostic.py:628-639` requires installed SDK hooks/hashes,
restoration, reader/loop stop and exactly one start/exit each, no pending partial
frame, no observation failure, and zero listed capture/schema/reader/queue/receive
failures. The ONLY nonzero invalidating counter in this archive is
`recv_exceptions=1`. Dropped/oversize/hook/schema/unknown-message/decoder/logged-
reader/abnormal-reader/queue failures are all0. Thus the receive-exception clause
is the recorded reason coverage is false; no capture-budget overflow is involved.
`_Socket.recv:712-724` counts every non-timeout exception and retains only its
safe exception class. Finalization merely enforces that predicate.

Actual existing lifecycle:
`final_broker_audit:153-219` accepts the native end only while transport/loop are
live, sets query_completed/count, then its finally invokes the same client's
`disconnect`. Native `IbkrClient.disconnect:221-250` sets stop, invalidates owned
requests, calls EClient.disconnect and joins its callback loop. Pinned SDK
EClient.disconnect sets DISCONNECTED, invokes Connection.disconnect, clears/reset
state. Connection.disconnect closes its socket under its lock; the current
`_Socket.__getattr__:677` forwards close WITHOUT an observation. A concurrently
blocked recv can fail on that close. Separately, SDK Connection.recvMsg catches
socket.error/OSError and itself invokes Connection.disconnect; an independent
receive failure can therefore also finish with orderly disconnect/reader exit.
The same exception class/end-before-error/final-stopped flags support BOTH paths.

Missing from THIS archive: the audit owner's disconnect entry, same-socket close
entry/result, an ordered receive/close association, and bounded OS errno/winerror
category. No account/order payload is needed to observe those boundaries. Neither
an OSError class nor a connected check taken earlier proves which path occurred.
The counter is not suppressed; the archived exception remains unattributed.

### Targeted guarded offline controls — synthetic, not Windows/runtime evidence

Executed three new bounded synthetic experiments using the EXISTING
`tests/test_quote_sdk_transport_probe.py` orders_prepared owner/guards, actual
SDK serializer/Connection/Reader/Decoder, native callback loop and disconnect.
No real socket connection or acquisition; guarded request/mutation/execution
methods forbidden, one actual serialized16/version1 in-memory query per case.
A controlled in-memory recv blocks with2s failure bounds; no timeout changes in
production. Results:

- Owned native disconnect closes the same in-memory socket and deterministically
  releases its pending recv into OSError AFTER a genuine native end callback:
  recv_exceptions1; coverage/absence=false; hooks restored and threads stopped.
- Independent injected OSError AFTER that callback and after live after-wait
  checks, BEFORE any owned close: the same relevant exported outcome/stage/counter
  fields, coverage/absence=false, restored/stopped. SDK then closes the socket.
- Independent failure BEFORE end: no end callback, last positive stage local
  socket acceptance, coverage/absence=false; cleanup/restoration retained.

All3 controls passed. The first two prove that this evidence projection cannot
attribute the archived error; they do NOT prove the Windows error was caused by
owned shutdown. They also show why simply ignoring post-end OSError is unsafe.
Scratch experiment (not a new repository module/harness):
`/workspace/scratch/final-orders-investigation/ambiguity_control.py`, SHA256
`d2ad08395f8879890f6be53d357f3f74ae2df45bcc758cd3b63d43a1deec800a`;
output `control-results.json` beside it. Ran under existing tests/offline
sitecustomize network/native-transfer guard with the repository virtualenv.
These are local synthetic controls, not CI, Windows behavior proof, a repair
regression or natural acceptance. No completed suite was repeated.

No production classification repair is justified from the captured causal
evidence. Coverage remains conservatively invalid, and the actual successful
query remains authoritative independently. No source/test/launcher changes,
new repair draft, new exact-head repair review or changed-head production CI are
claimed. Documentation checks are proportionate; PR1143's accepted review/CI are
historical implementation receipts, not verification of the missing attribution.

### ONE next action

Review a bounded OFFLINE-ONLY shutdown-attribution extension in the EXISTING
observer/audit seam before considering another inquiry: record audit-owned
finalization entry, same-socket close entry/return/failure, receive sequence and
allowlisted numeric OS closure-error categories, without raw exception text or
identifiers. Exact scope would be TransportDiagnostic's ObservedConnection/
_Socket and final_broker_audit's existing optional observer seam. Keep all receive
errors counted, current coverage policy unchanged until guarded controls establish
an enforceable causal classification. Require independent loss before/after end,
close failure, concurrent close/recv, late callback, Windows closed-socket behavior,
privacy/budget/restoration and quote-default controls. Do not infer ownership from
end/stop/disconnect flags or event timing alone. This is a precise evidence proposal,
not an implemented repair, broker command, inquiry authorization or automatic
rerun. A later PAPER inquiry still needs separate explicit authorization.

The separate unclassified Windows news-cache failure remains unresolved (run
40860190569); later success and this cache-free diagnostic do not repair it.
PR1140 history, PR1141 position authority, PR1142 audit fail-closed authority,
all five positions/global ownership veto, GUI draft and PARKED/fail-closed listing
provenance remain unchanged. No broker inquiry, acquisition, preflight, runtime
rerun, holdings action, SDK change, timeout extension, gate relaxation or trading
occurred. Natural supported catalyst-to-intent progression remains unproven.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## 29 October 2026 — PR1144 bounded shutdown-attribution evidence (OFFLINE ONLY)

Explicit authorization covers offline implementation of the proposal above, not
broker execution or integration. Current main remains7e918815f623d5f34bf349d9af72f0098d6a3ec1,
treeab7d9f40cee17273c7236cc46b617d21f0aadc0a. Continued on the EXISTING PR1144
branch fromffc1f17354b9bf8759760b967245a2bc1e3be630, retaining42c28a and the
complete saved checkpoint/proposal. Applicable instructions/ledger were checked;
no AGENTS.md found; no owner retired or replaced, ledger unchanged. Original
checkout, all receipts and saved branches remain preserved.

Implemented only in existing TransportDiagnostic and final_broker_audit owners:

- Optional audit_finalization observer seam runs immediately before the audit
  owner's existing finally-disconnect, including aborted queries. It records
  entry only, cannot supply completion/count or change the ten-second wait.
  Seam failure is an observer cleanup failure; disconnect still runs and actual
  query authority is preserved. Default audit without an observer is unchanged.
- Final-orders socket proxy records close entry/return/failure and receive entry/
  failure with a bounded, instance-local observation sequence. Same-proxy close
  sequences accompany receive errors. No socket addresses/object identities or
  invented broker request tokens export. A thread-local marker says only whether
  that close invocation is on the thread that entered audit finalization; it does
  NOT prove causal ownership of any receive failure.
- Relationships BEFORE_CLOSE/OVERLAPS_CLOSE/AFTER_CLOSE_RETURN/AFTER_CLOSE_FAILURE
  describe observed wrapper spans, not kernel syscall linearization or causality.
  Every exported causal assessment remains UNKNOWN. A close wrapper entry can
  precede the actual OS call, and concurrent close/recv cannot prove causality.
  Missing/failed/dropped observation invalidates absence proof as before.
- Error fields expose only allowlisted numeric errno/winerror categories (0 means
  absent/unallowlisted), never arbitrary codes or free-form exception messages.
  Allowlist: platform EBADF/ENOTSOCK/ECONNRESET/ECONNABORTED/ENOTCONN/ESHUTDOWN/
  EINTR/EPIPE/ETIMEDOUT and Windows995/10004/10009/10038/10053/10054/10057/10058/
  10060. A category alone is never provenance or permission to disregard failure.
- ALL existing receive-error counters remain. The coverage/absence snapshot
  predicate is AST-identical to the accepted runtime: ANY non-timeout receive
  exception still invalidates coverage, even with an end and owned finalization.
  Default quote close is an unobserved passthrough; quote controls remain intact.
- Existing64-record/4096-byte limits, eight startup samples, finalization reserve,
  saturating counters and explicit omissions remain. Finalization/close evidence
  uses the existing reserved slots; repeated receive entries are first-sample
  details plus occurrence counts. No eviction or silent overflow promotion.
  No extra query, connection, retry, reconnect, scanner or acquisition owner.

Guarded proportional validation extends the EXISTING three diagnostic test
modules, with actual SDK serializer/Connection/EReader/Decoder/native disconnect
and the audit seam. New controls cover independent receive failures before/after
end, owned close unblocking recv, deliberately concurrent close/receive (UNKNOWN),
close failure and original return/exception identity, observation failure,
instance isolation/late callbacks, reserved final evidence under saturation,
quote passthrough and every sealed ZIP member including late-output canaries.
Actual OS closed-socket control creates/closes a local socket, then calls recv:
NO bind/listen/connect/socketpair, broker or network permission exemption. Existing
global offline guards are unchanged; test additionally forbids network operations.
Windows CI must confirm actual10038 behavior; Linux EBADF is not Windows proof.
All order mutations, execution, acquisition and broker connections are forbidden
by the existing guarded fixtures. No production timeouts or waits are extended.

Local development receipts are retained, not CI: initial82existing controls passed;
first new run1failed/92passed because its assertion expected the sticky flag,
where existing observe() instead increments hook_errors (coverage already invalid).
Corrected that test to assert the real hook-error/coverage contract. Next run
1failed/94passed because a packaging stub bypassed the existing observer factory,
so it could not model the actual finalizer's exit1. Connected the synthetic stub
to that factory; no production exit policy changed. Failed output retained at
/workspace/scratch/final-orders-investigation/shutdown-attribution-focused.log.
Final affected validation/review/changed-head Linux/Windows receipts will be
recorded on PR1144 at its immutable head, without status-only source commits.
CI selection/configuration is unchanged; full changed-head checks are justified
by this new transport/audit source, not documentation status reconciliation.

Archived count0/end-confirmed successful audit AND transport FAIL/exit1 remain
unaltered. Neither the archived OSError nor historical missing openOrderEnd is
explained by this addition. Five unmatched positions/global ownership veto,
PR1140 history/PR1141 position authority/PR1142 audit semantics, GUI draft,
separate unclassified news-cache failure and PARKED/fail-closed listing provenance
remain intact. Zero orders never establishes zero positions. No inquiry,
preflight, observation, runtime rerun, holdings action or trading occurred.

ONE next action: review the exact draft implementation and its offline/Windows
receipts for controlled integration; no merge or subsequent PAPER inquiry is
authorized here. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## 29 October 2026 — PR1144 accepted; one pinned final-orders block prepared

Explicit controlled-integration authorization applied to PR1144 only. Verified
unchanged main7e918815f623d5f34bf349d9af72f0098d6a3ec1, exact PR head
e21bc436a842bb62d3f07ff0bd535754604727b2 and reviewed tree
e66b6daa84f04ec95dce1155fde2a9a4e156cf14. Independent agent review5702801668
(no blockers,95guarded controls independently passed) and successfulCI40929046617
were verified; Linux3618passed/3skipped and Windows3620passed/1skipped, focused95,
actual Windows closed-socket10038, cache and PowerShell checks all passed. No new
blocking findings/unresolved threads. Tested merge2d094a5761b9c760dc3ed0aaa636b752853e7d3c
was fetched and its tree exactly equaled reviewed head. No completed suite rerun.
Acceptance receipt: PR1144 issuecomment6505354959. Marked ready and merged with
expected-head guarde21bc436 and merge method.

Accepted merge/main: `a501c88bcc926bef87875f6352f210b19b6e438b`.
Fetched main tree: `e66b6daa84f04ec95dce1155fde2a9a4e156cf14`, exactly the
reviewed/tested tree (empty diff). Integration receipt: PR1144
issuecomment6505366918. Original checkout/saved branches/all receipts preserved.
AGENTS search found none applicable; DEPRECATION_LEDGER read and unchanged, with
no retirement or owner change. This checkpoint-only branch is NOT merged and
DOES NOT alter the literal accepted runtime pin above. It contains this new
accepted-pin preparation, not a status-only repetition of prior verification.
No subsequent merge is authorized here.

### Required conditions and actual existing caller

Accepted existing launcher:
`scripts/certification/run_quote_transport_diagnostic.ps1`.
Only parameters are ExpectedCommit, DiagnosticProfile (quotes/final-orders),
ExpectedTree. Final-orders requires explicit reviewed tree. No Root, Python or
RuntimeSeconds parameter exists. Its own fresh qtransport GUID root is required;
never reuse/delete C:\tmp\qtransport-2ad3bad8 or another historical root.

Use Windows PowerShell5.1 Desktop and existing Windows Python3.13.3 at
C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe with SDK9.81.1.post1. Source
checkout remains C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system.
PAPER TWS at127.0.0.1:7497, Read-Only API enabled, unused client71, no running Ross
runtime, valid existing session/environment and disk/inventory guards mandatory.
No overrides or guard bypass. Current accepted session owner uses New York local
09:30 <= clock <16:00 on a permitted weekday (holiday/half-day rules apply).
For29October2026 the normal window converts to13:30 <= Europe/London <20:00;
clock time alone does not prove eligibility. Let startup and the ten-second audit
fit in the normal session; the existing child gate remains authoritative. No
broker/session preflight was executed while preparing this block.

The block reads the EXISTING launcher from the immutable accepted Git object,
not a possibly stale working-tree file. It performs one invocation only. Launcher
retains fresh detached worktree, isolated operator-state copy, normal RTH and
READ_ONLY checks, one actual fresh audit client/query, ten-second native end
requirement,120s probe/30s stop supervision and90s package/seal budgets with their
existing stop bounds. No quote/scanner acquisition, extra query, retry or reconnect.
All cleanup/mutation/source/operator/inventory/privacy/sealing owners remain.

### ONE copy-paste Windows PowerShell5.1 block — prepared, NOT executed here

```powershell
# Prepared for ONE user-started final-orders inquiry when all conditions hold.
& {
    $ErrorActionPreference = 'Stop'
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or
        $PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSVersion.Minor -ne 1) {
        throw 'Use Windows PowerShell5.1 Desktop.'
    }

    $SourceCheckout = 'C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system'
    $Python = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
    $RuntimePin = 'a501c88bcc926bef87875f6352f210b19b6e438b'
    $ExpectedTree = 'e66b6daa84f04ec95dce1155fde2a9a4e156cf14'

    if (!(Test-Path -LiteralPath $SourceCheckout -PathType Container) -or
        !(Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw 'Verified original checkout/Python path missing; nothing launched.'
    }

    & git -C $SourceCheckout fetch origin main
    if ($LASTEXITCODE -ne 0) { throw 'Fetch failed; nothing launched.' }
    $currentMain = (& git -C $SourceCheckout rev-parse refs/remotes/origin/main | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $currentMain -cne $RuntimePin) {
        throw 'Main advanced/differs: stop for delta review; do not substitute a pin.'
    }
    $actualTree = (& git -C $SourceCheckout rev-parse ($RuntimePin + '^{tree}') | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $actualTree -cne $ExpectedTree) {
        throw 'Accepted tree mismatch; nothing launched.'
    }

    $launcherText = (& git -C $SourceCheckout show ($RuntimePin + ':scripts/certification/run_quote_transport_diagnostic.ps1') | Out-String)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($launcherText)) {
        throw 'Accepted existing launcher unavailable; nothing launched.'
    }

    Write-Host 'ONE final-orders inquiry; no automatic retry.'
    Write-Host 'Normal RTH; PAPER127.0.0.1:7497; Read-Only API; unused client71; no Ross runtime.'
    Write-Host 'Retain the fresh root and the final privacy-verified ZIP, including nonzero results.'
    $launchArgs = @{
        ExpectedCommit = $RuntimePin
        DiagnosticProfile = 'final-orders'
        ExpectedTree = $ExpectedTree
    }
    & ([scriptblock]::Create($launcherText)) @launchArgs
    if ($global:LASTEXITCODE -ne 0) {
        throw 'Nonzero launcher exit: preserve all evidence; do not retry automatically.'
    }
}
```

Expected ZIP pattern:
`C:\tmp\qtransport-<8-hex>\final-orders-diagnostic-upload.zip`.
The existing launcher announces its exact absolute path only after packaging and
privacy sealing succeed. Random root is not predictable or a caller parameter.
A nonzero probe can still produce a correctly sealed diagnostic ZIP before the
launcher throws: retain it and root; never retry automatically. Failed privacy/
sealing or unverified process exit means no trustworthy announced shareable ZIP.

Information gain is bounded: new records can distinguish audit-finalization
entry, same-proxy close entry/return/failure and wrapper-level receive ordering,
plus safe OS categories. They cannot establish kernel syscall/broker causality;
concurrent close/receive and all causal assessments may remain UNKNOWN. A full
socket send remains local acceptance only, never broker acknowledgement. ANY
non-timeout receive error still invalidates coverage under the unchanged
predicate; do not expect/promise exit0. A nonzero diagnostic exit can coexist
with end-confirmed query_completed=true/count0. Read audit and transport outcomes
separately. Missing end is UNKNOWN, never zero orders. Historical missing callback
and archived OSError are not explained or retroactively corrected.

Archived successful count0 audit AND transport FAIL/exit1 remain preserved.
Zero orders never establishes zero positions. Five unmatched positions/global
ownership veto, GUI draft, separate cache uncertainty, PR1140-1143 semantics and
PARKED/fail-closed listing provenance remain unchanged. No block, preflight,
broker inquiry, observation, holdings action or trading was executed here.

ONE next action: user reviews this pinned block and starts that SINGLE inquiry
when all actual conditions hold. No retry or follow-on inquiry is authorized by
its result. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## 29 October 2026 — Latest final-order receipt and bounded coverage decision

Offline reconciliation of root `C:\tmp\qtransport-475cc611`; supplied ZIP SHA256
`076131123d63156c20bf8f4957d940e5730d98f177254ddd9c5905c43df6003e` verified.
Current GitHub main remains `a501c88bcc926bef87875f6352f210b19b6e438b`, tree
`e66b6daa84f04ec95dce1155fde2a9a4e156cf14`; PR1144 is merged at that commit.
This documentation descends from saved update1ec652debcb71d41b92edef8158f5a02fe80ef07
and carries it forward completely, including all earlier receipts and the
qtransport-2ad3bad8 count0/FAIL receipt. Original checkout/roots/saved branches
remain untouched. Applicable AGENTS search found none; DEPRECATION_LEDGER read
and unchanged because no owner/module is retired or replaced. No attachment
instructions or archived operator script were executed.

### Direct archive verification

- All2686 source manifest entries are unchanged before/after and match the exact
  accepted Git tree:33 raw blob matches,2653 Windows CRLF checkout matches.
  Archived operator.py matches accepted code after newline normalization AND its
  unmodified hash matches result.json. All six archived SDK source hashes match
  pinned9.81.1.post1 source. This is filesystem/source verification, not acquisition.
- final-order-audit.json reports query_completed/end_received=true,
  open_orders_count=0, elapsed0.10214289976283908s, unchanged10s limit, connection
  and callback loop alive before/after wait, disconnected=true, no audit error
  or observer cleanup failure. Count is an end-confirmed open-order snapshot,
  not continuous inventory and never a position snapshot.
- Exactly one query method/serialization/socket call; ID16/version1,9bytes fully
  sent, no short send/send exception. All ORDER_END frame/put/get/decode/decoded
  counts are1; native end entry/return are1. Decoder entry/return totals11/11;
  queue put/get10/10; frames11. Full send is local acceptance only, not broker
  acknowledgement or invented request-token correlation.
- End callback record0.172936s and end decoder return0.172978s precede audit
  finalization0.173228s (sequence7). Receive entered6; same-proxy close entry8
  occurred on the audit-finalization thread; receive failure9 recorded both
  errno/winerror10038 and OVERLAPS_CLOSE; close return10 followed. Causality is
  explicitly UNKNOWN. These are wrapper observations, not kernel causal proof.
- Reader/loop start/exit each1; close entry/return1, close failures0. Reader exit
  at0.173872s, loop exit0.374467s; hooks restored and both stopped. Mutation counts
  place/modify/cancel all0; source/operator PASS; initial/final inventories
  completed and empty; probe did not time out; scanner_attempted=false.
- Privacy probe/package/seal passed; independent existing sanitizer scan of ALL
  20 extracted ZIP members passed with0occurrences.29 records, maximum encoded
  record2055bytes, within64x4096 limits. records_dropped/oversize/hook/schema/
  unknown-message/decoder/reader-abnormal/queue failures are0. Background42 and
  repeated-detail1 omissions are explicit policy-limited detail, not hidden drops.
  Query-window error counters are not a claim of no global/startup broker messages.
- The SOLE nonzero coverage-invalidating counter is recv_exceptions=1.
  coverage_verified/absence_claims_valid=false, transport_evidence_incomplete=true;
  result/outer-status preserve overall FAIL/probe exit1/final exit1. No archive is
  rewritten, no exit0 inferred and no earlier failure is retroactively explained.

Receipt-specific offline assertions and source/privacy verification are saved at
/workspace/scratch/final-order-coverage-decision/receipt-verification.json.
They are not CI, runtime reruns or newly certified production behavior.

### Explicit three-boundary contract (existing owners, no relaxed gate)

| Boundary | Authority, pass evidence and honest failure meaning |
| --- | --- |
| Query delivery/completion through authoritative acceptance | final_broker_audit153-195 owns fresh client/event reset, sole dispatch,10s wait, native end and live connection/callback-loop checks. query_completed/count are its snapshot authority. Diagnostic method/send/frame/queue/decoder/native callback RETURN facts are separate corroboration. A full send or end-entry alone never suffices. Missing end, inactive transport at acceptance, dispatch failure or stale-instance completion stays unavailable. Missing/failed decoder or callback return cannot certify a complete query trace even if a native event was set. |
| Post-completion transport observations | Preserve EVERY receive/error/schema/queue/reader/capture counter and its available ordering. In this receipt there is a complete positive end chain before finalization and then an unresolved receive error during close. Do not call it harmless, assign syscall causality or certify uninterrupted transport. Current whole-lifecycle coverage predicate still fails on that error; transport absence claims remain invalid. A query-success fact is not an exemption for later failures. |
| Owned cleanup and final safety | Disconnect, both reader/loop stops, hook restoration, verified process exit/inventory, zero mutations, source/operator equality and privacy sealing each require their own evidence. Close failure, leak, restoration failure, missing inventory or unsafe mutation/equality/privacy evidence fails the relevant safety/terminal/package gate even when the query completed. This receipt confirms the bounded probe's cleanup/safety facts, not natural-runtime terminal acceptance. |

No new runtime query_coverage_verified boolean is fabricated from the archive or
added to production. Positive end/return facts are not transport-absence claims.
In particular absence_claims_valid=false is NOT an assertion that the native
end-confirmed zero-order snapshot is unavailable; its scope is transport negative
inference, not holdings or inventory authority.

Source assessment: TransportDiagnostic.snapshot655-689 intentionally covers the
WHOLE observed lifecycle through restoration/reader cleanup. PR1144 explicitly
preserved its all-non-timeout-receive-error precondition; caller
quote_transport_diagnostic.py280-288/338-361 preserves audit result separately and
sets overall failure on invalid transport coverage. It does combine domains for
a conservative DIAGNOSTIC overall result; it does NOT erase query_completed/count.
That is the reviewed contract, not a demonstrated implementation defect. A claim
that post-end10038 is harmless, or changing the lifecycle predicate to exclude it,
would be a further policy change unsupported by syscall causality. No such
correction is justified or needed to interpret this successful audit honestly.
No production/test/launcher changes or added instrumentation are made.

### Adversarial assessment and carried-forward proof

| Case | Required disposition under the separated contract |
| --- | --- |
| Independent receive failure before end | Query unavailable without authoritative end/live acceptance; all error evidence retained; transport gate fails. Never infer0 from partial/empty data. |
| Error after end signal but before accepted live-after-wait check | End signal alone does not authorize completion; failed live check rejects query. Do not classify by end timing. |
| Independent receive loss after accepted complete end/returns | Preserve the historical query snapshot fact, retain unexpected post-completion failure/UNKNOWN cause and FAIL whole-lifecycle transport. It does not become harmless or authority for selection/execution. |
| Incomplete decoder/native callback return or handler error | Do not certify complete positive query trace from entry/event alone; current exception/hook/schema failures invalidate transport. An ambiguous cut point cannot be repaired by deleting later counters. |
| Close failure, reader leak, failed hook restoration | Query fact does not rescue cleanup. Actual audit disconnect errors leave disconnected=false; observer cleanup failure/reader non-stop invalidates diagnostic coverage; terminal safety requires its own successful cleanup/process proof. |
| Lost/oversize records, observation failure or unplaceable events | Absence/coverage invalid, including loss only discovered during finalization. Do not assume all missing evidence was after end; preserve explicit counters/unknowns. |
| Late/stale end or order event | Old instance cannot complete the fresh audit; pre-dispatch event is cleared. Events after the snapshot cannot create reusable authority or a continuous zero-orders claim; contradictory/unplaceable evidence remains incomplete. |

Relevant guarded source controls ALREADY passed at reviewed PR1144 head/CI40929046617
and are carried forward, not rerun for status: tests/test_final_order_audit_completion.py
completed/partial/no-end/error/inactive/late-instance/observer-failure/stop cases;
tests/test_quote_sdk_transport_probe.py independent-before/after-end and owned/
concurrent-close controls, decoder/handler and dispatch gaps, reader join failure,
restoration retry, saturation, instance isolation and quote defaults. All95 focused
controls passed locally/independently and on Windows; Linux3618/3skip and
Windows3620/1skip receipts remain on PR1144. Windows closed-socket10038 proves
that specific local error behavior, not causality of either archived receive error.
No failing-before production defect is claimed; no new repair PR, repair review
or changed-head production CI is warranted for this documentation decision.

### Natural Ross critical path — stop the transport-diagnostic loop

The EXISTING natural supervisor calls final_broker_audit() WITHOUT an observer
(pr1090_terminal_observation_supervisor.py383-385). Existing
src/ibkr/shutdown_evidence.py285-291 requires query_completed AND disconnected;
its validate_terminal/finalize_report also enforce ordered hooks, process identity/
exit/inventory, mutation checks and artifact/privacy proof. natural_readonly_operator.py
validates that terminal receipt separately. It does NOT require a final-orders
TransportDiagnostic exit0 or erase its safety gates because this standalone query
completed. Therefore no coverage-policy change or additional targeted inquiry is
needed as a prerequisite merely to PREPARE natural validation. Every future
natural observation must still produce its OWN authoritative final audit and ALL
terminal safety evidence; this receipt cannot be transplanted into it.

ONE next action: prepare ONE900-second natural Ross READ_ONLY observation for
user review at literal accepted a501c88bcc926bef87875f6352f210b19b6e438b/tree
e66b6daa84f04ec95dce1155fde2a9a4e156cf14 with EXISTING
scripts/certification/run_natural_readonly_observation.ps1 (RuntimeSeconds900,
existing1260s supervisor), preserving all normal-session, natural-selection,
freshness, acquisition budgets, ownership/mutation/equality/shutdown/privacy
bounds. Do NOT execute it in this task. Defined information gain: first saved
joint natural validation at this pin of PR1140 end-confirmed history/attempt-local
deduplication, PR1141 initialized authoritative position truth and repaired final
audit lifecycle after a real bounded Ross session. This is not an unchanged run
solely hoping for a catalyst. Review terminal safety, real scans/Watchlist,
actual news coverage, canonical qualification and downstream formation separately.
If a natural supported opportunity occurs, raw intent plus
POSITION_TRUTH_BLOCK_NEW_ENTRIES may prove formation; five unmatched positions
must still block canonical/risk new-entry admission. Positive risk admission,
execution and PAPER readiness are NOT certified. No opportunity remains negative
evidence, never authority for automatic retry. No additional diagnostic inquiry,
source expansion or forced progression is proposed.

Archived count0/FAIL receipts, historical callback cause, separate unclassified
cache failure, five positions/global ownership veto, GUI draft, PR1140-1143
semantics and PARKED/fail-closed listing provenance remain preserved. No broker
inquiry, acquisition, preflight, observation, runtime rerun, holdings action,
SDK change, timeout extension, gate relaxation or trading occurred.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## 29 October 2026 — One natural READ_ONLY observation prepared for 30 October

PREPARATION ONLY: no helper, preflight, broker inquiry, acquisition or observation
was executed. Main verified unchanged at literal accepted
`a501c88bcc926bef87875f6352f210b19b6e438b`, tree
`e66b6daa84f04ec95dce1155fde2a9a4e156cf14`; PR1144 integration verified. This
checkpoint descends from BOTH saved1ec652debcb71d41b92edef8158f5a02fe80ef07 and
6b8ecdbe9ed57e77d3d6fcf4a3d38070cdaed706. Their complete receipts/coverage
decision and every historical root/outcome remain preserved. AGENTS search found
none applicable; DEPRECATION_LEDGER read/unchanged. Original checkout/GUI draft
and saved branches remain untouched. Documentation-only preparation is not merged
and DOES NOT change the runtime pin. No completed suite or CI repeated.

### Date, session and bounded time allowance

At preparation the verified UTC/London clock was29October19:25:29 (rechecked
19:27:14). Normal29October RTH ends20:00London. The full conservative child
allowance is90s preflight +1260s observation supervisor (includes900s runtime and
existing shutdown allowance) +90s package +90s seal, plus four30s owned-stop
allowances and up to four10s pipe-drain allowances:1690s/28m10s, before operator
review/preparation/network/filesystem slack. Remaining time is too tight for a
reliable reviewed preparation with margin; this is NOT a claim that the current
session gate itself has closed. Choose the NEXT eligible weekday instead.

Intended date: FRIDAY30October2026. Accepted get_current_market_session uses
America/New_York local09:30 <= clock <16:00 on weekdays, with configured holiday/
early-close handling. Accepted default holiday/half-day sets are empty;30October
is a Friday. New York remains EDT and London is GMT on this date, giving NORMAL
permitted window13:30 <= Europe/London <20:00. No calendar/session override.
Actual preflight remains authoritative; clock alone proves neither eligibility
nor broker/environment/ownership safety.

The prepared block is date-specific and further restricts STARTS to30October
13:30–19:20London, checked BEFORE preparation and AGAIN immediately before the
runner. At the latest permitted start40minutes remain, exceeding1690s child
allowance by11m50s. This is conservative operator scheduling only; runtime gates,
deadlines and budgets are unchanged. The block does not wait, loop or retry.
Wrong date/time or main advancement stops for review; never silently change pin
or date. If a prepared root is left after a stop, retain it, never reuse/delete it.

### Actual accepted helper/runner and mandatory protections

Preparation helper: docs/ross/PR1108_NATURAL_READONLY_ACCEPTANCE.ps1.
Actual parameters: ExpectedCommit, Python, SourceCheckout, BaseDirectory,
RuntimeSeconds. It checks Python3.13.3, local commit and space, creates a fresh
C:\tmp\ro-<8hex>\s detached worktree, preserves old roots/original checkout, and
prints a later runner command; it DOES NOT execute preflight/observation.
The block loads this helper from the accepted Git blob and invokes it ONCE.

Runner: scripts/certification/run_natural_readonly_observation.ps1.
Actual parameters ONLY Python, Root, ExpectedCommit, RuntimeSeconds. The block
passes900; existing supervisor budget is900+360=1260s. It invokes the runner ONCE;
DO NOT additionally execute the helper's printed command. No ExpectedTree runner
parameter is invented: block verifies literal tree before and after preparation,
prepared HEAD/cleanliness and fresh worktree identity before launch.

Use Windows PowerShell5.1 Desktop, existing
C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe (Python3.13.3, pinnedSDK and
repository dependencies), PAPER TWS normally authenticated at127.0.0.1:7497 with
Read-Only API enabled, UNUSED client71, normal scanner/market-data subscriptions,
no running Ross runtime and all existing session/environment/inventory guards.
The existing harness isolates caches/state, privately copies original order-ID
state, preserves source/operator equality, READ_ONLY mutation auditing, genuine
fresh timeframe inputs, normal TopN50/Watchlist15/Focus5 limits and mandatory
canonical catalyst. Existing production news/source profile, total/tier/request
budgets and freshness rules unchanged. No forced candidates/news/patterns/setups/
triggers/intents/approvals. Preserve all five positions and their ownership veto.

Owned graceful stop, final independent authoritative audit/disconnect, runtime
identity/OS exits, empty final runtime inventory, zero mutations, equality and
privacy/sealing remain mandatory. The natural harness uses its OWN default audit,
not TransportDiagnostic; no further final-order diagnostic/instrumentation is
needed. Standalone count0 audit AND transport FAIL/exit1 remain historical facts,
not substitutes for the future observation's own terminal proof.

### ONE complete operator block — prepared only, NOT executed here

```powershell
# ONE user-started observation on Friday30October2026; no automatic retry.
& {
    $ErrorActionPreference = 'Stop'
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or
        $PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSVersion.Minor -ne 1) {
        throw 'Use Windows PowerShell5.1 Desktop.'
    }
    $LondonZone = [TimeZoneInfo]::FindSystemTimeZoneById('GMT Standard Time')
    $EarliestStart = [datetime]::new(2026,10,30,13,30,0)
    $LatestStart = [datetime]::new(2026,10,30,19,20,0)
    $LondonNow = [TimeZoneInfo]::ConvertTimeFromUtc([datetime]::UtcNow, $LondonZone)
    if ($LondonNow -lt $EarliestStart -or $LondonNow -gt $LatestStart) {
        throw 'Prepared for30October2026,13:30-19:20 London only; nothing launched.'
    }

    $SourceCheckout = 'C:\Users\nelzo\PycharmProjectsDec2025\ibkr-trading-system'
    $Python = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
    $RuntimePin = 'a501c88bcc926bef87875f6352f210b19b6e438b'
    $ExpectedTree = 'e66b6daa84f04ec95dce1155fde2a9a4e156cf14'
    if (!(Test-Path -LiteralPath $SourceCheckout -PathType Container) -or
        !(Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw 'Verified checkout/Python path missing; nothing launched.'
    }
    & git -C $SourceCheckout fetch origin main
    if ($LASTEXITCODE -ne 0) { throw 'Fetch failed; nothing launched.' }
    $fetchedMain = (& git -C $SourceCheckout rev-parse refs/remotes/origin/main | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $fetchedMain -cne $RuntimePin) {
        throw 'Main differs: stop for delta review; do not substitute a pin.'
    }
    $pinTree = (& git -C $SourceCheckout rev-parse ($RuntimePin + '^{tree}') | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $pinTree -cne $ExpectedTree) {
        throw 'Accepted tree mismatch; nothing launched.'
    }

    $beforeWorktrees = @(& git -C $SourceCheckout worktree list --porcelain)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inventory existing worktrees.' }
    $prepareText = (& git -C $SourceCheckout show ($RuntimePin + ':docs/ross/PR1108_NATURAL_READONLY_ACCEPTANCE.ps1') | Out-String)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($prepareText)) {
        throw 'Pinned preparation helper unavailable.'
    }
    $prepareArgs = @{
        ExpectedCommit = $RuntimePin
        Python = $Python
        SourceCheckout = $SourceCheckout
        BaseDirectory = 'C:\tmp'
        RuntimeSeconds = 900
    }
    & ([scriptblock]::Create($prepareText)) @prepareArgs

    $afterWorktrees = @(& git -C $SourceCheckout worktree list --porcelain)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot verify prepared worktree; preserve roots.' }
    $addedWorktrees = @($afterWorktrees | Where-Object {
        $_.StartsWith('worktree ') -and $beforeWorktrees -notcontains $_
    } | ForEach-Object { $_.Substring(9) })
    if ($addedWorktrees.Count -ne 1) {
        throw 'Expected exactly one new worktree; preserve roots and inspect.'
    }
    $checkout = [IO.Path]::GetFullPath($addedWorktrees[0])
    if ($checkout -notmatch '^C:\\tmp\\ro-[0-9a-f]{8}\\s$') {
        throw 'Unexpected prepared path; preserve it without launching.'
    }
    $root = Split-Path -Parent $checkout
    $actualHead = (& git -C $checkout rev-parse HEAD | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $actualHead -cne $RuntimePin) { throw 'Prepared head mismatch.' }
    $actualTree = (& git -C $checkout rev-parse 'HEAD^{tree}' | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $actualTree -cne $ExpectedTree) { throw 'Prepared tree mismatch.' }
    $dirty = @(& git -C $checkout status --porcelain)
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -ne 0) { throw 'Prepared checkout is not clean.' }
    $runner = Join-Path $checkout 'scripts\certification\run_natural_readonly_observation.ps1'
    if (!(Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Existing runner missing.' }

    $LondonNow = [TimeZoneInfo]::ConvertTimeFromUtc([datetime]::UtcNow, $LondonZone)
    if ($LondonNow -lt $EarliestStart -or $LondonNow -gt $LatestStart) {
        throw 'Start window expired; retain the prepared root. No preflight launched.'
    }
    Write-Host "Runtime pin: $RuntimePin; retained root: $root"
    Write-Host 'PAPER127.0.0.1:7497; Read-Only API; unused client71; no Ross runtime.'
    Write-Host 'This invokes ONCE. Do not also run the preparation helper printed command.'
    Write-Host 'Use only the final DIAGNOSTIC ZIP announcement after successful privacy sealing.'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner -Python $Python -Root $root -ExpectedCommit $RuntimePin -RuntimeSeconds 900
    $operatorExit = $LASTEXITCODE
    Write-Host "Operator exit: $operatorExit. Preserve all evidence; no automatic retry."
    $global:LASTEXITCODE = $operatorExit
}
```

Expected final sealed ZIP pattern:
C:\tmp\ro-<8hex>\ross-natural-readonly-upload.zip.
The helper's fresh root determines the absolute path. Share only the final
DIAGNOSTIC ZIP announcement after successful sealing; raw state/root files stay
private. Nonzero/preflight-rejected/partial receipts must be retained; packaging
success alone never means observation success. Missing/failed seal means no
verified shareable archive, even if a ZIP exists. No retry is implied by any exit.

Review all five existing acceptance outcomes separately: terminal safety; genuine
scans/Watchlist continuity; actual news requests/coverage; canonical catalyst
qualification; Focus/setup/trigger/raw intent and decision/risk outcomes. Natural
supported raw intent followed by POSITION_TRUTH_BLOCK_NEW_ENTRIES can prove
formation. Five unmatched positions globally veto new-entry admission AFTER
formation and BEFORE canonical artifact/risk admission, so zero downstream risk
input is expected. No qualifying opportunity means no positive formation proof,
not permission to rerun. This cannot certify positive risk admission, execution
or PAPER readiness. Historical callback causes, archived OSError causality and
separate cache failure remain unresolved; listing provenance stays PARKED/fail
closed. No holdings adoption/liquidation/cancellation or suppression is allowed.

Proportional checks only: exact main/tree/helper/runner source inspection, literal
parameter/scheduling/budget review, source equality/whitespace and deterministic
timezone conversion. No helper, preflight, broker inquiry, acquisition, observation,
SDK operation or completed suite executed. GUI draft/holdings/all receipts intact.

ONE pending action: user starts this SINGLE prepared observation on30October
within13:30–19:20London when all ACTUAL prerequisites hold. Do not execute now,
automatically retry, silently change date/pin or infer readiness from its result.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
