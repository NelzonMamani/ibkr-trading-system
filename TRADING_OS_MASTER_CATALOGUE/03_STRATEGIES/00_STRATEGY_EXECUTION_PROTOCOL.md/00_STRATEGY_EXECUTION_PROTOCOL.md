# 00_STRATEGY_EXECUTION_PROTOCOL.md
# Strategy Execution & Certification Protocol (Post‑Epoch E21)

**Status:** AUTHORITATIVE ADDENDUM  
**Applies after:** Core Epochs E0–E21 and Metadata Epochs M0–M10 are CERTIFIED  
**Timestamp:** 2026-02-08T01:42:37Z

---

## 0. Authority & Relationship to Global Instructions

This document is an **addendum** to:

- `CODEX_GLOBAL_EXECUTION_INSTRUCTIONS.md` (FROZEN)

All rules in that document remain fully in force.

This protocol **does not modify**:
- epoch verification discipline,
- file edit permissions,
- certification append rules,
- stop conditions.

It **extends** them to govern execution of strategy folders under:

```
TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/
```

---

## 1. Strategy Processing Model (Critical)

After E21 is certified, **each strategy (Pxx_*) is treated as a certifiable unit equivalent to an epoch**.

For Codex, this means:

- One strategy at a time
- No parallel work
- No partial implementation
- No carry‑over assumptions between strategies

Each strategy must independently reach a **CERTIFIED** state before Codex proceeds.

---

## 2. Mandatory Strategy Lifecycle (Non‑Negotiable)

For each strategy `Pxx_<NAME>` in strict order:

### Step 1 — Verify
Codex must inspect:
- existing code (if any),
- existing tests (if any),
- existing runtime wiring,

against:
- strategy governance documents,
- canonical registries (SF / XL / C / K / SCP / MCP / LVL / INV),
- E18–E21 guarantees.

Result:
- A strategy‑local gap assessment (implicit or explicit).

---

### Step 2 — Implement (Full, Not Partial)

Codex **MUST implement a complete, production‑ready strategy**, including:

- full `strategy_policy.py` (single tuning surface),
- complete algorithm logic,
- exhaustive setup family utilisation (no omissions),
- execution trigger usage as declared,
- invalidation logic,
- traceability fields on all TradeIntents,
- strategy‑local unit tests,
- wiring through the Strategy Factory (E13/E19).

Skeletons, TODOs, placeholders, or “future work” are **forbidden**.

---

### Step 3 — Re‑Verify

Before certification, Codex must run **at minimum**:

- `python -m compileall src`
- `pytest -q`
- Strategy‑local unit tests
- E21 end‑to‑end runs:
  - SIM
  - PAPER
  - READ_ONLY
  - LIVE‑safety (no unintended orders)

Failures must be fixed, not deferred.

---

### Step 4 — Strategy Certification

Only when all verification passes:

- The strategy is considered **CERTIFIED**
- Codex may proceed to the next strategy

Certification evidence must be recorded in:
- `PR_VERIFICATION_REPORT.md`
- or an equivalent audit artifact referenced by commit

---

## 3. Ordering & Scope

Strategies must be processed **strictly in catalogue order**, e.g.:

```
P05_OPENING_DRIVE
P06_VWAP_RECLAIM
P07_POWER_HOUR
...
P20_REGIME_ADAPTIVE_META_ALLOCATOR
```

Codex must not:
- skip strategies,
- reorder strategies,
- partially implement multiple strategies.

---

## 4. No Partial Acceptance Rule (Hard Stop)

If **any** of the following occur, Codex must **STOP and REPORT**:

- missing setup families relevant to the strategy,
- missing execution triggers declared as required,
- incomplete condition / confirmation coverage,
- untested logic paths,
- failure in any required run mode,
- uncertainty about canonical interpretation.

“No partials” is absolute.

---

## 5. Relationship to LIVE Trading

- Certification does **not** automatically enable LIVE trading.
- Execution authority remains governed by:
  - risk engine (E3),
  - execution engine authority (E5),
  - no‑trade contexts (E16),
  - operator configuration.

This protocol ensures the system is **ready**, not that it is **armed**.

---

## 6. Completion Condition

The strategy phase is complete only when:

- All strategies in `03_STRATEGIES/` are CERTIFIED
- All certification evidence is present
- No unresolved gaps remain

At that point, the Trading OS is considered **functionally complete**.

END
