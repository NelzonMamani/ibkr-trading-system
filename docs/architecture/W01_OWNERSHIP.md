# W01 ownership and migration record

Baseline: PR1092, 238d99639a6d305969d973d8212741b84e12bc42. The original checkout remains untouched, including all unrelated changes and historical evidence. Work occurs on codex/w01-consolidation in the managed W01 worktree. Python 3.13.3 / pytest 9.1.1 from the existing certification environment passed bounded import checks. No applicable AGENTS.md was found in repository or ancestor directories.

## Authority and pre-deletion trace

Read System Tree, locked architecture implementation instructions, catalogue global instructions, scanner-to-strategy contract, scanner responsibilities, Phase 24 scanner field checklist, Ross specification and Ross runtime contract. This bounded W01 instruction authorizes source changes and supersedes older programme-only scope/epoch ordering and live execution smoke instructions. No execution smoke orders are authorized.

| Existing path | Callers / authority | W01 disposition |
| --- | --- | --- |
| scanner/scanner_runner.py | orchestrator, scanner_main, Ross runner, diagnostic adapter, selection/continuity regressions | Canonical selection orchestration; strategy policies remain eligibility authority. |
| scanner/scanner_main.py | module CLI and smoke commands | Retain supported CLI delegating to runner. |
| scanner/scanner_master_v2026_01_06_07.py | historical CLI docs and _selftest only; independent broker/history/news/printer bodies | Replace dated command with delegate to scanner_main; retire duplicate implementation. |
| scanner/news_engine.py | dated master only; independent RSS parsing/cache/substring matching | Delete after dated command migration; normalizer/service preserve news reporting. |
| scanner/scanner.py | only verification_scripts/verify_paper_execution_harness.py | Delete teaching/live competing scanner; harness uses an explicit offline fixture. |
| scanner/scanner_live_readonly.py | no executable caller/import, only historical docs/config affects metadata | Delete unused alternate scanner and natural READ_ONLY mock fallback. |
| data/news/news_provider.py | PreMarketPrepEngine; three verification scripts; source-group compatibility test | Replace provider body with import-only compatibility; canonical service owns retrieval/cache; news prep adapter projects its result. |
| news/news_intelligence_service.py | active scanner and new prep adapter | Canonical bounded retrieval, revalidation and evidence cache authority. |
| news/batch_rss_adapter.py, news_fetcher.py, news_normalizer.py | canonical service and diagnostic/test provider injection | Legitimate retrieval/normalization layers, not competing service caches. |
| scanner/reference_resolver.py | runner, IBKR scanner provider, identity/reference tests | Move sole reference/cache implementation to market_data; import-only old path. |
| scanner/session_pct_change.py | session callers, providers, policies, diagnostics and tests | Move unchanged shared market/session calculations to market_data; import-only old path. |
| core/managers/market_data_snapshot_manager.py | orchestrator, CLI diagnostics, market authority tests | Move sole snapshot translation/quality implementation to market_data; import-only old path. |
| market_data/market_data_hub.py | orchestrator, price feed | Keep per-cycle broker snapshot cache/events; distinct from snapshot translation/quality manager. |
| market_data/market_snapshot_enricher.py | runner | Keep batch snapshot hydration and provenance. |
| ibkr/market_data_client.py and adapters/brokers/ibkr | shared SDK transport, snapshot callbacks/history acquisition | Retain transport and lifecycle authority; market_data consumes transport facts. |
| data/fundamentals/float_provider.py, data/float_discovery_worker.py | scanner provider and runner | Move sole provider/worker implementations to market_data; preserve Yahoo/Finviz alternatives, JSON/SQLite formats and worker lifecycle; import-only old paths. |

Import/caller searches covered src, tests, scripts, verification_scripts and repository text including registries and CLI docs. Historical certification documents are evidence and are not rewritten. Config thresholds, provider source groups and budgets remain unchanged. NEWS_CACHE_FILE and reference cache formats remain supported through their canonical stores; legacy persisted evidence is revalidated, never trusted by its old classification or receipt time.

Compatibility paths contain no implementation, policy or cache. Remove them when downstream external imports/dated command users have migrated for a release; all in-repository operational callers migrate now. Old cache formats may be removed only after users migrate persisted evidence and a separate compatibility decision is recorded.

## Protected behavior

Five Ross pillars, mandatory fail-closed catalyst, absolute volume versus RVOL, session rules, genuine 10s/1m/5m provenance, requested/returned data type, market/receipt time, Focus accounting and PR1092 console/evidence safeguards remain protected. Recovery, shutdown/PANIC, risk, execution and generic strategy functionality are outside the rewrite.

PAPER_READY=NO
PAPER_READINESS_GATE=FAIL


Additional market fact moves: candidate_identity and market_metrics_context move from scanner to market_data, keeping identical types, math and provenance. Scanner retains per-cycle selection/hydration views of canonical float facts; these are not a second persistent provider. MarketDataHub retains its per-cycle cache/events while MarketDataSnapshotManager translates native snapshots and flags quality. These responsibilities intentionally remain distinct.

Scanner `_NEWS_CACHE` is only a derived rendering/change-signature memo populated after canonical retrieval on every invocation; it does not bypass retrieval or own persisted evidence. BatchRss provider injection remains available for offline tests. MockScannerProvider remains an explicit SIM/PAPER/offline adapter; AUTO in READ_ONLY/LIVE connects IBKR and propagates failures. Retired live scanner mock fallback is deleted.

Intentional defects corrected: unsafe legacy substring issuer matching and unbounded per-symbol RSS fetch loops are removed; prep no longer trusts stale cached classifications or a separate raw cache; relative news age cannot reset at each read, missing/future dates cannot become fresh, and RSS UTC dates no longer use host-local time. Prep catalyst_tag is descriptive canonical event metadata or generic; it no longer runs a competing substring classifier. Ross bounded catalyst vocabulary and all thresholds are unchanged.


Dead `_prep_news_context_from_entry` / `_prep_news_contexts_for_symbols` bodies were retired after confirming no consumers. They trusted old freshness flags and catalyst tags independently; the active path already uses canonical evidence. `_prep_tag_to_catalyst_type` remains strategy projection used by `_catalyst_type_from_evidence`, and `_merge_news_contexts` remains active selection orchestration, not retrieval/cache authority.


## Live diagnostic evidence (2026-09-28 RTH)

Evidence is in artifacts/w01/preflight_20260928 and artifacts/w01/live_20260928T1730Z. Fresh Paper-only managed-account identity, three READ_ONLY action guards, process isolation and zero open orders passed before capture. No unidentified process was interrupted. Existing PR1040 bounded adapter captured one genuine IBKR scan with two candidates, KNRX and LFCR; no forced Focus or synthetic universe was used. Diagnostic source was unchanged PR1092.

Adapter runtime: 17:29:46.630699Z to 17:30:13.186093Z; scanner 20.903 seconds, budget 120 seconds. Both candidates failed catalyst with DATA_UNAVAILABLE/budget_exhausted. News retrieval took 7.288 seconds within an 8-second diagnostic allocation (fast 5.2 seconds, extended reserve 2.8 seconds). No Focus or pattern certification resulted. LFCR had all required quote fields; KNRX lacked bid/ask. Coverage/latency gaps remain external evidence, not relaxed gates.

A follow-up quote/bar capture used the first two candidates from the saved scanner result. Initial ContractDetails unpacking failed; its artifact is retained. The corrected capture completed at 17:33:44.630732Z, within five minutes of initial preflight. Each symbol returned 180 genuine 10-second bars, 31 one-minute bars and 7 five-minute bars through IBKR historical TRADES, without aggregation. Requested and returned quote data type were LIVE. Bar timestamps, acquisition intervals, missing quote fields and candidate provenance are preserved separately. Current/incomplete last bars are diagnostic facts, not certified pattern authority.

Every diagnostic ended with disconnection. Final independent reqAllOpenOrders audit observed openOrderEnd, zero open orders and zero place/modify/cancel attempts. Final process inventory completed with no remaining runtime. This is diagnostic evidence, not trading certification. PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

## Validation notes

Initial protected regressions: 84 passed. Expanded canonical/float/reference regressions: 118 passed. Consuming-boundary run: 116 passed, one documentation string assertion failed; wording was repaired. Final additional boundary run including optional src/tests session/quote tests: 37 passed. A stale optional test expected last to be copied to missing close; its assertion now preserves the accepted missing-field contract. Historical failed logs remain intact. Final full-suite result and source hashes are recorded separately under artifacts/w01.


Local final full suite: **1,978 passed, 1 skipped**, 212 warnings, 288.83 seconds; compile exit 0; test exit 0; no source changes during that run. `final_suite_status.json` binds its log and source hashes. A final projection review then added summary/issuer metadata preservation across prep serialization with a roundtrip regression; 75 targeted regressions passed. `post_suite_delta.json` records precisely those three changed sources, and `pr_source_hashes.json` binds the PR source. Required PR CI supplies the full-suite result for that exact final head; the local full run is not misrepresented as covering the follow-up delta.

Seven fresh-process import checks passed. All seven market-data moves were verified byte-for-byte (normalized line endings) against baseline after only import-path replacement. Four catalogue files regenerated by tests are preserved in artifacts/w01/test_generated and restored outside the implementation patch. Historical original-checkout evidence is untouched. No owned Python/runtime/test process remained after validation.


## Exact-head review follow-up

The first PR head (8c96d97c0d463426c37c954a6d72c73c362bc618) passed required CI. Its automated review found two blocking regressions, both repaired before merge: prep serialization must retain canonical evidence IDs so duplicate copies cannot displace a distinct offering at the five-item cap; prep acquisition cadence must use NEWS_REFRESH_SECONDS_PREP independently of headline freshness. The canonical store now persists per-symbol acquisition timestamps and outcomes, including empty/unavailable responses. Explicit scanner refresh requests retain precedence. Prep remains a projection with no independent cache or retrieval authority.

Follow-up validation: 97 targeted tests passed, covering the five-item dilution case, fresh-headline refresh after 30 minutes, negative-result reuse across service restarts, and explicit refresh precedence. Two intermediate runs failed only because new test overrides used integers for float-typed configuration; their logs are retained. The original full-suite evidence is unchanged. Required CI and review must validate the subsequent exact head.
