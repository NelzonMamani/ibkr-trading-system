# SYSTEM_CONSTITUTION.md
## SYSTEM CONSTITUTION — IMMUTABLE LAW

### Purpose
This document defines the immutable laws governing the ibkr-trading-system.
These laws exist to prevent architectural drift, unsafe execution, strategy contamination,
and AI-induced scope corruption.

This system is a **Trading Operating System**, not a script, bot, or single-strategy algorithm.

### Core Principles (Non‑Negotiable)
1. **Determinism** — identical inputs must produce identical outputs.
2. **Explainability** — every decision must be human-readable and auditable.
3. **Strategy Isolation** — strategies may not alter each other’s logic or data.
4. **Risk First** — no execution without explicit risk approval.
5. **No Silent Learning** — learning may observe, never mutate live rules.

### Module Authority Hierarchy
Scanner → Strategy → Risk → Execution → Storage  
No module may bypass another.

### Epoch Discipline
Development proceeds in ordered Epochs.
Each Epoch:
- has a governance file
- defines what is allowed and forbidden
- must complete before the next begins

### Authorized Epoch
**Epoch 2 — Decision Intelligence** is authorized.
Permitted:
- Strategy modeling
- Pattern detection
- Candlestick libraries
- Entry/exit intent modeling

Forbidden until Epoch 3:
- Order execution
- Capital risk
- Broker interaction

Violation of this constitution invalidates the system state.
