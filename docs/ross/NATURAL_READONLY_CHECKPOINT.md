# Natural READ_ONLY diagnostic checkpoint — 15 October 2026

Accepted baseline: `1b632f8131183a776a6532d2785644a8a0309efb` (PR1107).
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
