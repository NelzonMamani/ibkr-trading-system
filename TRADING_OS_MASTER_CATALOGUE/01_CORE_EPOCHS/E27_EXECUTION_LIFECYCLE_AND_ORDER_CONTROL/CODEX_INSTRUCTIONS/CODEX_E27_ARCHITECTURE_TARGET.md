FILE: CODEX_E27_ARCHITECTURE_TARGET.md
TITLE: TARGET ARCHITECTURE FOR E27 EXECUTION LIFECYCLE AND ORDER CONTROL
END MARKER: END_OF_CODEX_INSTRUCTION

TARGET ARCHITECTURE

Desired logical flow:

TradeIntent
→ RiskDecision
→ ExecutionPolicy
→ ExecutionPlanBuilder
→ ExecutionPlan
→ OrderControlEngine
→ Broker Adapter
→ LifecycleCoordinator
→ RecoveryEngine / Reconciliation

---

REQUIRED COMPONENTS

1. ExecutionPolicy
   Strategy-provided policy object for:
   - stop model
   - target model
   - trail model
   - scale rules
   - pause/re-arm rules
   - session behavior

2. ExecutionPlanBuilder
   Must convert TradeIntent + RiskDecision + ExecutionPolicy into a concrete ExecutionPlan.

3. ExecutionPlan
   Should include at minimum:
   - entry_order_spec
   - initial_stop_spec
   - first_target_spec
   - trailing_spec
   - scaling_spec
   - pause_rules
   - recovery_metadata

4. OrderControlEngine
   Responsible for:
   - building broker-ready parent/child orders
   - attaching protection
   - updating trailing stops
   - resizing child orders after partial fills

5. LifecycleCoordinator
   Responsible for canonical state transitions and event handling.

6. RecoveryEngine
   Responsible for broker restart recovery and orphan repair/escalation.

---

ARCHITECTURAL CONSTRAINTS

- Current execution path must keep working during refactor.
- Use additive integration where possible.
- Preserve current logs and add new logs rather than removing observability.
- Existing IBKR adapter remains broker-facing authority.
- E27 should sit above broker adapter, not replace it.

END_OF_CODEX_INSTRUCTION
