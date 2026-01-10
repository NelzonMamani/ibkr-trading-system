# SYSTEM_CONSTITUTION
This document is permanent system law. It overrides code and all secondary documentation.

## 1. Mission
Build a professional-grade modular trading system that supports multiple strategies (momentum, quant,
mean reversion, scalping, etc.) without redesign. The system is orchestrator-centric and phase-governed.

## 2. Safety Is Non-Negotiable
- Execution is HARD DISABLED unless explicitly enabled by configuration.
- LIVE_READ_ONLY mode MUST NEVER route orders.
- Scanner modules are intelligence-only and may not submit trades.
- All LIVE modes must degrade safely on data or connectivity failure.
- MOCK fallback is mandatory when IBKR or external data is unavailable.

## 3. Orchestrator & Scanner Roles
- The orchestrator is the authority for lifecycle, logging cadence, and phase gating.
- Scanner output is advisory intelligence only, never an execution trigger by itself.
- Scanner must never call order APIs (openOrders/completedOrders/order placement).
- Scanner must produce canonical output regardless of news or broker availability.
- The orchestrator must treat scanner inputs as data with provenance (source labels, timestamps, flags).

## 4. Data Trust & Provenance Policy
- Market data priority: IBKR → MOCK (fallback).
- Paid IBKR scanner subscriptions are not required or assumed.
- News data is advisory, probabilistic, and non-blocking.
- `verified_rss.txt` at repo root is the ONLY authoritative list of permitted RSS sources.
- News unavailability must NEVER crash the scanner.
- Trust is separate from availability.

## 5. Phase Authority Model
- The system advances through explicit phases.
- A phase is complete only when its acceptance criteria are met.
- No partial or implicit phase transitions are allowed.
- Phase documents are authoritative over code when ambiguity exists.

## 6. Teaching-First & No Silent Failures
- Teaching-first: explain degradations explicitly.
- No silent failures: missing data must produce explicit logs and file headers.
- Configuration mismatches must be surfaced in console output.

## 7. Logging & Configuration Authority
- Configuration is resolved by `src/config/config_resolver.py` and is authoritative.
- Configuration sources (ENV/DEFAULT/OVERRIDE) must be logged for key caps and safety gates.
- Logging must be human-readable, concise, and summary-first (no spam).

## 8. AI & Automation Conduct Rules
Automated agents (Codex, AI tools) must:
- Read `SYSTEM_CONSTITUTION.md`, `SYSTEM_STATE.md`, and `README.md` before making changes.
- NOT guess intent. Derive intent ONLY from those authoritative documents and existing code behavior.
- Log assumptions, and prefer minimal, reversible changes.
