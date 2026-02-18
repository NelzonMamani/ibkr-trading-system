# PHASE 4 — VERSION CONTROL RULES

## Versioning Model

StrategyPolicyV2 follows semantic governance versioning:

MAJOR.MINOR.PATCH

MAJOR → Structural domain change
MINOR → Logic extension within domain
PATCH → Documentation clarification

## Branch Discipline

- No direct edits on main for structural strategy changes.
- All modifications must go through feature branch.
- PR must include audit artifact regeneration.

## Freeze Tag

Create tag:

STRATEGY_POLICY_V2_LOCK_v1.0.0

This represents institutional baseline.
