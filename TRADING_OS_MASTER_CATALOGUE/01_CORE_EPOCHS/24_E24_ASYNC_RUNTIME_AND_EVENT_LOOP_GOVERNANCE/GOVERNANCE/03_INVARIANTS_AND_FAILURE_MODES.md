# 03 — Invariants and Failure Modes

## Hard Invariants (must hold)
1. **Pytest Collection Safety**
   - `pytest -q` must not crash during import/collection because of async loop absence.

2. **Import-Time Purity**
   - Importing any `src/*` module must not require a running event loop.
   - If third-party libraries violate this, Trading OS must wrap/guard import paths.

3. **Mode-Consistent Boot**
   - SIM/PAPER/READ_ONLY must boot without requiring TWS/IBG.
   - LIVE must remain execution-disabled by default unless operator explicitly enables execution.

4. **Deterministic Loop Ownership**
   - Exactly one component owns loop creation/closing per process.

5. **No Silent Behavioural Drift**
   - Any compatibility shim must be logged/audited and included in evidence.

## Failure Modes (examples)
- **FM1**: Import chain triggers `eventkit.util.get_event_loop()` → raises at import.
- **FM2**: Tests import scanner provider factory and import IBKR provider unconditionally.
- **FM3**: Multiple loops created → task leakage, nondeterministic behaviour.
- **FM4**: Loop created but wrong policy on Windows causing low-level selector errors.
- **FM5**: “Fix” masks issues by globally monkeypatching asyncio in unsafe ways (forbidden).

## Forbidden Fixes
- Broad monkeypatch of `asyncio` semantics at import for the entire interpreter without clear containment and audit.
- Disabling large parts of the test suite instead of making imports safe (skip is acceptable only for tests that truly require IBKR connectivity and must be explicitly tagged).

