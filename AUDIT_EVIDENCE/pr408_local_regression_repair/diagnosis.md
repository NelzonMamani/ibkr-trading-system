# PR408 Local Regression Repair — Diagnosis

## Scope
Diagnosed and repaired only the 4 reported local regressions, with narrow control-flow/state authority fixes.

## 1) `test_early_rth_candidate_can_promote_with_discovery_context`
- **Root cause type:** Control-flow bug.
- **Root cause:** `_evaluate_focus_gates` could mark `focus_decision=KEEP_EARLY_RTH_CONTEXT` but continued through later gates (including spread), allowing an override to `DROP_SPREAD`.
- **Repair:** Made early-RTH context keep a **terminal pass** (`return None`) immediately after RVOL decision logging so later spread/bid-ask checks cannot override this approved exception path.
- **Repaired function/file:** `src/scanner/scanner_runner.py::_evaluate_focus_gates`.

## 2) `test_watchlist_artifact_written_when_universe_empty`
- **Root cause type:** Authority bypass + state leakage.
- **Root cause:** `run_scanner_cycle` reused module-level `_PERSISTENT_PROVIDER` before calling `build_provider()`. In tests that monkeypatch `build_provider` to fail, a cached live provider could bypass the patched constructor and continue scanning non-empty universe.
- **Repair:**
  - Removed pre-build reuse path so authoritative provider construction is evaluated per cycle unless an explicit provider object is injected.
  - Added canonical runtime reset helper and invoked it from config override mutation path to deterministically clear persistent scanner/provider state between scenarios.
- **Repaired functions/files:**
  - `src/scanner/scanner_runner.py::run_scanner_cycle`
  - `src/scanner/scanner_runner.py::reset_scanner_runtime_state` (new helper)
  - `src/config/config_resolver.py::set_config_overrides` (calls reset helper)

## 3) `test_watchlist_print_suppressed_when_unchanged`
- **Root cause type:** State leakage susceptibility.
- **Root cause:** Watchlist suppression depends on module globals (`_WATCHLIST_HASH`, `_LAST_SESSION_LABEL`, cycle counters). Cross-test reuse could perturb suppression behavior on local environments.
- **Repair:** Introduced canonical scanner runtime reset helper and switched relevant test fixtures to use it explicitly, ensuring deterministic watchlist print state across cycles/tests.
- **Repaired files:**
  - `src/scanner/scanner_runner.py` (reset helper)
  - `tests/test_scanner_watchlist_prints.py` (fixture uses canonical reset)

## 4) `test_live_readonly_connectivity_retry`
- **Root cause type:** Degraded marker emission gap.
- **Root cause:** `STATE=DEGRADED` was emitted only on mock-fallback branch; when fallback is disabled (LIVE_READ_ONLY/READ_ONLY retry path), degraded state existed but marker could be absent in observed output.
- **Repair:** Emit `STATE=DEGRADED` immediately on provider connection failure regardless of whether fallback is permitted.
- **Repaired function/file:** `src/scanner/scanner_runner.py::run_scanner_cycle`.
