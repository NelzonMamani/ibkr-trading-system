FILE: CODEX_E27_VERIFICATION_AND_RECOVERY.md
TITLE: IMPLEMENT E27 RECOVERY, RECONCILIATION, AND VERIFICATION EVIDENCE
END MARKER: END_OF_CODEX_INSTRUCTION

MISSION

Implement recovery and verification authority for E27.

---

RECOVERY REQUIREMENTS

On restart / reconnect:
- query open orders
- query positions
- query recent executions where possible
- rebuild LifecycleRecord objects
- identify:
  - orphan positions
  - orphan protective orders
  - naked positions
  - duplicate working orders
- repair or escalate

---

REQUIRED LOG EVIDENCE

Add explicit evidence logs such as:
- [EXECUTION][PLAN_BUILT]
- [EXECUTION][STOP_ATTACHED]
- [EXECUTION][TARGET_ATTACHED]
- [EXECUTION][TRAIL_UPDATE]
- [EXECUTION][PARTIAL_TAKE]
- [EXECUTION][EXIT_REASON=RED_VOLUME]
- [EXECUTION][EXIT_REASON=RETRACE_FAILURE]
- [EXECUTION][EXIT_REASON=LEVEL_TARGET]
- [RECOVERY][REBUILD]
- [RECOVERY][ORPHAN_POSITION]
- [RECOVERY][ORPHAN_ORDER]
- [RECOVERY][PROTECTION_REPAIR]
- [RECONCILIATION][VERDICT]

---

VERIFICATION CASES TO IMPLEMENT

1. entry submitted and acknowledged
2. entry filled
3. stop executed
4. first target executed
5. trailing stop updated
6. >50% retrace exit fired
7. red volume exit fired
8. duplicate working order blocked
9. restart with working order recovered
10. restart with open position recovered

END_OF_CODEX_INSTRUCTION
