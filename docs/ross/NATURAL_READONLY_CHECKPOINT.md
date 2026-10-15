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
