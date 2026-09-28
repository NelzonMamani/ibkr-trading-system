# W02 News Intelligence acceptance

## Identity and scope

Baseline: `ddb05c3750a05d0e491e874b6bdd7a55e40fb073` (verified main containing merged W01). Branch: `codex/w02-news-acceptance`; reused free managed worktree `C:/Users/nelzo/.codex/worktrees/w01-consolidation/ibkr-trading-system`. Interpreter: `C:/tmp/pr1091-cert-env-20260923/Scripts/python.exe`, Python 3.13.3, pytest 9.1.1, requests 2.34.2, feedparser 6.0.14. No environment rebuild or W01 baseline-suite rerun. No applicable AGENTS.md found. Original checkout, unrelated changes and original W01 evidence remain untouched.

W02 uses canonical service/store, batch RSS, fetcher, runtime helpers, source groups and prep projection. No broker connection, trading runtime, operational scanner loop, market observation or order activity was run. Offline tests exercise consumer functions and fixture-driven existing integration tests. Sources, order, budgets, freshness limits, cadence, catalyst requirement and Ross thresholds remain unchanged. The News contract corrects the five pillars to Price, Gap/% Change, RVOL, mandatory Catalyst/News and low Float; absolute Volume is separate.

## Recorded failure: why 7.288 seconds exhausted an eight-second allocation

The saved KNRX/LFCR trace is **4.480777s FAST + 2.807618s EXTENDED = 7.288395s**, rather than one continuous eight-second provider call. The scanner reserves 35% (2.8s) for EXTENDED and caps its request at `min(reserve, total - FAST elapsed)`. FAST's unused 0.719223s is not transferred into that fixed reserve. EXTENDED legitimately reached its own deadline; the aggregate budget flag reports incomplete retrieval even though the two reported provider durations sum to less than eight seconds. This is not proof of an external provider defect. Policy reallocation is outside W02.

FAST attempted all eight sources: seven available/no-match outcomes and Reuters HTTP 401. EXTENDED scheduled thirteen, attempted eight (four available/no-match, four pending when discarded), and skipped five before attempt. W01 did not retain HTTP/parse bodies for successful sources, so its 'available' labels cannot prove recognized RSS or fresh content. Earlier saved PR1086 direct and scanner traces exhibit the same independent-tier timing. Exact source rows, provenance hashes, code references and timings are in [recorded_timing_diagnosis.json](../../artifacts/w02/recorded_timing_diagnosis.json).

The service reads canonical cache and prep evidence first, preserves publication age and per-symbol acquisition cadence, and retrieves only allowed refresh symbols. FAST evidence is matched and time-filtered; the caller supplies unresolved symbols for EXTENDED. Deduplicated objective evidence plus per-symbol retrieval diagnostics persist through the canonical store. Empty success, unavailable acquisition and usable persisted evidence are different states. Fresh validated prep/cache evidence remains authoritative during an unsuccessful refresh, as required by the existing contract and unchanged Ross positive-evidence precedence; provider failure alone cannot create confirmation.

## One provider-only capture

The only external provider pass started **2026-09-28T19:19:10.270673Z** and completed **19:19:24.704801Z**: 14.434 seconds including setup, 12.803 seconds for the provider/health phase. A 240-second watchdog bounded it below the ten-minute authorization. All 21 configured URLs were attempted once: eight FAST and six EXTENDED production-budget attempts, then seven independent health-only attempts for previously unattempted sources. No blocked endpoint was retried. A dedicated diagnostic cache and empty prep loader were used; the operational cache SHA-256 remained `adb8e35abda1f6c4511dfbac7b4fe8676cce4ec9efafbb9d88b80a638fdfcd88`. No ibapi/ib_insync import occurred.

Resolved defaults: total allocation 8s, request timeout 5s, reserve fraction 0.35, lookback and evidence freshness 6h, max five evidence items, refresh cadence PREP/PRE/RTH 1800/300/120s. The separate Ross maximum news age remains 3600s. The actual probe FAST policy was 5.2s; EXTENDED received 2.786858s after FAST consumed 5.213142s. These are environment/request values, not a universal runtime budget. Full resolution trace and policies are in [source_evidence_matrix.json](../../artifacts/w02/source_evidence_matrix.json).

The probe reused saved KNRX/LFCR tickers; W01 did not retain original issuer metadata. It did not run current Ross qualification. It recorded the baseline HEAD during W02 work, but did not capture loaded module hashes. Its pending-source timeout flags and extended deadline retain pre-repair behavior; exact dirty source state at import is unverified. Script, unchanged baseline-module and raw-capture hashes are recorded; the final offline implementation receives a separate complete source manifest. No repaired live behavior is claimed.

Eighteen HTTP 200 responses were recognized RSS/Atom. Reuters returned 401, France24 403, VentureBeat 429. No fresh KNRX/LFCR match occurred. This supports insufficient sampled coverage, not proof that no real issuer news existed. A genuine IRON issuer article from the capture is replayed with original publication time and response hash in offline acceptance; its legal notice is correctly non-qualifying under Ross policy.

HTTP-call time below includes requests/redirect handling; it is not a total tier deadline. Requests' scalar timeout bounds connection/read waits rather than the entire HTTP-plus-parse wall duration. No request timeout exception was observed in this capture. Item columns separate fresh/stale/future counts (recognized empty feeds have zero items).

| Source | HTTP | HTTP seconds | Items | Fresh/stale/future | Original production outcome / scope |
|---|---:|---:|---:|---|---|
| Benzinga | 200 | 2.911 | 10 | 10/0/0 | available |
| GlobeNewswire Finance | 200 | 3.129 | 20 | 20/0/0 | available |
| GlobeNewswire Technology | 200 | 2.881 | 20 | 20/0/0 | available |
| Reuters | 401 | 2.754 | - | -/-/- | provider_error |
| MarketWatch | 200 | 5.154 | 10 | 10/0/0 | budget_exhausted; completed late |
| Business Insider custom | 200 | 1.492 | 20 | 20/0/0 | budget_exhausted; completed late |
| Seeking Alpha | 200 | 1.464 | 30 | 30/0/0 | budget_exhausted; completed late |
| CNN Business | 200 | 0.322 | 20 | 0/20/0 | available |
| Dow Jones Markets | 200 | 2.611 | 20 | 0/20/0 | available |
| Fortune | 200 | 3.184 | 10 | 4/6/0 | budget_exhausted; completed late |
| Forbes Business | 200 | 2.669 | 25 | 25/0/0 | available; completed late |
| Forbes Finance | 200 | 2.605 | 0 | 0/0/0 | available |
| BBC News | 200 | 2.932 | 33 | 15/17/1 | budget_exhausted; completed late |
| BBC Business | 200 | 4.151 | 51 | 10/41/0 | budget_exhausted; completed late |
| Sky News | 200 | 2.993 | 10 | 0/10/0 | skipped; health only |
| France24 | 403 | 2.544 | - | -/-/- | skipped; health only |
| Markets Business Insider | 200 | 4.190 | 20 | 20/0/0 | skipped; health only |
| Investing.com | 200 | 2.953 | 10 | 10/0/0 | skipped; health only |
| MarketBeat | 200 | 1.833 | 100 | 1/99/0 | skipped; health only |
| TechCrunch | 200 | 1.167 | 20 | 18/2/0 | skipped; health only |
| VentureBeat | 429 | 1.156 | - | -/-/- | skipped; health only |

The [full CSV matrix](../../artifacts/w02/source_evidence_matrix.csv) records per-source attempted/skipped status, timeout, applicable deadline, completion offset, parse/version, rejection counts, issuer matches and raw SHA-256. Original response bodies remain locally in `output/w02/provider_pass_20260928/raw_responses`; complete bodies are not published with this PR.

Health-only successes and coordinator-discarded late completions do not count as evidence returned by the production-budget service. One captured exception demonstrated a defect: Forbes Business was accepted 6.891ms after the tier deadline. Its native HTTP/parse completed 17.604ms before the deadline; diagnostic analysis added 24.495ms and caused this particular crossing. The fetcher lacked a worker-completion deadline check after waiting. Offline controlled clocks isolate the defect and verify its repair. The matrix preserves the original observed outcome.

Instrumentation consumed 0.273 source-thread seconds in total (concurrent and non-additive), and the cold-cache/FAST/EXTENDED service sequence took 8.186s including service/instrumentation overhead. It is not an exact recreation of W01 scanner-stage wall time. Neither late completion nor overall measured elapsed beyond an HTTP timeout proves an HTTP timeout exception.

## Demonstrated repairs and offline acceptance

| Repair | Before | After / evidence |
|---|---|---|
| Explicit EXTENDED deadline and symbol status | Smaller explicit tier budget was ignored in favor of total deadline; required tier incompleteness could be omitted or contaminate unrelated symbol status | Enforce `min(total deadline, tier start + tier budget)` and keep total-deadline versus aggregate/per-symbol exhaustion separate; five controlled regressions |
| Source timeout classification | Pending local-deadline cancellation asserted HTTP timeout without observing an exception | Deadline remains budget exhaustion; timeout is false unless observed. Real controlled ReadTimeout remains a timeout, including an observed late failure; HTTP errors and exhausted deadlines remain separately recorded |
| Deadline crossing after wait | Completed futures could be accepted after the applicable deadline | Worker completion timestamps enforce stage/tier boundaries, including equality; in-time completion survives coordinator lag. Late results are discarded without increasing any budget |
| Persisted unknown outcomes | Default per-symbol summaries erased explicit failure on cadence reuse/restart | Canonical normalization preserves explicit per-symbol unavailable/budget facts and objective status before persistence; healthy peers retain their own outcome |
| Scanner/Ross availability projection | Mixed batch exhaustion poisoned healthy symbols; generic/empty unavailable results could appear available/ABSENT; missing provider label inherited failed batch; default unknown summaries could mask explicit failure | Canonical per-symbol status controls consumer diagnostics. Healthy no-match remains ABSENT; unavailable/generic unknown remains DATA_UNAVAILABLE; fresh confirmed cached evidence retains authority |

Before/after evidence: adapter tier/status tests reproduced 3 failures and then passed all 5 cases; deadline-vs-timeout classification reproduced 1 failure/1 pass and then 2 passes; strict stage/tier completion tests reproduced 4 failures and then passed 10 cases including timeout checks. Peer review exposed late-error diagnostic loss in the intermediate repair (8 failures); all 18 source-outcome cases then passed. Unknown-summary persistence reproduced 2 failures before repair, and explicit legacy failure-label preservation reproduced 2 additional failures. The final consumer matrix has 29 cases; its related service/ownership/diagnostic run passed 71 tests. Consumer comparison and final combined results are recorded below.

The public-service acceptance path is actual BatchRssNewsIntelligenceProvider ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¾ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ CanonicalNewsIntelligenceService/evidence_store ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¾ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ NewsProvider ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¾ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ PreMarketPrepEngine serialization/hydration ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¾ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ a new service ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¾ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ scanner's pure Ross projection and `assess_catalyst`. It uses controlled clocks and blocked sockets. The IPDN positive catalyst replay uses historical issuer text/URL with explicitly controlled publication time; it is not new live coverage evidence. The IRON match uses the single capture's original timestamp and provenance.

Acceptance covers cold acquisition, warm reuse with increasing publication age, restart reuse, explicit refresh, per-symbol cadence for empty/unavailable results, actual prep persistence, genuine issuer-positive matching, unrelated ticker words, missing/future/stale publication rejection, UTC timestamps, evidence identity deduplication and offering preservation, plus mixed provider/budget outcomes. Before-fix logs distinguish initial fixture-clock correction from actual production failures; the authoritative consumer comparison is `consumer_before_corrected_clock.log` (7 failures, 8 passes) and final expanded consumer coverage (see final logs).

## Changed files

Production changes are limited to `src/news/batch_rss_adapter.py`, `src/news/news_fetcher.py`, `src/news/news_intelligence_service.py` and `src/scanner/scanner_runner.py`. Documentation is this report plus `NEWS_INTELLIGENCE_CONTRACT.md`. Three `tests/test_w02_*.py` modules and `tests/fixtures/w02_captured_issuer_news.json` supply regressions. `scripts/diagnostics/w02_news_provider_pass.py` records the one-shot diagnostic and `w02_offline_guard.py` enforces offline verification. `artifacts/w02/` contains source/outcome evidence, before/after logs, test manifests and the final supervisor results. The exact versioned file list is `artifacts/w02/changed_files.txt`; the final source manifest binds Python content before and after the full suite.

## Verification and verdicts

The combined 20-module run passed **230 tests** in 23.66s. Its socket guard blocked four connection attempts from an existing offline scanner test; no provider/broker connection was allowed. Windows stdlib socketpair self-pipes are the sole loopback exception. Initial guard setup rejected a Windows asyncio self-pipe during collection; that harness-only failure is retained as `guard_collection_*`, and the corrected combined run passed. Final full-suite results and source hashes are recorded under `artifacts/w02/`. CI and exact-head review are recorded after publication in the PR and local `output/w02/closure_report.md` so recording gate outcomes does not move the reviewed head. A new full suite is run only on the stable changed implementation; previously accepted W01 verification is not repeated.

**OFFLINE_CONTRACT: PASS for the verified service/persistence/consumer contract.** Combined targeted: 230 passed. The one final local full suite: **2,042 passed, 1 skipped, 212 warnings in 322.01s**; compileall passed. No Python source changed during verification. Manifest SHA-256: `406102807065b8734bad32c9de868cd9583e73eb5b8e33a7f417d4f7790c7697`. The full-suite guard blocked 20 connection attempts in existing tests and allowed 26 stdlib private socketpair self-pipes. No provider/broker connection was allowed. News and prep hashes were unchanged. The four generated catalogue files were preserved in a local patch and restored to baseline; original-checkout changes were untouched.

**PROVIDER_SERVICE: PARTIAL HEALTH / INSUFFICIENT KNRX-LFCR COVERAGE.** Eighteen of 21 configured URLs returned recognized feeds in the standalone sample; source access, freshness, broad-feed issuer coverage and production latency remain limitations. Truthful unavailable results can pass the contract while provider coverage remains insufficient. No natural strategy integration or paper readiness is established.

## Remaining decisions and next useful task

No source, endpoint, entitlement, timeout, reserve allocation or freshness policy was changed. A separate decision can authorize investigation of Reuters' documented access/entitlement requirements, France24's denied response and VentureBeat's rate-limit response. Do not retry or bypass them on the basis of W02. The stale CNN/Dow Jones/Sky content and empty Forbes Finance feed justify a separately approved source-quality review. Fresh broad-market feeds with no sampled issuer match support considering issuer-focused coverage, with source selection and costs assessed explicitly. Increasing/reallocating the EXTENDED allocation would trade latency for source completion and would not repair missing issuer coverage; it requires a separate policy decision.

Next useful task: controlled merge after green exact-head CI/review, then an authorized source-access/coverage decision based on this matrix. No new market opening is needed to finish standalone acceptance.

`PAPER_READY=NO`  
`PAPER_READINESS_GATE=FAIL`
