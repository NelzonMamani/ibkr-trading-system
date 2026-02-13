# 02_IMPLEMENTATION_PLAN.md
# Implementation Plan — E23
Last updated: 2026-02-13

## Deliverables to Implement (Code + Docs)
Implement the following in the repo (additive, no redesign):

A) E23 Runner
   - src/integrity/e23_platform_integrity_runner.py (or equivalent path aligned to repo)
   - CLI entrypoint: python -m src.integrity.e23

B) Epoch Verification Registry
   - src/integrity/epoch_verification_registry.yaml
   - includes E0..E22 and M0..M10 and existing strategies P01..P04
   - each entry defines:
     - verification commands (pytest/script/cmd)
     - evidence artifacts expected
     - acceptance checks

C) Evidence Crawler
   - Finds latest audit evidence per epoch
   - Determines freshness relative to current code base
   - Default: rerun fast verification (compileall + pytest -q) unless configured otherwise

D) Drift Detectors (hard + soft)
   Hard drift: fails E23 run
     - canonical run modes mismatch
     - unsafe execution routing in READ_ONLY/PAPER where forbidden
     - risk engine permission bypass
   Soft drift: recorded and auto-fixed when safe
     - stale SYSTEM_STATE doc
     - alias normalization missing
     - duplicated responsibility flags

E) Reconciliation Engine
   - Applies precedence rules
   - Emits deprecation/supersession/compat decisions into ledger
   - Auto-fixes allowed by governance (docs, shims, registry updates)

F) Regenerated Global Truth Artifacts
   - SYSTEM_STATE_CERTIFIED.md (keep current name if it exists)
   - platform_integrity_state.json
   - DEPRECATION_LEDGER.md
   - RECONCILIATION_REPORT.md

G) Audit Evidence Write
   - E23 writes evidence artifacts including:
     - run summary JSON
     - verification command list
     - drift list

## Constraints
- Preserve safety invariants (no unsafe LIVE routing)
- Prefer compatibility shims over deletions
- Deletions are only recommended, not performed, unless already under housekeeping patterns
- Keep runtime fast path: avoid heavy enrichment in live path

END
