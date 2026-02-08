# E18 — CERTIFICATION CRITERIA (BINARY PASS/FAIL)

E18 is certified ONLY if all criteria below hold:

A) COMPLETE TREE-LIST COVERAGE (MANDATORY)
- All SF_* setup families exist (see File 05)
- All XL_* execution triggers exist (see File 06)
- All C_* conditions exist (see File 07)
- All K_* confirmations exist (see File 08)

B) CANDLESTICK FOUNDATION COMPLETE (MANDATORY)
- Named single-candle checklist complete (File 10)
- Named multi-candle checklist complete (File 11)
- Functional behaviours implemented (File 12)
- Contextual candle states implemented (File 13)

C) NEUTRAL CONTEXT PRIMITIVES (MANDATORY)
- Levels & zones primitives defined and usable (File 14)
- Market structure state vocabulary implemented (File 15)
- Invalidation semantics supported (File 16)

D) SYMBOL COMMITMENT EDGE (MANDATORY)
- Immediate context hydration on commitment (File 17)
- Completeness flags present
- HAS_NEWS boolean available (minimum)

E) RESETTABLE, REGENERABLE STATE (MANDATORY)
- Lifecycle classes implemented (File 18)
- Soft/hard/version reset available
- Safe degradation after reset

F) STRATEGY POLICY TRANSLATION (MANDATORY)
- Translation report generation
- Coverage checklist generation
- Drift detection and compatibility verdicts (File 19)

G) TESTABILITY & VERSIONING (MANDATORY)
- Deterministic unit tests for foundation primitives
- Explicit foundation versioning and compatibility semantics (File 20)

H) NO POLICY IMPOSITION (MANDATORY)
- Foundation does not enforce Ross-only gates globally
- Dumb/simple strategies remain viable
- Specialized strategies retain their unique rules

FAILURE OF ANY ITEM ABOVE = E18 NOT CERTIFIED.

END
