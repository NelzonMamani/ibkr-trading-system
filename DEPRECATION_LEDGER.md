# DEPRECATION_LEDGER.md

## Compatibility / Superseded Entries
- READONLY CLI alias -> compatibility-only; canonical mode is READ_ONLY.
- Governing truth: src/config/runtime_config.py RunMode enum.
- Evidence: output/audit/e23/* READ_ONLY and PAPER boot logs.


## W01 Scanner / News / Market Data

- Deleted `src/scanner/news_engine.py`, `scanner.py`, and `scanner_live_readonly.py` after caller migration. Their independent RSS, teaching/live selection and READ_ONLY mock-fallback bodies are retired.
- Dated master scanner command delegates to `scanner_main.main`; `_selftest` now imports the canonical command. Remove the dated alias after external command users migrate for a release.
- `src/data/news/news_provider.py` only re-exports the canonical prep result adapter; no independent retrieval or cache remains.
- Old scanner reference/session/identity/market-metrics paths, core manager snapshot path and data float provider/worker paths only re-export their `src/market_data` implementations. All repository operational consumers use canonical imports. Remove aliases after external imports migrate for a release.
- Retained legacy news-cache serialization is read through the canonical evidence store with issuer and time revalidation. Remove the legacy shape only after a separate persisted-data migration decision.
- Unused prep-news conversion helpers in scanner runner were deleted; active strategy projections and derived change-signature memo remain.

Authority, caller map, preserved behavior, defects and evidence: `docs/architecture/W01_OWNERSHIP.md`.

## 2026-11-14 — Targeted executable retirement

Baseline: `c65bc001fc3428c8eef0315fd1e1b8a903b7c53c`; queue authority:
`bf476ae0e835a7fc0c0ba6e64676b262c75af910`. This retires competing executable
recipes, not broker capabilities, historical certification evidence or data.

Complete-checkout local text checks (including hidden workflows, imports, module
names, CLI/registry/dynamic-dispatch strings, tests, scripts and active/historical
docs) found the following caller sets. No executable external compatibility
commitment was found for these standalone files. Git history retains source;
no runnable archive is added. External private callers cannot be inventoried;
users of deleted commands must migrate to the current guarded runbook, not LIVE.

| Deleted executable | Repository caller/reference evidence and disposition |
| --- | --- |
| `RUN_LIVE_MICRO_1SHARE.ps1` | Its only executable caller is its own recursive invocation; unsupported LIVE_MICRO. Directory-tree snapshot only otherwise. Retire without translating mode. |
| `RUN_LIVE_READ_ONLY.ps1` | No executable caller. Historical E5/E7/E10 instructions/audit outputs and active catalogue E7/E21/global lists; unsupported LIVE_READ_ONLY, live port and fallback. Active lists migrated to offline checks. Active E5/E7/E10 command instructions migrated; historical audit outputs retained. |
| `RUN_PAPER_TRADING.ps1` | No executable caller. Historical E5/E6/E7/E8/E10 instructions/audit outputs and active E21 list; unbounded writable main loop. Active E5/E6/E7/E8/E10/E21 command instructions migrated; historical audit evidence retained. |
| `verification_concole_commands/RUN_LIVE_MICRO.ps1` | No caller/import/workflow/registry reference; directory-tree snapshot and own comment only. Unsupported mode, unbounded runtime. |
| `verification_concole_commands/RUN_LIVE_READ_ONLY.ps1` | No caller/import/workflow/registry reference; directory-tree snapshot and own comment only. Unsupported mode/live port. |
| `verification_concole_commands/RUN_PAPER.ps1` | No caller/import/workflow/registry reference; directory-tree snapshot only. Redundant unbounded writable launcher. |
| `verification_concole_commands/RUN_SIM.ps1` | No caller/import/workflow/registry reference; directory-tree snapshot only. Redundant wrapper; bounded root `RUN_SIMULATION.ps1` retained. |
| `troubleshooting/stock_selection/stock_selection_scanner_25_jan_2026.py` | Only its own comment, derivative-script lineage comments, historical tree and issuer-RSS source research document. Direct standalone IBKR/HTTP/Yahoo scanner; no import/dynamic caller. |
| `troubleshooting/stock_selection/ross_stock_selection_2026_01_27_001734_UTC.py` | Only own comment, historical tree and issuer-RSS source research document. Direct standalone scanner, no import/dynamic caller. |
| `troubleshooting/stock_selection/ross_stock_selection_scanner_v1_2026_01_27_003749_UTC.py` | Only derivative-script lineage comments, historical tree and issuer-RSS source research document. Local `main`/news helper only, no external caller. |
| `troubleshooting/stock_selection/ross_stock_selection_scanner_v2_2026_01_27_014955_UTC.py` | Historical tree and issuer-RSS source research document only; local `main`/news helper only. |
| `troubleshooting/stock_selection/ross_stock_selection_scanner_v2_1_2026_01_27_143909_UTC.py` | Historical tree and issuer-RSS source research document only; local `main`/news helper only. |
| `troubleshooting/backup/stock_selection_scanner_25_jan_2026.py` | Historical tree and issuer-RSS source research document only. Duplicate standalone source, no caller. Output text files remain. |

Active README/runbook/status/deployment and catalogue lists now separate current
runtime semantics from historical smoke/certification claims. The old deployment
path remains a non-executable retirement notice; its live database-reset, writable
flags and unbounded first-trade recipe are withdrawn. Historical certified-state
bodies and dated audit records remain with prominent current-status
corrections; they are not upgraded or retroactively counted as natural proof.

Retained: bounded root SIM wrapper, console RESET_ENV/VERIFY_STATIC, all
`verification_scripts` pending their own caller/authority checks, active
`src/core_engine` session compatibility imports, W01 import/dated-command aliases
and legacy cache serialization subject to the existing external migration
conditions. All troubleshooting output text, certification receipts/failures,
SQLite databases and recovery/accounting state remain unchanged. No whole folder
is retired by name/age; removal of the six scanner source files leaves their
output evidence directories intact.

The immutable next-week distribution `3f48bf3f`, its accepted c65 source pin and
reviewed calendar are unchanged. No runtime, observer or broker/provider command
was executed for this cleanup. Focused offline validation and final review/CI
receipts are recorded in the maintained programme records upon integration.

PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
