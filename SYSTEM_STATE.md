# SYSTEM_STATE
## Current Authoritative Runtime State

CURRENT_PHASE: 25
PREVIOUS_PHASE: 24 (COMPLETE)
SYSTEM_MODE: LIVE_READ_ONLY (IBKR primary, MOCK fallback)
EXECUTION_STATUS: HARD DISABLED
BROKER_WRITE_ACCESS: DISABLED

### Phase 24 Summary (Complete)
Phase 24 focused on scanner hardening and observability:
- scanner_runner runs as module and script without ImportError.
- RSS/news failures are summarized and non-blocking.
- Symbol limits are printed with sources and resolved caps.
- Watchlist file is always written (with header counts and exclusion reasons).
- Field audit + mechanical checklist artifacts are produced under docs/.

### Phase 25 Objective (Active)
Phase 25 focuses on execution-layer import hygiene, orchestrator boot integrity, and scanner cap sanity.

#### Triggering Evidence (Observed)
Running:
- `python -m src.main`

Fails during import resolution with:
- `ModuleNotFoundError: No module named 'utils'`
Origin:
- `src/execution/liquidity_engine.py` importing `from utils.price_math import ...`

#### Non-Negotiable Requirements
- Orchestrator must boot successfully in module mode:
  - `python -m src.main`
- Execution layer must not block startup when execution is disabled.
- Invalid flat imports (e.g., `utils.*`) must be refactored to package-correct imports.
- No sys.path manipulation is allowed for production paths (tests/tools may be exceptions with justification).

### Acceptance Criteria for Phase 25
1) `python -m src.main` starts without ImportError/ModuleNotFoundError.
2) Startup prints configuration summary and safety banners.
3) Orchestrator can enter at least one teaching cycle in SIM/LIVE_READ_ONLY.
4) Broker/execution modules do not import optional dependencies at import-time unless guarded.
5) Any remaining execution limitations are explicitly logged and do not crash the process.
6) Scanner teaching cap defaults to disabled (0), so non-teaching runs resolve symbol limits from SCANNER_TOP_GAINERS_COUNT and IBKR_MAX_SYMBOLS_PER_CYCLE.

### Known Degradations (Allowed During Phase 25)
- Execution pathways may remain disabled or stubbed (by design) while imports are fixed.
- Live order routing is out of scope unless explicitly enabled and validated.

### How to Run
- Orchestrator:
  - `python -m src.main`
- Standalone scanner:
  - `python -m src.scanner.scanner_runner`
  - `python src/scanner/scanner_runner.py`

### Outputs
- Watchlists: `output/watchlists/watchlist_RossMomentum_<timestamp>.txt`
- Scanner audit artifacts: `docs/PHASE_24_SCANNER_FIELD_AUDIT.json`, `docs/PHASE_24_SCANNER_MECHANICAL_CHECKLIST.md`

Last updated: 2026-01-10T09:30:00Z
