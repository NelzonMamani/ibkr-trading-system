fix_runtime_errors.md
TASK
Fix runtime errors preventing the system from starting after Phase 19 merge.

SCOPE
- Fix Python dataclass correctness issues (field ordering).
- Fix missing imports or type hint errors revealed at runtime.
- Fix circular imports ONLY if they cause runtime failure.

STRICT RULES
- DO NOT change strategy logic.
- DO NOT change risk logic.
- DO NOT change execution logic.
- DO NOT refactor behaviour.
- DO NOT rename fields unless strictly required for correctness.

KNOWN ERROR
TypeError: non-default argument 'asof_utc' follows default argument 'volume'
Location: src/domain/market_snapshot.py

EXPECTED OUTCOME
- System starts successfully.
- Behaviour remains unchanged.
- Only structural/syntactic fixes applied.

DELIVERABLE
Minimal commits that restore runtime correctness.
END 