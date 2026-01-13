# System Document: Strategy Tunable Parameter Framework (STPF)
**Version:** 1.0  
**Date:** January 2026  
**Scope:** Applies to *all* strategies implemented in the ibkr-trading-system.

## 1. Purpose
The STPF defines a safe, auditable, and scalable way to evolve strategies over time without guesswork or destructive “online tuning.”
It standardises how each strategy declares:
- **Invariants** (frozen identity)
- **Tunable thresholds** (numeric knobs)
- **Selectable policy families** (discrete models)
- **Context gates** (conditional modifiers)

This framework is mandatory for every strategy specification and is intended to be consumed by:
- Strategy authors (human or AI)
- Codex implementation prompts (as binding constraints)
- Learning/analytics modules (as allowed parameter surfaces)
- Orchestrator governance (to prevent cross-strategy drift)

## 2. Non‑negotiable guardrails
1. **No strategy-to-strategy dependency:** strategies may depend on shared services/primitives, never on other strategies.
2. **No silent auto‑tuning:** parameter changes may be recommended but require explicit approval and versioning.
3. **Context‑conditioned optimisation only:** no global parameter changes without context buckets.
4. **Determinism:** rankings and decisions must be deterministic with stable tie-breakers.
5. **Auditability:** every decision must be explainable (drop reasons, gating outcomes, policy selections).

## 3. Parameter classes
### 3.1 Class 1 — Invariants (Frozen)
Identity-defining assumptions that must never be auto‑tuned. Changing these creates a new strategy.
Examples:
- Asset class (stocks only)
- Directional bias (long-only)
- Core style (momentum vs mean reversion)
- Whether confirmation is required
- Whether management is structure-based vs time-based

### 3.2 Class 2 — Tunable thresholds (Numeric knobs)
Selection pressure, tradeability, and risk controls that may be adjusted under governance.
Examples:
- Min/max price
- Min % change
- Min RVOL
- Max float
- Min dollar volume
- Max spread %
- Risk per trade cap, daily loss limit
- Universe size and watchlist size

### 3.3 Class 3 — Selectable policy families (Discrete choices)
Model families that can be selected by context (or recommended by learning), not implied or blended ad-hoc.
Examples:
- Entry families: breakout confirmation, micro pullback continuation, VWAP reclaim
- Stop families: fixed %, structure, VWAP, ATR/volatility, hybrid
- Exit families: partial+trail, first-bump partial + higher-low trail, momentum fade exit

### 3.4 Class 4 — Context gates (Conditional modifiers)
Rules enabling/disabling policies or tightening constraints based on context buckets.
Mandatory buckets (minimum):
- Session bucket (open / mid / late)
- RVOL bucket
- Float bucket
- Spread bucket
- Price bucket
- Volatility proxy bucket (ATR or market proxy)
- News freshness bucket (if applicable)

## 4. Learning interaction model (high level)
Learning systems may:
- Compute expectancy and risk metrics (R-multiples, drawdowns, MAE/MFE)
- Attribute outcomes to entry reasons and policy families
- Recommend parameter changes or family switches *by context bucket*
- Propose new versions (semantic versioning)

Learning systems must **not**:
- Change live parameters in the loop
- Modify invariants
- Optimise on insufficient sample sizes
- Remove audit trails

## 5. Governance workflow
1. Run strategy version **vX.Y**
2. Accumulate evidence (trade logs + context snapshots)
3. Produce diagnostics + recommendations
4. Approve changes → release **vX.Y+1**
5. Validate in paper / reduced size
6. Promote to full deployment

## 6. Template requirement for strategy specs
Every strategy document must include:
- Strategy identity
- Invariants
- Tunable thresholds
- Supported policy families
- Context gates
- Logging + learning hooks (what must be recorded)
- Definition of Done

---
