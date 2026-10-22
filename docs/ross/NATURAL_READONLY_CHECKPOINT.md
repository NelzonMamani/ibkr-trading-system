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

### Receipt9 — current Ross checklist after offline catalyst investigation

Accepted `be5cc0090c067a965f8a1398f631d2d984e4fc6a`; archive
SHA256 `eefa84ae5d17280b27651afc670c9dc2bd01152bc2266b108c8ade3bf30f1940`.
See [the symbol trace and offline replay findings](RECEIPT9_CATALYST_FINDINGS.md).
This current checklist supplements the historical checklists above; receipt7 FAIL,
receipt8 FAIL and earlier receipts retain their original provenance and status.

| Ross completion outcome | Current receipt9 evidence / remaining work |
| --- | --- |
| Terminal shutdown, completed independent audit, inventory, zero mutations |PASS preserved and independently revalidated offline; query end received, both mutation counter sets zero, final inventory empty.|
| Source and operator order state |PASS preserved; complete source-before/source-after equality; order-state comparison unchanged.|
| Natural broker discovery / Watchlist |3 confirmed50-row matching-end scans; Watchlists5/4/4; no teaching injection, seeding or backfill.|
| Independent background acquisition and serialized publication |Natural evidence arrival established: first evidence5.5736879s; completed161/failed5;161 persisted publications including21 nonempty publication events; cleanup complete. Partial provider coverage remains open.|
| Whole-Watchlist reconsideration through Core between scans |Natural58 canonical reassessments with no failure; positive0/Focus0. Offline real-Core replay confirms later evidence is read without rediscovery or HTTP; existing positive-path/strict-gate tests pass.|
| Canonical catalyst qualification |NOT ESTABLISHED naturally. PFSA2/NCPL1 retained commentary articles are nonqualifying; other requested symbols retain0.13 logged Focus evaluations drop at mandatory catalyst gate.|
| Coverage / attribution gaps |403/401/timeouts, stale/empty issuer feeds and deferred extended tier remain partial coverage. CLIK's fresh rejected text was not captured, so correctness of that specific relevance exclusion remains unresolved. No proven implementation repair from this receipt.|
| Downstream setup / trigger / intent progression |NOT ESTABLISHED; no forced Focus, synthetic natural-success claim or trading.|
| Undefined lifecycle policy |Correction/retraction and financing-risk expiry remain undefined; retained dilution veto unchanged.|
| Holdings, ownership blockers and GUI draft |Preserved unchanged. PAPER_READY=NO.|

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
