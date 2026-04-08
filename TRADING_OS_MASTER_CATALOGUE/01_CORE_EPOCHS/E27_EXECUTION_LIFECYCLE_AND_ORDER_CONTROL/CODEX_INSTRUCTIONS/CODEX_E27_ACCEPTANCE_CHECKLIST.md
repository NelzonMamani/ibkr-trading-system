# E27 Acceptance Checklist

Codex implementation is not complete until all are true.

## Architecture
- [ ] E27 exists as shared infrastructure
- [ ] strategy code does not directly manage broker orders
- [ ] Ross consumes E27 via ExecutionPolicy

## Contracts
- [ ] ExecutionPolicy exists
- [ ] ExecutionPlan exists
- [ ] LifecycleRecord exists
- [ ] RecoveryVerdict exists

## Lifecycle
- [ ] entry plan builds
- [ ] stop attaches
- [ ] first target attaches
- [ ] trail updates
- [ ] exits close positions cleanly

## Rules
- [ ] whole/half-dollar levels influence targeting
- [ ] HOD influences targeting
- [ ] red volume thresholds influence exit
- [ ] green volume thresholds influence scale/hold
- [ ] >50% retrace exits and pauses symbol

## Recovery
- [ ] restart recovers open orders
- [ ] restart recovers positions
- [ ] duplicate prevention remains active

## Evidence
- [ ] logs exist for plan build, attach, trail, exit, recovery
- [ ] at least one end-to-end scenario is verified

## Safety
- [ ] no naked entries
- [ ] broker truth remains authoritative
