# PHASE 24 — Codex Instruction Block (Scanner Finalisation)

## ADDENDUM — Legacy 54-Field Contract Deprecation (Authoritative)

The legacy 54-field scanner print contract is **explicitly deprecated in Phase 24**.

Phase 24 introduces a new authoritative output model:
- FAST_VIEW (hot-path, decision-critical fields for Watchlist K)
- DEEP_VIEW (enriched context printed only for Focus M = top 3–5)

Existing files such as `print_contract_54.py` and related tests are **out of scope for Phase 24**
and are not required to pass or be maintained for Phase 24 completion.

Phase 24 is considered COMPLETE **without** satisfying the legacy 54-field output contract.
Any archival, adaptation, or removal of legacy 54-field artifacts is deferred to Phase 27+.
