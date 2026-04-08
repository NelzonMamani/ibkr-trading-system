FILE: CODEX_E27_MASTER_IMPLEMENTATION.md
TITLE: IMPLEMENT E27 EXECUTION LIFECYCLE AND ORDER CONTROL AS SHARED INFRASTRUCTURE
END MARKER: END_OF_CODEX_INSTRUCTION

MISSION

Implement E27_EXECUTION_LIFECYCLE_AND_ORDER_CONTROL as the shared execution lifecycle epoch for the Trading OS.

E27 must convert strategy intent into:
- execution plans
- broker-ready order structures
- protected positions
- managed exits
- restart recovery
- broker-truth reconciliation

This is shared infrastructure. Ross is the first consumer profile, but no Ross-specific execution plumbing is allowed to live outside strategy policy adapters.

---

NON-NEGOTIABLE RULES

- DO NOT redesign or break existing broker-truth authority.
- DO NOT remove duplicate-working-order prevention.
- DO NOT put broker order management directly inside strategy code.
- DO NOT create strategy-specific copies of shared lifecycle machinery.
- DO NOT assume fills without broker evidence.
- DO NOT permit naked entries without an exit/protection plan.

---

IMPLEMENTATION OBJECTIVES

1. Introduce shared E27 contracts:
   - ExecutionPolicy
   - ExecutionPlan
   - LifecycleRecord
   - RecoveryVerdict

2. Introduce shared E27 components:
   - ExecutionPlanBuilder
   - OrderControlEngine
   - LifecycleCoordinator
   - RecoveryEngine

3. Add Ross as the first strategy consumer via an execution policy adapter.

4. Preserve current entry submission success, then extend lifecycle to support:
   - stop orders
   - first targets
   - structure trailing
   - red/green volume management
   - >50% retrace hard-fail exits
   - level-based partials
   - restart recovery and orphan repair

---

DELIVERY PHASES

PHASE 1
Create contracts and shared architecture skeleton with no regression.

PHASE 2
Implement plan building from existing TradeIntent + RiskDecision.

PHASE 3
Implement order control for:
- entry
- stop
- target
- OCA/bracket semantics where supported
- synthetic protection fallback where needed

PHASE 4
Implement lifecycle coordination:
- entry working
- entry filled
- position open
- position managed
- exit working
- exit filled
- position closed

PHASE 5
Implement Ross execution policy:
- micro pullback consumer profile
- level-first target logic
- red/green volume rules
- >50% retrace failure
- structure trail
- symbol pause/re-arm logic

PHASE 6
Implement recovery and verification.

---

SUCCESS CRITERIA

- E27 exists as shared infrastructure
- Ross consumes E27 through policy, not plumbing
- entry, stop, target, trail, and recovery are supported
- duplicate prevention still works
- broker truth remains authoritative

END_OF_CODEX_INSTRUCTION
