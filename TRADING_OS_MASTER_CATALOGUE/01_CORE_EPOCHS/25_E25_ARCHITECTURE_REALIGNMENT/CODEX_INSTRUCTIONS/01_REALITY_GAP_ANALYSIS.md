# Reality Verification & Gap Analysis

Codex tasks:

1. Print the current high-level tree (top 3 levels):
   - `src/`
   - `tests/`
   - `data/`
   - `output/`
   - `TRADING_OS_MASTER_CATALOGUE/`

2. Identify:
   - any core modules importing adapters at import time
   - any `python src/...py` style scripts that should be converted to `python -m`
   - any runtime side-effects at import (event loop, broker connect, file opens)

3. Produce a concise gap list:
   - GAP-1: CLI entrypoints not runnable with `-m`
   - GAP-2: Import-boundary side effects
   - GAP-3: Wrong folder placement (e.g., DB files in repo, outputs tracked)
   - GAP-4: Adapter leakage

Deliverable: add `AUDIT_EVIDENCE/E25_gap_analysis.json` with:
- detected gaps
- affected modules
- proposed fixes (mapped to steps in the migration sequence)
