# E18 — TESTABILITY, EXPLAINABILITY, VERSIONING (FUTURE-PROOFING)

TESTABILITY (MANDATORY):
- Every foundation primitive must have deterministic unit tests.
- Tests must include boundary cases and reference examples.
- Candlestick and level/zone detectors must be testable with fixed OHLCV inputs.

EXPLAINABILITY (REQUIRED HOOKS):
- Each primitive should optionally expose “why” fields (non-binding).
- Must include enough detail for learning and debugging (e.g., failed subcondition).

VERSIONING (MANDATORY):
- Foundation version must be explicit.
- Components must declare compatibility with foundation version.
- Backward compatibility must be supported via semantic contract stability.
- Version reset semantics must invalidate derived caches safely.

STRATEGY-LOCAL EXTENSIONS:
- Allowed only with explicit contracts and inclusion in translation reports.

END
