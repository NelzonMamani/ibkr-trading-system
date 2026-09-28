# W03 standalone news lookup

The supported command is `scripts/verify_news_discovery.py`. It accepts one ticker or a batch and calls `CanonicalNewsIntelligenceService.get_news` once with `NewsCandidate` objects. `src/news/standalone_lookup.py` builds an explicit research request and formats the result; the canonical service, evidence store and batch RSS adapter retain retrieval/cache ownership. The command does not need market hours, an IBKR contract or a broker connection.

Baseline: merged W02 / PR1094, `a3ece50407869a203e93fee83064d9eb90daf29d`. Implementation branch: `codex/w03-news-lookup`. The established interpreter is `C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe`. Final source identity and gate evidence are recorded below.

## PowerShell commands

These examples target the isolated worktree and use a dedicated diagnostic cache. They are usage examples, not a claim that the named tickers have discoverable articles.

```powershell
$newsPython = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
$newsRepo = 'C:\Users\nelzo\.codex\worktrees\w01-consolidation\ibkr-trading-system'
Set-Location -LiteralPath $newsRepo

# One ticker, with issuer identity and an explicit network refresh.
& $newsPython .\scripts\verify_news_discovery.py IRON --company-name 'Disc Medicine, Inc.' --alias 'Disc Medicine' --lookback-hours 24 --source-groups FAST_TRADING PREP_EXTENDED --cache-mode refresh --cache-file .\output\w03\examples\news_cache.json --json-output .\output\w03\examples\iron.json

# A list of tickers; JSON is the only document written to stdout.
& $newsPython .\scripts\verify_news_discovery.py IRON KNRX LFCR --lookback-hours 24 --source-groups FAST_TRADING PREP_EXTENDED --cache-mode use --cache-file .\output\w03\examples\news_cache.json --format json --json-output .\output\w03\examples\batch.json

# Reuse the same single-symbol identity/settings without any network retrieval.
& $newsPython .\scripts\verify_news_discovery.py IRON --company-name 'Disc Medicine, Inc.' --alias 'Disc Medicine' --lookback-hours 24 --source-groups FAST_TRADING PREP_EXTENDED --cache-mode only --cache-file .\output\w03\examples\news_cache.json --format json
```

Tickers can also be comma-separated. At least one nonempty ticker is required, and a batch is limited to 50 distinct symbols. Symbols are uppercased and deduplicated. Duplicate richer identities fill missing fields and retain aliases/metadata. `--company-name` and repeatable `--alias` are single-symbol conveniences; use a candidate file for a batch with issuer identities. Ordinary ticker words remain subject to the canonical issuer matcher.

For complete identities, save this JSON as `output/w03/examples/candidates.json`. This example shows every `NewsCandidate` field; null market fields are optional context, and `issuer_id` is illustrative user-supplied metadata, not a verified identifier.

```json
{
  "candidates": [
    {
      "symbol": "IRON",
      "company_name": "Disc Medicine, Inc.",
      "aliases": ["Disc Medicine"],
      "exchange": "NASDAQ",
      "market": "US",
      "region": "US",
      "priority_rank": null,
      "session": null,
      "price": null,
      "gap_pct": null,
      "percentage_move": null,
      "float_shares": null,
      "absolute_share_volume": null,
      "relative_volume_rvol": null,
      "metadata": {"issuer_id": "user-supplied-id"}
    },
    {"symbol": "LFCR", "company_name": "Lifecore Biomedical, Inc.", "aliases": ["Lifecore Biomedical"]}
  ]
}
```

```powershell
& $newsPython .\scripts\verify_news_discovery.py --candidates-file .\output\w03\examples\candidates.json --lookback-hours 24 --cache-mode refresh --cache-file .\output\w03\examples\identity_cache.json --json-output .\output\w03\examples\identity_batch.json
```

The file may instead contain a plain list of candidate objects or ticker strings. Unknown candidate keys are rejected; additional issuer attributes belong in `metadata`. `--json-output` must differ from cache, preparation and candidate input paths. Canonical diagnostic messages go to stderr, preserving machine-readable stdout with `--format json`.

## Research defaults and limits

| Setting | Default | Accepted range / behavior |
|---|---:|---|
| `--lookback-hours` | 24 | Greater than 0, at most 720 hours |
| `--budget-seconds` | 30 | Greater than 0, at most 120 seconds |
| `--request-timeout-seconds` | 5 | Greater than 0, at most 15 seconds; clamped to remaining retrieval allocation |
| `--cleanup-seconds` | 10 | 0–30 seconds |
| `--refresh-interval-seconds` | 300 | 0–86400 seconds; acquisition reuse cadence |
| `--max-items` | 20 | 1–100 evidence items per symbol |
| `--source-groups` | `FAST_TRADING PREP_EXTENDED` | Either or both; comma-separated values also accepted |
| `--cache-mode` | `use` | `use`, `refresh`, `only`, `off` |
| `--cache-file` | `<repository>/output/news_lookup/news_cache.json` | Canonical evidence-store format in a diagnostic location |
| `--prep-file` | None | Optional explicit preparation artifact; operational prep is not read by default |
| `--format` | `human` | `human` or `json`; `--json-output` can accompany either |

All numeric settings must be finite. The research profile is `standalone_research_v1`, with both request lookback and evidence freshness set to the requested window. An appropriately dated 18-hour-old article can therefore appear in a 24-hour query. Display filtering also excludes cached evidence outside the requested window, future publication timestamps, and missing/naive timestamps. Publication time and article identity remain unchanged on cache reuse; age increases with time.

Live scanner budgets, preparation defaults, Ross freshness, mandatory catalyst qualification and source membership/order remain unchanged. The 30-second research budget is not a new trading budget. RSS feeds are rolling lists; a longer lookback filters available entries and does not turn a feed into an archive.

## Sources and batch retrieval

The command exposes the two existing adapter-supported groups: eight `FAST_TRADING` URLs and thirteen `PREP_EXTENDED` URLs. Their authority remains `src/news/source_groups.py`; URLs and membership/order are unchanged. Unsupported groups are rejected instead of silently producing an empty selection. FAST precedes EXTENDED regardless of argument ordering; sources shared across tiers are deduplicated by the existing adapter.

The canonical service passes the symbols needing acquisition through the adapter's existing explicit unresolved-symbol contract. When EXTENDED is selected, its fallback uses that contract and the remaining bounded allocation. The research profile uses the existing 0.35 reserve fraction. The same source response is fetched/parsed once and matched against the batch, including a batch of one. No preparation FAST-only wrapper limits the research request.

## Cache and provenance

| Mode | Read cache | Write cache | Network behavior |
|---|---|---|---|
| `use` | Yes | Yes | Refresh missing, incompatible or cadence-due acquisitions |
| `refresh` | Yes | Yes | Explicitly refresh requested symbols; retained prior evidence remains identifiable |
| `only` | Yes | No | Never retrieve; incompatible or missing acquisition coverage is unknown |
| `off` | No | No | Retrieve without canonical cache reads/writes |

The research request opts into an acquisition profile recorded per symbol. It covers issuer identity, the requested window/freshness, evidence limit and objective request options, selected groups and ordered URLs, and retrieval settings including budgets/timeouts. A changed profile cannot silently count a prior acquisition as complete coverage. Legacy records without this profile may supply revalidated evidence but do not prove compatible research coverage. The profile check is opt-in; accepted scanner/preparation cadence is preserved.

An optional explicit prep file can contribute revalidated evidence. It has no independent retrieval or cache authority and, by itself, does not prove source coverage. The existing `NewsProvider.get_news` and `get_news_batch` preparation APIs retain their result shapes and string inputs; they also preserve supplied `NewsCandidate` identity. `scripts/verify_news_provider_batch.py` delegates to the supported CLI and accepts the same arguments. Both commands now require input rather than choosing a fixed demonstration batch.

Each symbol reports coverage separately from evidence: `complete`, `partial`, `unavailable` or `unknown`. `completed_no_match` requires complete selected-source coverage; an empty partial/unavailable query is not reported as completed no-match. A symbol can have an article while retrieval is partial or unavailable.

Symbol provenance `provider_refresh` describes an acquisition attempt. Article `acquisition_origin=current_retrieval` requires that article's ID in the current provider result; `cache_or_prep` identifies retained evidence, and `unknown` remains explicit when provenance cannot be established. Counts distinguish current retrieval and reused articles. An empty or failed refresh does not relabel an older cached article as a new discovery. Offline replay through an injected provider is still replay: the field describes the call's origin, not independent proof that a live network discovery occurred.

## Timing, deadlines and cleanup

Per-source output preserves attempted/skipped status, retrieval failure, observed HTTP timeout and budget exhaustion separately. W02 completion rules remain authoritative: results completed before their applicable deadline are retained; late results are excluded even if the worker subsequently finishes during cleanup. Cancelling a future does not guarantee that an active HTTP request stops.

The optional lifecycle observer records request and parser elapsed time where the native HTTP path measures them, plus HTTP status, feed entry count and response closure. Request timing covers the HTTP call; parser timing covers feed parsing. They need not sum to the full source duration. Injected transports and unmeasured phases remain null. Requests' scalar timeout bounds connection/read waits, not the entire request-plus-parse wall duration.

The helper reports service/retrieval/total elapsed time and waits up to the cleanup allowance for its owned workers. Cleanup observations are separate from the immutable retrieval result. `cleanup_complete=true` means observed futures/workers ended with no observed response-close failure; an injected service without a lifecycle observer reports unknown cleanup. Worker completion and source retrieval success are separate facts.

The CLI supervises a private worker process. Its wait limit is 10 seconds of startup allowance plus the retrieval budget plus cleanup allowance: 50 seconds with defaults. If that limit expires, it terminates its owned process, waits up to 5 seconds, then kills and waits up to another 5 seconds if needed. These are separate shutdown allowances, not extra retrieval time. The result records actual process exit, termination and elapsed time. A forced termination returns failure and `cleanup_complete=false`, while retaining any already-written bounded retrieval result. Direct Python use of `lookup_news` does not acquire this CLI process boundary.

Successful command execution returns exit code 0 even when provider coverage is partial or unavailable; callers must inspect the per-symbol outcomes. Input errors return 2. Worker errors or supervisor deadline termination return 1. JSON includes the current Git head/dirty state, interpreter/dependency versions and hashes of the news modules/entrypoints, with a before/after source-hash check.

## Acceptance evidence

The live capture used the dirty W03 implementation on base `a3ece50407869a203e93fee83064d9eb90daf29d`, with Python 3.13.3, requests 2.34.2 and feedparser 6.0.14 from the interpreter above. [live_source_hashes.json](../../artifacts/w03/live_source_hashes.json) records the actual complete Python snapshot (SHA-256 `12c052543ba2436c75393c475afab59e5e56f821d6510a70a323b3aefb4366ff`); it was unchanged through retrieval and cleanup. The supported cached CLI independently recorded news-module/entrypoint hashes and an unchanged-source check. Final test hashes and any later review changes are recorded separately; the base commit alone is not claimed to identify dirty capture code.

Production changes are the supported command and its compatibility delegate, new `src/news/standalone_lookup.py` and `src/news/rss_lifecycle.py`, and narrow changes to `news_fetcher.py`, `batch_rss_adapter.py`, `news_intelligence_contract.py`, `news_intelligence_service.py` and `prep_adapter.py`. Three `tests/test_w03_*.py` modules cover the added contract. `scripts/diagnostics/w03_news_acceptance.py` supplies the one-shot capture wrapper. This report and `artifacts/w03/` contain commands and acceptance evidence; [changed_files.txt](../../artifacts/w03/changed_files.txt) gives the exact versioned list.

The one provider-only session ran **2026-09-28 22:08:10.670760Z to 22:10:44.211693Z**, **153.541 seconds** within the 600-second limit. It comprised publisher verification, one live canonical batch (IRON/MSFT/LFCR), and a cache-only public single-symbol CLI call. There was no additional uncached single lookup, endpoint retry or independent health pass. The batch process exited normally after 21.407 seconds under its 90-second watchdog; canonical service elapsed was 18.000 seconds and retrieval plus cleanup 18.093 seconds. All 21 submitted requests/workers completed, zero were cancelled, zero remained alive, all observed responses closed, and cleanup was complete. No broker modules loaded. Exact settings and identity are embedded in [live_batch.json](../../artifacts/w03/live_batch.json): 24h lookback/freshness, 30s budget, 5s request timeout, 10s cleanup, 20 items, both ordered groups, explicit refresh. Cache and empty prep were restricted to `output/w03/live/`; operational paths were not used.

[Publisher verification](../../artifacts/w03/publisher_verification.json) confirms the original [Disc Medicine issuer legal notice](https://www.globenewswire.com/news-release/2026/09/28/3370223/673/en/disc-medicine-investor-news-if-you-have-suffered-losses-in-disc-medicine-inc-nasdaq-iron-you-are-encouraged-to-contact-the-rosen-law-firm-about-your-rights.html) publication at **2026-09-28T19:02:00Z**. The publisher returned HTTP 200; visible time, structured `datePublished` and publication metadata agree. The web tool could not open/index the page; direct publisher HTTP supplied the verification. This page fetch is publisher research, not service discovery. The target URL was absent from the saved configured feeds, including GlobeNewswire Finance's rolling 20 entries. It was inside the requested window; that target miss is sampled feed coverage, not age filtering or a request deadline.

**Actual W03 live discovery:** zero returned articles for the three symbols, with partial coverage. Eighteen HTTP 200 responses were recognized feeds; Reuters returned 401, France24 403 and VentureBeat 429. Every URL was attempted once, with no observed HTTP timeout, skipped source or budget exhaustion. HTTP-call duration can exceed the scalar timeout without a timeout exception. The sampled Business Insider feeds contained a fresh Microsoft-brand article, but the existing matcher deliberately requires explicit ticker notation or a company alias with at least two non-legal-suffix words. `Microsoft Corporation` reduces to one word, so this is an existing matching limitation, not missing feed content. That guard was retained to protect ordinary ticker-word rejection. LFCR had no observed accepted issuer match.

**Cached reuse:** [cached_single.json](../../artifacts/w03/cached_single.json) is the supported command querying IRON with the same complete identity/profile and `--cache-mode only`. It exited 0, attempted zero sources, retained the original acquisition and partial coverage, and reported `cached_acquisition` with compatible profile. No article was inserted to manufacture a match.

**Offline replay:** the accepted original IRON capture is replayed at publication plus 18 hours in the new interface tests. A 24-hour request returns its unchanged URL, publication time and evidence identity; warm reuse advances age by 60 seconds, and a six-hour cache-only request excludes it and reports incompatible coverage. [offline_article_example.json](../../artifacts/w03/offline_article_example.json) supplies the example output. It is neither W03 live discovery nor a qualifying Ross catalyst.

The [source matrix](../../artifacts/w03/source_evidence_matrix.csv), [detailed JSON](../../artifacts/w03/source_evidence_matrix.json), and [coverage analysis](../../artifacts/w03/live_coverage_analysis.md) record request/parse/total timing, source status, response hashes, original timestamp ranges, freshness counts and exact-target checks. Raw response bodies and publisher HTML remain locally under `output/w03/live/`.

The combined affected run passed **368 tests in 34.39s** across 23 modules, including 63 new W03 cases and the directly affected W01/W02 regressions. It blocked four connection attempts from an existing scanner test, allowing only two Windows stdlib socketpair self-pipes. Production/test sources were frozen; only the diagnostic wrapper received two integrity safeguards during that run, as recorded in [source_snapshot_comparison.json](../../artifacts/w03/source_snapshot_comparison.json). No tested production or test file changed.

The **one final local full suite passed 2,180 tests, with 1 skipped and 212 warnings, in 323.22s**. `compileall -q src` passed. The full source snapshot is identical to the live-capture snapshot, and no Python source changed during verification. [final_suite_status.json](../../artifacts/w03/final_suite_status.json) records commands, process IDs, exits, hashes and protected-file comparisons. Full-manifest SHA-256: `f6c37055b0a53269ebd3eb54e7261ed4aacaa9ad684fe9884d0f5a33cff0361f`; full-suite log SHA-256: `d74e002d5b5775e1721bf42952d7a47b94cde83b4521334a8a9206fb3cdfa76a`. The guard blocked 20 existing-test connection attempts and allowed 26 stdlib private socketpair self-pipes; no external provider/broker connection was allowed. News/prep files were unchanged. Four test-generated catalogue changes were preserved in a local patch and restored in this worktree; all six pre-existing original-checkout tracked changes retained their hashes.

Before/after logs demonstrate the added contracts and the two integration repairs: retained cache evidence no longer claims current acquisition, and a real threaded slow response close no longer hides an in-time parsed article. The latter reproduced one failure before repair; 11 lifecycle cases plus 68 affected W02 timing checks then passed. Independent peer reviews found no remaining implementation blocker.

Final-head GitHub CI, exact-head review, unresolved-thread count and controlled merge outcome are recorded in the PR and the consolidated local `output/w03/closure_report.md`. Keeping gate results there avoids moving the reviewed head solely to record its own checks. Any review repair receives affected verification and full final-head CI; the unchanged local full suite is not repeated. Exact recorded invocations are in [commands.ps1](../../artifacts/w03/commands.ps1). Staged whitespace validation then removed one trailing empty line from the standalone test file; [post_suite_formatting.json](../../artifacts/w03/post_suite_formatting.json) proves this was the only post-suite Python-byte change, with no executable change. Final-head CI covers the committed form.

**STANDALONE_CONTRACT: PASS for the verified canonical single/batch research interface. PROVIDER_COVERAGE: PARTIAL, with no W03 live issuer discovery for the sampled batch.** Completion of the interface does not guarantee historical RSS coverage. Residual decisions are whether to investigate authorized access for the three denied/rate-limited endpoints, select issuer-focused/archive coverage, and separately evaluate a conservative policy for distinctive single-word issuer names. None was changed or bypassed in W03. No natural strategy integration or paper readiness is established.

`PAPER_READY=NO`

`PAPER_READINESS_GATE=FAIL`
