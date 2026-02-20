# Migration Sequence (Concrete Tasks)

Codex must implement **only what is necessary** to satisfy E25 acceptance criteria.

### Task 1 — Fix CLI invocation for `submit_one_order.py`

Current symptom:
- running `python src/cli/submit_one_order.py --help` fails with `No module named 'src'`.

Target:
- `python -m src.cli.submit_one_order --help` works.

Actions:
- Ensure `submit_one_order.py` uses absolute imports from `src...` (already does).
- Add a guard in help text if necessary: run via `-m`.
- Optional: add a small top-level wrapper script in `scripts/` if you want file-based launching, but not required.

### Task 2 — Enforce import-safe runtime boundaries

Scan for any remaining imports of `ib_insync` at module top-level outside adapters/runtime.
- If found, refactor to use `src.runtime.async_runtime_bootstrap.safe_import_ib_insync()`.

### Task 3 — Ensure generated artifacts are not required

- Confirm no module import depends on `data/ibkr_system.db` existing.
- Update tests to create temporary DBs if needed.

### Task 4 — Evidence updates

- Add:
  - `AUDIT_EVIDENCE/E25_architecture_realignment_report.json`
- Update:
  - `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md` to include E25 status (NOT_STARTED → CERTIFIED once green)

Do not alter strategy policies/content unless absolutely required for import-safety.
