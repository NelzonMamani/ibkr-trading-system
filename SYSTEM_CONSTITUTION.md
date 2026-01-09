# SYSTEM CONSTITUTION
## IBKR Modular Trading System

### 1. System Identity
This repository defines a professional-grade, modular, multi-strategy trading platform.
The first-class, reference strategy is Ross Cameron–style momentum trading, but the
architecture MUST support additional strategies (quantitative, algorithmic, mean-reversion,
scalping, etc.) without redesign.

The system is orchestrator-centric and phase-governed.

### 2. Safety Is Non-Negotiable
- LIVE_READ_ONLY is mandatory when execution is disabled.
- Execution is HARD DISABLED unless explicitly enabled by configuration.
- LIVE_READ_ONLY mode MUST NEVER route orders.
- Scanner modules are intelligence-only and may not submit trades.
- All LIVE modes must degrade safely on data or connectivity failure.
- MOCK fallback is mandatory when IBKR or external data is unavailable.

### 3. Orchestrator & Scanner Roles
- The orchestrator is the authority for lifecycle, logging cadence, and phase gating.
- Scanner output is advisory intelligence only, never an execution trigger.
- Scanner must never call order APIs (openOrders/completedOrders/order placement).
- Scanner must produce canonical output regardless of news or broker availability.

### 4. Data Trust & Provenance Policy
- Market data priority: IBKR → MOCK (fallback).
- News data is advisory, probabilistic, and non-blocking.
- verified_rss.txt at repo root is the ONLY authoritative list of permitted RSS sources.
- News unavailability must NEVER crash the scanner.
- Trust is separate from availability.

### 5. Teaching-First & No Silent Failures
- Teaching-first: explain degradations explicitly.
- No silent failures: missing data must produce explicit logs and file headers.
- Configuration mismatches must be surfaced in console output.

### 6. Logging & Configuration Authority
- Configuration is resolved by config_resolver.py and is authoritative.
- Configuration sources (ENV/DEFAULT/OVERRIDE) must be logged for key caps.
- Logging must be human-readable, concise, and summary-first (no spam).

### 7. AI & Automation Conduct Rules
- Automated agents (Codex, AI tools) must read this document before changes.
- Guessing system intent is forbidden.
- All assumptions must be logged or documented.
- Changes must align with current SYSTEM_STATE.md.

This document changes rarely and defines permanent system law.
