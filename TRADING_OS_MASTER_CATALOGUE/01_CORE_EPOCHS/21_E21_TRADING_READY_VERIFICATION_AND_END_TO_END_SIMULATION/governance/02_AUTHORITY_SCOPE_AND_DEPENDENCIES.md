# 02_AUTHORITY_SCOPE_AND_DEPENDENCIES

## Authority
E21 is a **Core+Metadata readiness epoch**. It has authority over:
- Verification standards
- Evidence requirements
- PASS/FAIL semantics
- Required simulation coverage
- Mandatory failure drills
- Required audit artifacts and storage

E21 does **not** override:
- SYSTEM_CONSTITUTION.md (system law)
- Run-mode authority rules (SIM/PAPER/READ_ONLY/LIVE)
- Strategy policy primacy (strategy is the boss)

## Scope
E21 scope is explicitly end-to-end:
- Market/session state classification
- Data quality flags and handling (frozen/delayed/subscription gaps)
- Scanner outputs and contract compliance
- Strategy selection → focus list → intent creation
- Risk engine permissioning (caps, exposure, kill, halts)
- Execution engine order lifecycle (submit/ack/partial/fill/cancel/reject)
- Position lifecycle state machine
- Exit logic (targets, trailing, invalidation, emergency liquidation)
- Storage durability and traceability (event spine, ordering, correlation IDs)
- Recovery after failures and process restarts

## Dependencies (must already be certified enough to run)
E21 depends on earlier epochs being present (even if not perfect yet):
- E0..E7 (modes, execution authority, scanner contract, safety)
- E12 (recovery/housekeeping controls)
- E14 (decision artifacts)
- E15/E16 (failure modes + no-trade contexts)
- E18/E19/E20 (foundation registries + interface translation)

If any dependency is missing, E21 must **fail loudly** and record the gap in the certification report. No “assumed working” is allowed.
