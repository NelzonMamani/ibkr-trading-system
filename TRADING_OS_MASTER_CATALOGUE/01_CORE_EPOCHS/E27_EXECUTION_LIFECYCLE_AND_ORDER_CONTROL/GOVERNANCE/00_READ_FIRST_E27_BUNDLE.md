# 00_READ_FIRST — E27 Execution Lifecycle & Order Control Bundle

This bundle defines the governance for **E27_EXECUTION_LIFECYCLE_AND_ORDER_CONTROL**.

## Purpose
E27 is the shared execution lifecycle epoch for the Trading OS. It is not Ross-only. It is the authoritative layer that translates strategy intent into:
- broker-ready order structures
- protective control
- lifecycle state transitions
- recovery and reconciliation

## Why E27 exists
The system has already proven:
- setup detection
- trigger generation
- intent creation
- broker submission
- callback acknowledgement
- working-order tracking

What is still not formally governed at epoch level is the full lifecycle after intent:
- bracket and attached protection
- 2R / level-based targets
- structure trailing
- red/green volume management
- >50% retrace hard-fail exits
- recovery after restart / disconnect
- broker-truth reconstruction of order and position state

## Bundle contents
- `E27_GOVERNANCE_MASTER.md` — authoritative epoch governance
- `E27_ROSS_EXECUTION_POLICY_PROFILE.md` — Ross-specific consumer profile for E27
- `E27_TABLES_AND_PARAMETERS.md` — tabulated rules and config values
- `E27_STATE_MACHINE_AND_RECOVERY.md` — lifecycle state machine and recovery rules
- `E27_VERIFICATION_AUTHORITY.md` — required evidence and test matrix
- `OPTIONAL_CONSTITUTION_AND_SYSTEM_STATE_UPDATES.md` — suggested catalogue/governance updates

## Reading order
1. `E27_GOVERNANCE_MASTER.md`
2. `E27_ROSS_EXECUTION_POLICY_PROFILE.md`
3. `E27_TABLES_AND_PARAMETERS.md`
4. `E27_STATE_MACHINE_AND_RECOVERY.md`
5. `E27_VERIFICATION_AUTHORITY.md`
6. `OPTIONAL_CONSTITUTION_AND_SYSTEM_STATE_UPDATES.md`

## Core epoch thesis
Strategies must never manage broker orders directly.
Strategies emit policy and intent.
E27 owns:
- execution plan building
- order control
- lifecycle management
- exit control
- recovery
- reconciliation
