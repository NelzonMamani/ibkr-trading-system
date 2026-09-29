# W04 optional historical ticker news

## Scope and preserved authority

Baseline: `630660201abb4374cf09c233d601734f8258ebef` (merged W03/PR1095). Work uses branch `codex/w04-historical-news` in the existing managed W01 worktree and the existing Python 3.13.3 interpreter at `C:/tmp/pr1091-cert-env-20260923/Scripts/python.exe`. Main had no newer changes on recovery. No baseline verification was repeated. Original checkout edits and W01/W02/W03 evidence remain preserved. No applicable AGENTS.md was found.

The supported W03 command selects one optional `MassiveNewsIntelligenceProvider` through `CanonicalNewsIntelligenceService`; canonical relevance, deduplication and evidence persistence remain authoritative. RSS remains the default. RSS source membership/order, preparation APIs, scanner settings, Ross thresholds and the five pillars remain unchanged. Price, Gap/% Change, RVOL, mandatory Catalyst/News and low Float remain distinct from absolute Volume. Historical evidence is research data and never an automatic Ross catalyst. This request expressly excludes the older architecture document's runtime/broker smoke commands.

## Provider contract

The [official news endpoint](https://massive.com/docs/rest/stocks/news) documents `GET /v2/reference/news`, a case-sensitive ticker, publication filters and cursor pagination. It currently lists Basic news history as two years and hourly updates. W04 makes separate ticker requests, freezes the UTC interval for the lookup and all pages, and enforces exact inclusive bounds locally. Explicit historical windows do not reset publication age or acquisition timestamps.

The [REST quickstart](https://massive.com/docs/rest/quickstart) supports Bearer header authentication. Credentials are private environment values, absent from lookup settings, request URLs, cache profiles and manifests. Redirects are not followed. Cursor destinations must remain HTTPS on `api.massive.com`, default port or 443, with the exact news endpoint path; embedded credentials are rejected. Raw provider error bodies and exception text are not published.

The [rate-limit documentation](https://massive.com/knowledge-base/article/what-is-the-request-limit-for-massives-restful-apis) says Basic limits depend on account subscriptions and asset-class/reference buckets; creating more keys does not increase them. W04 conservatively shares five requests per minute across all its local Massive requests and keys, including pages, using a user-level quota ledger. This ledger holds rate facts, not news data or keys. Other applications/devices cannot be observed by the local limiter and must share the account allowance operationally. No paid entitlement is assumed, and no upgrade or account creation is performed. A provider 429 remains a rate failure with a shared cooldown. Total request/page caps and the retrieval deadline bound work; partial or unattempted results never prove exhaustive coverage.

## Commands and local configuration

Run in PowerShell. The key is entered locally using a concealed prompt and inherited by the command's owned child process; it is not a CLI argument. `POLYGON_API_KEY` is accepted as a legacy fallback when `MASSIVE_API_KEY` is absent. No `.env` loader or generic config registry is added.

```powershell
$newsPython = 'C:\tmp\pr1091-cert-env-20260923\Scripts\python.exe'
$newsRepo = 'C:\Users\nelzo\.codex\worktrees\w01-consolidation\ibkr-trading-system'
Set-Location -LiteralPath $newsRepo
$env:MASSIVE_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Massive API key (local only)' -AsSecureString)).Password

# Recorded W03 24-hour interval, fixed at its batch start. No target URL is supplied.
& $newsPython .\scripts\verify_news_discovery.py IRON --company-name 'Disc Medicine, Inc.' --alias 'Disc Medicine' --provider massive --published-after '2026-09-27T22:08:37.432754Z' --published-before '2026-09-28T22:08:37.432754Z' --cache-mode refresh --budget-seconds 90 --format json

# Same adapter, small batch with complete issuer identities in a public example file.
& $newsPython .\scripts\verify_news_discovery.py --candidates-file .\artifacts\w04\example_candidates.json --provider massive --published-after '2026-09-27T22:08:37.432754Z' --published-before '2026-09-28T22:08:37.432754Z' --cache-mode use --budget-seconds 90 --format json

# Repeat the identical arguments with --cache-mode only for no-network reuse.
Remove-Item Env:\MASSIVE_API_KEY
```

The paired `--published-after` / `--published-before` timestamps require explicit timezones, normalize to UTC, span at most 720 hours, and must end no later than the current time. Their endpoints are inclusive. `--massive-page-size` accepts 1-1000, `--massive-max-pages-per-symbol` 1-10, and `--massive-max-requests` 1-50. These are caps rather than a promise that the deadline can reach them.

Defaults remain a 24-hour rolling window, 30-second total retrieval budget, five-second HTTP timeout and ten-second cleanup. Massive defaults are 100 articles per page, two pages per symbol and five total requests. The total deadline can prevent reaching configured caps. The CLI retains W03's owned-process supervision; cancellation does not assert that a running HTTP call stopped. Dedicated default cache: `output/news_lookup/news_cache.json`, still the canonical evidence-store format. Explicit prep input remains opt-in.

Provider/window and pagination/rate settings participate in acquisition compatibility. A different provider or explicit interval cannot silently reuse completed coverage from another profile. The canonical cache remains bounded to the current acquisition per symbol; selecting a historical window may evict saved same-symbol articles outside that window. It is not an unbounded archive or an independent provider cache. Warm reuse preserves original discovery facts and identifies retained evidence separately from current retrieval. Provider ticker associations and sentiment do not enter text relevance; the conservative existing single-word issuer and ordinary-word/ticker rules remain unchanged.

## Acceptance status

The local Process/User/Machine environment and established settings in both checkouts contain no configured Massive/Polygon key. No API request is authorized without that configured credential. Live-service acceptance is **PENDING — missing authorized credential**. The known W03 IRON target is therefore **NOT TESTED with Massive**, not absent from it. No genuine Massive article discovery, publisher verification, live cached reuse or latency certification is claimed. No account, subscription or key was created.

Only labelled synthetic offline fixtures are committed. No licensed live payload was acquired or published; the [individual terms](https://massive.com/legal/individuals-terms-of-service) remain relevant to later authorized use. Future live acceptance must remain one provider-only session of at most ten minutes, use the fixed interval above, preserve raw payloads privately, verify any accepted article at its original publisher and distinguish returned/accepted/rejected/cached/offline evidence. Do not seed the known target URL or cache.

Verification and final gate evidence are recorded in `artifacts/w04/` and the PR. The consolidated local `output/w04/closure_report.md` records final CI, exact-head review and merge without moving the reviewed head to describe its own checks.

`PAPER_READY=NO`

`PAPER_READINESS_GATE=FAIL`

## W04 verification record

The change adds 82 deterministic tests: 46 provider/rate/lifecycle cases, 15 canonical history/cache cases and 21 public helper/CLI cases. Fixtures are explicitly synthetic and carry no claim of live Massive coverage. The new tests cover single/list identities including metadata/aliases, exact UTC boundaries and real publication age, pagination/duplicates/caps, isolated symbol failures, shared-process quota and deadline behavior, missing keys/auth/429, provider/window profile changes, association-versus-text matching and credential redaction.

The combined affected run passed **461 tests in 28.85 seconds** across 26 modules. `compileall -q src` passed. Its complete Python source manifest remained unchanged. The reused W02 guard blocked four existing scanner-fixture connection attempts and permitted only two standard-library socketpair self-pipes; no external or broker connection occurred. Both operational news/prep files retained their prior hashes.

The actual supported CLI was captured twice without credentials: single IRON and the IRON/MSFT/LFCR identity batch. Both exited zero because they successfully reported an unavailable research outcome, not because retrieval succeeded. Every symbol reported `missing_credential`, zero pages and zero HTTP attempts. No worker threads were submitted and cleanup was complete. Command wall times were 1.240 and 2.043 seconds. Source hashes remained unchanged across both commands. Evidence: `artifacts/w04/missing_key_single.json`, `missing_key_batch.json` and `missing_key_exits.json`. Exit-zero lookup semantics are unchanged from W03; inspect outcomes.

Pre-full-suite peer review corrected provider metadata/alias preservation, strict cursor validation, HTTP-200 error-payload validation, bounded article normalization before completion, and per-page counts. The first provider test iterations also contained three fixture problems: a secret was embedded in the supposed valid article URL, a fake clock advanced before the intended worker had actually completed, and a two-token alias reduced to one word after legal-suffix stripping. These fixtures were corrected without weakening the conservative matcher or pending-worker deadline semantics. Earlier logs remain labelled as development iterations, not acceptance failures of the final implementation. The final provider affected run passed 102 tests (46 new and 56 accepted W02/W03 timing tests). Independent final review found no concrete blocker.

The shared quota ledger is `%LOCALAPPDATA%/ibkr-trading-system/massive-rate.sqlite3` on Windows, with `~/.local/state/ibkr-trading-system/massive-rate.sqlite3` as the fallback. It is shared across this OS user's worktrees and keys. Five starts within a rolling minute exhaust the allowance; failed attempts are charged. No automatic retry is enabled. A 429 records the shared cooldown, including whether persistence succeeded. This is conservative local coordination, not observation of all remote account users.

The **one local full suite passed 2,273 tests, with 1 skipped and 212 warnings, in 295.63 seconds**. Compilation passed. The complete Python source manifest was unchanged and matches the affected run (`cc636db36bb1158c63070b9895a64512ac19a944b8a90c9e6e1e6ff04dfb6075`). The guard blocked 40 existing-test connection attempts and allowed 26 standard-library socketpair self-pipes. Four generated catalogue edits were preserved as a local patch and restored.

The full-suite audit detected an existing consumer test writing empty failed acquisitions to the managed news cache. The generated cache was preserved, and the original 421 bytes were recovered and restored only after matching their preflight/W02/W03 SHA-256 exactly (`adb8e35abda1f6c4511dfbac7b4fe8676cce4ec9efafbb9d88b80a638fdfcd88`). `artifacts/w04/operational_cache_recovery.json` records the transparent recovery method and hashes. Prep remained unchanged; the original checkout was untouched. The original `full_status.json` retains the detected mutation rather than rewriting history. No full suite or provider session was repeated.
