# Runtime diagnosis

## Root causes found
- `src/core/orchestrator.py` forced `WEEKEND` during preparation mode even for weekday overnight runs.
- `src/scanner/session_pct_change.py` normalized `CLOSED` to `WEEKEND`, collapsing weekday-closed semantics into weekend semantics.
- `src/scanner/reference_resolver.py` could ignore valid snapshot close data and leave `reference_price` unresolved even when a last RTH close was available.
- `src/config/config_resolver.py` derived `IBKR_READONLY_ENABLED` too aggressively, allowing startup/runtime disagreement.
- Same-cycle qualification/history work needed stronger memoization in `CanonicalReferenceResolver`.

## Current verification status
- Targeted closed/prep/reference/readonly verifiers pass.
- Repository-wide `pytest -q` is still failing in unrelated broader runtime smoke/integration coverage and the failure log is preserved in `pytest.log`.
